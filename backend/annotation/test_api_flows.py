"""End-to-end API tests for the role-based data-registration + assignment flow."""

import os
import tempfile

from django.contrib.auth.models import User
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import AnnotatorProfile, UserProfile
from annotation.models import AnnotationTask
from core.choices import UserRole
from projects.models import Project
from volumes.services import create_tasks_from_volume

_TMP_ROOT = tempfile.mkdtemp(prefix="mito_api_test_")


@override_settings(MITO_DATA_ROOT=_TMP_ROOT)
class DataRegistrationFlowTests(APITestCase):
    def setUp(self):
        # An HPC directory holding supported + unsupported files.
        self.data_dir = tempfile.mkdtemp(dir=_TMP_ROOT)
        for name in ("crop_a.tif", "crop_b.nii.gz", "ignore.txt"):
            with open(os.path.join(self.data_dir, name), "wb") as fh:
                fh.write(b"II*\x00")

        # A requester (registered through the public endpoint).
        res = self.client.post(
            reverse("api-register"),
            {"username": "req", "password": "pw-abc-12345", "role": "requester"},
        )
        self.assertEqual(res.status_code, 201, res.data)
        self.req_token = res.data["token"]

        # A manager (superuser) and an annotator.
        self.manager = User.objects.create_superuser("mgr", password="x")
        self.annotator = User.objects.create_user("ann", password="x")
        UserProfile.objects.update_or_create(
            user=self.annotator, defaults={"role": UserRole.ANNOTATOR}
        )
        AnnotatorProfile.objects.create(user=self.annotator)

    def _auth(self, token=None, user=None):
        self.client.credentials()
        if token:
            self.client.credentials(HTTP_AUTHORIZATION=f"Token {token}")
        elif user:
            self.client.force_authenticate(user=user)

    def test_requester_registers_data_and_sees_own_project(self):
        self._auth(token=self.req_token)

        # Scan the HPC directory.
        scan = self.client.post(
            reverse("api-hpc-scan"), {"hpc_directory": self.data_dir}
        )
        self.assertEqual(scan.status_code, 200, scan.data)
        names = {f["name"] for f in scan.data["files"]}
        self.assertEqual(names, {"crop_a.tif", "crop_b.nii.gz"})

        # Register the dataset with metadata.
        reg = self.client.post(
            reverse("api-register-data"),
            {
                "dataset": "CortexA",
                "volume": "big_vol",
                "hpc_directory": self.data_dir,
                "metadata": {"organism": "mouse"},
                "files": [
                    {"name": "crop_a.tif", "chunk_id": "c1"},
                    {"name": "crop_b.nii.gz"},
                ],
            },
            format="json",
        )
        self.assertEqual(reg.status_code, 201, reg.data)
        self.assertEqual(len(reg.data["volumes"]), 2)
        project_id = reg.data["project"]["id"]
        self.assertEqual(reg.data["project"]["dataset"], "CortexA")
        self.assertEqual(reg.data["project"]["metadata"]["organism"], "mouse")

        # Requester sees the project in their own list.
        lst = self.client.get(reverse("project-list"))
        self.assertEqual(lst.status_code, 200)
        self.assertEqual([p["id"] for p in lst.data], [project_id])

        # And the project summary (progress) is viewable by the requester.
        summ = self.client.get(reverse("project-summary", args=[project_id]))
        self.assertEqual(summ.status_code, 200)
        self.assertIn("progress", summ.data)

    def test_register_data_rejects_unsupported_file(self):
        self._auth(token=self.req_token)
        res = self.client.post(
            reverse("api-register-data"),
            {
                "dataset": "d",
                "volume": "v",
                "hpc_directory": self.data_dir,
                "files": [{"name": "ignore.txt"}],
            },
            format="json",
        )
        self.assertEqual(res.status_code, 400)

    def test_annotator_cannot_register_data(self):
        self._auth(user=self.annotator)
        res = self.client.post(
            reverse("api-register-data"),
            {"dataset": "d", "volume": "v", "hpc_directory": self.data_dir},
            format="json",
        )
        self.assertEqual(res.status_code, 403)

    def test_manager_manual_assignment(self):
        # Set up a project + a task owned by nobody.
        project = Project.objects.create(title="P", dataset="P", created_by=self.manager)
        from volumes.services import register_volume

        volume = register_volume(
            project=project, name="v", image_path="v.tiff", autodetect_shape=False
        )
        volume.shape_x, volume.shape_y, volume.shape_z = 8, 8, 16
        volume.save()
        task = create_tasks_from_volume(volume, z_step=16)[0]
        self.assertIsNone(task.assigned_to_id)

        # Manager assigns it to the annotator.
        self._auth(user=self.manager)
        res = self.client.post(
            reverse("api-task-assign", args=[task.id]),
            {"annotator_id": self.annotator.id},
            format="json",
        )
        self.assertEqual(res.status_code, 200, res.data)
        task.refresh_from_db()
        self.assertEqual(task.assigned_to_id, self.annotator.id)
        self.assertEqual(task.status, "assigned")

        # Reassigning to null unassigns the same task (no duplicate).
        res = self.client.post(
            reverse("api-task-assign", args=[task.id]),
            {"annotator_id": None},
            format="json",
        )
        self.assertEqual(res.status_code, 200, res.data)
        task.refresh_from_db()
        self.assertIsNone(task.assigned_to_id)
        self.assertEqual(AnnotationTask.objects.count(), 1)

    def test_annotator_cannot_manually_assign(self):
        project = Project.objects.create(title="P2", created_by=self.manager)
        from volumes.services import register_volume

        volume = register_volume(
            project=project, name="v2", image_path="v2.tiff", autodetect_shape=False
        )
        volume.shape_x, volume.shape_y, volume.shape_z = 8, 8, 16
        volume.save()
        task = create_tasks_from_volume(volume, z_step=16)[0]

        self._auth(user=self.annotator)
        res = self.client.post(
            reverse("api-task-assign", args=[task.id]),
            {"annotator_id": self.annotator.id},
            format="json",
        )
        self.assertEqual(res.status_code, 403)
