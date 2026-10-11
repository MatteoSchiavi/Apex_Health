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
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_IMAGE = "ghcr.io/matteoschiavi/apex_health:main"
SOURCE = "https://github.com/MatteoSchiavi/Apex_Health"
IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}\Z")
REVISION = re.compile(r"[0-9a-f]{40}\Z")
REGISTRY_REPOSITORY = "ghcr.io/matteoschiavi/apex_health"
RELEASE_CHANNEL = "org.apex.release-channel"
MIN_FREE_BYTES = 1024 ** 3
MIGRATION_REVISION = re.compile(r"[A-Za-z0-9_]{1,128}\Z")
MIGRATION_GRAPH = """import json
from alembic.config import Config
from alembic.script import ScriptDirectory
script = ScriptDirectory.from_config(Config('/app/alembic.ini'))
def ids(value):
    return list(value) if isinstance(value, (tuple, list)) else [value] if value else []
rows = list(script.walk_revisions())
print(json.dumps({'heads': list(script.get_heads()), 'revisions': {
    row.revision: ids(row.down_revision) + ids(row.dependencies) for row in rows}}))
"""

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


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise UpdateError("Release verification refused an HTTP redirect")


class GitHubReleaseVerifier:
    """Bounded public GitHub checks; no credentials or response bodies logged."""
    root = "https://api.github.com/repos/MatteoSchiavi/Apex_Health"
    required_jobs = {"frontend", "pytest", "updater", "agent-evals", "backend-release"}

    def __init__(self, opener=None):
        self.opener = opener or urllib.request.build_opener(NoRedirect())

    def get(self, path):
        request = urllib.request.Request(self.root + path, headers={
            "Accept": "application/vnd.github+json", "User-Agent": "apex-updater",
            "X-GitHub-Api-Version": "2022-11-28"})
        try:
            with self.opener.open(request, timeout=10) as response:
                raw = response.read(1024 * 1024 + 1)
                if response.status != 200 or len(raw) > 1024 * 1024:
                    raise UpdateError("Release verification response is unavailable or oversized")
                value = json.loads(raw)
                if not isinstance(value, dict):
                    raise ValueError("Expected an object")
                return value
        except (OSError, ValueError, urllib.error.URLError) as exc:
            raise UpdateError("Release verification request failed; retry when GitHub is available") from None

    def verify(self, current_revision, candidate_revision):
        try:
            return self._verify(current_revision, candidate_revision)
        except (AttributeError, KeyError, IndexError, TypeError):
            raise UpdateError("Release verification returned malformed metadata") from None

    def _verify(self, current_revision, candidate_revision):
        if not all(isinstance(r, str) and REVISION.fullmatch(r) for r in (current_revision, candidate_revision)):
            raise UpdateError("Cannot verify progression without full running and candidate revisions")
        comparison = self.get(f"/compare/{current_revision}...{candidate_revision}?per_page=1")
        if (comparison.get("status") not in ("ahead", "identical")
                or comparison.get("base_commit", {}).get("sha") != current_revision
                or comparison.get("merge_base_commit", {}).get("sha") != current_revision):
            raise UpdateError("Candidate source revision is older, divergent or unverifiable")
        query = urllib.parse.urlencode({"head_sha": candidate_revision, "branch": "main", "event": "push", "per_page": 20})
        runs = self.get("/actions/workflows/tests.yml/runs?" + query).get("workflow_runs", [])
        for run in runs[:20]:
            if (run.get("head_sha") != candidate_revision or run.get("head_branch") != "main"
                    or run.get("event") != "push" or run.get("status") != "completed"
                    or run.get("conclusion") != "success" or run.get("path") != ".github/workflows/tests.yml"
                    or not isinstance(run.get("id"), int) or isinstance(run.get("id"), bool)
                    or run["id"] <= 0):
                continue
            jobs = []
            for page in range(1, 6):
                batch = self.get(f"/actions/runs/{run['id']}/jobs?filter=latest&per_page=100&page={page}").get("jobs", [])
                jobs.extend(batch)
                if len(batch) < 100:
                    break
            else:
                raise UpdateError("Release job list exceeds verification limit")
            if (self.required_jobs <= {job.get("name") for job in jobs}
                    and all(job.get("status") == "completed" and job.get("conclusion") == "success" for job in jobs)):
                return
            raise UpdateError("Release workflow has missing, skipped or unsuccessful required jobs")
        raise UpdateError("Exact candidate revision lacks a completed successful main push release workflow")


def validate_migration_graph(graph, current):
    """Every candidate revision must belong to one complete forward graph."""
    if not isinstance(graph, dict):
        raise UpdateError("Invalid candidate migration graph")
    heads, revisions = graph.get("heads"), graph.get("revisions")
    if not isinstance(heads, list) or len(heads) != 1 or not isinstance(revisions, dict) or not 0 < len(revisions) <= 10000:
        raise UpdateError("Candidate must have exactly one complete migration head")
    if not current or len(current) != len(set(current)):
        raise UpdateError("Current database migration revisions are empty or invalid")
    for revision, parents in revisions.items():
        if (not isinstance(revision, str) or not MIGRATION_REVISION.fullmatch(revision)
                or not isinstance(parents, list) or any(not isinstance(p, str) or p not in revisions for p in parents)
                or len(parents) != len(set(parents))):
            raise UpdateError("Candidate migration graph has invalid or missing revisions")
    if not isinstance(heads[0], str) or heads[0] not in revisions:
        raise UpdateError("Candidate migration head is missing")
    # Iterative DFS avoids recursion limits for long valid migration chains.
    visited, active, stack = set(), set(), [(heads[0], False)]
    while stack:
        node, leaving = stack.pop()
        if leaving:
            active.remove(node)
            visited.add(node)
        elif node in active:
            raise UpdateError("Candidate migration graph contains a cycle")
        elif node not in visited:
            active.add(node)
            stack.append((node, True))
            stack.extend((parent, False) for parent in revisions[node])
    if visited != set(revisions):
        raise UpdateError("Candidate migration graph is disconnected or has undeclared heads")
    if any(revision not in visited for revision in current):
        raise UpdateError("Candidate lacks a forward migration path from the current database revisions")
    return heads[0]


class Docker:
    def __init__(self, context=None, timeout=1800):
        self.context = context
        self.timeout = timeout

    def run(self, *args: str) -> str:
        prefix = ["docker"] + (["--context", self.context] if self.context else [])
        result = subprocess.run([*prefix, *args], text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=self.timeout)
        if result.returncode:
            # Registry errors and container output can include tokens, raw
            # network bodies or health data. Never copy them into the journal.
            raise UpdateError(f"Docker {args[0]} failed (exit {result.returncode}); inspect Docker locally")
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
                 compose_files=(), project=None, docker=None, release_verifier=None,
                 disk_usage=None):
        self.repo = repo.resolve()
        self.directory = state_dir.resolve()
        self.image = image
        self.docker = docker or Docker()
        self.release_verifier = release_verifier or GitHubReleaseVerifier()
        self.disk_usage = disk_usage or shutil.disk_usage
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
        info = self.image_metadata(reference)
        return info["Id"], (info.get("Config", {}).get("Labels") or {})

    def image_metadata(self, reference):
        try:
            info = json.loads(self.docker.run("image", "inspect", reference))[0]
            if not isinstance(info, dict) or not IMAGE_ID.fullmatch(info.get("Id", "")):
                raise ValueError("Invalid image ID")
            config = info.get("Config") or {}
            if not isinstance(config, dict) or not isinstance(config.get("Labels") or {}, dict):
                raise ValueError("Invalid image labels")
            if not isinstance(info.get("RepoDigests", []), list):
                raise ValueError("Invalid registry digests")
            return info
        except (ValueError, KeyError, IndexError, TypeError):
            raise UpdateError("Cannot verify immutable local image metadata") from None

    def disk_preflight(self):
        try:
            if any(self.disk_usage(path).free < MIN_FREE_BYTES for path in (self.directory, self.repo)):
                raise UpdateError("Preflight requires at least 1 GiB free on checkout and updater-state filesystems")
        except OSError:
            raise UpdateError("Cannot verify available deployment disk reserve") from None

    def candidate_preflight(self, candidate, labels, current):
        revision = labels.get("org.opencontainers.image.revision", "")
        if (not isinstance(revision, str) or not REVISION.fullmatch(revision)
                or labels.get("org.opencontainers.image.source") != SOURCE
                or labels.get(RELEASE_CHANNEL) != "main"):
            raise UpdateError("Candidate lacks exact Apex source/revision and main release channel metadata")
        exact_reference = REGISTRY_REPOSITORY + ":sha-" + revision
        if self.image not in (DEFAULT_IMAGE, exact_reference):
            raise UpdateError("Automatic updates require main or the exact candidate revision release tag")
        trusted = re.compile(re.escape(REGISTRY_REPOSITORY) + r"@sha256:[0-9a-f]{64}\Z")
        moving = self.image_metadata(candidate)
        digests = {value for value in moving.get("RepoDigests", []) if isinstance(value, str) and trusted.fullmatch(value)}
        if not digests:
            raise UpdateError("Candidate lacks a trusted immutable registry digest")
        # Pulling the exact release tag pins its registry content independently
        # of a moving main tag, including manifest-index/platform resolution.
        self.docker.run("pull", exact_reference)
        exact = self.image_metadata(exact_reference)
        if (exact["Id"] != candidate or not digests.intersection(exact.get("RepoDigests", []))):
            raise UpdateError("Moving image differs from the immutable revision release")
        self.release_verifier.verify(current.get("revision"), revision)
        try:
            raw = self.docker.run("run", "--rm", "--network", "none", "--read-only",
                "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                "--entrypoint", "python", candidate, "-B", "-c", MIGRATION_GRAPH)
            head = validate_migration_graph(json.loads(raw), current["schema"])
        except (ValueError, KeyError, TypeError):
            raise UpdateError("Candidate migration metadata could not be verified") from None
        self.disk_preflight()
        return {"image": candidate, "revision": revision, "digests": sorted(digests), "migration_head": head}

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
        # Resuming is explicit authorization, but health alone cannot establish
        # release/database compatibility after a manually recovered outage.
        current = self.running()
        self.disk_preflight()
        self.docker.run("pull", self.image)
        candidate, labels = self.image_info(self.image)
        if candidate != current["image"]:
            raise UpdateError("Running image differs from the selected release; verify manual recovery before resuming")
        verified = self.candidate_preflight(candidate, labels, current)
        if current["schema"] != [verified["migration_head"]]:
            raise UpdateError("Running deployment has not reached its verified migration head; recover manually before resuming")
        self.compose("exec", "-T", "api", "python", "-c", BACKUP_READY)
        current.update(digests=verified["digests"], migration_head=verified["migration_head"])
        self.state.update(current=current, paused=False, in_progress=None, failed_image=None)
        self.save()
        print("Healthy running deployment adopted; automatic updates resumed")

    def verify(self):
        """Download and inspect a candidate without state/application changes."""
        current = self.running()
        self.disk_preflight()
        self.docker.run("pull", self.image)
        candidate, labels = self.image_info(self.image)
        verified = self.candidate_preflight(candidate, labels, current)
        self.compose("exec", "-T", "api", "python", "-c", BACKUP_READY)
        return {**verified, "current_schema": current["schema"],
                "deployment_required": candidate != current["image"],
                "manual_recovery_required": candidate == current["image"] and current["schema"] != [verified["migration_head"]]}

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
        self.disk_preflight()
        self.docker.run("pull", self.image)
        candidate, labels = self.image_info(self.image)
        if candidate == self.state.get("failed_image") and not retry:
            print("Skipping the previously failed image; wait for a new tested commit or use --retry")
            return
        current = self.running()
        self.state["current"] = current
        self.save()
        if current["image"] == candidate:
            print("Already running the selected immutable image; no deployment attempted")
            return
        verified = self.candidate_preflight(candidate, labels, current)
        revision = verified["revision"]
        # Check before downtime, including an already-current installation
        # during timer setup. No unencrypted health backups are ever created.
        self.compose("exec", "-T", "api", "python", "-c", BACKUP_READY)
        self.docker.run("image", "tag", current["image"], "apex-health-rollback:" + current["image"].split(":")[1][:12])
        deployment = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + revision[:12]
        old = self.override("previous", current["image"])
        new = self.override("candidate", candidate)
        phase = "stopping"
        self.state.update(in_progress=phase, candidate=verified)
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
            if schema != [verified["migration_head"]]:
                raise UpdateError("Migration did not reach the verified candidate head; manual recovery required")
            phase = "starting"
            self.state.update(in_progress=phase, candidate_schema=schema)
            self.save()
            self.start(candidate)
            self.state.update(previous=current,
                              current={**verified, "schema": schema},
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
    parser.add_argument("action", choices=["update", "verify", "status", "doctor", "pause", "resume", "rollback"], nargs="?", default="update")
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
        if args.action not in ("status", "doctor", "verify"):
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
            elif args.action == "verify":
                print(json.dumps(updater.verify(), indent=2))
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
