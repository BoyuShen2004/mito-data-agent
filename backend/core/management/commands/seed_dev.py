"""Load the standard mock dataset for local development.

    python manage.py seed_dev

Creates the standard accounts (manager / alice / bob / lab_requester, password
"demo12345"), registers a demo dataset from mock TIFF volumes, splits a volume
into tasks, assigns a couple, and leaves one submission awaiting review.

Safe to run repeatedly (idempotent for the accounts/dataset). Use ``--fresh`` to
wipe existing development data first.
"""

from django.core.management import call_command
from django.core.management.base import BaseCommand

from core.dev_data import DEMO_PASSWORD, seed_standard_data


class Command(BaseCommand):
    help = "Load the standard mock dataset used during development."

    def add_arguments(self, parser):
        parser.add_argument(
            "--fresh",
            action="store_true",
            help="Clear existing development data before seeding.",
        )

    def handle(self, *args, **options):
        if options["fresh"]:
            call_command("clear_dev_data", "--no-input", "--files")

        result = seed_standard_data(log=self.stdout.write)

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded project #{result['project_id']} "
                f"({result['volumes']} volume(s), {result['tasks']} task(s))."
            )
        )
        self.stdout.write(
            "Logins (password "
            + self.style.WARNING(DEMO_PASSWORD)
            + "): manager, alice, bob (annotators), lab_requester (requester)."
        )
