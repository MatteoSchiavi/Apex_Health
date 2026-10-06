"""Offline orchestration tests for the deployment updater."""
import json
from pathlib import Path
import tempfile
import unittest

from infra.auto_update import BACKUP_READY, DEFAULT_IMAGE, SOURCE, UpdateError, Updater


OLD_IMAGE = "sha256:" + "1" * 64
NEW_IMAGE = "sha256:" + "2" * 64
REV = "a" * 40
OLD_SCHEMA = ["001"]
NEW_SCHEMA = ["002"]


class FakeDocker:
    """A small Docker/Compose model that records the updater's real commands."""

    def __init__(self):
        self.events = []
        self.images = {
            DEFAULT_IMAGE: (NEW_IMAGE, {
                "org.opencontainers.image.revision": REV,
                "org.opencontainers.image.source": SOURCE,
            }),
            OLD_IMAGE: (OLD_IMAGE, {}),
            NEW_IMAGE: (NEW_IMAGE, {
                "org.opencontainers.image.revision": REV,
                "org.opencontainers.image.source": SOURCE,
            }),
        }
        self.services = {name: OLD_IMAGE for name in ("api", "worker", "bot")}
        self.bot_exists = True
        self.schema_value = list(OLD_SCHEMA)
        self.fail = set()
        self.pulled = False

    def _service_override(self, args):
        indexes = [i for i, value in enumerate(args) if value == "-f"]
        index = indexes[-1] if indexes else None
        if index is None:
            return None
        return Path(args[index + 1])

    def run(self, *args):
        self.events.append(tuple(args))
        if args[:1] == ("ps",):
            filters = " ".join(args)
            if ("label=com.docker.compose.project=apex-health" in filters
                    and "label=com.docker.compose.service=bot" in filters
                    and self.bot_exists):
                return "legacy-bot-container"
            return ""
        if args[:1] == ("stop",):
            if "legacy-bot-container" in args:
                self.services["bot"] = None
            return ""
        if args[:1] == ("rm",):
            if "legacy-bot-container" in args:
                self.services["bot"] = None
                self.bot_exists = False
            return ""
        if args[:1] == ("pull",):
            if "pull" in self.fail:
                raise UpdateError("fake pull failed")
            self.pulled = True
            return ""
        if args[:2] == ("image", "inspect"):
            reference = args[2]
            image, labels = self.images[reference]
            return json.dumps([{"Id": image, "Config": {"Labels": labels}}])
        if args[:2] == ("image", "tag"):
            return ""
        if args[:1] == ("container",):
            image = self.services[args[2]]
            return json.dumps([{"Image": image, "State": {"Running": image is not None}}])
        if args[:1] != ("compose",):
            raise AssertionError(f"unexpected docker command: {args}")

        # Compose options precede the command; find its first known verb.
        verbs = {"ps", "exec", "run", "up", "stop"}
        command_at = next((i for i, value in enumerate(args) if value in verbs), None)
        if command_at is None:
            raise AssertionError(f"unknown compose command: {args}")
        cmd, tail = args[command_at], args[command_at + 1:]
        if cmd == "ps":
            service = tail[-1]
            return service if self.services.get(service) is not None else ""
        if cmd == "exec":
            service = tail[1]
            if service == "db":
                return "\n".join(self.schema_value)
            if service == "api" and BACKUP_READY in tail and "backup_ready" in self.fail:
                raise UpdateError("fake backup key check failed")
            if service == "api" and "probe" in self.fail and "health" in " ".join(tail):
                raise UpdateError("fake health probe failed")
            return ""
        if cmd == "run":
            service = tail[-4] if "python" in tail else tail[-1]
            # --rm/--no-deps/options and the Python command follow the service.
            service = next((x for x in tail if x in ("api", "migrate")), service)
            if service == "api":
                if "backup" in self.fail:
                    raise UpdateError("fake backup failed")
                return json.dumps({"size": 10, "sha256": "b" * 64, "path": "/backups/deploy.zip"})
            if "migration" in self.fail:
                if "migration_changes_schema" in self.fail:
                    self.schema_value = list(NEW_SCHEMA)
                raise UpdateError("fake migration failed")
            if "migration_keeps_schema" not in self.fail:
                self.schema_value = list(NEW_SCHEMA)
            return ""
        if cmd == "up":
            override = self._service_override(args)
            image = json.loads(override.read_text())["services"]["api"]["image"]
            if "start" in self.fail and image == NEW_IMAGE:
                raise UpdateError("fake start failed")
            for service in tail:
                if service in self.services:
                    self.services[service] = image
            return ""
        if cmd == "stop":
            if "stop" in self.fail:
                raise UpdateError("fake stop failed")
            for service in tail[2:]:
                if service in self.services:
                    self.services[service] = None
            return ""
        raise AssertionError(f"unhandled compose command: {args}")


class AutoUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.state_dir = root / "state"
        self.state_dir.mkdir()
        self.docker = FakeDocker()
        self.updater = Updater(root, self.state_dir, docker=self.docker)

    def tearDown(self):
        self.temp.cleanup()

    def count(self, command):
        return sum(command in event for event in self.docker.events)

    def test_success_backs_up_before_migration_and_start_and_pins_images(self):
        self.updater.update()
        events = self.docker.events
        backup = next(i for i, e in enumerate(events) if "run" in e and "APEX_DEPLOYMENT=" in " ".join(e))
        migration = next(i for i, e in enumerate(events) if "run" in e and "migrate" in e)
        start = next(i for i, e in enumerate(events) if "up" in e)
        self.assertLess(backup, migration)
        self.assertLess(migration, start)
        bot_stop = next(i for i, e in enumerate(events) if "legacy-bot-container" in e and "stop" in e)
        bot_remove = next(i for i, e in enumerate(events) if "legacy-bot-container" in e and "rm" in e)
        self.assertLess(bot_stop, backup)
        self.assertGreater(bot_remove, start)
        self.assertEqual(self.docker.services["api"], NEW_IMAGE)
        self.assertEqual(self.docker.services["worker"], NEW_IMAGE)
        self.assertIsNone(self.docker.services["bot"])
        self.assertTrue(any("--pull" in e and "never" in e for e in events))
        self.assertTrue((self.state_dir / "active.compose.yml").exists())
        self.assertEqual(self.updater.state["current"]["image"], NEW_IMAGE)
        self.assertEqual(self.updater.state["previous"]["image"], OLD_IMAGE)
        self.assertIsNone(self.updater.state["in_progress"])

    def test_unchanged_image_does_not_stop_services(self):
        self.docker.images[DEFAULT_IMAGE] = (OLD_IMAGE, {
            "org.opencontainers.image.revision": REV,
            "org.opencontainers.image.source": SOURCE,
        })
        self.updater.update()
        self.assertEqual(self.count("stop"), 0)
        self.assertEqual(self.docker.services["api"], OLD_IMAGE)

    def test_pull_bad_labels_and_missing_backup_key_leave_services_running(self):
        for failure in ("pull", "labels", "backup_ready"):
            with self.subTest(failure=failure):
                self.temp.cleanup()
                self.setUp()
                if failure == "pull":
                    self.docker.fail.add("pull")
                elif failure == "labels":
                    self.docker.images[DEFAULT_IMAGE] = (NEW_IMAGE, {})
                else:
                    self.docker.fail.add("backup_ready")
                with self.assertRaises(UpdateError):
                    self.updater.update()
                self.assertEqual(self.docker.services["api"], OLD_IMAGE)
                self.assertEqual(self.docker.services["worker"], OLD_IMAGE)
                self.assertEqual(self.count("stop"), 0)

    def test_backup_failure_restores_old_deployment(self):
        self.docker.fail.add("backup")
        with self.assertRaises(UpdateError):
            self.updater.update()
        self.assertEqual(self.docker.services["api"], OLD_IMAGE)
        self.assertEqual(self.docker.services["worker"], OLD_IMAGE)
        self.assertFalse(self.updater.state["paused"])
        self.assertIsNone(self.updater.state["in_progress"])
        self.assertEqual(self.updater.state["failure_phase"], "backup")

    def test_start_failure_with_unchanged_schema_restores_old_deployment(self):
        # Model a migration image that succeeds without advancing the schema.
        self.docker.fail.add("start")
        self.docker.fail.add("migration_keeps_schema")
        with self.assertRaises(UpdateError):
            self.updater.update()
        self.assertEqual(self.docker.services["api"], OLD_IMAGE)
        self.assertFalse(self.updater.state["paused"])
        self.assertIsNone(self.updater.state["in_progress"])

    def test_start_failure_after_schema_change_requires_manual_recovery(self):
        self.docker.fail.add("start")
        with self.assertRaises(UpdateError):
            self.updater.update()
        self.assertEqual(self.docker.schema_value, NEW_SCHEMA)
        self.assertTrue(self.updater.state["paused"])
        self.assertEqual(self.updater.state["in_progress"], "manual_recovery")
        self.assertIsNone(self.docker.services["api"])

    def test_update_recreates_only_application_services(self):
        self.updater.update()
        up_events = [e for e in self.docker.events if "up" in e]
        self.assertEqual(len(up_events), 2)
        self.assertEqual(self.docker.services, {"api": NEW_IMAGE, "worker": NEW_IMAGE, "bot": None})
        override = json.loads((self.state_dir / "active.compose.yml").read_text())
        self.assertEqual(set(override["services"]), {"api", "worker", "migrate"})

    def test_mixed_api_and_worker_images_refuse_before_stopping(self):
        self.docker.services["worker"] = "sha256:" + "3" * 64
        with self.assertRaisesRegex(UpdateError, "different images"):
            self.updater.update()
        self.assertEqual(self.count("stop"), 0)

    def test_same_schema_manual_rollback_succeeds_and_stays_paused(self):
        self.updater.state["previous"] = {"image": NEW_IMAGE, "bot": True, "schema": OLD_SCHEMA}
        self.updater.rollback()
        self.assertEqual(self.docker.services["api"], NEW_IMAGE)
        self.assertTrue(self.updater.state["paused"])
        self.assertIsNone(self.updater.state["in_progress"])

    def test_state_is_private_and_round_trips(self):
        self.updater.state = {"paused": True, "current": {"image": OLD_IMAGE}}
        self.updater.save()
        self.assertEqual(self.updater.state_path.stat().st_mode & 0o777, 0o600)
        reloaded = Updater(self.updater.repo, self.state_dir, docker=self.docker)
        self.assertEqual(reloaded.state, self.updater.state)

    def test_retry_attempts_a_previously_failed_image(self):
        self.updater.state["failed_image"] = NEW_IMAGE
        self.updater.update(retry=True)
        self.assertEqual(self.docker.services["api"], NEW_IMAGE)
        self.assertEqual(self.updater.state["failed_image"], None)

    def test_backup_key_preflight_runs_before_any_stop(self):
        self.docker.fail.add("backup_ready")
        with self.assertRaises(UpdateError):
            self.updater.update()
        ready = next(i for i, e in enumerate(self.docker.events) if BACKUP_READY in e)
        self.assertFalse(any("stop" in e for e in self.docker.events[:ready]))
        self.assertEqual(self.docker.services["api"], OLD_IMAGE)

    def test_migration_failure_pauses_and_requires_manual_recovery(self):
        self.docker.fail.add("migration")
        with self.assertRaises(UpdateError):
            self.updater.update()
        self.assertTrue(self.updater.state["paused"])
        self.assertEqual(self.updater.state["in_progress"], "manual_recovery")
        self.assertIsNone(self.docker.services["api"])

    def test_migration_failure_that_changes_schema_requires_manual_recovery(self):
        self.docker.fail.update(("migration", "migration_changes_schema"))
        with self.assertRaises(UpdateError):
            self.updater.update()
        self.assertTrue(self.updater.state["paused"])
        self.assertIsNone(self.docker.services["api"])

    def test_paused_or_interrupted_update_does_not_pull(self):
        for state in ({"paused": True}, {"in_progress": "migrating"}):
            with self.subTest(state=state):
                self.updater.state = state
                with self.assertRaises(UpdateError):
                    self.updater.update()
                self.assertFalse(self.docker.pulled)

    def test_failed_image_is_skipped_until_retry(self):
        self.updater.state["failed_image"] = NEW_IMAGE
        self.updater.update()
        self.assertEqual(self.count("stop"), 0)
        self.assertEqual(self.docker.services["api"], OLD_IMAGE)

    def test_manual_rollback_refuses_changed_schema(self):
        self.updater.state["previous"] = {"image": OLD_IMAGE, "bot": True, "schema": OLD_SCHEMA}
        self.docker.schema_value = list(NEW_SCHEMA)
        with self.assertRaisesRegex(UpdateError, "schema changed"):
            self.updater.rollback()
        self.assertEqual(self.count("stop"), 0)

    def test_resume_adopts_healthy_running_deployment(self):
        self.docker.services.update(api=NEW_IMAGE, worker=NEW_IMAGE)
        self.docker.schema_value = list(NEW_SCHEMA)
        self.updater.resume()
        self.assertEqual(self.updater.state["current"]["image"], NEW_IMAGE)
        self.assertEqual(self.updater.state["current"]["schema"], NEW_SCHEMA)
        self.assertFalse(self.updater.state["paused"])
        self.assertIsNone(self.updater.state["in_progress"])


if __name__ == "__main__":
    unittest.main()
