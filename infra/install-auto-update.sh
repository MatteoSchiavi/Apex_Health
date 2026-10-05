#!/usr/bin/env bash
# Install an outbound-only systemd user timer for the existing Compose stack.
set -euo pipefail
updater_repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
exec python3 - "$updater_repo" "$@" <<'PY'
import argparse
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile

if sys.version_info < (3, 10):
    raise SystemExit('Python 3.10 or newer is required')

parser = argparse.ArgumentParser(description='Verify the first update, then install a five-minute systemd user timer')
parser.add_argument('repo', type=Path)
parser.add_argument('--dry-run', action='store_true', help='Print the units without deploying or writing files')
parser.add_argument('--compose-file', action='append', type=Path)
parser.add_argument('--project-name')
args = parser.parse_args()
repo = args.repo.resolve()
state = repo / '.apex-updater'
source = repo / 'infra/auto_update.py'
installed = state / 'auto_update.py'
command = [sys.executable, str(installed), 'update', '--repo', str(repo), '--state-dir', str(state)]
for file in args.compose_file or []:
    command += ['--compose-file', str(file.resolve())]
if args.project_name:
    command += ['--project-name', args.project_name]

def unit_argument(value):
    # systemd parses quoted arguments and expands %/$, even without a shell.
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%').replace('$', '$$') + '"'

service = '''[Unit]
Description=Update Apex Health from tested GitHub main images

[Service]
Type=oneshot
UMask=0077
TimeoutStartSec=1h
ExecStart={command}
'''.format(command=' '.join(map(unit_argument, command)))
timer = '''[Unit]
Description=Check for tested Apex Health updates every five minutes

[Timer]
OnBootSec=2min
OnUnitInactiveSec=5min
RandomizedDelaySec=30s
Unit=apex-health-update.service

[Install]
WantedBy=timers.target
'''
if args.dry_run:
    print('# apex-health-update.service\n' + service + '\n# apex-health-update.timer\n' + timer)
    raise SystemExit(0)

subprocess.run(['systemctl', '--user', 'show-environment'], stdout=subprocess.DEVNULL, check=True)
subprocess.run(['docker', 'compose', 'version'], check=True)
subprocess.run(['docker', 'info'], stdout=subprocess.DEVNULL, check=True)
# Verify registry access, the healthy existing stack, encryption and the first
# deployment before installing a recurring job. Do not log .env or keys.
first = [sys.executable, str(source), *command[2:]]
subprocess.run(first, check=True)

def atomic_write(path, contents, mode=0o600):
    fd, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, 'w') as output:
            output.write(contents)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)

units = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config'))) / 'systemd/user'
units.mkdir(parents=True, exist_ok=True)
atomic_write(installed, source.read_text(), 0o700)
atomic_write(units / 'apex-health-update.service', service)
atomic_write(units / 'apex-health-update.timer', timer)
subprocess.run(['systemctl', '--user', 'daemon-reload'], check=True)
subprocess.run(['systemctl', '--user', 'enable', '--now', 'apex-health-update.timer'], check=True)
print('Installed: checks every five minutes. Logs: journalctl --user -u apex-health-update.service')
print('For updates after logout/reboot, enable linger once: sudo loginctl enable-linger ' + shlex.quote(os.environ.get('USER', 'YOUR_USER')))
PY
