#!/usr/bin/env bash
# Install an independent host process; no application deploy or Docker socket mount.
set -euo pipefail
control_repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
exec python3 - "$control_repo" "$@" <<'PY'
import argparse
import fcntl
import os
from pathlib import Path
import subprocess
import sys
import tempfile

if sys.version_info < (3, 10):
    raise SystemExit('Python 3.10 or newer is required')
p = argparse.ArgumentParser(description='Install owner-only Telegram remote controls as a systemd user service')
p.add_argument('repo', type=Path)
p.add_argument('--dry-run', action='store_true')
p.add_argument('--compose-file', action='append', type=Path)
p.add_argument('--project-name', default=os.environ.get('COMPOSE_PROJECT_NAME'))
p.add_argument('--docker-context', default=os.environ.get('DOCKER_CONTEXT'))
a = p.parse_args()
repo = a.repo.resolve()
state = repo / '.apex-updater'
if a.compose_file is None and os.environ.get('COMPOSE_FILE'):
    a.compose_file = [Path(v) for v in os.environ['COMPOSE_FILE'].split(os.environ.get('COMPOSE_PATH_SEPARATOR', os.pathsep)) if v]
if not a.dry_run and not a.docker_context:
    if os.environ.get('DOCKER_HOST'):
        raise SystemExit('Use a named Docker context and pass --docker-context; session-only DOCKER_HOST is unsupported')
    a.docker_context = subprocess.run(['docker', 'context', 'show'], check=True, text=True, stdout=subprocess.PIPE).stdout.strip()
    if not a.docker_context:
        raise SystemExit('Cannot identify the installation Docker context')
command = [sys.executable, str(state / 'telegram_control.py'), '--repo', str(repo), '--state-dir', str(state)]
for file in a.compose_file or []:
    command += ['--compose-file', str(file.resolve())]
if a.project_name:
    command += ['--project-name', a.project_name]
if a.docker_context:
    command += ['--docker-context', a.docker_context]

def quote(value):
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%').replace('$', '$$') + '"'

unit = '''[Unit]
Description=Apex Health owner Telegram remote controls
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
UMask=0077
NoNewPrivileges=yes
Restart=always
RestartSec=10
TimeoutStopSec=20
Environment=PYTHONUNBUFFERED=1
ExecStart={command}

[Install]
WantedBy=default.target
'''.format(command=' '.join(map(quote, command)))
if a.dry_run:
    print(unit)
    raise SystemExit(0)
subprocess.run([sys.executable, str(repo / 'infra/telegram_control.py'), '--repo', str(repo), '--check-config'], check=True)
subprocess.run(['systemctl', '--user', 'show-environment'], check=True, stdout=subprocess.DEVNULL)
subprocess.run(['docker', '--context', a.docker_context, 'info'], check=True, stdout=subprocess.DEVNULL)
state.mkdir(mode=0o700, parents=True, exist_ok=True)
os.chmod(state, 0o700)
# Keep the lock through copying and systemd restart: never kill a controller
# whose background operation is stopping, backing up or migrating the app.
install_lock = (state / 'update.lock').open('a')
try:
    fcntl.flock(install_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    raise SystemExit('A deployment operation is running; reinstall controls after it finishes') from None
units = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config'))) / 'systemd/user'
units.mkdir(parents=True, exist_ok=True)

def write(path, text, mode=0o600):
    fd, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, 'w') as output:
            output.write(text)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)

write(state / 'telegram_control.py', (repo / 'infra/telegram_control.py').read_text(), 0o700)
# Independent dependency: installing controls does not replace a running timer's updater.
write(state / 'telegram_updater.py', (repo / 'infra/auto_update.py').read_text())
write(units / 'apex-health-telegram.service', unit)
subprocess.run(['systemctl', '--user', 'daemon-reload'], check=True)
subprocess.run(['systemctl', '--user', 'enable', 'apex-health-telegram.service'], check=True)
subprocess.run(['systemctl', '--user', 'restart', 'apex-health-telegram.service'], check=True)
print('Installed Telegram control service. Send /help in the configured private owner chat.')
print('Logs: journalctl --user -u apex-health-telegram.service')
print('Enable linger for reboot/logout survival: sudo loginctl enable-linger YOUR_USER')
PY
