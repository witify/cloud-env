"""Run with: python3 -m unittest discover tests"""
import json
import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
DETECT = ROOT / 'detect.py'
DEFAULTS = ROOT / 'defaults.sh'
FIND_PASSWORD = ROOT / 'find-seeded-password.php'


class ProjectTestCase(unittest.TestCase):
    def project(self, name='my-project', **files):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = pathlib.Path(directory.name) / name
        root.mkdir()
        for path, content in files.items():
            file = root / path.replace('__', '/')
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(content)
        return root

    def detect(self, root):
        output = subprocess.run(['python3', '-I', DETECT, root], capture_output=True, text=True, check=True).stdout
        return dict(line.split('=', 1) for line in output.splitlines())


class DetectTest(ProjectTestCase):
    def composer(self, **require):
        return json.dumps({'require': require})

    def test_php_version_comes_from_the_constraint(self):
        cases = {
            '8.3.*': "'8.3'",
            '8.4.*': "'8.4'",
            '^8.3': "'8.3'",
            '8.3.* || 8.4.*': "'8.4'",
            '^8.9|^8.10': "'8.10'",
            '>=8.2 <8.4': "'8.2'",
            '^8.2 <=8.3': "'8.2'",
        }
        for constraint, expected in cases.items():
            root = self.project(**{'composer.json': self.composer(php=constraint)})
            self.assertEqual(self.detect(root)['PHP_VERSION'], expected, constraint)

    def test_php_version_with_nothing_to_read_stays_on_the_default(self):
        for content in ['not json', '[]', '{"require": []}', self.composer(), self.composer(php='7.4.*'), self.composer(php='$(reboot)')]:
            self.assertNotIn('PHP_VERSION', self.detect(self.project(**{'composer.json': content})), content)

    def test_a_package_in_the_lock_can_raise_the_php_version(self):
        def lock(*constraints):
            return json.dumps({
                'packages': [{'name': 'a/one', 'require': {'php': constraints[0]}}],
                'packages-dev': [{'name': 'a/two', 'require': {'php': constraint}} for constraint in constraints[1:]],
            })

        cases = [
            (lock('>=8.4.1'), "'8.4'"),
            (lock('^8.1', '>=8.4'), "'8.4'"),
            (lock('8.4.*'), "'8.4'"),
            (lock('^7.4|^8.4'), "'8.3'"),
            (lock('^8.4'), "'8.4'"),
            (lock('~8.4.0'), "'8.4'"),
            (lock('^8.5 || ^8.3'), "'8.3'"),
            (lock('^8.0 || ^7.4'), "'8.3'"),
            (lock('^8.1'), "'8.3'"),
        ]
        for content, expected in cases:
            root = self.project(**{'composer.json': self.composer(php='^8.3'), 'composer.lock': content})
            self.assertEqual(self.detect(root)['PHP_VERSION'], expected, content)

    def test_a_lock_with_null_dev_packages_is_read(self):
        lock = json.dumps({'packages': [{'name': 'a/one', 'require': {'php': '>=8.4'}}], 'packages-dev': None})
        root = self.project(**{'composer.json': self.composer(php='^8.3'), 'composer.lock': lock})
        self.assertEqual(self.detect(root)['PHP_VERSION'], "'8.4'")

    def test_a_constraint_cannot_inject_shell(self):
        root = self.project(**{'composer.json': self.composer(php="8.3'; reboot; '")})
        self.assertEqual(self.detect(root)['PHP_VERSION'], "'8.3'")

    def test_mysql_version_comes_from_the_ci_image(self):
        cases = {
            'image: mysql:8.0': "'8.0'",
            'image: mysql:8.0.36': "'8.0'",
            'image: mysql:8.4': "'8.4'",
        }
        for line, expected in cases.items():
            root = self.project(**{'.github__workflows__run-tests.yml': line})
            self.assertEqual(self.detect(root)['MYSQL_VERSION'], expected, line)

    def test_a_mysql_version_with_no_apt_source_stays_on_the_default(self):
        for line in ['image: mysql:5.7', 'image: mysql:8.3', 'image: mysql:latest', 'image: postgres:16']:
            root = self.project(**{'.github__workflows__run-tests.yml': line})
            self.assertNotIn('MYSQL_VERSION', self.detect(root), line)

    def test_the_first_workflow_with_a_mysql_image_decides(self):
        root = self.project(**{'.github__workflows__a.yaml': 'image: mysql:8.4', '.github__workflows__b.yml': 'image: mysql:8.0'})
        self.assertEqual(self.detect(root)['MYSQL_VERSION'], "'8.4'")

        root = self.project(**{'.github__workflows__a.yml': 'image: mysql:5.7', '.github__workflows__b.yml': 'image: mysql:8.4'})
        self.assertNotIn('MYSQL_VERSION', self.detect(root))

    def test_no_workflow_stays_on_the_default(self):
        self.assertNotIn('MYSQL_VERSION', self.detect(self.project()))

    def test_database_name_is_safe_in_sql_and_shell(self):
        cases = {'statim': "'statim'", 'witify-portal': "'witify_portal'", 'witify.io': "'witify_io'", 'My Repo!': "'my_repo'"}
        for name, expected in cases.items():
            self.assertEqual(self.detect(self.project(name=name))['APP_DATABASE'], expected, name)

    def test_app_title_comes_from_the_repository_name(self):
        self.assertEqual(self.detect(self.project(name='witify-portal'))['APP_TITLE'], "'Witify Portal Cloud'")
        self.assertNotIn('APP_TITLE', self.detect(self.project(name='---')))

    def test_a_filament_panel_has_its_own_login_page(self):
        values = self.detect(self.project(**{'composer.json': self.composer(**{'filament/filament': '^4'})}))
        self.assertEqual(values['SITE_CHECK_PATH'], "'/admin/login'")
        self.assertEqual(values['SITE_LOGIN_PATH'], "'/admin/login'")
        self.assertEqual(values['SITE_LANDING_PATH'], "'/admin'")

    def test_admin_routes_keep_the_plain_login_page_beside_filament(self):
        values = self.detect(self.project(**{'composer.json': self.composer(**{'filament/filament': '^4'}), 'routes__admin.php': ''}))
        self.assertNotIn('SITE_CHECK_PATH', values)
        self.assertNotIn('SITE_LOGIN_PATH', values)
        self.assertEqual(values['SITE_LANDING_PATH'], "'/admin'")

    def test_landing_path_follows_the_admin_routes(self):
        self.assertEqual(self.detect(self.project(**{'routes__admin.php': ''}))['SITE_LANDING_PATH'], "'/admin'")
        self.assertNotIn('SITE_LANDING_PATH', self.detect(self.project()))

    def test_only_an_install_command_that_takes_seed_counts(self):
        standard = "protected $signature = 'install {--seed}';"
        other = "protected $signature = 'install\n    {--fresh : Drop every table}\n    {--name= : The name}';"

        self.assertEqual(self.detect(self.project(**{'src__App__Console__Commands__Install.php': standard}))['HAS_INSTALL_COMMAND'], "'true'")
        self.assertEqual(self.detect(self.project(**{'src__App__Console__Commands__Install.php': other}))['HAS_INSTALL_COMMAND'], "'false'")
        self.assertEqual(self.detect(self.project(**{'app__Console__Commands__Install.php': 'protected $signature = "install {--seed}";'}))['HAS_INSTALL_COMMAND'], "'true'")
        self.assertEqual(self.detect(self.project())['HAS_INSTALL_COMMAND'], "'false'")

    def test_demo_seeder_and_workers(self):
        root = self.project(**{
            'composer.json': self.composer(**{'laravel/horizon': '^5', 'laravel/reverb': '^1'}),
            'database__seeders__DemoSeeder.php': '',
        })
        values = self.detect(root)

        self.assertEqual(values['HAS_DEMO_SEEDER'], "'true'")
        self.assertEqual(values['USES_HORIZON'], "'true'")
        self.assertEqual(values['USES_REVERB'], "'true'")

        values = self.detect(self.project(**{'composer.json': self.composer()}))
        self.assertEqual(values['HAS_DEMO_SEEDER'], "'false'")
        self.assertEqual(values['USES_HORIZON'], "'false'")
        self.assertEqual(values['USES_REVERB'], "'false'")


class WorkersFromDefaultsTest(unittest.TestCase):
    def workers(self, horizon, reverb):
        script = f'source "{DEFAULTS}"; USES_HORIZON={horizon}; USES_REVERB={reverb}; background_workers'
        return subprocess.run(['bash', '-c', script], capture_output=True, text=True, check=True).stdout.splitlines()

    def test_each_detected_package_gives_its_worker(self):
        self.assertEqual(self.workers('false', 'false'), [])
        self.assertEqual(self.workers('true', 'false'), ['horizon|php artisan horizon'])
        self.assertEqual(
            self.workers('true', 'true'),
            ['horizon|php artisan horizon', 'reverb|php artisan reverb:start --host=127.0.0.1 --port=8080|8080'],
        )


@unittest.skipUnless(shutil.which('php'), 'php is not installed')
class FindSeededPasswordTest(ProjectTestCase):
    def hash(self, password):
        script = "echo password_hash($argv[1], PASSWORD_BCRYPT, ['cost' => 4]);"
        return subprocess.run(['php', '-r', script, '--', password], capture_output=True, text=True, check=True).stdout

    def find(self, root, password_hash):
        return subprocess.run(['php', FIND_PASSWORD, password_hash], cwd=root, capture_output=True, text=True)

    def test_finds_the_password_in_the_install_command(self):
        root = self.project(**{'src__App__Console__Commands__Install.php': "const A = 'info@witify.io';\nconst B = 'Seeded-Secret1';"})

        result = self.find(root, self.hash('Seeded-Secret1'))

        self.assertEqual((result.returncode, result.stdout), (0, 'Seeded-Secret1'))

    def test_finds_the_password_in_a_seeder_or_the_user_factory(self):
        for path in ['database__seeders__DatabaseSeeder.php', 'database__factories__UserFactory.php']:
            root = self.project(**{path: "Hash::make(\"another-one\");"})
            self.assertEqual(self.find(root, self.hash('another-one')).stdout, 'another-one', path)

    def test_a_password_that_is_not_in_the_project_gives_nothing(self):
        root = self.project(**{'src__App__Console__Commands__Install.php': "const B = 'Seeded-Secret1';"})

        result = self.find(root, self.hash('generated-at-random'))

        self.assertEqual((result.returncode, result.stdout), (1, ''))

    def test_a_string_that_is_not_safe_in_single_quotes_is_never_printed(self):
        root = self.project(**{'database__seeders__DatabaseSeeder.php': 'Hash::make("it$\'s-a-password");'})

        result = self.find(root, self.hash("it$'s-a-password"))

        self.assertEqual((result.returncode, result.stdout), (1, ''))


if __name__ == '__main__':
    unittest.main()
