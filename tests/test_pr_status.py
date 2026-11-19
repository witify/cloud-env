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
import unittest
import unittest.mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
PR_STATUS = ROOT / 'bin' / 'pr-status'
SHA = 'a' * 40
OLD_SHA = 'b' * 40
CODEX = {'login': 'chatgpt-codex-connector[bot]'}
PASSED = [{'name': 'PHPUnit', 'status': 'completed', 'conclusion': 'success'},
          {'name': 'lint', 'status': 'completed', 'conclusion': 'skipped'}]
RUNNING = [{'name': 'PHPUnit', 'status': 'in_progress', 'conclusion': None}]

# Answers `gh api [flags] <path>` from one JSON file for each kind of path, the way GitHub would.
# With --slurp, the answer is the list of its pages: <name>.pages.json when it exists, else one page.
# A list read without --paginate --slurp fails, so a test sees a read of the first page only.
FAKE_GH = """#!/usr/bin/env python3
import os, re, sys
flags = [argument for argument in sys.argv[2:] if argument.startswith('-')]
path = next(argument for argument in sys.argv[2:] if not argument.startswith('-')).split('?')[0]
names = [
    (r'/commits/\\w+/check-runs$', 'checks'), (r'/commits/\\w+/check-suites$', 'suites'), (r'/commits/\\w+$', 'commit'),
    (r'/issues/\\d+/reactions$', 'reactions'), (r'/issues/\\d+/comments$', 'comments'), (r'/pulls/\\d+/reviews$', 'reviews'),
    (r'/pulls/\\d+$', 'pull'),
]
name = next(name for pattern, name in names if re.search(pattern, path))
slurp = '--paginate' in flags and '--slurp' in flags
if name in ('checks', 'suites', 'reactions', 'comments', 'reviews') and not slurp:
    sys.exit(f'fake gh: {path} read without --paginate --slurp')
directory = os.environ['FAKE_GH_DIR']
pages = os.path.join(directory, name + '.pages.json')
file = os.path.join(directory, name + '.json')
if slurp and os.path.exists(pages):
    print(open(pages).read())
elif not os.path.exists(file):
    sys.exit('gh: Not Found (HTTP 404)')
elif slurp:
    print('[' + open(file).read() + ']')
else:
    print(open(file).read())
"""


def minutes_ago(minutes):
    moment = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=minutes)
    return moment.strftime('%Y-%m-%dT%H:%M:%SZ')


def summary(sha, status='completed', findings=False):
    state = {'code_review': {'commit_sha': sha, 'has_any_findings': findings, 'has_unresolved_findings': findings, 'status': status},
             'security_review': {'status': 'skipped'}}
    return {'user': CODEX, 'body': f'## Codex Review Summary\n<!-- codex-review-state:v1 {json.dumps(state)} -->\nReview trigger: PR opened'}


def load_pr_status():
    loader = importlib.machinery.SourceFileLoader('pr_status', str(PR_STATUS))
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader('pr_status', loader))
    loader.exec_module(module)
    return module


class PrStatusTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = pathlib.Path(directory.name)
        gh = self.directory / 'gh'
        gh.write_text(FAKE_GH)
        gh.chmod(0o755)
        subprocess.run(['git', 'init', '--quiet', str(self.directory)], check=True)
        subprocess.run(['git', '-C', str(self.directory), 'remote', 'add', 'origin', 'https://github.com/witify/app.git'], check=True)
        self.env = {**os.environ, 'PATH': f'{self.directory}:{os.environ["PATH"]}', 'FAKE_GH_DIR': str(self.directory)}

    def github(self, committed=30, pushed=None, opened=60, runs=None, reactions=(), reacted=0, comments=(), reviews=(),
               state='open', merged=False):
        """The pull request as GitHub shows it: its last commit made `committed` minutes ago, its first check suite
        created `pushed` minutes ago (when the commit was made, by default), the pull request opened `opened` minutes ago."""
        files = {
            'pull': {'head': {'sha': SHA}, 'created_at': minutes_ago(opened), 'state': state, 'merged': merged},
            'commit': {'commit': {'committer': {'date': minutes_ago(committed)}}},
            'suites': {'total_count': 1, 'check_suites': [{'created_at': minutes_ago(committed if pushed is None else pushed)}]},
            'checks': {'total_count': len(PASSED if runs is None else runs), 'check_runs': PASSED if runs is None else runs},
            'reactions': [{'user': CODEX, 'content': content, 'created_at': minutes_ago(reacted)} for content in reactions],
            'comments': list(comments),
            'reviews': list(reviews),
        }
        for name, content in files.items():
            (self.directory / f'{name}.json').write_text(json.dumps(content))

    def pages(self, name, *pages):
        (self.directory / f'{name}.pages.json').write_text(json.dumps(list(pages)))

    def status(self, *arguments):
        result = subprocess.run(['python3', '-I', str(PR_STATUS), *(arguments or ['12'])], capture_output=True, text=True,
                                cwd=self.directory, env=self.env, timeout=30)
        return result.returncode, result.stdout + result.stderr

    def test_green_checks_and_an_approval(self):
        self.github(comments=[{'user': {'login': 'a-person'}, 'body': 'codex-review-state:v1 {} -->'}, summary(SHA)])
        code, output = self.status()
        self.assertEqual(0, code, output)
        self.assertIn('pull request: witify/app#12, commit aaaaaaa\n', output)
        self.assertIn('ci: passed (2 checks)', output)
        self.assertIn('codex: approved', output)

    def test_a_failed_check_and_a_review(self):
        self.github(runs=[{'name': 'PHPUnit', 'status': 'completed', 'conclusion': 'failure'}],
                    reviews=[{'user': CODEX, 'commit_id': SHA, 'state': 'COMMENTED'}])
        code, output = self.status()
        self.assertEqual(0, code, output)
        self.assertIn('ci: failed (PHPUnit)', output)
        self.assertIn('codex: findings', output)

    def test_a_check_still_running_is_pending(self):
        self.github(runs=RUNNING, comments=[summary(SHA)])
        code, output = self.status()
        self.assertEqual(0, code, output)
        self.assertIn('ci: pending (PHPUnit)', output)

    def test_findings_in_the_summary_comment_count_as_an_answer(self):
        self.github(comments=[summary(SHA, findings=True)])
        self.assertIn('codex: findings', self.status()[1])

    def test_a_thumbs_up_after_the_last_commit_is_an_approval(self):
        self.github(reactions=['+1'])
        self.assertIn('codex: approved', self.status()[1])

    def test_a_thumbs_up_older_than_the_last_commit_is_not_an_approval(self):
        self.github(committed=10, reactions=['+1'], reacted=20)
        self.assertIn('codex: absent', self.status()[1])

    def test_a_thumbs_up_older_than_the_push_is_not_an_approval(self):
        # Made 10 minutes ago, pushed 1 minute ago: the thumbs up of 5 minutes ago is for the commit before.
        self.github(committed=10, pushed=1, reactions=['+1'], reacted=5)
        output = self.status()[1]
        self.assertNotIn('codex: approved', output)
        self.assertIn('codex: waiting', output)

    def test_a_thumbs_up_does_not_approve_when_the_summary_names_another_commit(self):
        self.github(reactions=['+1'], comments=[summary(OLD_SHA)])
        output = self.status()[1]
        self.assertIn('codex: older-commit', output)
        self.assertIn('bbbbbbb', output)

    def test_a_review_in_progress_is_reviewing(self):
        self.github(reactions=['eyes'], comments=[summary(SHA, status='in_progress')])
        self.assertIn('codex: reviewing', self.status()[1])

    def test_no_sign_of_codex_on_a_recent_commit_is_waiting(self):
        self.github(committed=1)
        self.assertIn('codex: waiting (no sign yet, the last commit was pushed 1 min ago', self.status()[1])

    def test_no_sign_of_codex_after_five_minutes_is_absent(self):
        self.github(committed=6)
        self.assertIn('codex: absent', self.status()[1])

    def test_no_sign_of_codex_on_an_old_commit_pushed_recently_is_waiting(self):
        # The commit was made 30 minutes ago, but reached GitHub or the pull request 1 minute ago.
        for when in ({'opened': 1}, {'pushed': 1}):
            with self.subTest(**when):
                self.github(committed=30, **when)
                self.assertIn('codex: waiting (no sign yet, the last commit was pushed 1 min ago', self.status()[1])

    def test_an_unreadable_check_suite_list_falls_back_on_the_other_moments(self):
        self.github(committed=30, opened=1)
        (self.directory / 'suites.json').unlink()
        code, output = self.status()
        self.assertEqual(0, code, output)
        self.assertIn('codex: waiting', output)

    def test_an_answer_for_an_older_commit_is_not_an_approval(self):
        self.github(committed=6, comments=[summary(OLD_SHA)])
        output = self.status()[1]
        self.assertIn('codex: older-commit', output)
        self.assertIn('bbbbbbb', output)

    def test_an_answer_for_an_older_commit_on_a_recent_push_is_waiting(self):
        self.github(committed=30, pushed=1, comments=[summary(OLD_SHA)])
        output = self.status()[1]
        self.assertIn('codex: waiting', output)
        self.assertIn('bbbbbbb', output)

    def test_an_answer_on_a_recent_push_stays_as_it_is(self):
        cases = {
            'approved': {'comments': [summary(SHA)]},
            'findings': {'reviews': [{'user': CODEX, 'commit_id': SHA, 'state': 'COMMENTED'}]},
            'reviewing': {'reactions': ['eyes'], 'comments': [summary(SHA, status='in_progress')]},
        }
        for expected, sides in cases.items():
            with self.subTest(expected):
                self.github(committed=1, **sides)
                self.assertIn(f'codex: {expected}', self.status()[1])

    def test_eyes_after_an_answer_for_an_older_commit_is_a_review_in_progress(self):
        self.github(reactions=['eyes'], comments=[summary(OLD_SHA)])
        self.assertIn('codex: reviewing', self.status()[1])

    def test_no_check_run(self):
        self.github(runs=[], comments=[summary(SHA)])
        self.assertIn('ci: none', self.status()[1])

    def test_every_page_of_comments_is_read(self):
        self.github()
        self.pages('comments', [{'user': {'login': 'a-person'}, 'body': 'hello'}, summary(OLD_SHA)], [summary(SHA)])
        self.assertIn('codex: approved', self.status()[1])

    def test_every_page_of_reviews_is_read(self):
        self.github(comments=[summary(OLD_SHA)])
        self.pages('reviews', [{'user': CODEX, 'commit_id': OLD_SHA, 'state': 'COMMENTED'}] * 100,
                   [{'user': CODEX, 'commit_id': SHA, 'state': 'COMMENTED'}])
        self.assertIn('codex: findings (a review on this commit)', self.status()[1])

    def test_check_runs_of_every_page_count(self):
        self.github(comments=[summary(SHA)])
        self.pages('checks', {'total_count': 2, 'check_runs': PASSED[:1]},
                   {'total_count': 2, 'check_runs': [{'name': 'Pint', 'status': 'completed', 'conclusion': 'failure'}]})
        self.assertIn('ci: failed (Pint)', self.status()[1])

    def test_check_runs_not_all_read_are_pending(self):
        self.github(comments=[summary(SHA)])
        self.pages('checks', {'total_count': 3, 'check_runs': PASSED})
        self.assertIn('ci: pending (not all check runs read: 2 of 3)', self.status()[1])

    def test_a_closed_or_merged_pull_request_is_named_and_read(self):
        self.github(state='closed')
        code, output = self.status()
        self.assertEqual(0, code, output)
        self.assertIn('commit aaaaaaa, closed', output)
        self.github(state='closed', merged=True)
        code, output = self.status()
        self.assertEqual(0, code, output)
        self.assertIn('commit aaaaaaa, merged', output)

    def test_a_wrong_call_or_an_unreadable_pull_request_exits_2(self):
        self.assertEqual(2, self.status('twelve')[0])
        self.assertEqual(2, self.status('12', '13')[0])
        self.assertEqual(2, self.status('12', '--minutes', '5')[0])
        self.assertEqual(2, self.status('12', '--wait', '--minutes', 'soon')[0])
        self.assertEqual(2, self.status('12', '--wait', '--minutes', '0')[0])
        code, output = self.status()
        self.assertEqual(2, code, output)
        self.assertIn('could not be read', output)

    def test_a_read_failing_midway_exits_2(self):
        self.github(comments=[summary(SHA)])
        (self.directory / 'reviews.json').unlink()
        code, output = self.status()
        self.assertEqual(2, code, output)
        self.assertIn('could not be read', output)

    def test_wait_returns_at_once_when_both_are_known(self):
        self.github(comments=[summary(SHA)])
        code, output = self.status('12', '--wait')
        self.assertEqual(0, code, output)
        self.assertIn('codex: approved', output)
        self.assertRegex(output, r'waited: \d+ s\n')

    def test_wait_on_a_closed_pull_request_exits_1(self):
        self.github(state='closed', merged=True)
        code, output = self.status('12', '--wait', '--minutes', '10')
        self.assertEqual(1, code, output)
        self.assertIn('commit aaaaaaa, merged', output)


class Clock:
    """Time that moves only when the command sleeps."""

    def __init__(self):
        self.now = 0.0
        self.sleeps = 0

    def monotonic(self):
        return self.now

    def time(self):
        return 1_800_000_000 + self.now

    def sleep(self, seconds):
        self.now += seconds
        self.sleeps += 1


class PrStatusWaitTest(unittest.TestCase):
    """The --wait loop, in process: GitHub's answers come in order, and sleeping takes no time."""

    PENDING = (SHA, 'open', ('pending', 'PHPUnit'), ('reviewing', 'no answer yet'))
    KNOWN = (SHA, 'open', ('passed', '2 checks'), ('approved', 'no finding on this commit'))

    def setUp(self):
        self.module = load_pr_status()
        self.clock = Clock()

    def run_wait(self, answers, *arguments):
        answers = iter(answers)

        def read(repo, number):
            answer = next(answers, self.PENDING)
            if isinstance(answer, Exception):
                raise answer
            return answer

        output = io.StringIO()
        with unittest.mock.patch.object(self.module, 'time', self.clock), \
                unittest.mock.patch.object(self.module, 'read', read), \
                unittest.mock.patch.object(self.module, 'repository', lambda: 'witify/app'), \
                unittest.mock.patch.object(self.module.sys, 'argv', ['pr-status', '12', '--wait', *arguments]), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            code = self.module.main()
        return code, output.getvalue()

    def test_it_reads_until_both_are_known(self):
        code, output = self.run_wait([self.PENDING, self.PENDING, self.KNOWN])
        self.assertEqual(0, code, output)
        self.assertEqual(2, self.clock.sleeps)
        self.assertIn('codex: approved', output)
        self.assertIn('waited: 40 s\n', output)

    def test_waiting_codex_is_not_known(self):
        waiting = (SHA, 'open', ('passed', '2 checks'), ('waiting', 'no sign yet'))
        absent = (SHA, 'open', ('passed', '2 checks'), ('absent', 'no sign'))
        code, output = self.run_wait([waiting, waiting, absent])
        self.assertEqual(0, code, output)
        self.assertIn('codex: absent', output)

    def test_one_failed_read_mid_wait_does_not_end_it(self):
        code, output = self.run_wait([self.PENDING, self.module.GitHubError('HTTP 502'), self.KNOWN])
        self.assertEqual(0, code, output)
        self.assertIn('codex: approved', output)

    def test_more_than_three_failed_reads_in_a_row_exit_2(self):
        failure = self.module.GitHubError('HTTP 502')
        code, output = self.run_wait([self.PENDING, failure, failure, failure, failure, self.KNOWN])
        self.assertEqual(2, code, output)
        self.assertIn('could not be read', output)

    def test_a_failed_first_read_exits_2(self):
        code, output = self.run_wait([self.module.GitHubError('HTTP 404'), self.KNOWN])
        self.assertEqual(2, code, output)
        self.assertEqual(0, self.clock.sleeps)
        self.assertIn('could not be read', output)

    def test_it_exits_1_when_the_time_runs_out(self):
        code, output = self.run_wait([], '--minutes', '1')
        self.assertEqual(1, code, output)
        self.assertIn('ci: pending (PHPUnit)', output)
        self.assertIn('codex: reviewing', output)
        self.assertIn('waited: 60 s, the time ran out after 1 min', output)

    def test_it_exits_1_when_the_pull_request_is_closed(self):
        closed = (SHA, 'closed', ('pending', 'PHPUnit'), ('reviewing', 'no answer yet'))
        code, output = self.run_wait([self.PENDING, closed])
        self.assertEqual(1, code, output)
        self.assertIn('commit aaaaaaa, closed', output)


if __name__ == '__main__':
    unittest.main()
