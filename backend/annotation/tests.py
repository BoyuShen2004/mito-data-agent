import tempfile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from accounts.models import AnnotatorProfile
from annotation.services import (
    assign_tasks_rule_based,
    calculate_annotator_workload,
    review_submission,
    submit_annotation,
)
from core.choices import (
    LabelType,
    PaymentStatus,
    QCStatus,
    ReviewDecision,
    TaskStatus,
)
from payments.models import PaymentRecord
from projects.services import calculate_project_progress, create_project
from volumes.services import create_tasks_from_volume, register_volume

from .models import AnnotationTask

_TMP_ROOT = tempfile.mkdtemp(prefix="mito_test_")


def make_annotator(username, max_active=5, rate="1.00"):
    user = User.objects.create_user(username=username, password="x")
    AnnotatorProfile.objects.create(
        user=user, is_active_annotator=True, max_active_tasks=max_active,
        pay_rate_per_task=rate,
    )
    return user


@override_settings(MITO_DATA_ROOT=_TMP_ROOT)
class WorkflowIntegrationTests(TestCase):
    def setUp(self):
        self.project = create_project(title="Mito project")
        self.volume = register_volume(
            project=self.project,
            name="vol1",
            image_path="vol1.tiff",
            label_type=LabelType.NONE,
            autodetect_shape=False,
        )
        self.volume.shape_x, self.volume.shape_y, self.volume.shape_z = 64, 64, 32
        self.volume.save()

    def test_full_workflow(self):
        # Split into frame-based tasks.
        tasks = create_tasks_from_volume(self.volume, z_step=16, payment_amount="3.00")
        self.assertEqual(len(tasks), 2)
        self.assertTrue(
            all(t.status == TaskStatus.UNASSIGNED for t in tasks)
        )

        # Assign to an annotator.
        annotator = make_annotator("ann1")
        result = assign_tasks_rule_based(project=self.project)
        self.assertEqual(result["assigned"], 2)
        self.assertEqual(result["remaining_unassigned"], 0)
        task = AnnotationTask.objects.filter(assigned_to=annotator).first()
        self.assertEqual(task.status, TaskStatus.ASSIGNED)
        self.assertIsNotNone(task.assigned_at)

        # Annotator submits a label file; QC runs.
        upload = SimpleUploadedFile(
            "vol1_z0.tif", b"II*\x00fake-tiff-bytes", content_type="image/tiff"
        )
        submission = submit_annotation(
            task=task, annotator=annotator, label_file=upload, notes="done"
        )
        task.refresh_from_db()
        self.assertEqual(task.status, TaskStatus.SUBMITTED)
        self.assertEqual(submission.qc_status, QCStatus.PASSED)

        # Manager approves -> task approved + payment record created.
        manager = User.objects.create_user("mgr", password="x", is_superuser=True)
        review_submission(
            submission=submission,
            reviewer=manager,
            decision=ReviewDecision.APPROVED,
            comments="ok",
        )
        task.refresh_from_db()
        self.assertEqual(task.status, TaskStatus.APPROVED)
        self.assertIsNotNone(task.approved_at)

        payment = PaymentRecord.objects.get(task=task)
        self.assertEqual(str(payment.amount), "3.00")
        self.assertEqual(payment.status, PaymentStatus.APPROVED)

        # Progress reflects one approved of two tasks.
        progress = calculate_project_progress(self.project)
        self.assertEqual(progress["total_tasks"], 2)
        self.assertEqual(progress["approved_tasks"], 1)
        self.assertEqual(progress["percent_complete"], 50.0)

    def test_reject_and_revision_paths(self):
        tasks = create_tasks_from_volume(self.volume, z_step=32)
        annotator = make_annotator("ann2")
        assign_tasks_rule_based(project=self.project)
        task = tasks[0]
        task.refresh_from_db()

        upload = SimpleUploadedFile("x.tif", b"data")
        submission = submit_annotation(task=task, annotator=annotator, label_file=upload)

        review_submission(
            submission=submission, reviewer=None,
            decision=ReviewDecision.REVISION_REQUESTED,
        )
        task.refresh_from_db()
        self.assertEqual(task.status, TaskStatus.REVISION_REQUESTED)
        self.assertFalse(PaymentRecord.objects.filter(task=task).exists())

    def test_qc_rejects_bad_extension(self):
        tasks = create_tasks_from_volume(self.volume, z_step=32)
        annotator = make_annotator("ann3")
        assign_tasks_rule_based(project=self.project)
        task = tasks[0]
        bad = SimpleUploadedFile("notes.txt", b"not a label")
        submission = submit_annotation(task=task, annotator=annotator, label_file=bad)
        self.assertEqual(submission.qc_status, QCStatus.FAILED)


@override_settings(MITO_DATA_ROOT=_TMP_ROOT)
class AssignmentCapacityTests(TestCase):
    def setUp(self):
        self.project = create_project(title="Capacity")
        self.volume = register_volume(
            project=self.project, name="v", image_path="v.tiff",
            label_type=LabelType.NONE, autodetect_shape=False,
        )
        self.volume.shape_x, self.volume.shape_y, self.volume.shape_z = 8, 8, 64
        self.volume.save()

    def test_respects_max_active_tasks(self):
        # 4 tasks, one annotator capped at 2 -> only 2 assigned.
        create_tasks_from_volume(self.volume, z_step=16)
        make_annotator("cap", max_active=2)
        result = assign_tasks_rule_based(project=self.project)
        self.assertEqual(result["assigned"], 2)
        self.assertEqual(result["remaining_unassigned"], 2)

    def test_priority_ordering(self):
        create_tasks_from_volume(self.volume, z_step=16)  # 4 tasks
        # Bump one task's priority; it should be assigned first.
        hi = AnnotationTask.objects.order_by("z_start").last()
        hi.priority = 10
        hi.save()
        make_annotator("solo", max_active=1)
        assign_tasks_rule_based(project=self.project)
        hi.refresh_from_db()
        self.assertEqual(hi.status, TaskStatus.ASSIGNED)

    def test_no_active_annotators_assigns_nothing(self):
        create_tasks_from_volume(self.volume, z_step=16)
        result = assign_tasks_rule_based(project=self.project)
        self.assertEqual(result["assigned"], 0)
        self.assertEqual(calculate_annotator_workload(project=self.project), [])
