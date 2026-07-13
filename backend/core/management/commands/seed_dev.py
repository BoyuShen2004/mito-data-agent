"""Create the standard development accounts.

    python manage.py seed_dev

Creates one manager and four annotator accounts (password "demo12345"). It does
**not** register any datasets, volumes, or tasks — developers register data
manually through the app (as the manager, or by signing up a requester).

Safe to run repeatedly. Use ``--fresh`` to wipe existing development data first.
"""

from django.core.management import call_command
from django.core.management.base import BaseCommand

from core.dev_data import DEMO_PASSWORD, seed_standard_data


class Command(BaseCommand):
    help = "Create the standard development accounts (manager + annotators, no data)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--fresh",
            action="store_true",
            help="Clear existing development data before seeding accounts.",
        )

    def handle(self, *args, **options):
        if options["fresh"]:
            call_command("clear_dev_data", "--no-input")

        result = seed_standard_data(log=self.stdout.write)

        self.stdout.write(
            self.style.SUCCESS(
                f"Ready: {len(result['managers'])} manager, "
                f"{len(result['annotators'])} annotator account(s)."
            )
        )
        self.stdout.write(
            "Manager: "
            + ", ".join(result["managers"])
            + " · Annotators: "
            + ", ".join(result["annotators"])
            + " · password "
            + self.style.WARNING(DEMO_PASSWORD)
        )
        self.stdout.write(
            "No data is pre-registered — register datasets manually in the app."
        )
