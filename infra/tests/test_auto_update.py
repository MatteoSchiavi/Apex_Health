"""Offline orchestration tests for the deployment updater."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import subprocess
import os
import fcntl
import io

from infra.auto_update import BACKUP_READY, DEFAULT_IMAGE, SOURCE, WORKER_PROBE, Docker, UpdateError, Updater, main
from infra.auto_update import (GitHubReleaseVerifier, MIN_FREE_BYTES, RELEASE_CHANNEL,
    REGISTRY_REPOSITORY, validate_migration_graph)
from types import SimpleNamespace


OLD_IMAGE = "sha256:" + "1" * 64
NEW_IMAGE = "sha256:" + "2" * 64
REV = "a" * 40
CURRENT_REV = "b" * 40
DIGEST = REGISTRY_REPOSITORY + "@sha256:" + "c" * 64
OLD_SCHEMA = ["001"]
NEW_SCHEMA = ["002"]


class FakeReleaseVerifier:
    def __init__(self):
        self.calls = []
        self.fail = False

    def verify(self, current_revision, candidate_revision):
        self.calls.append((current_revision, candidate_revision))
        if self.fail:
            raise UpdateError("fake release verification failed")


class FakeDocker:
    """A small Docker/Compose model that records the updater's real commands."""

    def __init__(self):
        self.events = []
        self.images = {
            DEFAULT_IMAGE: (NEW_IMAGE, {
                "org.opencontainers.image.revision": REV,
                "org.opencontainers.image.source": SOURCE,
                RELEASE_CHANNEL: "main",
            }),
            OLD_IMAGE: (OLD_IMAGE, {"org.opencontainers.image.revision": CURRENT_REV}),
            NEW_IMAGE: (NEW_IMAGE, {
                "org.opencontainers.image.revision": REV,
                "org.opencontainers.image.source": SOURCE,
                RELEASE_CHANNEL: "main",
            }),
        }
        self.images[REGISTRY_REPOSITORY + ":sha-" + REV] = self.images[NEW_IMAGE]
        self.digests = {NEW_IMAGE: [DIGEST], OLD_IMAGE: []}
        self.graph = {"heads": ["002"], "revisions": {"001": [], "002": ["001"]}}
        self.services = {name: OLD_IMAGE for name in ("api", "worker", "bot")}
        self.bot_exists = True
        self.schema_value = list(OLD_SCHEMA)
        self.fail = set()
        self.pulled = False
        self.project_label = None

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
        if args[:2] == ("manifest", "inspect"):
            if "registry" in self.fail:
                raise UpdateError("registry error including sensitive-token")
            return "{}"
        if args[:2] == ("image", "inspect"):
            reference = args[2]
            image, labels = self.images[reference]
            return json.dumps([{"Id": image, "Config": {"Labels": labels}, "RepoDigests": self.digests.get(image, [])}])
        if args[:1] == ("run",):
            if "graph" in self.fail:
                raise UpdateError("fake candidate migration inspection failed")
            return json.dumps(self.graph)
        if args[:2] == ("image", "tag"):
            return ""
        if args[:1] == ("container",):
            image = self.services[args[2]]
            labels = {"com.docker.compose.project": self.project_label} if self.project_label else {}
            return json.dumps([{"Image": image, "State": {"Running": image is not None}, "Config": {"Labels": labels}}])
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
            if WORKER_PROBE in tail and ('worker_probe' in self.fail or
                    ('new_worker_probe' in self.fail and self.services['api'] == NEW_IMAGE)):
                raise UpdateError('fake worker health failure')
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
        self.release_verifier = FakeReleaseVerifier()
        self.updater = Updater(root, self.state_dir, docker=self.docker,
            release_verifier=self.release_verifier, disk_usage=lambda _: SimpleNamespace(free=4 * MIN_FREE_BYTES))

    def tearDown(self):
        self.temp.cleanup()

    def count(self, command):
        return sum(command in event for event in self.docker.events)

    def assert_preflight_untouched(self):
        self.assertEqual(self.count("stop"), 0)
        self.assertEqual(self.count("up"), 0)
        self.assertFalse(any(e[0] == "compose" and "run" in e for e in self.docker.events))
        self.assertFalse(any(e[:2] == ("image", "tag") for e in self.docker.events))
        self.assertEqual(self.docker.services["api"], OLD_IMAGE)
        self.assertEqual(self.docker.services["worker"], OLD_IMAGE)
        self.assertFalse((self.state_dir / "candidate.compose.yml").exists())

    def test_old_image_new_0026_database_rejected_before_stop_backup_migration(self):
        self.docker.schema_value = ["0026"]
        self.docker.graph = {"heads": ["0023"], "revisions": {
            f"{i:04}": [f"{i-1:04}"] if i > 1 else [] for i in range(1, 24)}}
        with self.assertRaisesRegex(UpdateError, "forward migration path"):
            self.updater.update()
        self.assert_preflight_untouched()

    def test_candidate_migration_graph_inspection_has_no_production_access(self):
        self.updater.update()
        event = next(e for e in self.docker.events if e[0] == "run")
        self.assertEqual(event[1:5], ("--rm", "--network", "none", "--read-only"))
        self.assertIn("--entrypoint", event)
        self.assertIn(NEW_IMAGE, event)
        for forbidden in ("-e", "--env", "--env-file", "-v", "--volume", "--mount"):
            self.assertNotIn(forbidden, event)
        inspection = self.docker.events.index(event)
        stopping = next(i for i,e in enumerate(self.docker.events) if "stop" in e)
        self.assertLess(inspection, stopping)
        self.assertEqual(self.release_verifier.calls, [(CURRENT_REV, REV)])
        self.assertEqual(self.updater.state['candidate']['digests'], [DIGEST])

    def test_malformed_missing_cyclic_disconnected_and_multihead_graphs_fail_closed(self):
        graphs = [
            {"heads": ["002"], "revisions": {"002": ["001"]}},
            {"heads": ["001"], "revisions": {"001": ["002"], "002": ["001"]}},
            {"heads": ["002"], "revisions": {"001": [], "002": ["001"], "003": []}},
            {"heads": ["001", "002"], "revisions": {"001": [], "002": []}},
            {"heads": [], "revisions": {}},
            {"heads": ["003"], "revisions": {"001": [], "002": ["001"]}},
            {"heads": ["002"], "revisions": {"001": [], "002": "001"}},
        ]
        for graph in graphs:
            with self.subTest(graph=graph):
                self.docker.graph = graph
                self.docker.events.clear()
                with self.assertRaises(UpdateError):
                    self.updater.update()
                self.assert_preflight_untouched()

    def test_multiple_database_heads_require_forward_paths_to_one_merge_head(self):
        graph = {'heads':['merge'], 'revisions': {'root':[], 'left':['root'], 'right':['root'], 'merge':['left','right']}}
        self.assertEqual(validate_migration_graph(graph, ['left','right']), 'merge')
        with self.assertRaises(UpdateError):
            validate_migration_graph(graph, ['unknown'])

    def test_wrong_source_channel_or_revision_fails_before_downtime(self):
        for key,value in (("org.opencontainers.image.source", "https://github.com/Other/Project"),
                (RELEASE_CHANNEL, "development"), (RELEASE_CHANNEL, None),
                ("org.opencontainers.image.revision", "short")):
            with self.subTest(key=key,value=value):
                labels = dict(self.docker.images[NEW_IMAGE][1])
                labels[key] = value
                self.docker.images[DEFAULT_IMAGE] = (NEW_IMAGE, labels)
                self.docker.events.clear()
                with self.assertRaises(UpdateError):
                    self.updater.update()
                self.assert_preflight_untouched()

    def test_missing_or_untrusted_registry_digest_fails_before_downtime(self):
        for digests in ([], ['other.example/apex@sha256:'+'c'*64], [REGISTRY_REPOSITORY+'@sha256:short']):
            with self.subTest(digests=digests):
                self.docker.digests[NEW_IMAGE] = digests
                self.docker.events.clear()
                with self.assertRaisesRegex(UpdateError, "registry digest"):
                    self.updater.update()
                self.assert_preflight_untouched()

    def test_invalid_local_image_id_fails_before_downtime(self):
        self.docker.images[DEFAULT_IMAGE] = ('mutable-tag', {})
        with self.assertRaises(UpdateError):
            self.updater.update()
        self.assert_preflight_untouched()

    def test_revision_tag_content_must_equal_moving_image(self):
        self.docker.images[REGISTRY_REPOSITORY+':sha-'+REV] = self.docker.images[OLD_IMAGE]
        with self.assertRaisesRegex(UpdateError, "immutable revision release"):
            self.updater.update()
        self.assert_preflight_untouched()

    def test_arbitrary_registry_tag_is_rejected_even_with_main_labels(self):
        reference = REGISTRY_REPOSITORY + ':experimental'
        self.updater.image = reference
        self.docker.images[reference] = self.docker.images[NEW_IMAGE]
        with self.assertRaisesRegex(UpdateError, 'main or the exact'):
            self.updater.update()
        self.assert_preflight_untouched()

    def test_exact_revision_tag_can_be_selected_and_identity_is_persisted(self):
        self.updater.image = REGISTRY_REPOSITORY+':sha-'+REV
        self.updater.update()
        self.assertEqual(self.updater.state['current']['digests'], [DIGEST])
        self.assertEqual(self.updater.state['current']['migration_head'], '002')

    def test_successful_migration_with_wrong_head_never_starts_candidate(self):
        self.docker.fail.add('migration_keeps_schema')
        with self.assertRaisesRegex(UpdateError, 'verified candidate head'):
            self.updater.update()
        self.assertEqual(self.count('up'), 0)
        self.assertTrue(self.updater.state['paused'])
        self.assertEqual(self.updater.state['in_progress'], 'manual_recovery')

    def test_release_or_graph_network_failure_leaves_services_running(self):
        for failure in ('release', 'graph'):
            with self.subTest(failure=failure):
                self.release_verifier.fail = failure == 'release'
                self.docker.fail = {'graph'} if failure == 'graph' else set()
                self.docker.events.clear()
                with self.assertRaises(UpdateError):
                    self.updater.update()
                self.assert_preflight_untouched()

    def test_low_disk_reserve_fails_before_pull_or_stop(self):
        self.updater.disk_usage = lambda _: SimpleNamespace(free=MIN_FREE_BYTES-1)
        with self.assertRaisesRegex(UpdateError, "1 GiB"):
            self.updater.update()
        self.assertEqual(self.count('pull'), 0)
        self.assert_preflight_untouched()

    def test_unchanged_unlabelled_image_is_noop_without_release_verification(self):
        self.docker.images[DEFAULT_IMAGE] = (OLD_IMAGE, {})
        self.docker.images[OLD_IMAGE] = (OLD_IMAGE, {})
        self.updater.update()
        self.assert_preflight_untouched()
        self.assertEqual(self.release_verifier.calls, [])
        self.assertFalse(any(e[0] == 'run' for e in self.docker.events))

    def test_duplicate_scheduled_update_does_not_construct_or_call_docker(self):
        with (self.state_dir / 'update.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with patch('infra.auto_update.Updater') as construct:
                self.assertEqual(main(['update', '--repo', str(self.updater.repo), '--state-dir', str(self.state_dir)]), 0)
            construct.assert_not_called()

    def test_docker_error_does_not_log_registry_tokens_or_response_bodies(self):
        result = subprocess.CompletedProcess([], 1, 'sensitive-body', 'Bearer sensitive-token')
        with patch('infra.auto_update.subprocess.run', return_value=result):
            with self.assertRaises(UpdateError) as raised:
                Docker().run('pull', DEFAULT_IMAGE)
        self.assertNotIn('sensitive', str(raised.exception))

    def test_current_worker_health_failure_never_stops_application(self):
        self.docker.fail.add('worker_probe')
        with self.assertRaisesRegex(UpdateError, 'worker health'):
            self.updater.update()
        self.assert_preflight_untouched()

    def test_new_worker_health_failure_after_migration_requires_manual_recovery(self):
        self.docker.fail.add('new_worker_probe')
        with self.assertRaisesRegex(UpdateError, 'worker health'):
            self.updater.update()
        self.assertTrue(self.updater.state['paused'])
        self.assertEqual(self.updater.state['in_progress'], 'manual_recovery')
        self.assertIsNone(self.docker.services['api'])

    def test_verify_returns_release_identity_without_saving_state_or_deploying(self):
        self.updater.state = {'paused':True, 'in_progress':'manual_recovery', 'failed_image':NEW_IMAGE}
        initial = dict(self.updater.state)
        report = self.updater.verify()
        self.assertEqual(report['digests'], [DIGEST])
        self.assertEqual(report['migration_head'], '002')
        self.assertEqual(report['revision'], REV)
        self.assertTrue(report['deployment_required'])
        self.assertEqual(self.updater.state, initial)
        self.assertFalse(self.updater.state_path.exists())
        self.assert_preflight_untouched()

    def test_verify_failure_preserves_pause_and_never_deploys(self):
        self.updater.state = {'paused':True}
        self.docker.schema_value = ['0026']
        with self.assertRaises(UpdateError):
            self.updater.verify()
        self.assertEqual(self.updater.state, {'paused':True})
        self.assert_preflight_untouched()

    def test_install_only_refreshes_tools_but_preserves_pause_and_never_deploys_or_enables(self):
        root = self.updater.repo
        infrastructure = root / 'infra'
        infrastructure.mkdir()
        installer = Path(__file__).resolve().parents[1] / 'install-auto-update.sh'
        copied_installer = infrastructure / installer.name
        copied_installer.write_bytes(installer.read_bytes())
        source = infrastructure / 'auto_update.py'
        source.write_text("raise SystemExit('deployment must not run')\n")
        state = root / '.apex-updater'
        state.mkdir()
        paused = b'{"paused":true,"in_progress":"manual_recovery"}\n'
        (state / 'state.json').write_bytes(paused)
        commands = root / 'commands'
        binaries = root / 'bin'
        binaries.mkdir()
        for name in ('systemctl','docker'):
            stub = binaries / name
            stub.write_text('#!/bin/sh\nprintf "%s %s\\n" "'+name+'" "$*" >> "$APEX_INSTALL_TEST_COMMANDS"\n')
            stub.chmod(0o700)
        with patch.dict(os.environ, {'PATH':str(binaries)+os.pathsep+os.environ['PATH'],
                'XDG_CONFIG_HOME':str(root / 'config'), 'APEX_INSTALL_TEST_COMMANDS':str(commands)}):
            result = subprocess.run(['bash',str(copied_installer),'--install-only','--docker-context','offline'],
                check=True, capture_output=True, text=True)
        self.assertIn('Installed host script/units only', result.stdout)
        self.assertEqual((state / 'state.json').read_bytes(), paused)
        self.assertEqual((state / 'auto_update.py').read_bytes(), source.read_bytes())
        self.assertEqual((state / 'auto_update.py').stat().st_mode & 0o777, 0o700)
        self.assertTrue((root / 'config/systemd/user/apex-health-update.service').exists())
        self.assertEqual(commands.read_text().splitlines(),
            ['systemctl --user show-environment', 'systemctl --user daemon-reload'])

    def test_install_only_dry_run_preserves_named_context_in_units(self):
        installer = Path(__file__).resolve().parents[1] / 'install-auto-update.sh'
        result = subprocess.run(['bash', str(installer), '--install-only', '--dry-run', '--docker-context','offline'],
            check=True, capture_output=True, text=True)
        self.assertIn('"--docker-context" "offline"',result.stdout)

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
        self.docker.graph = {'heads':['001'], 'revisions':{'001':[]}}
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

    def test_resume_preserves_pause_for_unverified_or_mismatched_release(self):
        self.updater.state = {'paused':True, 'in_progress':'manual_recovery', 'failed_image':NEW_IMAGE}
        initial = dict(self.updater.state)
        with self.assertRaisesRegex(UpdateError, 'differs from the selected release'):
            self.updater.resume()
        self.assertEqual(self.updater.state, initial)
        self.docker.services.update(api=NEW_IMAGE, worker=NEW_IMAGE)
        self.docker.schema_value = list(NEW_SCHEMA)
        self.release_verifier.fail = True
        with self.assertRaises(UpdateError):
            self.updater.resume()
        self.assertEqual(self.updater.state, initial)
        self.assertEqual(self.count('stop'), 0)

    def test_resume_requires_compatible_graph_and_backup_key_before_clearing_pause(self):
        self.docker.services.update(api=NEW_IMAGE, worker=NEW_IMAGE)
        self.updater.state = {'paused':True, 'failed_image':NEW_IMAGE}
        self.docker.schema_value = ['0026']
        with self.assertRaises(UpdateError):
            self.updater.resume()
        self.assertTrue(self.updater.state['paused'])
        self.docker.schema_value = list(NEW_SCHEMA)
        self.docker.fail.add('backup_ready')
        with self.assertRaises(UpdateError):
            self.updater.resume()
        self.assertTrue(self.updater.state['paused'])
        self.assertEqual(self.updater.state['failed_image'], NEW_IMAGE)

    def test_resume_requires_running_schema_at_exact_image_head(self):
        self.docker.services.update(api=NEW_IMAGE, worker=NEW_IMAGE)
        self.docker.schema_value = list(OLD_SCHEMA)
        self.updater.state = {'paused': True, 'in_progress': 'manual_recovery', 'failed_image': NEW_IMAGE}
        initial = dict(self.updater.state)
        with self.assertRaisesRegex(UpdateError, 'migration head'):
            self.updater.resume()
        self.assertEqual(self.updater.state, initial)
        self.assertEqual(self.count('stop'), 0)

    def test_verify_reports_incomplete_running_image_as_manual_recovery(self):
        self.docker.services.update(api=NEW_IMAGE, worker=NEW_IMAGE)
        self.docker.schema_value = list(OLD_SCHEMA)
        self.updater.state = {'paused': True}
        verified = self.updater.verify()
        self.assertTrue(verified['manual_recovery_required'])
        self.assertFalse(verified['deployment_required'])
        self.assertEqual(self.updater.state, {'paused': True})
        self.assertEqual(self.count('stop'), 0)

    @staticmethod
    def healthy_host(command, **kwargs):
        if command[0] == "loginctl":
            return subprocess.CompletedProcess(command, 0, "yes\n", "")
        stdout = "LoadState=loaded\nActiveState=active\nUnitFileState=enabled\n" if "apex-health-update.timer" in command else "Result=success\n"
        return subprocess.CompletedProcess(command, 0, stdout, "")

    def test_doctor_checks_runtime_without_downloading_or_deploying(self):
        (self.state_dir / 'auto_update.py').write_text('installed')
        report = self.updater.diagnose(host_run=self.healthy_host)
        self.assertFalse(any(c['status'] == 'error' for c in report['checks']))
        self.assertEqual(report['running']['image'], OLD_IMAGE)
        self.assertTrue(any(e[:2] == ('manifest', 'inspect') for e in self.docker.events))
        self.assertEqual(self.count('pull'), 0)
        self.assertEqual(self.count('stop'), 0)
        self.assertEqual(self.count('up'), 0)
        self.assertEqual(self.count('run'), 0)
        self.assertFalse(self.updater.state_path.exists())

    def test_doctor_reports_missing_timer_pause_and_registry_without_secrets(self):
        self.updater.state = {'paused': True, 'failed_image': NEW_IMAGE}
        self.docker.fail.add('registry')
        def unavailable(command, **kwargs):
            return subprocess.CompletedProcess(command, 1, '', 'sensitive-token')
        report = self.updater.diagnose(host_run=unavailable)
        checks = {c['check']: c for c in report['checks']}
        for name in ('installation', 'timer', 'automation', 'registry'):
            self.assertEqual(checks[name]['status'], 'error')
        self.assertEqual(checks['linger']['status'], 'warning')
        self.assertEqual(checks['failed_image']['status'], 'warning')
        self.assertNotIn('sensitive-token', json.dumps(report))
        self.assertEqual(self.count('stop'), 0)

    def test_project_cleanup_uses_actual_container_label(self):
        self.docker.project_label = 'custom-home'
        self.updater.running()
        self.updater.legacy_bot_containers()
        self.assertIn('label=com.docker.compose.project=custom-home', self.docker.events[-1])

    def test_docker_context_is_explicit_in_every_daemon_command(self):
        with patch('infra.auto_update.subprocess.run', return_value=subprocess.CompletedProcess([], 0, 'ok', '')) as run:
            self.assertEqual(Docker('home-rootless').run('compose', 'version'), 'ok')
        self.assertEqual(run.call_args.args[0], ['docker', '--context', 'home-rootless', 'compose', 'version'])

    def test_installer_preserves_terminal_project_and_context_in_timer(self):
        installer = Path(__file__).resolve().parents[1] / 'install-auto-update.sh'
        with patch.dict(os.environ, {'COMPOSE_PROJECT_NAME': 'custom-home', 'DOCKER_CONTEXT': 'home-rootless'}):
            result = subprocess.run(['bash', str(installer), '--dry-run'], text=True, capture_output=True, check=True)
        self.assertIn('"--project-name" "custom-home"', result.stdout)
        self.assertIn('"--docker-context" "home-rootless"', result.stdout)

    def test_installer_explicit_options_override_terminal_defaults(self):
        installer = Path(__file__).resolve().parents[1] / 'install-auto-update.sh'
        with patch.dict(os.environ, {'COMPOSE_PROJECT_NAME': 'other', 'DOCKER_CONTEXT': 'other'}):
            result = subprocess.run(['bash', str(installer), '--dry-run', '--project-name', 'chosen', '--docker-context', 'chosen'], text=True, capture_output=True, check=True)
        self.assertIn('"--project-name" "chosen"', result.stdout)
        self.assertIn('"--docker-context" "chosen"', result.stdout)

    def test_installer_preserves_compose_file_order_and_custom_separator(self):
        installer = Path(__file__).resolve().parents[1] / 'install-auto-update.sh'
        paths = [self.updater.repo / 'base.yml', self.updater.repo / 'home.yml']
        with patch.dict(os.environ, {'COMPOSE_FILE': ';'.join(map(str, paths)), 'COMPOSE_PATH_SEPARATOR': ';'}):
            result = subprocess.run(['bash', str(installer), '--dry-run'], text=True, capture_output=True, check=True)
        self.assertIn(f'"--compose-file" "{paths[0]}" "--compose-file" "{paths[1]}"', result.stdout)

    def test_status_remains_available_during_an_update(self):
        self.updater.state = {'in_progress': 'migrating'}
        self.updater.save()
        with (self.state_dir / 'update.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            output = io.StringIO()
            with patch('sys.stdout', output):
                code = main(['status', '--repo', str(self.updater.repo), '--state-dir', str(self.state_dir)])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(output.getvalue())['in_progress'], 'migrating')

    def test_doctor_reports_missing_backup_key_separately(self):
        self.docker.fail.add('backup_ready')
        report = self.updater.diagnose(host_run=self.healthy_host)
        checks = {c['check']: c for c in report['checks']}
        self.assertEqual(checks['application']['status'], 'ok')
        self.assertEqual(checks['backup_key']['status'], 'error')
        self.assertEqual(self.count('stop'), 0)


class ReleaseVerificationTests(unittest.TestCase):
    def setUp(self):
        self.comparison = {'status':'ahead', 'base_commit':{'sha':CURRENT_REV}, 'merge_base_commit':{'sha':CURRENT_REV}}
        self.release = {'head_sha':REV, 'head_branch':'main', 'event':'push', 'status':'completed',
            'conclusion':'success', 'path':'.github/workflows/tests.yml', 'id':10}
        self.jobs = [{'name':name, 'status':'completed', 'conclusion':'success'}
            for name in GitHubReleaseVerifier.required_jobs]
        self.verifier = GitHubReleaseVerifier()
        self.paths = []
        def get(path):
            self.paths.append(path)
            if path.startswith('/compare/'):
                return self.comparison
            if path.startswith('/actions/workflows/tests.yml/runs?'):
                return {'workflow_runs':[self.release]}
            if path.startswith('/actions/runs/10/jobs?'):
                return {'jobs':self.jobs}
            raise AssertionError('unexpected GitHub endpoint')
        self.verifier.get = get

    def test_exact_successful_main_push_all_jobs_including_release(self):
        self.verifier.verify(CURRENT_REV, REV)
        self.assertEqual(len(self.paths), 3)
        self.assertIn('head_sha='+REV, self.paths[1])
        self.assertIn('event=push', self.paths[1])
        self.assertIn('branch=main', self.paths[1])

    def test_older_divergent_or_unknown_progression_rejected(self):
        for status in ('behind', 'diverged', None):
            with self.subTest(status=status):
                self.comparison['status'] = status
                with self.assertRaisesRegex(UpdateError, 'older, divergent'):
                    self.verifier.verify(CURRENT_REV, REV)
        self.comparison['status'] = 'ahead'
        self.comparison['merge_base_commit']['sha'] = 'c'*40
        with self.assertRaises(UpdateError):
            self.verifier.verify(CURRENT_REV, REV)

    def test_missing_current_revision_cannot_authorize_upgrade(self):
        with self.assertRaisesRegex(UpdateError, 'full running'):
            self.verifier.verify(None, REV)
        self.assertEqual(self.paths, [])

    def test_exact_revision_branch_event_path_and_completed_success_required(self):
        for field,value in (('head_sha',CURRENT_REV), ('head_branch','other'), ('event','pull_request'),
                ('path','.github/workflows/other.yml'), ('status','in_progress'), ('conclusion','failure')):
            with self.subTest(field=field):
                original = self.release[field]
                self.release[field] = value
                with self.assertRaisesRegex(UpdateError, 'lacks a completed successful'):
                    self.verifier.verify(CURRENT_REV, REV)
                self.release[field] = original

    def test_required_release_and_every_other_job_must_succeed(self):
        original = self.jobs
        for jobs in ([j for j in original if j['name'] != 'backend-release'],
                original + [{'name':'additional-safety', 'status':'completed', 'conclusion':'skipped'}],
                [{**j,'conclusion':'failure'} if j['name']=='backend-release' else j for j in original]):
            with self.subTest(jobs=jobs):
                self.jobs = jobs
                with self.assertRaisesRegex(UpdateError, 'missing, skipped or unsuccessful'):
                    self.verifier.verify(CURRENT_REV, REV)

    def test_malformed_release_metadata_is_sanitized(self):
        self.verifier.get = lambda _: {'status':'ahead', 'base_commit':'sensitive-token'}
        with self.assertRaises(UpdateError) as raised:
            self.verifier.verify(CURRENT_REV, REV)
        self.assertNotIn('sensitive-token', str(raised.exception))

    def test_network_failures_never_include_response_bodies_or_auth(self):
        class Offline:
            def open(self, *args, **kwargs):
                raise OSError('sensitive-token response-body')
        with self.assertRaises(UpdateError) as raised:
            GitHubReleaseVerifier(opener=Offline()).get('/compare/'+CURRENT_REV+'...'+REV)
        self.assertNotIn('sensitive', str(raised.exception))

    def test_public_fixed_endpoint_timeout_and_response_limit(self):
        class Response(io.BytesIO):
            status = 200
        class Recording:
            def open(inner, request, timeout):
                self.assertEqual(timeout, 10)
                self.assertEqual(request.full_url, GitHubReleaseVerifier.root+'/test')
                self.assertFalse(request.has_header('Authorization'))
                return Response(b'{"ok":true}')
        self.assertEqual(GitHubReleaseVerifier(opener=Recording()).get('/test'), {'ok':True})
        class Oversized:
            def open(inner, *args, **kwargs):
                return Response(b'x'*(1024*1024+1))
        with self.assertRaisesRegex(UpdateError, 'oversized'):
            GitHubReleaseVerifier(opener=Oversized()).get('/test')


if __name__ == "__main__":
    unittest.main()
