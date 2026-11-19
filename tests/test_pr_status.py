"""Run with: python3 -m unittest discover tests"""
import datetime
import json
import os
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
PR_STATUS = ROOT / 'bin' / 'pr-status'
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

    def github(self, committed=30, runs=None, reactions=(), reacted=0, comments=(), reviews=(), state='open', merged=False):
        """The pull request as GitHub shows it, with its last commit `committed` minutes old."""
        files = {
            'pull': {'head': {'sha': SHA}, 'state': state, 'merged': merged},
            'commit': {'commit': {'committer': {'date': minutes_ago(committed)}}},
            'checks': {'check_runs': PASSED if runs is None else runs},
            'reactions': [{'user': CODEX, 'content': content, 'created_at': minutes_ago(reacted)} for content in reactions],
            'comments': list(comments),
            'reviews': list(reviews),
        }
        for name, content in files.items():
            (self.directory / f'{name}.json').write_text(json.dumps(content))

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

    def test_a_review_in_progress_is_reviewing(self):
        self.github(reactions=['eyes'], comments=[summary(SHA, status='in_progress')])
        self.assertIn('codex: reviewing', self.status()[1])

    def test_no_sign_of_codex_on_a_recent_commit_is_waiting(self):
        self.github(committed=1)
        self.assertIn('codex: waiting (no sign yet, the last commit is 1 minutes old', self.status()[1])

    def test_no_sign_of_codex_after_five_minutes_is_absent(self):
        self.github(committed=6)
        self.assertIn('codex: absent', self.status()[1])

    def test_an_answer_for_an_older_commit_is_not_an_approval(self):
        self.github(committed=6, comments=[summary(OLD_SHA)])
        output = self.status()[1]
        self.assertIn('codex: older-commit', output)
        self.assertIn('bbbbbbb', output)

    def test_eyes_after_an_answer_for_an_older_commit_is_a_review_in_progress(self):
        self.github(reactions=['eyes'], comments=[summary(OLD_SHA)])
        self.assertIn('codex: reviewing', self.status()[1])

    def test_no_check_run(self):
        self.github(runs=[], comments=[summary(SHA)])
        self.assertIn('ci: none', self.status()[1])

    def test_a_closed_or_merged_pull_request_is_named(self):
        self.github(state='closed')
        self.assertIn('commit aaaaaaa, closed', self.status()[1])
        self.github(state='closed', merged=True)
        self.assertIn('commit aaaaaaa, merged', self.status()[1])

    def test_a_wrong_call_or_an_unreadable_pull_request_exits_2(self):
        self.assertEqual(2, self.status('twelve')[0])
        self.assertEqual(2, self.status('12', '13')[0])
        code, output = self.status()
        self.assertEqual(2, code, output)
        self.assertIn('could not be read', output)


if __name__ == '__main__':
    unittest.main()
