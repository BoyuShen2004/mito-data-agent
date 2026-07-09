from django.core.management.base import BaseCommand, CommandError

from volumes.models import Volume
from volumes.services import create_tasks_from_volume


class Command(BaseCommand):
    help = "Split a volume into frame-based annotation tasks."

    def add_arguments(self, parser):
        parser.add_argument("--volume-id", type=int, required=True)
        parser.add_argument("--z-step", type=int, default=16)
        parser.add_argument("--payment-amount", type=float, default=0)
        parser.add_argument(
            "--task-type",
            default=None,
            help="Override the inferred task type (required for partial labels).",
        )

    def handle(self, *args, **options):
        try:
            volume = Volume.objects.get(pk=options["volume_id"])
        except Volume.DoesNotExist:
            raise CommandError(f"Volume {options['volume_id']} does not exist")

        try:
            tasks = create_tasks_from_volume(
                volume,
                z_step=options["z_step"],
                payment_amount=options["payment_amount"],
                task_type=options["task_type"],
            )
        except ValueError as exc:
            raise CommandError(str(exc))

        self.stdout.write(
            self.style.SUCCESS(
                f"Created {len(tasks)} tasks for volume '{volume.name}' "
                f"(type={tasks[0].task_type if tasks else 'n/a'})."
            )
        )
