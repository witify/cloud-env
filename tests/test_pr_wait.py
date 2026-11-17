"""Run with: python3 -m unittest discover tests"""
import datetime
import json
import os
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
PR_WAIT = ROOT / 'bin' / 'pr-wait'
SHA = 'a' * 40
OLD_SHA = 'b' * 40
CODEX = {'login': 'chatgpt-codex-connector[bot]'}

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
    state = {'code_review': {'commit_sha': sha, 'has_any_findings': findings, 'status': status}}
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
        self.env = {**os.environ, 'PATH': f'{self.directory}:{os.environ["PATH"]}', 'FAKE_GH_DIR': str(self.directory)}

    def github(self, opened=1, runs=None, reactions=(), comments=(), reviews=()):
        passed = [{'name': 'PHPUnit', 'status': 'completed', 'conclusion': 'success'},
                  {'name': 'lint', 'status': 'completed', 'conclusion': 'skipped'}]
        files = {
            'pull': {'head': {'sha': SHA}, 'created_at': minutes_ago(opened)},
            'commit': {'commit': {'committer': {'date': minutes_ago(opened + 10)}}},
            'checks': {'check_runs': passed if runs is None else runs},
            'reactions': [{'user': CODEX, 'content': content} for content in reactions],
            'comments': list(comments),
            'reviews': list(reviews),
        }
        for name, content in files.items():
            (self.directory / f'{name}.json').write_text(json.dumps(content))

    def wait(self, *arguments):
        result = subprocess.run(['python3', '-I', str(PR_WAIT), *(arguments or ['12'])], capture_output=True, text=True,
                                cwd=self.directory, env=self.env, timeout=30)
        return result.returncode, result.stdout + result.stderr

    def test_green_checks_and_an_approval_end_the_wait(self):
        self.github(comments=[{'user': {'login': 'a-person'}, 'body': 'codex-review-state:v1 {} -->'}, summary(SHA)])
        code, output = self.wait()
        self.assertEqual(0, code, output)
        self.assertIn('pull request: witify/app#12, commit aaaaaaa', output)
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

    def test_a_thumbs_up_alone_is_an_approval(self):
        self.github(reactions=['+1'])
        code, output = self.wait()
        self.assertEqual(0, code, output)
        self.assertIn('codex: approved', output)

    def test_a_check_still_running_after_the_time_is_reported_as_pending(self):
        self.github(opened=16, runs=[{'name': 'PHPUnit', 'status': 'in_progress', 'conclusion': None}], comments=[summary(SHA)])
        code, output = self.wait()
        self.assertEqual(1, code, output)
        self.assertIn('ci: pending (PHPUnit)', output)
        self.assertIn('stopped 15 minutes after', output)

    def test_a_review_in_progress_after_the_time_is_reported_as_reviewing(self):
        self.github(opened=16, reactions=['eyes'], comments=[summary(SHA, status='in_progress')])
        code, output = self.wait()
        self.assertEqual(1, code, output)
        self.assertIn('codex: reviewing', output)

    def test_no_sign_of_codex_after_five_minutes_leaves_ci_only(self):
        self.github(opened=6)
        code, output = self.wait()
        self.assertEqual(0, code, output)
        self.assertIn('codex: absent', output)

    def test_an_answer_for_an_older_commit_is_not_an_approval(self):
        self.github(opened=6, reactions=['+1'], comments=[summary(OLD_SHA)])
        code, output = self.wait()
        self.assertEqual(0, code, output)
        self.assertIn('codex: older-commit', output)
        self.assertIn('bbbbbbb', output)

    def test_no_check_run_is_not_a_wait(self):
        self.github(runs=[], comments=[summary(SHA)])
        code, output = self.wait()
        self.assertEqual(0, code, output)
        self.assertIn('ci: none', output)

    def test_the_minutes_option_shortens_the_wait(self):
        self.github(opened=2, reactions=['eyes'])
        code, output = self.wait('12', '--minutes', '1')
        self.assertEqual(1, code, output)
        self.assertIn('stopped 1 minutes after', output)

    def test_a_wrong_call_or_an_unreadable_pull_request_exits_2(self):
        self.assertEqual(2, self.wait('twelve')[0])
        self.assertEqual(2, self.wait('12', '--minutes')[0])
        code, output = self.wait()
        self.assertEqual(2, code, output)
        self.assertIn('could not be read', output)


if __name__ == '__main__':
    unittest.main()
