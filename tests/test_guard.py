"""Run with: python3 -m unittest discover tests"""
import json
import os
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
GUARD = ROOT / 'hooks' / 'guard-bash.py'
PRE_PUSH = ROOT / 'git-hooks' / 'pre-push'
NO_SHA = '0' * 40


def guard_denies(tool, tool_input, cwd, env=None):
    event = {'tool_name': tool, 'tool_input': tool_input, 'cwd': cwd}
    result = subprocess.run(['python3', '-I', str(GUARD)], input=json.dumps(event), capture_output=True, text=True, check=True, env=env)
    return 'deny' in result.stdout


# Answers `gh api <path>` from two JSON files, the way GitHub would.
FAKE_GH = """#!/usr/bin/env python3
import os, sys
path = sys.argv[2]
name = 'checks.json' if '/check-runs' in path else 'pull.json'
print(open(os.path.join(os.environ['FAKE_GH_DIR'], name)).read())
"""
SHA = 'a' * 40


class GuardTest(unittest.TestCase):
    DENIED = [
        'gh pr merge 1',
        'gh api repos/o/r/merges -f base=dev -f head=x',
        'gh api repos/o/r/merges --raw-field=base=dev',
        'gh api repos/o/r/merges --field=base=dev',
        'gh api repos/o/r/merges -fbase=dev',
        'gh api repos/o/r/merges -if base=dev',
        'gh api repos/o/r/merges --input=body.json',
        'gh api repos/o/r/merges --input body.json',
        'gh api repos/o/r/git/refs --raw-field=ref=refs/heads/dev',
        "gh api 'repos/o/r/pulls/1/merge?a=1&b=2' -X PUT",
        'gh api repos/o/r/pulls/1/merge -iXPUT',
        'gh api repos/o/r/pulls/1/merge --method=PUT',
        'gh api -X PUT repos/o/r/contents/a.txt -f content=x',
        'x=$(gh api repos/o/r/merges -f a=b)',
        'bash -c "gh api repos/o/r/merges -f a=b"',
        '/usr/bin/gh api repos/o/r/merges -f a=b',
        'git push origin dev',
        'git push origin HEAD:main',
        'git push --no-verify origin feat/x',
        'git push --delete origin feat/x',
        'git push origin :feat/x',
        'git -c core.hooksPath=/dev/null push origin feat/x',
        'git -c core.hooksPath=/dev/null config core.hooksPath',
        'git config core.hooksPath /dev/null',
        'git config core.hooksPath get',
        'git config core.hooksPath core.hooksPath',
        "git config core.hooksPath ';'",
        'git config core.hooksPath \\;',
        'git config core.hooksPath >/tmp/x /dev/null',
        'git config core.hooksPath </dev/null /dev/null',
        'git config --system core.hooksPath >/tmp/x /dev/null',
        'git config --system core.hooksPath /dev/null',
        'git config --system --unset core.hooksPath',
        'git config --add core.hooksPath /dev/null',
        'git config --file .git/config core.hooksPath /dev/null',
        'git config core.hooksPath; git config core.hooksPath /dev/null',
        'git config core.hooksPath\ngit config core.hooksPath /dev/null',
        'bash -c "git config core.hooksPath /dev/null"',
        'GIT_CONFIG_KEY_0=core.hooksPath git push origin feat/x',
        'x=$(git config core.hooksPath)',
        'gh api repos/o/r/pulls/1/merge -X PUT 2>&1',
        'echo x > .github/workflows/a.yml',
    ]
    ALLOWED = [
        'gh api repos/o/r/commits/abc/check-runs',
        'gh api repos/o/r/pulls/1/comments/2/replies -f body=ok',
        'gh api repos/o/r/contents/README.md',
        'gh api -X GET repos/o/r/contents/README.md -f ref=dev',
        "gh api 'repos/o/r/issues?state=open&labels=a'",
        'gh api repos/o/r/contents/README.md > out.md',
        'gh api repos/o/r/commits/abc/check-runs 2>&1 | head',
        'git push -u origin feat/x',
        'cat .github/workflows/a.yml',
        'git config core.hooksPath',
        'git config --get core.hooksPath',
        'git config --system core.hooksPath',
        'git config --system --get core.hooksPath',
        'git config --show-origin core.hooksPath',
        'git config --show-scope core.hooksPath',
    ]

    def test_commands(self):
        with tempfile.TemporaryDirectory() as directory:
            for command in self.DENIED:
                self.assertTrue(guard_denies('Bash', {'command': command}, directory), command)
            for command in self.ALLOWED:
                self.assertFalse(guard_denies('Bash', {'command': command}, directory), command)

    def test_files_and_tools(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertTrue(guard_denies('Edit', {'file_path': '/opt/cloud-env/hooks/guard-bash.py'}, directory))
            self.assertTrue(guard_denies('Write', {'file_path': '/home/user/app/.github/workflows/a.yml'}, directory))
            self.assertFalse(guard_denies('Edit', {'file_path': '/home/user/app/app/Models/User.php'}, directory))
            self.assertTrue(guard_denies('mcp__github__merge_pull_request', {}, directory))
            self.assertTrue(guard_denies('mcp__github__push_files', {}, directory))
            self.assertFalse(guard_denies('mcp__github__create_pull_request', {}, directory))


class AutoMergeTest(unittest.TestCase):
    MERGE = {'owner': 'witify', 'repo': 'app', 'pullNumber': 12, 'merge_method': 'merge'}

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        gh = pathlib.Path(self.directory.name) / 'gh'
        gh.write_text(FAKE_GH)
        gh.chmod(0o755)
        self.env = {**os.environ, 'PATH': f'{self.directory.name}:{os.environ["PATH"]}', 'FAKE_GH_DIR': self.directory.name}

    def github(self, pull=None, runs=None):
        base_pull = {'state': 'open', 'draft': False, 'base': {'ref': 'dev'},
                     'head': {'ref': 'feat/86abc-invoice-total', 'sha': SHA, 'repo': {'full_name': 'witify/app'}}}
        base_runs = [{'name': 'tests', 'status': 'completed', 'conclusion': 'success'},
                     {'name': 'lint', 'status': 'completed', 'conclusion': 'skipped'}]
        check_runs = base_runs if runs is None else runs
        (pathlib.Path(self.directory.name) / 'pull.json').write_text(json.dumps({**base_pull, **(pull or {})}))
        (pathlib.Path(self.directory.name) / 'checks.json').write_text(json.dumps({'total_count': len(check_runs), 'check_runs': check_runs}))

    def denies(self, tool_input=None):
        return guard_denies('mcp__github__merge_pull_request', tool_input or self.MERGE, self.directory.name, self.env)

    def test_green_feature_branch_into_dev_is_allowed(self):
        self.github()
        self.assertFalse(self.denies())

    def test_fix_branch_is_allowed(self):
        self.github(pull={'head': {'ref': 'fix/86abc-total', 'sha': SHA, 'repo': {'full_name': 'witify/app'}}})
        self.assertFalse(self.denies())

    def test_refused_cases(self):
        cases = {
            'base main': ({'base': {'ref': 'main'}}, None),
            'closed': ({'state': 'closed'}, None),
            'draft': ({'draft': True}, None),
            'other branch': ({'head': {'ref': 'chore/x', 'sha': SHA, 'repo': {'full_name': 'witify/app'}}}, None),
            'fork': ({'head': {'ref': 'feat/x', 'sha': SHA, 'repo': {'full_name': 'someone/app'}}}, None),
            'failed check': (None, [{'name': 'tests', 'status': 'completed', 'conclusion': 'failure'}]),
            'running check': (None, [{'name': 'tests', 'status': 'in_progress', 'conclusion': None}]),
            'no check': (None, []),
        }
        for name, (pull, runs) in cases.items():
            self.github(pull, runs)
            self.assertTrue(self.denies(), name)

    def test_bad_input_and_other_merge_paths_are_refused(self):
        self.github()
        self.assertTrue(self.denies({'owner': 'witify', 'repo': 'app'}))
        self.assertTrue(self.denies({**self.MERGE, 'repo': 'app/../../x'}))
        self.assertTrue(guard_denies('Bash', {'command': 'gh pr merge 12'}, self.directory.name, self.env))
        self.assertTrue(guard_denies('Bash', {'command': 'gh api repos/witify/app/pulls/12/merge -X PUT'}, self.directory.name, self.env))

    def test_unreadable_github_is_refused(self):
        self.assertTrue(self.denies())


class PrePushTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.git('init', '-q')
        self.git('config', 'user.email', 'a@b.c')
        self.git('config', 'user.name', 'x')
        self.git('config', 'commit.gpgsign', 'false')
        self.commit('a.txt', 'base')
        self.git('update-ref', 'refs/remotes/origin/main', 'HEAD')

    def git(self, *arguments):
        return subprocess.run(['git', *arguments], cwd=self.directory.name, capture_output=True, text=True, check=True).stdout.strip()

    def commit(self, path, message):
        target = pathlib.Path(self.directory.name) / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(message)
        self.git('add', path)
        self.git('commit', '-q', '-m', message)
        return self.git('rev-parse', 'HEAD')

    def push_status(self, local_sha, remote_ref):
        line = f'HEAD {local_sha} {remote_ref} {NO_SHA}\n'
        return subprocess.run(['bash', str(PRE_PUSH)], input=line, cwd=self.directory.name, capture_output=True, text=True).returncode

    def test_feature_branch_is_allowed(self):
        self.assertEqual(self.push_status(self.commit('b.txt', 'plain'), 'refs/heads/feat/x'), 0)

    def test_release_branch_is_refused(self):
        self.assertEqual(self.push_status(self.git('rev-parse', 'HEAD'), 'refs/heads/dev'), 1)

    def test_branch_deletion_is_refused(self):
        self.assertEqual(self.push_status(NO_SHA, 'refs/heads/feat/x'), 1)

    def test_workflow_change_is_refused_with_main_as_the_base(self):
        self.assertEqual(self.push_status(self.commit('.github/workflows/a.yml', 'workflow'), 'refs/heads/feat/x'), 1)


if __name__ == '__main__':
    unittest.main()
