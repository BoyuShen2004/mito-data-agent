import tempfile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from accounts.models import AnnotatorProfile
from annotation.services import (
    assign_task_to_annotator,
    assign_tasks_rule_based,
    auto_assign_project,
    calculate_annotator_workload,
    ensure_volume_tasks,
    review_submission,
    submit_annotation,
)
from core.choices import (
    LabelType,
    QCStatus,
    ReviewDecision,
    TaskStatus,
)
from projects.services import calculate_project_progress, create_project
from volumes.services import create_tasks_from_volume, register_volume

from .models import AnnotationTask

_TMP_ROOT = tempfile.mkdtemp(prefix="mito_test_")


def make_annotator(username, max_active=5):
    user = User.objects.create_user(username=username, password="x")
    AnnotatorProfile.objects.create(
        user=user, is_active_annotator=True, max_active_tasks=max_active,
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
        tasks = create_tasks_from_volume(self.volume, z_step=16)
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

        # Manager approves -> task approved (annotation work is unpaid).
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

    def test_even_distribution_across_annotators(self):
        # 4 tasks, 2 annotators -> 2 each (balanced, not piled on one).
        create_tasks_from_volume(self.volume, z_step=16)
        a = make_annotator("bal_a", max_active=10)
        b = make_annotator("bal_b", max_active=10)
        result = assign_tasks_rule_based(project=self.project)
        self.assertEqual(result["assigned"], 4)
        self.assertEqual(result["per_user"][a.id], 2)
        self.assertEqual(result["per_user"][b.id], 2)


@override_settings(MITO_DATA_ROOT=_TMP_ROOT)
class AutoAssignVolumeTests(TestCase):
    def _volume(self, project, name, shape_z=32, label_type=LabelType.NONE):
        vol = register_volume(
            project=project, name=name, image_path=f"{name}.tiff",
            label_type=label_type, autodetect_shape=False,
        )
        vol.shape_x, vol.shape_y, vol.shape_z = 16, 16, shape_z
        vol.save()
        return vol

    def test_ensure_volume_tasks_one_task_per_volume(self):
        project = create_project(title="P", reviewed=True)
        self._volume(project, "v1")
        self._volume(project, "v2")
        result = ensure_volume_tasks(project)
        self.assertEqual(result["created"], 2)
        tasks = AnnotationTask.objects.filter(project=project)
        self.assertEqual(tasks.count(), 2)
        # Each task spans its whole volume (no frame splitting).
        for t in tasks:
            self.assertEqual(t.z_start, 0)
            self.assertEqual(t.z_end, t.volume.shape_z)

    def test_volume_without_shape_is_skipped(self):
        project = create_project(title="P", reviewed=True)
        register_volume(
            project=project, name="noshape", image_path="noshape.tiff",
            autodetect_shape=False,
        )
        result = ensure_volume_tasks(project)
        self.assertEqual(result, {"created": 0, "skipped": 1})

    def test_auto_assign_distributes_volumes_evenly(self):
        # 8 volumes, 4 annotators -> 2 volumes each.
        project = create_project(title="Eight", reviewed=True)
        for i in range(8):
            self._volume(project, f"vol{i}")
        annotators = [make_annotator(f"ann{i}", max_active=10) for i in range(4)]

        summary = auto_assign_project(project)

        self.assertTrue(summary["reviewed"])
        self.assertEqual(summary["created_tasks"], 8)
        self.assertEqual(summary["assigned"], 8)
        for ann in annotators:
            self.assertEqual(summary["per_user"][ann.id], 2)

    def test_auto_assign_blocked_until_reviewed(self):
        project = create_project(title="Pending")  # reviewed defaults to False
        self._volume(project, "v1")
        make_annotator("solo", max_active=10)

        summary = auto_assign_project(project)

        self.assertFalse(summary["reviewed"])
        self.assertEqual(summary["assigned"], 0)
        self.assertEqual(AnnotationTask.objects.filter(project=project).count(), 0)
