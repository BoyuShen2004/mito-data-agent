"""Tests for the Manager Admin: access control, actions, and audit protection."""

import tempfile

from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import AnnotatorProfile, UserProfile
from annotation.models import AnnotationTask, ReviewRecord
from annotation.services import assign_task_to_annotator, submit_annotation
from core.choices import TaskStatus, UserRole
from projects.services import create_project
from volumes.services import register_volume

User = get_user_model()

_TMP_ROOT = tempfile.mkdtemp(prefix="mito_admin_test_")

CHANGELISTS = [
    "admin:projects_project_changelist",
    "admin:volumes_volume_changelist",
    "admin:annotation_annotationtask_changelist",
    "admin:annotation_annotationsubmission_changelist",
    "admin:annotation_reviewrecord_changelist",
    "admin:accounts_institution_changelist",
    "admin:accounts_userprofile_changelist",
    "admin:accounts_annotatorprofile_changelist",
]


def make_user(username, role=None, is_staff=False, is_superuser=False):
    user = User.objects.create_user(
        username=username, password="pw", is_staff=is_staff, is_superuser=is_superuser
    )
    if role is not None:
        UserProfile.objects.update_or_create(user=user, defaults={"role": role})
    return user


@override_settings(MITO_DATA_ROOT=_TMP_ROOT)
class AdminAccessTests(TestCase):
    def setUp(self):
        self.superuser = make_user("root", is_staff=True, is_superuser=True)
        self.manager = make_user("mgr", role=UserRole.MANAGER, is_staff=True)
        self.annotator = make_user("ann", role=UserRole.ANNOTATOR, is_staff=False)
        self.requester = make_user("req", role=UserRole.REQUESTER, is_staff=False)

    def test_manager_can_access_index_with_dashboard(self):
        self.client.force_login(self.manager)
        res = self.client.get(reverse("admin:index"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Operational dashboard")
        self.assertContains(res, "Mito Data Agent Manager")

    def test_manager_can_open_every_changelist(self):
        self.client.force_login(self.manager)
        for name in CHANGELISTS:
            res = self.client.get(reverse(name))
            self.assertEqual(res.status_code, 200, f"{name} -> {res.status_code}")

    def test_superuser_can_access(self):
        self.client.force_login(self.superuser)
        self.assertEqual(self.client.get(reverse("admin:index")).status_code, 200)
        self.assertEqual(
            self.client.get(
                reverse("admin:projects_project_changelist")
            ).status_code,
            200,
        )

    def test_annotator_denied(self):
        self.client.force_login(self.annotator)
        res = self.client.get(reverse("admin:projects_project_changelist"))
        self.assertEqual(res.status_code, 302)  # redirected to admin login

    def test_requester_denied(self):
        self.client.force_login(self.requester)
        res = self.client.get(reverse("admin:index"))
        self.assertEqual(res.status_code, 302)

    def test_staff_without_manager_role_denied(self):
        staff_annotator = make_user(
            "staffann", role=UserRole.ANNOTATOR, is_staff=True
        )
        self.client.force_login(staff_annotator)
        res = self.client.get(reverse("admin:index"))
        self.assertEqual(res.status_code, 302)


@override_settings(MITO_DATA_ROOT=_TMP_ROOT)
class AdminActionTests(TestCase):
    def setUp(self):
        self.manager = make_user("mgr", role=UserRole.MANAGER, is_staff=True)
        self.client.force_login(self.manager)
        self.annotator = make_user("ann", role=UserRole.ANNOTATOR)
        AnnotatorProfile.objects.create(
            user=self.annotator, is_active_annotator=True, max_active_tasks=10
        )

    def _volume(self, project, name="v", shape_z=32):
        vol = register_volume(
            project=project, name=name, image_path=f"{name}.tiff",
            autodetect_shape=False,
        )
        vol.shape_x, vol.shape_y, vol.shape_z = 16, 16, shape_z
        vol.save()
        return vol

    # --- project approval ---------------------------------------------------
    def test_approve_projects_action(self):
        project = create_project(title="Pending", created_by=None)
        self.assertFalse(project.manager_reviewed)
        self.client.post(
            reverse("admin:projects_project_changelist"),
            {
                "action": "approve_projects",
                ACTION_CHECKBOX_NAME: [project.pk],
            },
        )
        project.refresh_from_db()
        self.assertTrue(project.manager_reviewed)
        self.assertEqual(project.reviewed_by_id, self.manager.id)

    # --- volume splitting ---------------------------------------------------
    def test_split_action_requires_approved_project(self):
        pending = create_project(title="Pending")  # not reviewed
        vol = self._volume(pending)
        self.client.post(
            reverse("admin:volumes_volume_changelist"),
            {"action": "split_into_frame_tasks", ACTION_CHECKBOX_NAME: [vol.pk]},
        )
        self.assertEqual(vol.tasks.count(), 0)

    def test_split_action_on_approved_volume(self):
        project = create_project(title="Approved", reviewed=True)
        vol = self._volume(project, shape_z=32)
        self.client.post(
            reverse("admin:volumes_volume_changelist"),
            {"action": "split_into_frame_tasks", ACTION_CHECKBOX_NAME: [vol.pk]},
        )
        self.assertEqual(vol.tasks.count(), 2)  # 32 / z_step(16)
        # Re-running does not duplicate tasks.
        self.client.post(
            reverse("admin:volumes_volume_changelist"),
            {"action": "split_into_frame_tasks", ACTION_CHECKBOX_NAME: [vol.pk]},
        )
        self.assertEqual(vol.tasks.count(), 2)

    def test_create_whole_volume_task_action(self):
        project = create_project(title="Approved", reviewed=True)
        vol = self._volume(project)
        self.client.post(
            reverse("admin:volumes_volume_changelist"),
            {"action": "create_whole_volume_tasks", ACTION_CHECKBOX_NAME: [vol.pk]},
        )
        self.assertEqual(vol.tasks.count(), 1)
        task = vol.tasks.first()
        self.assertEqual((task.z_start, task.z_end), (0, vol.shape_z))

    # --- auto assignment ----------------------------------------------------
    def test_auto_assign_action(self):
        project = create_project(title="Approved", reviewed=True)
        self._volume(project, name="a")
        self._volume(project, name="b")
        self.client.post(
            reverse("admin:projects_project_changelist"),
            {"action": "auto_assign_selected", ACTION_CHECKBOX_NAME: [project.pk]},
        )
        tasks = AnnotationTask.objects.filter(project=project)
        self.assertEqual(tasks.count(), 2)
        self.assertEqual(tasks.filter(assigned_to=self.annotator).count(), 2)

    # --- manual assignment form + capacity ----------------------------------
    def test_manual_assign_form_respects_capacity(self):
        capped = make_user("cap", role=UserRole.ANNOTATOR)
        AnnotatorProfile.objects.create(
            user=capped, is_active_annotator=True, max_active_tasks=1
        )
        project = create_project(title="Approved", reviewed=True)
        vol = self._volume(project, shape_z=32)  # 2 tasks after split
        from volumes.services import create_tasks_from_volume

        tasks = create_tasks_from_volume(vol, z_step=16)
        self.client.post(
            reverse("admin:annotation_annotationtask_changelist"),
            {
                "action": "assign_to_annotator",
                ACTION_CHECKBOX_NAME: [t.pk for t in tasks],
                "apply": "Assign tasks",
                "annotator": capped.pk,
            },
        )
        assigned = AnnotationTask.objects.filter(assigned_to=capped).count()
        self.assertEqual(assigned, 1)  # capacity 1 respected
        self.assertEqual(
            AnnotationTask.objects.filter(status=TaskStatus.UNASSIGNED).count(), 1
        )

    def test_unassign_action(self):
        project = create_project(title="Approved", reviewed=True)
        vol = self._volume(project)
        from volumes.services import create_tasks_from_volume

        task = create_tasks_from_volume(vol, z_step=32)[0]
        assign_task_to_annotator(task, annotator=self.annotator)
        self.client.post(
            reverse("admin:annotation_annotationtask_changelist"),
            {"action": "unassign_tasks", ACTION_CHECKBOX_NAME: [task.pk]},
        )
        task.refresh_from_db()
        self.assertIsNone(task.assigned_to_id)
        self.assertEqual(task.status, TaskStatus.UNASSIGNED)


@override_settings(MITO_DATA_ROOT=_TMP_ROOT)
class AdminReviewTests(TestCase):
    def setUp(self):
        self.manager = make_user("mgr", role=UserRole.MANAGER, is_staff=True)
        self.client.force_login(self.manager)
        self.annotator = make_user("ann", role=UserRole.ANNOTATOR)
        AnnotatorProfile.objects.create(user=self.annotator, is_active_annotator=True)
        project = create_project(title="Approved", reviewed=True)
        vol = register_volume(
            project=project, name="v", image_path="v.tiff", autodetect_shape=False
        )
        vol.shape_x, vol.shape_y, vol.shape_z = 8, 8, 16
        vol.save()
        from volumes.services import create_tasks_from_volume

        self.task = create_tasks_from_volume(vol, z_step=16)[0]
        assign_task_to_annotator(self.task, annotator=self.annotator)
        upload = SimpleUploadedFile("label.tif", b"II*\x00data")
        self.submission = submit_annotation(
            task=self.task, annotator=self.annotator, label_file=upload
        )

    def test_approve_submission_action(self):
        self.client.post(
            reverse("admin:annotation_annotationsubmission_changelist"),
            {"action": "approve_selected", ACTION_CHECKBOX_NAME: [self.submission.pk]},
        )
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatus.APPROVED)
        self.assertEqual(self.submission.reviews.count(), 1)

    def test_reject_requires_comments(self):
        url = reverse("admin:annotation_annotationsubmission_changelist")
        # Empty comment -> intermediate form re-rendered, no review created.
        res = self.client.post(
            url,
            {
                "action": "reject_selected",
                ACTION_CHECKBOX_NAME: [self.submission.pk],
                "apply": "Confirm",
                "comments": "",
            },
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(ReviewRecord.objects.count(), 0)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatus.SUBMITTED)

        # With a comment -> review recorded, task rejected.
        self.client.post(
            url,
            {
                "action": "reject_selected",
                ACTION_CHECKBOX_NAME: [self.submission.pk],
                "apply": "Confirm",
                "comments": "Needs cleaner boundaries.",
            },
        )
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatus.REJECTED)
        self.assertEqual(ReviewRecord.objects.count(), 1)

    def test_request_revision_action(self):
        self.client.post(
            reverse("admin:annotation_annotationsubmission_changelist"),
            {
                "action": "request_revision_selected",
                ACTION_CHECKBOX_NAME: [self.submission.pk],
                "apply": "Confirm",
                "comments": "Please fix z-slice 4.",
            },
        )
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatus.REVISION_REQUESTED)


@override_settings(MITO_DATA_ROOT=_TMP_ROOT)
class AdminAuditProtectionTests(TestCase):
    def setUp(self):
        self.manager = make_user("mgr", role=UserRole.MANAGER, is_staff=True)
        self.superuser = make_user("root", is_staff=True, is_superuser=True)
        from annotation.admin import ReviewRecordAdmin
        from django.contrib import admin as dj_admin

        self.review_admin = ReviewRecordAdmin(ReviewRecord, dj_admin.site)

    def _request(self, user):
        from django.test import RequestFactory

        request = RequestFactory().get("/admin/")
        request.user = user
        return request

    def test_review_records_not_addable_or_editable_by_manager(self):
        req = self._request(self.manager)
        self.assertFalse(self.review_admin.has_add_permission(req))
        self.assertFalse(self.review_admin.has_change_permission(req))
        self.assertFalse(self.review_admin.has_delete_permission(req))

    def test_superuser_may_delete_review_records(self):
        req = self._request(self.superuser)
        self.assertTrue(self.review_admin.has_delete_permission(req))

    def test_manager_cannot_add_review_record_via_client(self):
        self.client.force_login(self.manager)
        res = self.client.get(reverse("admin:annotation_reviewrecord_add"))
        self.assertEqual(res.status_code, 403)
