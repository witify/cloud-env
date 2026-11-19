"""Run with: python3 -m unittest discover tests"""
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
DISPATCHER = ROOT / 'hooks' / 'flow-hook.py'
SETTINGS = ROOT / 'config' / 'claude-settings.json'
EVENTS = ['SessionStart', 'Stop', 'SubagentStart', 'SubagentStop', 'PreCompact', 'PostCompact', 'SessionEnd']
PAYLOAD = '{"session_id": "abc", "hook_event_name": "Stop", "text": "caf\\u00e9 \' \\" $HOME"}\n'


class FlowHookTest(unittest.TestCase):
    def setUp(self):
        self.project = pathlib.Path(tempfile.mkdtemp())
        self.logs = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.project)
        self.addCleanup(shutil.rmtree, self.logs)
        self.hooks = self.project / '.scratch' / 'flow' / 'core' / 'hooks'
        self.hooks.mkdir(parents=True)

    def script(self, event, body, executable=True):
        path = self.hooks / event
        path.write_text('#!/bin/sh\n' + body)
        path.chmod(0o755 if executable else 0o644)
        return path

    def dispatch(self, *arguments, payload=PAYLOAD):
        environment = {'PATH': os.environ['PATH'], 'CLAUDE_PROJECT_DIR': str(self.project), 'CLOUD_ENV_LOG_DIR': str(self.logs)}
        began = time.monotonic()
        result = subprocess.run(['python3', '-I', str(DISPATCHER), *arguments], input=payload.encode(),
                                capture_output=True, env=environment, cwd='/', timeout=30)
        return result, time.monotonic() - began

    def log_lines(self):
        path = self.logs / 'flow-hooks.log'
        return path.read_text().splitlines() if path.exists() else []

    def assertSilent(self, result):
        self.assertEqual(0, result.returncode)
        self.assertEqual(b'', result.stdout)
        self.assertEqual(b'', result.stderr)

    def test_no_script_does_nothing(self):
        for event in EVENTS:
            result, _ = self.dispatch(event)
            self.assertSilent(result)
        self.assertEqual([], self.log_lines())

    def test_a_script_gets_the_exact_stdin_and_runs_from_the_project_root(self):
        self.script('Stop', 'cat > received; pwd > where\n')
        result, _ = self.dispatch('Stop')
        self.assertSilent(result)
        self.assertEqual(PAYLOAD, (self.project / 'received').read_text())
        self.assertEqual(self.project.resolve(), pathlib.Path((self.project / 'where').read_text().strip()).resolve())
        self.assertEqual([], self.log_lines())

    def test_a_failing_and_talkative_script_changes_nothing_and_is_logged(self):
        self.script('SessionStart', 'echo context for the agent; echo oops >&2; exit 2\n')
        result, _ = self.dispatch('SessionStart')
        self.assertSilent(result)
        self.assertEqual(1, len(self.log_lines()))
        self.assertIn('SessionStart failed: exit 2', self.log_lines()[0])

    def test_a_script_that_hangs_is_killed_at_the_limit_and_logged(self):
        marker = self.project / 'still-running'
        self.script('SessionEnd', f'sleep 30; touch {marker}\n')
        result, elapsed = self.dispatch('SessionEnd')
        self.assertSilent(result)
        self.assertLess(elapsed, 1.5)
        self.assertIn('SessionEnd timeout: killed after 1 s', self.log_lines()[0])
        time.sleep(0.2)
        self.assertFalse(marker.exists())

    def test_a_background_child_does_not_hold_the_hook(self):
        self.script('Stop', 'sleep 5 </dev/null >/dev/null 2>&1 &\nexit 0\n')
        result, elapsed = self.dispatch('Stop')
        self.assertSilent(result)
        self.assertLess(elapsed, 3)

    def test_a_file_that_is_not_executable_or_not_regular_is_ignored(self):
        self.script('Stop', 'touch ran\n', executable=False)
        result, _ = self.dispatch('Stop')
        self.assertSilent(result)
        self.assertFalse((self.project / 'ran').exists())

        target = self.script('elsewhere', 'touch ran\n')
        (self.hooks / 'SubagentStop').symlink_to(target)
        (self.hooks / 'PreCompact').mkdir()
        for event in ('SubagentStop', 'PreCompact'):
            result, _ = self.dispatch(event)
            self.assertSilent(result)
        self.assertFalse((self.project / 'ran').exists())
        self.assertEqual([], self.log_lines())

    def test_an_event_outside_the_list_or_a_path_trick_is_ignored(self):
        for name in ('PreToolUse', 'PostToolUse', 'Notification', 'stop', 'elsewhere'):
            self.script(name, 'touch ran\n')
        outside = self.project / 'outside'
        outside.write_text('#!/bin/sh\ntouch ran\n')
        outside.chmod(0o755)

        for arguments in (['PreToolUse'], ['PostToolUse'], ['Notification'], ['stop'], ['elsewhere'],
                          ['../outside'], ['../../../../outside'], [str(outside)], ['Stop/../elsewhere'],
                          [], ['Stop', 'extra'], ['']):
            result, _ = self.dispatch(*arguments)
            self.assertSilent(result)
        self.assertFalse((self.project / 'ran').exists())
        self.assertEqual([], self.log_lines())

    def test_no_project_and_no_log_folder_still_exit_0_silently(self):
        environment = {'PATH': os.environ['PATH'], 'CLAUDE_PROJECT_DIR': '/nonexistent', 'CLOUD_ENV_LOG_DIR': '/nonexistent'}
        result = subprocess.run(['python3', '-I', str(DISPATCHER), 'Stop'], input=b'not json', capture_output=True, env=environment)
        self.assertSilent(result)

    def test_the_settings_register_exactly_the_seven_events_after_session_start(self):
        hooks = json.loads(SETTINGS.read_text())['hooks']
        registered = {event: [h['command'] for group in groups for h in group['hooks'] if 'flow-hook.py' in h['command']]
                      for event, groups in hooks.items()}
        self.assertEqual({event: [f'python3 -I __CLOUD_DIR__/hooks/flow-hook.py {event}'] for event in EVENTS},
                         {event: commands for event, commands in registered.items() if commands})
        self.assertIn('session-start.sh', hooks['SessionStart'][0]['hooks'][0]['command'])
        self.assertNotIn('timeout', hooks['SessionEnd'][0]['hooks'][0])
        self.assertTrue(all(group.get('matcher') is None for event in EVENTS for group in hooks[event] if 'flow-hook.py' in group['hooks'][0]['command']))


if __name__ == '__main__':
    unittest.main()
