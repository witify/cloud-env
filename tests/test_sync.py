"""Run with: python3 -m unittest discover tests"""
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
LIB = ROOT / 'lib.sh'


class FrontendFingerprintTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = pathlib.Path(directory.name)
        self.git('init', '--quiet')
        self.write('resources/js/List.vue', '<template>one</template>')
        self.write('app/Models/User.php', '<?php')
        self.git('add', '-A')
        self.commit('first')

    def git(self, *arguments):
        subprocess.run(['git', '-C', str(self.root), '-c', 'core.hooksPath=/dev/null', *arguments], check=True, capture_output=True)

    def commit(self, message):
        self.git('-c', 'user.name=test', '-c', 'user.email=test@example.com', 'commit', '--quiet', '-m', message)

    def write(self, path, content):
        file = self.root / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(content)

    def fingerprint(self):
        script = f'source "{LIB}" 2>/dev/null\nROOT_DIR="{self.root}"\nfrontend_fingerprint\n'
        return subprocess.run(['bash', '-s'], input=script, capture_output=True, text=True, check=True).stdout.strip()

    def test_a_commit_of_the_same_content_keeps_the_fingerprint(self):
        self.write('resources/js/List.vue', '<template>two</template>')
        self.write('resources/js/New.vue', '<template>new</template>')
        edited = self.fingerprint()

        self.git('add', '-A')
        self.assertEqual(edited, self.fingerprint())
        self.commit('second')
        self.assertEqual(edited, self.fingerprint())

    def test_a_change_of_content_changes_the_fingerprint(self):
        before = self.fingerprint()

        self.write('resources/js/List.vue', '<template>two</template>')
        edited = self.fingerprint()
        self.assertNotEqual(before, edited)

        self.write('resources/js/New.vue', '<template>new</template>')
        self.assertNotEqual(edited, self.fingerprint())

    def test_a_deleted_file_changes_the_fingerprint_once(self):
        before = self.fingerprint()

        (self.root / 'resources/js/List.vue').unlink()
        deleted = self.fingerprint()
        self.assertNotEqual(before, deleted)

        self.git('add', '-A')
        self.commit('delete')
        self.assertEqual(deleted, self.fingerprint())

    def test_a_file_the_build_does_not_read_is_ignored(self):
        before = self.fingerprint()

        self.write('app/Models/User.php', '<?php // changed')
        self.write('resources/views/notes.txt', 'notes')
        self.assertEqual(before, self.fingerprint())


if __name__ == '__main__':
    unittest.main()
