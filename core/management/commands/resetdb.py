from django.core.management.base import BaseCommand

from core.testdb import run_testdb

class Command(BaseCommand):
    help = 'Resets the database to a known test state'

    def add_arguments(self, parser):\
        pass

    def handle(self, *args, **options):
        run_testdb()