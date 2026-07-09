from django.core.management.base import BaseCommand, CommandError

from annotation.services import calculate_annotator_workload
from payments.services import calculate_payment_summary
from projects.models import Project
from projects.services import calculate_project_progress


class Command(BaseCommand):
    help = "Print a progress, workload, and estimated-payment report for a project."

    def add_arguments(self, parser):
        parser.add_argument("--project-id", type=int, required=True)

    def handle(self, *args, **options):
        try:
            project = Project.objects.get(pk=options["project_id"])
        except Project.DoesNotExist:
            raise CommandError(f"Project {options['project_id']} does not exist")

        progress = calculate_project_progress(project)
        workload = calculate_annotator_workload(project=project)
        payments = calculate_payment_summary(project=project)

        self.stdout.write(self.style.MIGRATE_HEADING(f"Project: {project.title}"))
        self.stdout.write(
            f"  Volumes: {progress['volumes']}  Tasks: {progress['total_tasks']}  "
            f"Approved: {progress['approved_tasks']}  "
            f"Complete: {progress['percent_complete']}%"
        )
        self.stdout.write("  Task status counts:")
        for status, count in progress["status_counts"].items():
            if count:
                self.stdout.write(f"    {status}: {count}")

        self.stdout.write(self.style.MIGRATE_HEADING("Annotator workload:"))
        if not workload:
            self.stdout.write("  (no assigned tasks)")
        for row in workload:
            self.stdout.write(
                f"  {row['username']}: active={row['active']} "
                f"submitted={row['submitted']} approved={row['approved']} "
                f"total={row['total']}"
            )

        self.stdout.write(self.style.MIGRATE_HEADING("Estimated payments:"))
        self.stdout.write(
            f"  Total: {payments['total_amount']} across "
            f"{payments['total_records']} record(s)"
        )
