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

    def test_register_image_mask_pairs_via_endpoint(self):
        # A folder with an image+mask pair plus an unrelated volume.
        import os

        pair_dir = os.path.join(self.data_dir, "pairs")
        os.makedirs(pair_dir, exist_ok=True)
        for name in ("s1_image.tif", "s1_mask.tif", "s2_image.tif"):
            with open(os.path.join(pair_dir, name), "wb") as fh:
                fh.write(b"II*\x00")

        self._auth(token=self.req_token)

        # Scan surfaces the auto-detected pair.
        scan = self.client.post(reverse("api-hpc-scan"), {"hpc_directory": pair_dir})
        self.assertEqual(scan.status_code, 200, scan.data)
        self.assertEqual(len(scan.data["pairs"]), 1)
        self.assertEqual(scan.data["pairs"][0]["image"], "s1_image.tif")
        self.assertEqual(scan.data["pairs"][0]["mask"], "s1_mask.tif")

        # Register just the explicit pair out of the folder.
        reg = self.client.post(
            reverse("api-register-data"),
            {
                "dataset": "Paired",
                "volume": "v",
                "hpc_directory": pair_dir,
                "label_type": "proofread",
                "pairs": [{"image": "s1_image.tif", "mask": "s1_mask.tif"}],
            },
            format="json",
        )
        self.assertEqual(reg.status_code, 201, reg.data)
        self.assertEqual(len(reg.data["volumes"]), 1)
        vol = reg.data["volumes"][0]
        self.assertTrue(vol["label_location"].endswith("s1_mask.tif"))
        self.assertEqual(vol["label_type"], "proofread")

    def test_review_gate_then_auto_assign_distributes_volumes(self):
        import os

        import numpy as np
        import tifffile

        # Real TIFFs so shape auto-detection works and tasks can be created.
        vol_dir = os.path.join(self.data_dir, "vols")
        os.makedirs(vol_dir, exist_ok=True)
        for i in range(2):
            tifffile.imwrite(
                os.path.join(vol_dir, f"v{i}.tif"),
                np.zeros((8, 16, 16), dtype=np.uint8),
            )

        # Requester registers -> project is pending manager review.
        self._auth(token=self.req_token)
        reg = self.client.post(
            reverse("api-register-data"),
            {"dataset": "Gated", "volume": "v", "hpc_directory": vol_dir},
            format="json",
        )
        self.assertEqual(reg.status_code, 201, reg.data)
        project_id = reg.data["project"]["id"]
        self.assertFalse(reg.data["project"]["manager_reviewed"])

        # Auto-assign is blocked until the manager reviews.
        self._auth(user=self.manager)
        blocked = self.client.post(
            reverse("api-assign-tasks", args=[project_id]), {}, format="json"
        )
        self.assertEqual(blocked.status_code, 400)
        self.assertFalse(blocked.data["reviewed"])

        # Manager approves the dataset.
        rev = self.client.post(
            reverse("project-review", args=[project_id]), {}, format="json"
        )
        self.assertEqual(rev.status_code, 200, rev.data)
        self.assertTrue(rev.data["manager_reviewed"])

        # Now auto-assign creates one task per volume and assigns them.
        res = self.client.post(
            reverse("api-assign-tasks", args=[project_id]), {}, format="json"
        )
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["created_tasks"], 2)
        self.assertEqual(res.data["assigned"], 2)

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
        # Set up a reviewed project + a task owned by nobody.
        project = Project.objects.create(
            title="P", dataset="P", created_by=self.manager, manager_reviewed=True
        )
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
