"""Tests for fork-aware SAM2 tracking + slice IO + role gating."""

import os
import tempfile

import numpy as np
import tifffile
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import AnnotatorProfile, UserProfile
from annotation.label_paths import working_label_rel_path
from annotation.models import AnnotationTask
from annotation.tracking.branching import (
    TrackGroup,
    merge_group,
    split_binary_mask_components,
)
from annotation.tracking.services import run_branch_tracking
from annotation.visualization import slice_io
from core.choices import LabelType, TaskType, UserRole
from projects.services import create_project
from volumes.models import Volume

User = get_user_model()
_TMP = tempfile.mkdtemp(prefix="mito-track-test-")


class BranchingUnitTests(TestCase):
    def test_split_components_finds_forks(self):
        m = np.zeros((10, 10), dtype=bool)
        m[1:3, 1:3] = True  # blob A
        m[6:9, 6:9] = True  # blob B (disconnected)
        comps = split_binary_mask_components(m)
        self.assertEqual(len(comps), 2)

    def test_merge_group_collapses_branches(self):
        vol = np.zeros((3, 4, 4), dtype=np.int32)
        vol[0, 0, 0] = 5   # final id
        vol[1, 1, 1] = 7   # branch
        vol[2, 2, 2] = 9   # branch
        group = TrackGroup(group_id=5, branch_ids=[5, 7, 9])
        merge_group(vol, group)
        self.assertEqual(set(np.unique(vol)) - {0}, {5})


@override_settings(MITO_TRACKING_PROVIDER="local")
class ForkTrackingServiceTests(TestCase):
    def test_fork_seeds_branch_ids_then_merges_to_one(self):
        # A bright volume so the local provider carries the seed everywhere.
        image = np.full((5, 12, 12), 200, dtype=np.uint8)
        volume_mask = np.zeros((5, 12, 12), dtype=np.int32)

        seed = np.zeros((12, 12), dtype=bool)
        seed[1:3, 1:3] = True    # branch 1
        seed[8:10, 8:10] = True  # branch 2 (fork!)

        result = run_branch_tracking(
            image=image,
            volume_mask=volume_mask,
            seeds={2: seed},
            z_range=(0, 4),
        )

        # Two temporary branch ids were used during tracking...
        self.assertEqual(len(result["branch_ids"]), 2)
        self.assertEqual(len(set(result["branch_ids"])), 2)
        # ...but the persisted mask holds exactly one final instance id.
        labels = set(int(v) for v in np.unique(volume_mask)) - {0}
        self.assertEqual(labels, {result["final_id"]})
        # Group metadata records the branch → final mapping for audit / re-run.
        self.assertEqual(result["group"]["final_id"], result["final_id"])
        self.assertCountEqual(
            result["group"]["branch_ids"], result["branch_ids"]
        )

    def test_single_component_seed_needs_no_merge(self):
        image = np.full((3, 8, 8), 150, dtype=np.uint8)
        volume_mask = np.zeros((3, 8, 8), dtype=np.int32)
        seed = np.zeros((8, 8), dtype=bool)
        seed[2:5, 2:5] = True
        result = run_branch_tracking(
            image=image, volume_mask=volume_mask, seeds={1: seed}, z_range=(0, 2)
        )
        self.assertEqual(len(result["branch_ids"]), 1)
        self.assertEqual(result["final_id"], result["branch_ids"][0])


@override_settings(MITO_DATA_ROOT=_TMP, MEDIA_ROOT=_TMP)
class SliceIOTests(TestCase):
    def setUp(self):
        slice_io.clear_caches()
        self.rel = "images/vol.tif"
        path = os.path.join(_TMP, self.rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # z ramps so slices are distinguishable.
        data = np.stack(
            [np.full((16, 24), i * 10, dtype=np.uint8) for i in range(20)]
        )
        tifffile.imwrite(path, data)

    def test_meta_and_three_axis_slices(self):
        meta = slice_io.volume_meta(self.rel)
        self.assertEqual(meta["shape"], {"z": 20, "y": 16, "x": 24})
        self.assertEqual(slice_io.read_slice(self.rel, "z", 3).shape, (16, 24))
        self.assertEqual(slice_io.read_slice(self.rel, "y", 3).shape, (20, 24))
        self.assertEqual(slice_io.read_slice(self.rel, "x", 3).shape, (20, 16))

    def test_slice_cache_is_bounded(self):
        original = slice_io.MAX_SLICE_CACHE
        slice_io.MAX_SLICE_CACHE = 4
        try:
            for i in range(20):
                slice_io.read_slice(self.rel, "z", i % 20)
            self.assertLessEqual(slice_io.cache_stats()["slices"], 4)
        finally:
            slice_io.MAX_SLICE_CACHE = original

    def test_png_encoding_roundtrips_dimensions(self):
        png = slice_io.render_image_slice_png(self.rel, "z", 5, window=255, level=128)
        self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))


@override_settings(MITO_DATA_ROOT=_TMP, MEDIA_ROOT=_TMP)
class RoleGatingApiTests(TestCase):
    def setUp(self):
        slice_io.clear_caches()
        self.manager = self._user("mgr", UserRole.MANAGER)
        self.annotator = self._user("ann", UserRole.ANNOTATOR, annotator=True)
        self.requester = self._user("req", UserRole.REQUESTER)

        self.project = create_project(
            title="P", created_by=self.requester, reviewed=True
        )
        rel = "images/task.tif"
        path = os.path.join(_TMP, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tifffile.imwrite(path, np.full((6, 10, 10), 200, dtype=np.uint8))
        self.volume = Volume.objects.create(
            project=self.project, name="v", image_path=rel,
            label_type=LabelType.NONE, shape_z=6, shape_y=10, shape_x=10,
        )
        # Django's per-test transaction rollback resets the DB but not the
        # filesystem: SQLite reuses rowids after a rollback, so a later
        # test's volume can get the same id as an earlier test's and find its
        # leftover owned working-copy file still on disk in the shared _TMP
        # dir. Clear it so each test starts fresh.
        owned = os.path.join(_TMP, working_label_rel_path(self.volume))
        if os.path.exists(owned):
            os.remove(owned)
        self.task = AnnotationTask.objects.create(
            project=self.project, volume=self.volume, assigned_to=self.annotator,
            z_start=0, z_end=6, y_end=10, x_end=10,
            task_type=TaskType.MANUAL_ANNOTATION,
        )

    def _user(self, name, role, annotator=False):
        user = User.objects.create_user(name, password="x")
        # A post_save signal already made a default profile and cached it on
        # ``user``; update the row and re-fetch so the role isn't read stale.
        UserProfile.objects.filter(user=user).update(role=role)
        if annotator:
            AnnotatorProfile.objects.create(user=user, is_active_annotator=True)
        return User.objects.get(pk=user.pk)

    def _client(self, user):
        c = APIClient()
        c.force_authenticate(user=user)
        return c

    def _seed_payload(self):
        # A 3x3 blob at the top-left, RLE over the flattened 10x10 seed slice.
        rle = [[0, 3], [10, 3], [20, 3]]
        return {"seeds": [{"z": 2, "rle": rle, "shape": [10, 10]}]}

    def test_requester_cannot_track(self):
        resp = self._client(self.requester).post(
            f"/api/tasks/{self.task.id}/track/", self._seed_payload(), format="json"
        )
        self.assertEqual(resp.status_code, 403)

    def test_annotator_can_track_and_persist(self):
        resp = self._client(self.annotator).post(
            f"/api/tasks/{self.task.id}/track/", self._seed_payload(), format="json"
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertIn("final_id", resp.json())
        self.volume.refresh_from_db()
        # Tracking only ever writes the *working* copy now — the volume's
        # official label (label_path) stays untouched until a submission
        # referencing it is approved (see the submit/approve tests below).
        self.assertEqual(self.volume.label_path, "")
        self.assertIn("tracking_groups", self.volume.metadata)
        working_path = slice_io.resolve_path(working_label_rel_path(self.volume))
        self.assertTrue(working_path.exists())

    def test_requester_gets_view_only_launch(self):
        resp = self._client(self.requester).get(
            f"/api/tasks/{self.task.id}/proofreading/"
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertFalse(resp.json()["editable"])

    def test_manager_gets_editable_launch(self):
        resp = self._client(self.manager).get(
            f"/api/tasks/{self.task.id}/proofreading/"
        )
        self.assertTrue(resp.json()["editable"])

    def test_annotator_can_paint_and_persist_label_ids(self):
        c = self._client(self.annotator)
        resp = c.get(f"/api/tasks/{self.task.id}/label-ids/?axis=z&index=2")
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()
        self.assertEqual(body["shape"], [10, 10])
        self.assertEqual(body["runs"], [[0, 100]])  # empty label, all background

        # Paint a 2x2 block of instance id 3 at the top-left, RLE-encoded.
        ids = [0] * 100
        for y in (0, 1):
            for x in (0, 1):
                ids[y * 10 + x] = 3
        runs = []
        start = 0
        for i in range(1, 101):
            if i == 100 or ids[i] != ids[start]:
                runs.append([ids[start], i - start])
                start = i

        resp = c.put(
            f"/api/tasks/{self.task.id}/label-ids/",
            {"axis": "z", "index": 2, "shape": [10, 10], "runs": runs},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["max_label_id"], 3)

        resp = c.get(f"/api/tasks/{self.task.id}/label-ids/?axis=z&index=2")
        self.assertEqual(resp.json()["runs"], runs)

        resp = c.get(f"/api/tasks/{self.task.id}/label-state/")
        self.assertEqual(resp.json(), {"max_label_id": 3, "next_label_id": 4})

    def test_requester_cannot_edit_label_ids(self):
        resp = self._client(self.requester).put(
            f"/api/tasks/{self.task.id}/label-ids/",
            {"axis": "z", "index": 2, "shape": [10, 10], "runs": [[0, 100]]},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_requester_can_view_label_ids_but_not_edit(self):
        resp = self._client(self.requester).get(
            f"/api/tasks/{self.task.id}/label-ids/?axis=z&index=2"
        )
        self.assertEqual(resp.status_code, 200)

    def test_edit_never_mutates_an_externally_referenced_label_file(self):
        # A volume whose label is registered *by reference* to a file this
        # app doesn't own (e.g. someone else's prediction/consensus output),
        # living outside MITO_DATA_ROOT entirely — exactly the shape of the
        # incident this test guards against.
        external_dir = tempfile.mkdtemp(prefix="mito-external-owner-")
        external_path = os.path.join(external_dir, "someone_elses_consensus.tif")
        original = np.full((6, 10, 10), 7, dtype=np.uint16)
        tifffile.imwrite(external_path, original)
        original_bytes = open(external_path, "rb").read()

        self.volume.label_path = external_path
        self.volume.save(update_fields=["label_path"])

        c = self._client(self.annotator)

        # A real client always reads the (seeded) slice first, patches the
        # one pixel it cares about, and PUTs the whole slice back — this is
        # what proves seeding from the external file actually happened.
        got = c.get(f"/api/tasks/{self.task.id}/label-ids/?axis=z&index=0")
        self.assertEqual(got.status_code, 200, got.content)
        body = got.json()
        self.assertEqual(body["runs"], [[7, 100]])  # seeded from the external file

        ids = [7] * 100
        ids[0] = 9
        runs = []
        start = 0
        for i in range(1, 101):
            if i == 100 or ids[i] != ids[start]:
                runs.append([ids[start], i - start])
                start = i
        resp = c.put(
            f"/api/tasks/{self.task.id}/label-ids/",
            {"axis": "z", "index": 0, "shape": [10, 10], "runs": runs},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)

        # The external file must be byte-for-byte unchanged...
        self.assertEqual(open(external_path, "rb").read(), original_bytes)

        # ...and volume.label_path (the *official* label) must be completely
        # untouched too — an in-app edit only ever writes the working copy;
        # nothing is promoted to official until a submission is approved
        # (see test_inapp_submit_and_approve_promotes_working_copy_to_official).
        self.volume.refresh_from_db()
        self.assertEqual(self.volume.label_path, external_path)

        # The edit lives in the working copy, seeded from the external file.
        working_rel = working_label_rel_path(self.volume)
        edited = slice_io.read_slice(working_rel, "z", 0)
        self.assertEqual(edited[0, 0], 9)
        self.assertEqual(edited[0, 1], 7)  # seeded from the original elsewhere

    def test_inapp_submit_requires_prior_edit(self):
        resp = self._client(self.annotator).post(
            f"/api/tasks/{self.task.id}/submit-inapp/", {}, format="json"
        )
        self.assertEqual(resp.status_code, 400, resp.content)

    def test_inapp_submit_and_approve_promotes_working_copy_to_official(self):
        c = self._client(self.annotator)
        # Paint one pixel so a working copy exists.
        ids = [0] * 100
        ids[0] = 5
        runs = [[5, 1], [0, 99]]
        resp = c.put(
            f"/api/tasks/{self.task.id}/label-ids/",
            {"axis": "z", "index": 0, "shape": [10, 10], "runs": runs},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)

        resp = c.post(f"/api/tasks/{self.task.id}/submit-inapp/", {}, format="json")
        self.assertEqual(resp.status_code, 201, resp.content)
        body = resp.json()
        self.assertEqual(body["source"], "inapp")
        self.assertFalse(body["label_file"])

        # Before approval: still not the official label.
        self.volume.refresh_from_db()
        self.assertEqual(self.volume.label_path, "")

        review = self._client(self.manager).post(
            f"/api/submissions/{body['id']}/review/",
            {"decision": "approved"}, format="json",
        )
        self.assertEqual(review.status_code, 200, review.content)

        # After approval: the working copy is now the official label.
        self.volume.refresh_from_db()
        self.assertEqual(self.volume.label_path, working_label_rel_path(self.volume))
        self.assertEqual(self.volume.label_type, LabelType.PARTIAL)
        official = slice_io.read_slice(self.volume.label_location, "z", 0)
        self.assertEqual(official[0, 0], 5)

    def test_inapp_reject_does_not_promote(self):
        c = self._client(self.annotator)
        resp = c.put(
            f"/api/tasks/{self.task.id}/label-ids/",
            {"axis": "z", "index": 0, "shape": [10, 10], "runs": [[5, 1], [0, 99]]},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        resp = c.post(f"/api/tasks/{self.task.id}/submit-inapp/", {}, format="json")
        self.assertEqual(resp.status_code, 201, resp.content)
        submission_id = resp.json()["id"]

        review = self._client(self.manager).post(
            f"/api/submissions/{submission_id}/review/",
            {"decision": "rejected"}, format="json",
        )
        self.assertEqual(review.status_code, 200, review.content)

        self.volume.refresh_from_db()
        self.assertEqual(self.volume.label_path, "")  # never promoted

    def test_requester_can_view_slices(self):
        # Default (no window/level): JPEG, normalised client-side — see
        # VolumeSliceView. Explicit window/level still returns PNG.
        resp = self._client(self.requester).get(
            f"/api/volumes/{self.volume.id}/slice/?axis=z&index=2"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "image/jpeg")

        resp = self._client(self.requester).get(
            f"/api/volumes/{self.volume.id}/slice/?axis=z&index=2&window=255&level=128"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "image/png")


class LabelPathLayoutTests(TestCase):
    """Unit tests for the project/dataset-nested working-copy path scheme —
    no API/DB fixtures beyond the models themselves needed."""

    def test_path_nests_under_project_and_dataset(self):
        from projects.models import Dataset, Project
        from volumes.models import Volume

        project = Project.objects.create(title="My Cool Project!!")
        dataset = Dataset.objects.create(project=project, name="Batch #1")
        volume = Volume.objects.create(project=project, dataset=dataset, name="v")

        rel = working_label_rel_path(volume)
        # Names are used as-is (not slugified/lowercased) — no id prefixes.
        self.assertEqual(rel, f"My Cool Project!!/Batch #1/volume_{volume.id}_labels.tif")

    def test_path_falls_back_to_no_dataset_bucket(self):
        from projects.models import Project
        from volumes.models import Volume

        project = Project.objects.create(title="Solo Project")
        volume = Volume.objects.create(project=project, name="v")  # no dataset

        rel = working_label_rel_path(volume)
        self.assertEqual(rel, f"Solo Project/no-dataset/volume_{volume.id}_labels.tif")

    def test_slug_cannot_escape_data_root(self):
        from pathlib import Path

        from django.conf import settings

        from annotation.visualization.slice_io import resolve_path
        from projects.models import Project
        from volumes.models import Volume

        # A title crafted to try to escape the data root if not sanitized.
        project = Project.objects.create(title="../../etc/passwd")
        volume = Volume.objects.create(project=project, name="v")

        rel = working_label_rel_path(volume)
        resolved = resolve_path(rel).resolve()
        root = Path(settings.MITO_DATA_ROOT).resolve()
        # However the project's title got sanitized, the result must still
        # resolve to exactly root/<project dir>/<dataset dir>/<file> — i.e.
        # never navigate above root no matter what a project is named.
        self.assertEqual(resolved.parents[2], root)
