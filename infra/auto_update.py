#!/usr/bin/env python3
"""Pull tested app images, back up, migrate and check a local Compose stack.

Only the application services change. Database/Redis images, volumes, .env,
and the host checkout are never replaced. Requires Python 3.10+ and Compose v2.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

DEFAULT_IMAGE = "ghcr.io/matteoschiavi/apex_health:main"
SOURCE = "https://github.com/MatteoSchiavi/Apex_Health"
IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}\Z")
REVISION = re.compile(r"[0-9a-f]{40}\Z")

# These run inside the existing image without printing keys or health data.
BACKUP_READY = "from app.core.config import get_settings; assert get_settings().backup_encryption_key, 'Set BACKUP_ENCRYPTION_KEY before enabling automatic updates'"
BACKUP = """import json, os
from app.core.config import get_settings
from app.core.backups import create_backup, iter_backup
s = get_settings()
r = create_backup(backup_encryption_key=s.backup_encryption_key,
    database_url=s.database_url, backup_dir=os.path.join(s.backup_dir, 'deployments', os.environ['APEX_DEPLOYMENT']), pg_dump_bin=s.pg_dump_bin)
assert sum(len(chunk) for chunk in iter_backup(r['path'], s.backup_encryption_key)) > 0
print(json.dumps(r))
"""
API_PROBE = """import json, urllib.request
with urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=5) as r:
    assert json.load(r) == {'status':'ok', 'db':'ok', 'redis':'ok'}
"""
WORKER_PROBE = "from app.tasks.health_tasks import ping; assert ping.delay().get(timeout=45) == {'status':'ok', 'db':'ok'}"
SCHEMA = 'psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "SELECT version_num FROM alembic_version ORDER BY version_num"'


class UpdateError(RuntimeError):
    pass


class Docker:
    def __init__(self, context=None, timeout=1800):
        self.context = context
        self.timeout = timeout

    def run(self, *args: str) -> str:
        prefix = ["docker"] + (["--context", self.context] if self.context else [])
        result = subprocess.run([*prefix, *args], text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=self.timeout)
        if result.returncode:
            # Docker errors can contain deployment details: keep the journal private.
            raise UpdateError(f"docker {' '.join(args[:3])} failed: {result.stderr[-2000:].strip()}")
        return result.stdout.strip()


def write_json(path: Path, value: dict) -> None:
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".state-")
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(value, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class Updater:
    def __init__(self, repo: Path, state_dir: Path, *, image=DEFAULT_IMAGE,
                 compose_files=(), project=None, docker=None):
        self.repo = repo.resolve()
        self.directory = state_dir.resolve()
        self.image = image
        self.docker = docker or Docker()
        self.project_name = project or os.environ.get("COMPOSE_PROJECT_NAME") or "apex-health"
        self.base = ["compose", "--env-file", str(self.repo / ".env")]
        if project:
            self.base += ["--project-name", project]
        for file in compose_files or (self.repo / "infra/docker-compose.yml",):
            self.base += ["-f", str(Path(file).resolve())]
        self.state_path = self.directory / "state.json"
        self.state = json.loads(self.state_path.read_text()) if self.state_path.exists() else {}

    def save(self):
        write_json(self.state_path, self.state)

    def compose(self, *args, override=None):
        extra = ["-f", str(override)] if override else []
        return self.docker.run(*self.base, *extra, *args)

    def override(self, name, image_id):
        if not IMAGE_ID.fullmatch(image_id):
            raise UpdateError("Expected an immutable local Docker image ID")
        path = self.directory / (name + ".compose.yml")
        # JSON is valid YAML and avoids interpolating configuration as shell code.
        write_json(path, {"services": {service: {"image": image_id, "pull_policy": "never"}
                                     for service in ("api", "worker", "migrate")}})
        return path

    def image_info(self, reference):
        info = json.loads(self.docker.run("image", "inspect", reference))[0]
        return info["Id"], (info.get("Config", {}).get("Labels") or {})

    def service_image(self, service, required=True):
        ids = self.compose("ps", "-q", service).splitlines()
        if len(ids) != 1:
            if not required and not ids:
                return None
            raise UpdateError(f"Expected one running {service} container; start the existing stack first")
        info = json.loads(self.docker.run("container", "inspect", ids[0]))[0]
        if not info["State"].get("Running"):
            raise UpdateError(f"{service} is not running")
        if service == "api":
            # The rendered Compose project can come from an override's name:
            # or .env. Use the actual container label for legacy cleanup.
            actual = (info.get("Config", {}).get("Labels") or {}).get("com.docker.compose.project")
            if actual:
                self.project_name = actual
        return info["Image"]

    def schema(self):
        return self.compose("exec", "-T", "db", "sh", "-c", SCHEMA).splitlines()

    def legacy_bot_containers(self):
        """Find only bot containers owned by this Compose project."""
        result = self.docker.run(
            "ps", "-aq", "--filter", "label=com.docker.compose.project=" + self.project_name,
            "--filter", "label=com.docker.compose.service=bot",
        )
        return result.splitlines()

    def stop_legacy_bot(self):
        containers = self.legacy_bot_containers()
        if containers:
            self.docker.run("stop", "-t", "120", *containers)

    def remove_legacy_bot(self):
        containers = self.legacy_bot_containers()
        if containers:
            self.docker.run("rm", "-f", *containers)

    def probe(self):
        self.compose("exec", "-T", "api", "python", "-c", API_PROBE)
        self.compose("exec", "-T", "api", "python", "-c", WORKER_PROBE)

    def running(self):
        current = self.service_image("api")
        if self.service_image("worker") != current:
            raise UpdateError("API and worker use different images; repair the existing stack first")
        self.probe()
        _, labels = self.image_info(current)
        return {"image": current, "revision": labels.get("org.opencontainers.image.revision"),
                "schema": self.schema()}

    def start(self, image_id):
        override = self.override("active", image_id)
        common = ("up", "-d", "--no-build", "--pull", "never", "--no-deps",
                  "--force-recreate", "--wait", "--wait-timeout", "120")
        self.compose(*common, "api", override=override)
        self.compose(*common, "worker", override=override)
        self.probe()
        self.remove_legacy_bot()

    def stop(self):
        self.stop_legacy_bot()
        self.compose("stop", "-t", "120", "worker")
        self.compose("stop", "-t", "60", "api")

    def resume(self):
        # Also adopts a manually repaired, healthy deployment. This does not
        # alter data or start services that were stopped after migration failure.
        current = self.running()
        self.state.update(current=current, paused=False, in_progress=None, failed_image=None)
        self.save()
        print("Healthy running deployment adopted; automatic updates resumed")

    def diagnose(self, host_run=subprocess.run):
        """Inspect prerequisites without pulling, deploying or modifying state.

        Return static explanations, never raw Compose output, environment
        values, registry credentials or potentially sensitive stderr.
        """
        checks = []
        report = {"checks": checks, "state": self.state, "running": None}

        def add(name, status, detail):
            checks.append({"check": name, "status": status, "detail": detail})

        installed = self.directory / "auto_update.py"
        add("installation", "ok" if installed.is_file() else "error",
            "Installed updater exists" if installed.is_file() else
            "Recurring updater is not installed here; run infra/install-auto-update.sh")
        if installed.is_file():
            source = self.repo / "infra/auto_update.py"
            if source.is_file() and installed.read_bytes() != source.read_bytes():
                add("updater_version", "warning", "Installed updater differs from this checkout; reinstall to apply script fixes")
        add("automation", "error" if self.state.get("paused") or self.state.get("in_progress") else "ok",
            "Paused or interrupted: inspect status and recover before resuming" if
            self.state.get("paused") or self.state.get("in_progress") else "No recorded pause or interrupted deployment")
        if self.state.get("failed_image"):
            add("failed_image", "warning", "A failed image is blocked; diagnose before retrying or wait for a newer release")

        def host(*command):
            try:
                result = host_run(list(command), text=True, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, timeout=10)
                return result.stdout.strip() if result.returncode == 0 else None
            except (OSError, subprocess.TimeoutExpired):
                return None

        timer = host("systemctl", "--user", "show", "apex-health-update.timer",
                     "--property=LoadState,ActiveState,UnitFileState")
        properties = dict(line.split("=", 1) for line in (timer or "").splitlines() if "=" in line)
        active = properties.get("LoadState") == "loaded" and properties.get("ActiveState") == "active"
        enabled = properties.get("UnitFileState") in ("enabled", "enabled-runtime")
        add("timer", "ok" if active and enabled else "error",
            "Five-minute timer is active and enabled" if active and enabled else
            "Timer unavailable, inactive or disabled; check systemctl --user status apex-health-update.timer")
        service = host("systemctl", "--user", "show", "apex-health-update.service", "--property=Result")
        if service and service != "Result=success":
            add("last_service_run", "warning", "Last updater service run failed; inspect its journal")
        linger = host("loginctl", "show-user", str(os.getuid()), "--property=Linger", "--value")
        add("linger", "ok" if linger == "yes" else "warning",
            "User services remain available after logout" if linger == "yes" else
            "Linger is disabled or unverifiable; enable it for this installation user to survive logout/reboot")
        try:
            report["running"] = self.running()
            add("application", "ok", "API, worker, database and queue probes passed")
        except (UpdateError, OSError, ValueError, KeyError, subprocess.TimeoutExpired):
            add("application", "error", "Docker/Compose or application health check failed; verify the Docker context and original Compose options")
        else:
            try:
                self.compose("exec", "-T", "api", "python", "-c", BACKUP_READY)
                add("backup_key", "ok", "Running API has a backup encryption key")
            except (UpdateError, OSError, subprocess.TimeoutExpired):
                add("backup_key", "error", "Backup key check failed; set BACKUP_ENCRYPTION_KEY securely and recreate the existing API/worker before installing updates")
        try:
            self.docker.run("manifest", "inspect", self.image)
            add("registry", "ok", "Registry manifest is readable with this user's Docker credentials; no image was downloaded")
        except (UpdateError, OSError, subprocess.TimeoutExpired):
            add("registry", "error", "Registry access failed; check connectivity, image name and Docker login for this installation user")
        return report

    def rollback(self):
        if self.state.get("in_progress"):
            raise UpdateError("Interrupted update: inspect the deployment and use resume after recovery")
        previous = self.state.get("previous")
        if not previous:
            raise UpdateError("No previous application image is recorded")
        if self.schema() != previous["schema"]:
            raise UpdateError("Database schema changed: restore/recover manually; no database rewind was attempted")
        current = self.running()
        self.state.update(paused=True, in_progress="rollback")
        self.save()
        self.stop()
        try:
            self.start(previous["image"])
        except Exception:
            self.save()
            raise
        self.state.update(current=previous, previous=current, in_progress=None)
        self.save()
        print("Previous application restored; updates paused until resume")

    def update(self, retry=False):
        if self.state.get("paused") or self.state.get("in_progress"):
            raise UpdateError("Updates paused/interrupted. Run status and follow docs/AUTO_UPDATES.md")
        self.docker.run("pull", self.image)
        candidate, labels = self.image_info(self.image)
        revision = labels.get("org.opencontainers.image.revision", "")
        if not REVISION.fullmatch(revision) or labels.get("org.opencontainers.image.source", "").lower() != SOURCE.lower():
            raise UpdateError("Image lacks the expected Apex repository and full Git commit labels")
        if candidate == self.state.get("failed_image") and not retry:
            print("Skipping the previously failed image; wait for a new tested commit or use --retry")
            return
        current = self.running()
        self.state["current"] = current
        self.save()
        # Check before downtime, including an already-current installation
        # during timer setup. No unencrypted health backups are ever created.
        self.compose("exec", "-T", "api", "python", "-c", BACKUP_READY)
        if current["image"] == candidate:
            print(f"Already running tested commit {revision[:12]}")
            return
        self.docker.run("image", "tag", current["image"], "apex-health-rollback:" + current["image"].split(":")[1][:12])
        deployment = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + revision[:12]
        old = self.override("previous", current["image"])
        new = self.override("candidate", candidate)
        phase = "stopping"
        self.state.update(in_progress=phase, candidate={"image": candidate, "revision": revision})
        self.save()
        try:
            self.stop()
            phase = "backup"
            self.state["in_progress"] = phase
            self.save()
            raw = self.compose("run", "--rm", "--no-deps", "-e", "APEX_DEPLOYMENT=" + deployment,
                               "api", "python", "-c", BACKUP, override=old)
            backup = json.loads(raw.splitlines()[-1])
            if not backup.get("size") or not backup.get("sha256") or not backup.get("path"):
                raise UpdateError("Backup verification did not return a valid artifact")
            self.state["backup"] = backup
            phase = "migrating"
            self.state["in_progress"] = phase
            self.save()
            self.compose("run", "--rm", "--no-deps", "migrate", override=new)
            schema = self.schema()
            phase = "starting"
            self.state.update(in_progress=phase, candidate_schema=schema)
            self.save()
            self.start(candidate)
            self.state.update(previous=current,
                              current={"image": candidate, "revision": revision, "schema": schema},
                              updated_at=deployment, in_progress=None, failed_image=None)
            self.save()
            print(f"Deployed tested commit {revision[:12]}; encrypted backup: {backup['path']}")
        except Exception:
            # Migration errors may include data changes even if the revision
            # marker did not advance. They always need operator inspection.
            safe = phase in ("stopping", "backup")
            if phase == "starting":
                try:
                    safe = self.schema() == current["schema"]
                except Exception:
                    safe = False
            self.state.update(failed_image=candidate, failure_phase=phase, paused=not safe)
            self.save()
            try:
                self.stop()
                if safe:
                    self.start(current["image"])
                    self.state.update(in_progress=None, current=current)
                    self.save()
                    print("Previous application restored; failed image will not be retried automatically", file=sys.stderr)
                else:
                    self.state["in_progress"] = "manual_recovery"
                    self.save()
                    print("Application stopped after migration-related failure; database and backups retained. Manual recovery required", file=sys.stderr)
            except Exception:
                self.state.update(paused=True, in_progress="manual_recovery")
                self.save()
                print("Recovery could not be verified; automatic updates are paused", file=sys.stderr)
            raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["update", "status", "doctor", "pause", "resume", "rollback"], nargs="?", default="update")
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--state-dir", type=Path)
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--compose-file", action="append", type=Path)
    parser.add_argument("--project-name")
    parser.add_argument("--docker-context", help="Use the same named Docker context as the existing installation")
    parser.add_argument("--retry", action="store_true")
    args = parser.parse_args(argv)
    directory = args.state_dir or args.repo / ".apex-updater"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(directory, 0o700)
    with (directory / "update.lock").open("a") as lock:
        # State is atomically replaced. Read-only diagnostics must remain
        # available while an update owns the deployment lock.
        if args.action not in ("status", "doctor"):
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                print("Another update is already running")
                return 0
        try:
            updater = Updater(args.repo, directory, image=args.image, compose_files=args.compose_file,
                              project=args.project_name,
                              docker=Docker(args.docker_context, timeout=60 if args.action == "doctor" else 1800))
            if args.action == "status":
                print(json.dumps(updater.state, indent=2))
            elif args.action == "doctor":
                report = updater.diagnose()
                print(json.dumps(report, indent=2))
                return 1 if any(c["status"] == "error" for c in report["checks"]) else 0
            elif args.action == "pause":
                updater.state["paused"] = True
                updater.save()
                print("Automatic updates paused; running services unchanged")
            elif args.action == "resume":
                updater.resume()
            elif args.action == "rollback":
                updater.rollback()
            else:
                updater.update(retry=args.retry)
        except (UpdateError, subprocess.TimeoutExpired, OSError, ValueError, KeyError) as exc:
            print(f"Update aborted: {exc}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
