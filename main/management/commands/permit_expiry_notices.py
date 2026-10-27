"""Tell the owners whose building permit ends within a month (or already ended) that it must be renewed. Run daily."""
from django.core.management.base import BaseCommand

from main.office import permit_extension


class Command(BaseCommand):
    help = 'Notify owners of building permits that are about to expire or have expired.'

    def handle(self, *args, **options):
        self.stdout.write(f'{permit_extension.notify_expiring()} notice(s) sent.')
