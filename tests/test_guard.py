"""Run with: python3 -m unittest discover tests"""
import json
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
GUARD = ROOT / 'hooks' / 'guard-bash.py'
PRE_PUSH = ROOT / 'git-hooks' / 'pre-push'
NO_SHA = '0' * 40


def guard_denies(tool, tool_input, cwd):
    event = {'tool_name': tool, 'tool_input': tool_input, 'cwd': cwd}
    result = subprocess.run(['python3', '-I', str(GUARD)], input=json.dumps(event), capture_output=True, text=True, check=True)
    return 'deny' in result.stdout


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
        'echo x > .github/workflows/a.yml',
    ]
    ALLOWED = [
        'gh api repos/o/r/commits/abc/check-runs',
        'gh api repos/o/r/pulls/1/comments/2/replies -f body=ok',
        'gh api repos/o/r/contents/README.md',
        'gh api -X GET repos/o/r/contents/README.md -f ref=dev',
        "gh api 'repos/o/r/issues?state=open&labels=a'",
        'git push -u origin feat/x',
        'cat .github/workflows/a.yml',
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
