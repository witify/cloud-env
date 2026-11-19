"""Run with: python3 -m unittest discover tests"""
import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
LIB = ROOT / 'lib.sh'
KEYS = ['CLOUD_ENV_VALUES_VERSION', 'ROOT_DIR', 'SITE_URL', 'SITE_LOGIN_PATH', 'SITE_LOGIN_EMAIL',
        'SITE_LOGIN_PASSWORD', 'SITE_LANDING_PATH', 'NODE_PATH']


def write_values(state_dir, assignments, environment=None):
    """Runs write_flow_values with lib.sh's state folder moved to state_dir and the given values set."""
    lines = ''.join(f'{name}={value}\n' for name, value in assignments.items())
    script = f'''
source "{LIB}" 2>/dev/null
STATE_DIR="{state_dir}"
VALUES_FILE="{state_dir}/values.sh"
{lines}
write_flow_values
'''
    subprocess.run(['bash', '-s'], input=script, capture_output=True, text=True, check=True, env=environment)
    return pathlib.Path(state_dir) / 'values.sh'


def read_values(path):
    """What a POSIX shell gets when it sources the file, as the flow's tools do."""
    shell = shutil.which('dash') or '/bin/sh'
    script = f'. "{path}"\n' + ''.join(f'printf "%s\\0" "${name}"\n' for name in KEYS)
    output = subprocess.run([shell, '-c', script], capture_output=True, text=True, check=True).stdout
    return dict(zip(KEYS, output.split('\0')[:-1]))


class FlowValuesTest(unittest.TestCase):
    def setUp(self):
        self.state = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.state)

    def test_every_key_reads_back_exactly_in_a_posix_shell(self):
        path = write_values(self.state, {
            'ROOT_DIR': '/home/user/statim',
            'SITE_URL': 'http://localhost',
            'SITE_LOGIN_PATH': '/admin/login',
            'SITE_LOGIN_EMAIL': 'ada@example.com',
            # A seeded password can hold anything a shell would interpret.
            'SITE_LOGIN_PASSWORD': '''"it's \\$HOME \\`id\\` \\\\ \\"q\\" ;&|"''',
            'SITE_LANDING_PATH': '/admin',
        }, environment={'PATH': '/usr/bin:/bin', 'NODE_PATH': '/opt/node22/lib/node_modules'})

        self.assertEqual(read_values(path), {
            'CLOUD_ENV_VALUES_VERSION': '1',
            'ROOT_DIR': '/home/user/statim',
            'SITE_URL': 'http://localhost',
            'SITE_LOGIN_PATH': '/admin/login',
            'SITE_LOGIN_EMAIL': 'ada@example.com',
            'SITE_LOGIN_PASSWORD': '''it's $HOME `id` \\ "q" ;&|''',
            'SITE_LANDING_PATH': '/admin',
            'NODE_PATH': '/opt/node22/lib/node_modules',
        })
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_an_empty_login_stays_empty_and_node_path_has_its_default(self):
        path = write_values(self.state, {'SITE_LOGIN_EMAIL': '""', 'SITE_LOGIN_PASSWORD': '""'},
                            environment={'PATH': '/usr/bin:/bin'})

        values = read_values(path)
        self.assertEqual(values['SITE_LOGIN_EMAIL'], '')
        self.assertEqual(values['SITE_LOGIN_PASSWORD'], '')
        self.assertEqual(values['NODE_PATH'], '/opt/node22/lib/node_modules')
        # The defaults of defaults.sh, which lib.sh loads.
        self.assertEqual(values['SITE_URL'], 'http://localhost')
        self.assertEqual(values['SITE_LANDING_PATH'], '/')

    def test_a_new_session_replaces_the_file_whole(self):
        write_values(self.state, {'SITE_LANDING_PATH': '/old'})
        path = write_values(self.state, {'SITE_LANDING_PATH': '/new'})

        self.assertEqual(read_values(path)['SITE_LANDING_PATH'], '/new')
        self.assertEqual(sorted(p.name for p in pathlib.Path(self.state).iterdir()), ['values.sh'])


if __name__ == '__main__':
    unittest.main()
