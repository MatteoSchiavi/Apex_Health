#!/usr/bin/env python3
"""Owner-only, outbound-polling host control plane. No Telegram text becomes shell code."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import time
import urllib.request

try:
    from .auto_update import Updater, Docker, UpdateError, BACKUP, BACKUP_READY, write_json
except ImportError:
    try:
        from telegram_updater import Updater, Docker, UpdateError, BACKUP, BACKUP_READY, write_json
    except ImportError:
        from auto_update import Updater, Docker, UpdateError, BACKUP, BACKUP_READY, write_json

HELP = """Apex Health remote controls
/status — deployment, containers and update state
/health — API, database, Redis and worker probes
/resources — host memory, disk and load
/logs — last 15 sanitized operational events
/jobs — worker and queue activity counts
/sync garmin|whoop|oura|strava|coros|technogym — sync active connected accounts
/update — fetch and deploy the latest tested release now
/verify — check release compatibility without deploying or resuming
/update retry — retry a previously failed release (confirmation)
/backup — create and verify an encrypted database backup
/restart api|worker|app — restart application services (confirmation)
/pause — pause automatic updates
/resume — adopt a healthy deployment and resume updates (confirmation)
/rollback — restore previous image only if schema matches (confirmation)
/confirm CODE — confirm within 60 seconds
/cancel — cancel a pending confirmation
/help — show these controls
Updates retain backup, health and migration recovery safeguards."""

LOGS = """import asyncio, json
from app.core.redis import get_redis
async def main():
 r=get_redis()
 try:
  rows=await r.lrange('apex:operational:logs',0,14)
  print(json.dumps([json.loads(x) for x in rows]))
 finally: await r.aclose()
asyncio.run(main())
"""

JOBS = """import json
from app.tasks.celery_app import celery_app
i=celery_app.control.inspect(timeout=3)
active=i.active() or {}
reserved=i.reserved() or {}
scheduled=i.scheduled() or {}
print(json.dumps({'responding_workers':len(active),'active':sum(map(len,active.values())),
 'reserved':sum(map(len,reserved.values())),'scheduled':sum(map(len,scheduled.values()))}))
"""

SYNC = """import asyncio, json, os
from app.tasks.provider_sync import enqueue_active
result=asyncio.run(enqueue_active(os.environ['APEX_SYNC_PROVIDER']))
print(json.dumps({'queued_accounts':len(result)}))
"""


def credentials(path):
    """Read only three literal dotenv settings; never source shell configuration."""
    allowed = {'OWNER_TELEGRAM_BOT_TOKEN', 'OWNER_TELEGRAM_CHAT_ID', 'OWNER_TELEGRAM_USER_ID'}
    values = {}
    import shlex
    for line in path.read_text().splitlines():
        key, sep, value = line.removeprefix('export ').partition('=')
        key = key.strip()
        if not sep or key not in allowed:
            continue
        parts = shlex.split(value, comments=True)
        if len(parts) > 1:
            raise ValueError('Telegram settings must be literal single values')
        values[key] = parts[0] if parts else ''
    values.update({k: os.environ[k] for k in allowed if k in os.environ})
    token = values.get('OWNER_TELEGRAM_BOT_TOKEN', '')
    chat = values.get('OWNER_TELEGRAM_CHAT_ID', '')
    user = values.get('OWNER_TELEGRAM_USER_ID') or chat
    if not re.fullmatch(r'[0-9]+:[A-Za-z0-9_-]+', token) or not chat.isdecimal() or not user.isdecimal() or int(chat) <= 0 or int(chat) != int(user):
        raise ValueError('Configure a bot token and matching positive private owner chat/user IDs')
    return token, int(chat), int(user)


class Telegram:
    def __init__(self, token, chat):
        self.token, self.chat = token, chat

    def request(self, method, payload):
        request = urllib.request.Request('https://api.telegram.org/bot' + self.token + '/' + method,
            data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
        # No request URLs or exceptions are logged: the URL contains a credential.
        with urllib.request.urlopen(request, timeout=35) as response:
            body = json.load(response)
        if body.get('ok') is not True:
            raise RuntimeError('Telegram request failed')
        return body['result']

    def send(self, text):
        return self.request('sendMessage', {'chat_id': self.chat, 'text': text[:3900], 'disable_web_page_preview': True})


@contextmanager
def deployment_lock(directory):
    with (directory / 'update.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise UpdateError('Another deployment operation is running') from None
        yield


def safe_logs(raw):
    rows = json.loads(raw)
    output = []
    for row in rows[:15]:
        if not isinstance(row, dict):
            continue
        fields = [str(row.get(k, '')) for k in ('timestamp', 'level', 'source', 'event')]
        if all(re.fullmatch(r'[A-Za-z0-9_.:+ -]{0,80}', v) for v in fields):
            output.append(' · '.join(fields))
    return '\n'.join(output) or 'No operational events available.'


class Controller:
    def __init__(self, factory, directory):
        self.factory, self.directory = factory, directory

    def status(self):
        updater = self.factory()
        updater.docker.timeout = 10
        state = updater.state
        revision = (state.get('current') or {}).get('revision')
        actual_revision = None
        try:
            _, labels = updater.image_info(updater.service_image('api'))
            actual_revision = labels.get('org.opencontainers.image.revision')
        except (UpdateError, OSError, subprocess.TimeoutExpired, ValueError, KeyError):
            pass
        revision = revision[:12] if isinstance(revision, str) and re.fullmatch(r'[0-9a-f]{40}', revision) else 'unrecorded'
        actual_revision = actual_revision[:12] if isinstance(actual_revision, str) and re.fullmatch(r'[0-9a-f]{40}', actual_revision) else 'unavailable'
        phase = state.get('in_progress')
        phase = phase if phase in {'stopping', 'backup', 'migrating', 'starting', 'rollback', 'manual_recovery'} else 'none'
        report = [f'Running revision: {actual_revision}', f'Updater recorded revision: {revision}', f'Update permission: {"paused" if state.get("paused") else "allowed"}',
            f'Deployment phase: {phase}', f'Failed release blocked: {bool(state.get("failed_image"))}']
        for service in ('api', 'worker', 'db', 'redis'):
            try:
                ids = updater.compose('ps', '--status', 'running', '-q', service)
                report.append(f'{service}: {"running" if ids else "stopped"}')
            except (UpdateError, OSError, subprocess.TimeoutExpired):
                report.append(f'{service}: unavailable')
        return '\n'.join(report)

    def resources(self):
        disk = shutil.disk_usage(self.directory)
        load = ', '.join(f'{n:.2f}' for n in os.getloadavg())
        memory = {}
        for line in Path('/proc/meminfo').read_text().splitlines():
            key, _, value = line.partition(':')
            if key in {'MemTotal', 'MemAvailable'}:
                memory[key] = int(value.split()[0])
        total = memory.get('MemTotal', 0)
        used = total - memory.get('MemAvailable', 0)
        return (f'Host load (1/5/15 min): {load}\nHost RAM: {used/1024:.0f}/{total/1024:.0f} MiB\n'
            f'Deployment filesystem: {disk.used/2**30:.1f}/{disk.total/2**30:.1f} GiB ({disk.used/disk.total:.0%})')

    def execute(self, command):
        action, *args = command.split()
        if action == 'status':
            return self.status()
        if action == 'resources':
            return self.resources()
        updater = self.factory()
        if action == 'health':
            updater.probe()
            return 'Healthy: API, database, Redis and worker round trip passed.'
        if action == 'verify':
            verified = updater.verify()
            recovery = ' Running schema requires manual recovery before resumption.' if verified['manual_recovery_required'] else ''
            return f'Published release {verified["revision"][:12]} verified. Migration head: {verified["migration_head"]}. Deployment required: {verified["deployment_required"]}.{recovery} Update permission is unchanged.'
        if action == 'logs':
            return safe_logs(updater.compose('exec', '-T', 'api', 'python', '-c', LOGS))
        if action == 'jobs':
            counts = json.loads(updater.compose('exec', '-T', 'api', 'python', '-c', JOBS).splitlines()[-1])
            return '\n'.join(f'{key.replace("_", " ")}: {int(counts[key])}' for key in ('responding_workers', 'active', 'reserved', 'scheduled'))
        with deployment_lock(self.directory):
            # Reload state after taking the same lock used by automatic updates.
            updater = self.factory()
            if action == 'pause':
                updater.state['paused'] = True
                updater.save()
                return 'Automatic updates paused. Application services remain running.'
            if action == 'resume':
                updater.resume()
                return 'Healthy deployment adopted; automatic updates resumed.'
            if action == 'update':
                updater.docker.timeout = 1800
                updater.update(retry=args == ['retry'])
                return 'Update check completed.\n' + self.status()
            if action == 'rollback':
                updater.rollback()
                return 'Previous image restored. Updates paused; use /resume after reviewing health.'
            if updater.state.get('in_progress'):
                raise UpdateError('Interrupted deployment requires manual recovery')
            if action == 'sync' and args in [[p] for p in ('garmin', 'whoop', 'oura', 'strava', 'coros', 'technogym')]:
                raw = updater.compose('exec', '-T', '-e', 'APEX_SYNC_PROVIDER=' + args[0], 'api', 'python', '-c', SYNC)
                count = int(json.loads(raw.splitlines()[-1])['queued_accounts'])
                return f'{args[0]} sync queued for {count} active connected accounts. /jobs shows worker activity.'
            if action == 'restart':
                services = {'api': ['api'], 'worker': ['worker'], 'app': ['api', 'worker']}[args[0]]
                # Restart existing containers; never switch the updater-selected image.
                updater.compose('restart', '-t', '60', *services)
                updater.probe()
                return 'Restart completed; API and worker health verified.'
            if action == 'backup':
                updater.docker.timeout = 1800
                updater.compose('exec', '-T', 'api', 'python', '-c', BACKUP_READY)
                name = 'telegram-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + secrets.token_hex(4)
                raw = updater.compose('exec', '-T', '-e', 'APEX_DEPLOYMENT=' + name, 'api', 'python', '-c', BACKUP)
                artifact = json.loads(raw.splitlines()[-1])
                if not artifact.get('size') or not re.fullmatch(r'[a-f0-9]{64}', str(artifact.get('sha256', ''))):
                    raise UpdateError('Backup verification failed')
                return f'Encrypted backup created and verified ({int(artifact["size"])} bytes). Retained on server.'
            raise ValueError('Unsupported command')


class Bot:
    def __init__(self, telegram, owner_id, controller, directory, clock=time.time):
        self.telegram, self.owner_id, self.controller, self.directory, self.clock = telegram, owner_id, controller, directory, clock
        self.path = directory / 'telegram-state.json'
        self.state = json.loads(self.path.read_text()) if self.path.exists() else {'offset': None, 'outbox': []}
        self.confirmation = None
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.future = None
        self.username = ''

    def save(self):
        write_json(self.path, self.state)

    def tell(self, text):
        # Persistent bounded outbox; telemetry never contains raw logs or exceptions.
        self.state.setdefault('outbox', []).append(text[:3900])
        self.state['outbox'] = self.state['outbox'][-100:]
        self.save()

    def flush(self):
        while self.state.get('outbox'):
            self.telegram.send(self.state['outbox'][0])
            self.state['outbox'].pop(0)
            self.save()

    def accept(self, update):
        ident = update.get('update_id')
        if not isinstance(ident, int) or ident < (self.state.get('offset') or 0):
            return
        # Commit cursor before any action: replay cannot restart/update twice.
        self.state['offset'] = ident + 1
        self.save()
        message = update.get('message', {})
        if (message.get('chat', {}).get('type') != 'private' or message.get('chat', {}).get('id') != self.owner_id
            or message.get('from', {}).get('id') != self.owner_id or message.get('from', {}).get('is_bot')
            or 'forward_origin' in message or 'forward_date' in message):
            return
        stamp = message.get('date')
        if not isinstance(stamp, int) or not 0 <= self.clock() - stamp <= 120:
            return
        text = message.get('text', '')
        if not isinstance(text, str) or not text.startswith('/') or len(text) > 100:
            return
        parts = text.strip().split()
        name, _, target = parts[0][1:].partition('@')
        if target and target.lower() != self.username.lower():
            return
        command = ' '.join([name.lower(), *parts[1:]])
        if command in {'start', 'help'}:
            self.tell(HELP)
            return
        if command == 'cancel':
            self.confirmation = None
            self.tell('Pending confirmation canceled. A running operation cannot be canceled.')
            return
        if command.startswith('confirm '):
            pending = self.confirmation
            self.confirmation = None
            if not pending or self.clock() > pending['expires'] or command != 'confirm ' + pending['token']:
                self.tell('Confirmation invalid or expired. Request the command again.')
                return
            command = pending['command']
        elif command in {'restart api', 'restart worker', 'restart app', 'rollback', 'resume', 'update retry'}:
            token = secrets.token_hex(4)
            self.confirmation = {'token': token, 'command': command, 'expires': self.clock() + 60}
            self.tell(f'Confirm /{command} within 60 seconds: /confirm {token}\n/cancel to dismiss.')
            return
        allowed = {'status', 'health', 'resources', 'logs', 'jobs', 'verify', 'update', 'update retry', 'backup', 'pause', 'resume', 'rollback', 'restart api', 'restart worker', 'restart app'} | {'sync ' + p for p in ('garmin', 'whoop', 'oura', 'strava', 'coros', 'technogym')}
        if command not in allowed:
            self.tell('Unknown command. Use /help. /restart requires api, worker or app.')
            return
        if self.future:
            if command == 'status':
                phase = self.controller.factory().state.get('in_progress')
                phase = phase if phase in {'stopping', 'backup', 'migrating', 'starting', 'rollback', 'manual_recovery'} else 'none'
                self.tell('Running /' + self.state.get('pending_command', 'operation') + '. Deployment phase: ' + phase)
                return
            if command == 'resources':
                self.tell(self.controller.resources())
                return
            self.tell('An operation is running. I will notify you when it finishes. /help remains available.')
            return
        self.state['pending_command'] = command
        self.save()
        self.tell(f'Accepted /{command}. I will send the result.')
        self.future = self.executor.submit(self.controller.execute, command)

    def finish(self):
        if self.future and self.future.done():
            command = self.state.pop('pending_command', 'operation')
            try:
                result = self.future.result()
            except Exception:
                result = 'Operation failed or deployment is busy. Use /status and /health. For recovery inspect the private host journal; no raw errors are sent to Telegram.'
            self.future = None
            self.tell(f'/{command}: {result}')

    def monitor(self):
        if self.future:
            return
        updater = self.controller.factory()
        fingerprint = {key: updater.state.get(key) for key in ('paused', 'in_progress', 'failed_image', 'updated_at')}
        fingerprint['revision'] = (updater.state.get('current') or {}).get('revision')
        previous = self.state.get('deployment')
        if previous is not None and fingerprint != previous:
            # Fixed summary avoids propagating updater state paths or error bodies.
            self.tell('Deployment state changed.\n' + self.controller.status())
        self.state['deployment'] = fingerprint
        if updater.state.get('in_progress'):
            self.save()
            return  # Expected maintenance downtime should not trigger health alerts.
        try:
            updater.probe()
            healthy = True
        except Exception:
            healthy = False
        previous_health = self.state.get('healthy')
        if not healthy and previous_health is not False:
            self.tell('Service health check failed. Use /status and /health; remote controls remain available.')
        elif healthy and previous_health is False:
            self.tell('Service recovered: API, database, Redis and worker checks passed.')
        self.state['healthy'] = healthy
        disk = shutil.disk_usage(self.directory)
        full = disk.used / disk.total >= .9
        if full and not self.state.get('disk_warning'):
            self.tell('Deployment disk usage is above 90%. Review host storage and backup retention.')
        elif not full and self.state.get('disk_warning'):
            self.tell('Deployment disk usage is below 90% again.')
        self.state['disk_warning'] = full
        self.save()

    def run(self):
        identity = self.telegram.request('getMe', {})
        self.username = identity['username']
        if self.state.get('bot_id') != identity['id'] or self.state.get('offset') is None:
            backlog = self.telegram.request('getUpdates', {'offset': -1, 'limit': 1, 'timeout': 0, 'allowed_updates': ['message']})
            self.state['offset'] = backlog[-1]['update_id'] + 1 if backlog else 0
            self.state['bot_id'] = identity['id']
            self.save()
        if self.state.pop('pending_command', None):
            self.tell('Controller restarted during an operation. It will not be replayed. Inspect /status and /health before retrying.')
        self.tell('Apex Health remote control is online. /help for commands.')
        # Menu failure must not disable polling when a bot has restricted API rights.
        try:
            self.telegram.request('setMyCommands', {'scope': {'type': 'chat', 'chat_id': self.owner_id}, 'commands': [
                {'command': c, 'description': d} for c, d in [('status', 'Service and deployment status'), ('health', 'Probe all services'),
                ('update', 'Deploy latest tested release'), ('verify', 'Verify release without deployment'), ('backup', 'Create encrypted backup'), ('resources', 'Host resources'),
                ('logs', 'Sanitized operational events'), ('jobs', 'Worker activity counts'), ('sync', 'Queue provider synchronization'), ('restart', 'Restart api, worker or app'), ('pause', 'Pause automatic updates'),
                ('resume', 'Resume after health verification'), ('rollback', 'Restore prior compatible image'), ('help', 'All remote controls')]]})
        except Exception:
            pass
        next_monitor = 0
        while True:
            try:
                self.finish()
                self.flush()
                if self.clock() >= next_monitor:
                    next_monitor = self.clock() + 60
                    self.monitor()
                    self.flush()
                updates = self.telegram.request('getUpdates', {'offset': self.state['offset'], 'timeout': 20, 'limit': 20, 'allowed_updates': ['message']})
                for update in updates:
                    self.accept(update)
            except Exception:
                # Includes transport outages: retained replies retry without logging credentials.
                time.sleep(5)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--state-dir', type=Path)
    parser.add_argument('--compose-file', action='append', type=Path)
    parser.add_argument('--project-name')
    parser.add_argument('--docker-context')
    parser.add_argument('--check-config', action='store_true')
    args = parser.parse_args(argv)
    directory = (args.state_dir or args.repo / '.apex-updater').resolve()
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(directory, 0o700)
    token, chat, owner = credentials(args.repo / '.env')
    if args.check_config:
        print('Private owner Telegram configuration is valid.')
        return
    # Only one getUpdates consumer per installation; lock remains held for daemon lifetime.
    with (directory / 'telegram.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        def factory():
            return Updater(args.repo, directory, compose_files=args.compose_file, project=args.project_name,
                docker=Docker(args.docker_context, timeout=90))
        Bot(Telegram(token, chat), owner, Controller(factory, directory), directory).run()


if __name__ == '__main__':
    try:
        main()
    except Exception:
        raise SystemExit('Remote control stopped. Check configuration, Docker and Telegram connectivity; credentials are never logged.') from None
