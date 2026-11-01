#!/usr/bin/env python3
"""Prints what a Witify Laravel project says about itself, as shell assignments.

setup.sh runs this once per snapshot, before PHP exists in the VM. The output is sourced by scripts
that run as root and ends up in apt package names, so only a strict format leaves this file. A value
it cannot read is left out, and defaults.sh applies.
"""
import json
import pathlib
import re
import sys

# The MySQL apt source has one series per LTS, and the image ships 8.0.
SUPPORTED_MYSQL_VERSIONS = ('8.0', '8.4')
INSTALL_COMMANDS = ('src/App/Console/Commands/Install.php', 'app/Console/Commands/Install.php')


def read_composer(root):
    try:
        return json.loads((root / 'composer.json').read_text())
    except (OSError, ValueError):
        return {}


def php_version(composer):
    constraint = str(composer.get('require', {}).get('php', ''))
    minors = re.findall(r'(?<![\d.])8\.(\d{1,2})(?!\d)', constraint)

    # "8.3.* || 8.4.*" allows both: the newest is the closest to what the project moves toward.
    return f'8.{max(map(int, minors))}' if minors else None


def mysql_version(root):
    for workflow in sorted((root / '.github/workflows').glob('*.y*ml')):
        match = re.search(r'\bmysql:(\d+\.\d+)', workflow.read_text(errors='ignore'))
        if match:
            return match.group(1) if match.group(1) in SUPPORTED_MYSQL_VERSIONS else None

    return None


def has_seed_install_command(root):
    for path in INSTALL_COMMANDS:
        file = root / path
        if file.is_file() and re.search(r"\$signature\s*=\s*['\"]install\s*\{--seed\}", file.read_text(errors='ignore')):
            return True

    return False


def detect(root):
    composer = read_composer(root)
    packages = composer.get('require', {})

    values = {
        'PHP_VERSION': php_version(composer),
        'MYSQL_VERSION': mysql_version(root),
        'APP_DATABASE': re.sub(r'[^a-z0-9]+', '_', root.name.lower()).strip('_') or None,
        'SITE_LANDING_PATH': '/admin' if (root / 'routes/admin.php').is_file() else None,
        'HAS_INSTALL_COMMAND': str(has_seed_install_command(root)).lower(),
        'HAS_DEMO_SEEDER': str((root / 'database/seeders/DemoSeeder.php').is_file()).lower(),
        'USES_HORIZON': str('laravel/horizon' in packages).lower(),
        'USES_REVERB': str('laravel/reverb' in packages).lower(),
    }

    return {name: value for name, value in values.items() if value is not None}


if __name__ == '__main__':
    for name, value in detect(pathlib.Path(sys.argv[1])).items():
        print(f"{name}='{value}'")
