"""Guards for the container setup: secrets stay out of the image, the stack is wired the way the docs say."""
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

ROOT = Path(settings.BASE_DIR)


def read(name):
    return (ROOT / name).read_text(encoding='utf-8')


class ContainerSetup(SimpleTestCase):
    def test_secrets_and_local_data_never_enter_the_image(self):
        ignored = read('.dockerignore').split()
        for name in ('.env', 'db.sqlite3', '.git', 'media', 'backups', 'node_modules'):
            self.assertIn(name, ignored)

    def test_container_does_not_run_as_root(self):
        self.assertRegex(read('Dockerfile'), r'(?m)^USER app$')

    def test_compose_has_the_three_services_and_a_private_database(self):
        compose = read('docker-compose.yml')
        for service in ('  db:', '  web:', '  nginx:'):
            self.assertIn(service, compose)
        self.assertNotRegex(compose, r'(?m)^\s+- "?5432')           # PostgreSQL is not published to the host
        self.assertIn('/healthz/', compose)
        self.assertIn('PGSSLMODE: disable', compose)

    def test_monitoring_ui_listens_on_localhost_only(self):
        self.assertIn('"127.0.0.1:3001:3001"', read('docker-compose.yml'))

    def test_example_env_has_placeholders_not_real_secrets(self):
        example = read('.env.docker.example')
        self.assertIn('change-me', example)
        self.assertIn('DEBUG=False', example)

    def test_backup_timer_runs_the_backup_command(self):
        self.assertIn('manage.py backup_db', read('deploy/milkid-backup.service'))
        self.assertIn('OnCalendar', read('deploy/milkid-backup.timer'))
