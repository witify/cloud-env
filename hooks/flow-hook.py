#!/usr/bin/env python3
"""Hook dispatcher of the cloud VM: hands a Claude Code hook event to the common part of the flow.

    python3 -I flow-hook.py <EventName>      (the hook JSON on stdin)

Claude Code reads its hooks from the VM's settings at session start, so the registration lives here
(config/claude-settings.json), for a fixed list of events. The logic lives in Navark: the common part of
every flow, which no flow can change, is downloaded with the flow into .scratch/flow/core/, and its hook
for an event is the executable file .scratch/flow/core/hooks/<EventName> (README, "The flow").

When that file exists, is a regular file (not a link) and is executable, it runs from the project root
with the same stdin, with a hard time limit per event. Anything else does nothing. Never PreToolUse or
PostToolUse: the guard is the only hook on tools.

It must never change the session, whatever the script does: it always exits 0 and prints nothing, on
stdout or stderr (a SessionStart hook's stdout becomes the agent's context, a Stop hook that exits 2
keeps the agent going). The script's own output is discarded. A failure or a timeout is one line in
/var/log/cloud-env/flow-hooks.log. A script that needs longer than its limit puts that work in the
background, detached from its stdin, stdout and stderr: on a timeout its whole process group is killed."""
import datetime
import glob
import os
import pathlib
import signal
import stat
import subprocess
import sys
import tempfile

# Seconds the script may run. Claude Code gives SessionEnd hooks 1.5 s in all (hooks docs, SessionEnd);
# the others get the `timeout` of config/claude-settings.json (15 s), above these limits.
LIMITS = {
    'SessionStart': 10,
    'Stop': 10,
    'SubagentStart': 10,
    'SubagentStop': 10,
    'PreCompact': 10,
    'PostCompact': 10,
    'SessionEnd': 1,
}
STATE_DIR = '/var/lib/cloud-env'
LOG_FILE = pathlib.Path(os.environ.get('CLOUD_ENV_LOG_DIR') or '/var/log/cloud-env') / 'flow-hooks.log'


def log(event, message):
    try:
        moment = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        with open(LOG_FILE, 'a') as file:
            file.write(f'{moment} {event} {message}\n')
    except OSError:
        pass


def project_root():
    """$CLAUDE_PROJECT_DIR, else what lib.sh finds: the root saved by setup.sh, else /home/user/*/artisan."""
    if os.environ.get('CLAUDE_PROJECT_DIR'):
        return pathlib.Path(os.environ['CLAUDE_PROJECT_DIR'])
    try:
        saved = pathlib.Path(STATE_DIR, 'root-dir').read_text().strip()
        if saved:
            return pathlib.Path(saved)
    except OSError:
        pass
    for candidate in sorted(glob.glob('/home/user/*/artisan')):
        if os.path.isfile(candidate):
            return pathlib.Path(candidate).parent
    return None


def run(event, payload):
    root = project_root()
    if root is None:
        return
    script = root / '.scratch' / 'flow' / 'core' / 'hooks' / event
    try:
        mode = script.lstat().st_mode
    except OSError:
        return
    if not stat.S_ISREG(mode) or not os.access(script, os.X_OK):
        return

    with tempfile.TemporaryFile() as stdin:
        stdin.write(payload)
        stdin.seek(0)
        process = subprocess.Popen([str(script)], cwd=root, stdin=stdin, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, start_new_session=True)
        try:
            status = process.wait(timeout=LIMITS[event])
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except OSError:
                pass
            process.wait()
            log(event, f'timeout: killed after {LIMITS[event]} s')
            return
    if status != 0:
        log(event, f'failed: exit {status}')


def main():
    event = sys.argv[1] if len(sys.argv) == 2 else ''
    if event not in LIMITS:
        return
    try:
        payload = sys.stdin.buffer.read()
    except (OSError, ValueError):
        payload = b''
    try:
        run(event, payload)
    except Exception as error:  # noqa: BLE001 - nothing may reach the session
        log(event, f'failed: {type(error).__name__}: {error}')


if __name__ == '__main__':
    try:
        main()
    except BaseException:  # noqa: BLE001
        pass
    os._exit(0)
