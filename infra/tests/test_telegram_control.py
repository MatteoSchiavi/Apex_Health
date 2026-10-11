"""Offline remote-control authorization, replay, lifecycle and orchestration checks."""
from concurrent.futures import Future
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch, Mock

from infra.telegram_control import Bot, Controller, credentials, deployment_lock, safe_logs
from infra.auto_update import Updater, UpdateError
from infra.tests.test_auto_update import FakeDocker, FakeReleaseVerifier, NEW_IMAGE, REV


class Executor:
    def __init__(self):
        self.calls = []
        self.future = Future()

    def submit(self, fn, command):
        self.calls.append(command)
        return self.future


class TelegramControlTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.controller = Mock()
        self.controller.factory.return_value.state = {}
        self.controller.resources.return_value = 'Host resources'
        self.telegram = Mock()
        self.bot = Bot(self.telegram, 123, self.controller, self.directory, clock=lambda: 1000)
        self.bot.executor.shutdown()
        self.bot.executor = Executor()
        self.bot.username = 'apex_bot'

    def message(self, text='/update', ident=1, **changes):
        message = {'chat': {'id': 123, 'type': 'private'}, 'from': {'id': 123, 'is_bot': False}, 'date': 1000, 'text': text}
        message.update(changes)
        return {'update_id': ident, 'message': message}

    def test_authorization_rejects_other_users_groups_bots_forwarded_and_old_commands(self):
        changes = [{'from': {'id': 9}}, {'chat': {'id': 123, 'type': 'group'}},
            {'chat': {'id': -123, 'type': 'private'}}, {'from': {'id': 123, 'is_bot': True}},
            {'forward_origin': {}}, {'date': 879}, {'date': 1001}, {'text': '/update@other_bot'}]
        for ident, change in enumerate(changes, 1):
            self.bot.accept(self.message(ident=ident, **change))
        self.assertEqual(self.bot.executor.calls, [])
        self.assertEqual(self.bot.state['outbox'], [])
        self.assertEqual(self.bot.state['offset'], len(changes) + 1)

    def test_commands_are_allowlisted_no_shell_or_host_service_arguments(self):
        for ident, text in enumerate(['/restart db', '/restart api;reboot', '/update --image evil', '/sync unknown', '/update retry && env'], 1):
            self.bot.accept(self.message(text, ident))
        self.assertEqual(self.bot.executor.calls, [])
        self.assertTrue(all('Unknown command' in s for s in self.bot.state['outbox']))

    def test_update_is_immediate_and_cursor_survives_restart(self):
        self.bot.accept(self.message())
        self.assertEqual(self.bot.executor.calls, ['update'])
        self.bot.accept(self.message())
        self.assertEqual(self.bot.executor.calls, ['update'])
        persisted = json.loads(self.bot.path.read_text())
        self.assertEqual(persisted['offset'], 2)
        other = Bot(self.telegram, 123, self.controller, self.directory, clock=lambda: 1000)
        other.executor.shutdown()
        other.executor = Executor()
        other.accept(self.message())
        self.assertEqual(other.executor.calls, [])
        self.assertEqual(other.state['pending_command'], 'update')

    def test_destructive_controls_require_one_time_confirmation(self):
        for command in ['restart api', 'restart worker', 'restart app', 'resume', 'rollback', 'update retry']:
            with self.subTest(command=command):
                self.bot.future = None
                self.bot.accept(self.message('/' + command, self.bot.state.get('offset') or 1))
                self.assertIsNotNone(self.bot.confirmation)
                token = self.bot.confirmation['token']
                self.bot.accept(self.message('/confirm ' + token, self.bot.state['offset']))
                self.assertEqual(self.bot.executor.calls[-1], command)
                self.assertIsNone(self.bot.confirmation)
                before = len(self.bot.executor.calls)
                self.bot.accept(self.message('/confirm ' + token, self.bot.state['offset']))
                self.assertEqual(len(self.bot.executor.calls), before)

    def test_expired_and_canceled_confirmations_never_run(self):
        self.bot.accept(self.message('/restart app'))
        token = self.bot.confirmation['token']
        self.bot.clock = lambda: 1061
        self.bot.accept(self.message('/confirm ' + token, 2, date=1061))
        self.assertEqual(self.bot.executor.calls, [])
        self.bot.accept(self.message('/rollback', 3, date=1061))
        self.bot.accept(self.message('/cancel', 4, date=1061))
        self.assertIsNone(self.bot.confirmation)

    def test_one_job_at_a_time_even_when_previous_future_already_finished(self):
        self.bot.accept(self.message())
        self.bot.executor.future.set_result('Done')
        self.bot.accept(self.message('/backup', 2))
        self.assertEqual(self.bot.executor.calls, ['update'])
        self.bot.finish()
        self.assertIsNone(self.bot.future)
        self.assertNotIn('pending_command', json.loads(self.bot.path.read_text()))
        self.assertIn('Done', self.bot.state['outbox'][-1])

    def test_status_and_resources_remain_available_during_update(self):
        self.bot.accept(self.message())
        self.controller.factory.return_value.state = {'in_progress': 'migrating'}
        self.bot.accept(self.message('/status', 2))
        self.assertIn('migrating', self.bot.state['outbox'][-1])
        self.bot.accept(self.message('/resources', 3))
        self.assertEqual(self.bot.state['outbox'][-1], 'Host resources')
        self.assertEqual(self.bot.executor.calls, ['update'])

    def test_errors_are_not_sent_to_telegram_and_audit_state_is_cleared(self):
        self.bot.accept(self.message())
        self.bot.executor.future.set_exception(RuntimeError('secret-token private-medical-data'))
        self.bot.finish()
        self.assertNotIn('secret-token', str(self.bot.state))
        self.assertNotIn('private-medical-data', str(self.bot.state))
        self.assertIn('Operation failed', self.bot.state['outbox'][-1])

    def test_failed_delivery_is_retained_across_restart(self):
        self.bot.tell('Service recovered')
        self.telegram.send.side_effect = OSError('outage')
        with self.assertRaises(OSError):
            self.bot.flush()
        self.assertEqual(json.loads(self.bot.path.read_text())['outbox'], ['Service recovered'])
        self.telegram.send.side_effect = None
        self.bot.flush()
        self.assertEqual(self.bot.state['outbox'], [])

    def test_health_and_disk_notifications_only_on_transitions(self):
        updater = Mock()
        updater.state = {}
        self.controller.factory.return_value = updater
        disk = SimpleNamespace(used=10, total=100)
        with patch('infra.telegram_control.shutil.disk_usage', return_value=disk):
            self.bot.monitor()
            self.assertEqual(self.bot.state['outbox'], [])
            updater.probe.side_effect = UpdateError('private error')
            self.bot.monitor()
            self.bot.monitor()
            self.assertEqual(len(self.bot.state['outbox']), 1)
            updater.probe.side_effect = None
            self.bot.monitor()
            self.assertEqual(len(self.bot.state['outbox']), 2)
            disk.used = 95
            self.bot.monitor()
            self.bot.monitor()
            self.assertEqual(len(self.bot.state['outbox']), 3)
            disk.used = 50
            self.bot.monitor()
            self.assertEqual(len(self.bot.state['outbox']), 4)

    def test_expected_deployment_downtime_skips_health_probe(self):
        updater = Mock()
        updater.state = {'in_progress': 'migrating'}
        self.controller.factory.return_value = updater
        self.bot.monitor()
        updater.probe.assert_not_called()

    def test_deployment_changes_notify_without_raw_state(self):
        updater = Mock()
        updater.state = {'current': {'revision': REV}, 'backup': {'path': '/private/backup'}}
        self.controller.factory.return_value = updater
        self.controller.status.return_value = 'Known service state'
        with patch('infra.telegram_control.shutil.disk_usage', return_value=SimpleNamespace(used=10, total=100)):
            self.bot.monitor()
            updater.state['paused'] = True
            self.bot.monitor()
            self.bot.monitor()
        self.assertEqual(len(self.bot.state['outbox']), 1)
        self.assertNotIn('/private/backup', str(self.bot.state))


class HostControlsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        self.docker = FakeDocker()
        self.controller = Controller(lambda: Updater(self.path, self.path, docker=self.docker,
            release_verifier=FakeReleaseVerifier()), self.path)

    def test_update_uses_existing_verified_deployment_path(self):
        result = self.controller.execute('update')
        self.assertIn('Update check completed', result)
        state = json.loads((self.path / 'state.json').read_text())
        self.assertEqual(state['current']['image'], NEW_IMAGE)
        self.assertTrue(state['backup']['sha256'])
        self.assertEqual(self.docker.services['api'], NEW_IMAGE)

    def test_mutations_share_updater_lock(self):
        with deployment_lock(self.path):
            with self.assertRaises(UpdateError):
                self.controller.execute('pause')
            with self.assertRaises(UpdateError):
                self.controller.execute('update')
        self.assertEqual(self.docker.events, [])
        self.controller.execute('pause')
        self.assertTrue(json.loads((self.path / 'state.json').read_text())['paused'])

    def test_paused_or_interrupted_updates_are_not_forced(self):
        for state in [{'paused': True}, {'in_progress': 'manual_recovery'}]:
            (self.path / 'state.json').write_text(json.dumps(state))
            with self.assertRaises(UpdateError):
                self.controller.execute('update')
        self.assertFalse(self.docker.pulled)

    def test_status_does_not_expose_arbitrary_revision_or_paths(self):
        (self.path / 'state.json').write_text(json.dumps({'current': {'revision': 'private-token'}, 'backup': {'path': 'private-health'}}))
        status = self.controller.status()
        self.assertNotIn('private-token', status)
        self.assertNotIn('private-health', status)
        self.assertIn('api: running', status)

    def test_only_structured_log_fields_are_returned(self):
        result = safe_logs(json.dumps([{'timestamp': '2026-10-09T20:00:00+00:00', 'level': 'ERROR', 'source': 'tasks.runtime', 'event': 'task_failed', 'message': 'private secret'}, {'source': 'unsafe\nsecret'}]))
        self.assertIn('task_failed', result)
        self.assertNotIn('private secret', result)
        self.assertNotIn('unsafe', result)

    def test_credentials_require_private_owner_ids_and_never_execute_shell(self):
        env = self.path / '.env'
        with patch.dict(os.environ, {}, clear=True):
            for chat, user in [('-123', '-123'), ('123', '456'), ('0', '0')]:
                env.write_text(f'OWNER_TELEGRAM_BOT_TOKEN=123:abc\nOWNER_TELEGRAM_CHAT_ID={chat}\nOWNER_TELEGRAM_USER_ID={user}\n')
                with self.assertRaises(ValueError):
                    credentials(env)
            env.write_text('export OWNER_TELEGRAM_BOT_TOKEN="123:abc"\nOWNER_TELEGRAM_CHAT_ID=123 # private\nOTHER=$(touch /unsafe)\n')
            self.assertEqual(credentials(env), ('123:abc', 123, 123))
            env.write_text('OWNER_TELEGRAM_BOT_TOKEN=$(touch /unsafe)\nOWNER_TELEGRAM_CHAT_ID=123\n')
            with self.assertRaises(ValueError):
                credentials(env)

    def test_installer_dry_run_contains_no_secrets_and_preserves_named_context(self):
        result = subprocess.run(['bash', 'infra/install-telegram-control.sh', '--dry-run', '--docker-context', 'home', '--project-name', 'my-apex'], check=True, text=True, capture_output=True)
        self.assertIn('apex-updater/telegram_control.py', result.stdout)
        self.assertIn('"--docker-context" "home"', result.stdout)
        self.assertIn('"--project-name" "my-apex"', result.stdout)
        self.assertIn('Restart=always', result.stdout)
        self.assertNotIn('BOT_TOKEN', result.stdout)

    def test_installer_refuses_deployment_lock_before_replacing_or_restarting(self):
        source = Path('infra/install-telegram-control.sh')
        infra = self.path / 'infra'
        infra.mkdir()
        installer = infra / source.name
        installer.write_bytes(source.read_bytes())
        (infra / 'telegram_control.py').write_text("print('synthetic configuration valid')\n")
        (infra / 'auto_update.py').write_text('# synthetic updater\n')
        state = self.path / '.apex-updater'
        state.mkdir()
        installed = state / 'telegram_control.py'
        installed.write_text('preserve running controller')
        binaries = self.path / 'bin'
        binaries.mkdir()
        commands = self.path / 'host-commands'
        for name in ('systemctl', 'docker'):
            stub = binaries / name
            stub.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$APEX_INSTALL_TEST_COMMANDS"\n')
            stub.chmod(0o700)
        with deployment_lock(state), patch.dict(os.environ, {
            'PATH': str(binaries) + os.pathsep + os.environ['PATH'],
            'XDG_CONFIG_HOME': str(self.path / 'config'), 'APEX_INSTALL_TEST_COMMANDS': str(commands)}):
            result = subprocess.run(['bash', str(installer), '--docker-context', 'synthetic'], text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('deployment operation is running', result.stderr)
        self.assertEqual(installed.read_text(), 'preserve running controller')
        self.assertNotIn('restart', commands.read_text())


if __name__ == '__main__':
    unittest.main()
