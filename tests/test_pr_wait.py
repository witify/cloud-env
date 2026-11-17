"""Run with: python3 -m unittest discover tests"""
import contextlib
import datetime
import importlib.machinery
import importlib.util
import io
import json
import os
import pathlib
import subprocess
import tempfile
import time
import unittest
import unittest.mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
PR_WAIT = ROOT / 'bin' / 'pr-wait'
SHA = 'a' * 40
OLD_SHA = 'b' * 40
CODEX = {'login': 'chatgpt-codex-connector[bot]'}
PASSED = [{'name': 'PHPUnit', 'status': 'completed', 'conclusion': 'success'},
          {'name': 'lint', 'status': 'completed', 'conclusion': 'skipped'}]
RUNNING = [{'name': 'PHPUnit', 'status': 'in_progress', 'conclusion': None}]

# Answers `gh api <path>` from one JSON file for each kind of path, the way GitHub would.
FAKE_GH = """#!/usr/bin/env python3
import os, re, sys
path = sys.argv[2].split('?')[0]
names = [
    (r'/commits/\\w+/check-runs$', 'checks'), (r'/commits/\\w+$', 'commit'), (r'/issues/\\d+/reactions$', 'reactions'),
    (r'/issues/\\d+/comments$', 'comments'), (r'/pulls/\\d+/reviews$', 'reviews'), (r'/pulls/\\d+$', 'pull'),
]
name = next(name for pattern, name in names if re.search(pattern, path))
file = os.path.join(os.environ['FAKE_GH_DIR'], name + '.json')
if not os.path.exists(file):
    sys.exit('gh: Not Found (HTTP 404)')
print(open(file).read())
"""


def minutes_ago(minutes):
    moment = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=minutes)
    return moment.strftime('%Y-%m-%dT%H:%M:%SZ')


def summary(sha, status='completed', findings=False):
    state = {'code_review': {'commit_sha': sha, 'has_any_findings': findings, 'has_unresolved_findings': findings, 'status': status},
             'security_review': {'status': 'skipped'}}
    return {'user': CODEX, 'body': f'## Codex Review Summary\n<!-- codex-review-state:v1 {json.dumps(state)} -->\nReview trigger: PR opened'}


class PrWaitTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = pathlib.Path(directory.name)
        gh = self.directory / 'gh'
        gh.write_text(FAKE_GH)
        gh.chmod(0o755)
        subprocess.run(['git', 'init', '--quiet', str(self.directory)], check=True)
        subprocess.run(['git', '-C', str(self.directory), 'remote', 'add', 'origin', 'https://github.com/witify/app.git'], check=True)
        self.env = {**os.environ, 'PATH': f'{self.directory}:{os.environ["PATH"]}', 'FAKE_GH_DIR': str(self.directory),
                    'PR_WAIT_STATE_DIR': str(self.directory)}
        self.state_file = self.directory / 'pr-wait-witify-app-12'

    def github(self, first_call=1, committed=30, runs=None, reactions=(), reacted=0, comments=(), reviews=(), state='open'):
        """The pull request as GitHub shows it, `first_call` minutes after pr-wait first saw its last commit."""
        files = {
            'pull': {'head': {'sha': SHA}, 'created_at': minutes_ago((first_call or 0) + 1), 'state': state, 'merged': False},
            'commit': {'commit': {'committer': {'date': minutes_ago(committed)}}},
            'checks': {'check_runs': PASSED if runs is None else runs},
            'reactions': [{'user': CODEX, 'content': content, 'created_at': minutes_ago(reacted)} for content in reactions],
            'comments': list(comments),
            'reviews': list(reviews),
        }
        for name, content in files.items():
            (self.directory / f'{name}.json').write_text(json.dumps(content))
        if first_call is not None:
            self.state_file.write_text(json.dumps({SHA: time.time() - first_call * 60}))

    def wait(self, *arguments):
        result = subprocess.run(['python3', '-I', str(PR_WAIT), *(arguments or ['12'])], capture_output=True, text=True,
                                cwd=self.directory, env=self.env, timeout=30)
        return result.returncode, result.stdout + result.stderr

    def test_green_checks_and_an_approval_end_the_wait(self):
        self.github(comments=[{'user': {'login': 'a-person'}, 'body': 'codex-review-state:v1 {} -->'}, summary(SHA)])
        code, output = self.wait()
        self.assertEqual(0, code, output)
        self.assertIn('pull request: witify/app#12, commit aaaaaaa\n', output)
        self.assertIn('ci: passed (2 checks)', output)
        self.assertIn('codex: approved', output)

    def test_a_failed_check_and_a_review_end_the_wait(self):
        self.github(runs=[{'name': 'PHPUnit', 'status': 'completed', 'conclusion': 'failure'}],
                    reviews=[{'user': CODEX, 'commit_id': SHA, 'state': 'COMMENTED'}])
        code, output = self.wait()
        self.assertEqual(0, code, output)
        self.assertIn('ci: failed (PHPUnit)', output)
        self.assertIn('codex: findings', output)

    def test_findings_in_the_summary_comment_count_as_an_answer(self):
        self.github(comments=[summary(SHA, findings=True)])
        code, output = self.wait()
        self.assertEqual(0, code, output)
        self.assertIn('codex: findings', output)

    def test_a_thumbs_up_after_the_last_commit_is_an_approval(self):
        self.github(reactions=['+1'])
        code, output = self.wait()
        self.assertEqual(0, code, output)
        self.assertIn('codex: approved', output)

    def test_a_thumbs_up_older_than_the_last_commit_is_not_an_approval(self):
        self.github(first_call=6, committed=10, reactions=['+1'], reacted=20)
        code, output = self.wait()
        self.assertEqual(0, code, output)
        self.assertIn('codex: absent', output)

    def test_a_check_still_running_after_the_time_is_reported_as_pending(self):
        self.github(first_call=16, runs=RUNNING, comments=[summary(SHA)])
        code, output = self.wait()
        self.assertEqual(1, code, output)
        self.assertIn('ci: pending (PHPUnit)', output)
        self.assertIn('stopped 15 minutes after the first call for this commit', output)

    def test_a_review_in_progress_after_the_time_is_reported_as_reviewing(self):
        self.github(first_call=16, reactions=['eyes'], comments=[summary(SHA, status='in_progress')])
        code, output = self.wait()
        self.assertEqual(1, code, output)
        self.assertIn('codex: reviewing', output)

    def test_no_sign_of_codex_after_five_minutes_leaves_ci_only(self):
        self.github(first_call=6)
        code, output = self.wait()
        self.assertEqual(0, code, output)
        self.assertIn('codex: absent', output)

    def test_an_answer_for_an_older_commit_is_not_an_approval(self):
        self.github(first_call=6, comments=[summary(OLD_SHA)])
        code, output = self.wait()
        self.assertEqual(0, code, output)
        self.assertIn('codex: older-commit', output)
        self.assertIn('bbbbbbb', output)

    def test_eyes_after_an_answer_for_an_older_commit_is_a_review_in_progress(self):
        self.github(first_call=16, reactions=['eyes'], comments=[summary(OLD_SHA)])
        code, output = self.wait()
        self.assertEqual(1, code, output)
        self.assertIn('codex: reviewing', output)

    def test_no_check_run_is_not_a_wait(self):
        self.github(runs=[], comments=[summary(SHA)])
        code, output = self.wait()
        self.assertEqual(0, code, output)
        self.assertIn('ci: none', output)

    def test_a_closed_pull_request_ends_the_wait(self):
        self.github(runs=RUNNING, state='closed')
        code, output = self.wait()
        self.assertEqual(1, code, output)
        self.assertIn('commit aaaaaaa, closed', output)

    def test_the_minutes_option_shortens_the_wait(self):
        self.github(first_call=2, reactions=['eyes'])
        code, output = self.wait('12', '--minutes', '1')
        self.assertEqual(1, code, output)
        self.assertIn('stopped 1 minutes after', output)

    def test_the_wait_counts_from_the_first_call_for_the_last_commit(self):
        self.github(first_call=None, runs=RUNNING)
        self.state_file.write_text(json.dumps({OLD_SHA: time.time() - 3600}))

        code, output = self.wait('12', '--minutes', '0')
        self.assertEqual(1, code, output)
        seen = json.loads(self.state_file.read_text())
        self.assertEqual([SHA], list(seen))
        self.assertAlmostEqual(time.time(), seen[SHA], delta=30)

    def test_a_wrong_call_or_an_unreadable_pull_request_exits_2(self):
        self.assertEqual(2, self.wait('twelve')[0])
        self.assertEqual(2, self.wait('12', '--minutes')[0])
        code, output = self.wait()
        self.assertEqual(2, code, output)
        self.assertIn('could not be read', output)


class PrWaitLoopTest(unittest.TestCase):
    """The loop itself, in process, so the test does not sleep."""

    def setUp(self):
        loader = importlib.machinery.SourceFileLoader('pr_wait', str(PR_WAIT))
        self.module = importlib.util.module_from_spec(importlib.util.spec_from_loader('pr_wait', loader))
        loader.exec_module(self.module)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.module.STATE_DIRECTORIES = (directory.name,)
        self.module.repository = lambda: 'witify/app'
        self.reads = 0

    def github(self, fail_on_read):
        def answer(path):
            path = path.split('?')[0]
            if path.endswith('/pulls/12'):
                self.reads += 1
                if self.reads == fail_on_read:
                    raise self.module.GitHubError('gh: HTTP 502')
                return {'head': {'sha': SHA}, 'state': 'open', 'merged': False}
            if path.endswith('/check-runs'):
                return {'check_runs': RUNNING if self.reads < 3 else PASSED}
            if path.endswith(f'/commits/{SHA}'):
                return {'commit': {'committer': {'date': minutes_ago(30)}}}
            if path.endswith('/comments'):
                return [summary(SHA)]
            return []
        return answer

    def run_main(self, fail_on_read):
        self.module.github = self.github(fail_on_read)
        output = io.StringIO()
        with unittest.mock.patch.object(self.module.sys, 'argv', ['pr-wait', '12']), \
                unittest.mock.patch.object(self.module.time, 'sleep') as sleep, \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            code = self.module.main()
        return code, output.getvalue(), sleep.call_count

    def test_one_failed_answer_during_the_wait_does_not_end_it(self):
        code, output, sleeps = self.run_main(fail_on_read=2)
        self.assertEqual(0, code, output)
        self.assertIn('ci: passed', output)
        self.assertEqual(3, self.reads)
        self.assertEqual(2, sleeps)

    def test_a_failed_first_answer_ends_it(self):
        code, output, sleeps = self.run_main(fail_on_read=1)
        self.assertEqual(2, code, output)
        self.assertIn('HTTP 502', output)
        self.assertEqual(0, sleeps)


if __name__ == '__main__':
    unittest.main()
