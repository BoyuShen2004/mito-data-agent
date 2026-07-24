"""Tests for the Cellable-ported interactive AI tools (Point/Box/Boundary
mask, 3D watershed Seeds) and the Labels-panel/3D-preview summaries.

Follows the same tempdir + ``@override_settings(MITO_DATA_ROOT=...)``
fixture pattern as ``test_tracking.py`` — see
``progress/history/04-incident-data-safety.md`` for why every destructive
test in this app isolates its filesystem like this rather than touching the
real dev database.
"""

import os
import tempfile
import unittest
import unittest.mock

import numpy as np
import tifffile
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import AnnotatorProfile, UserProfile
from annotation.cellable_port.labels_3d import label_summary, labels_3d_preview
from annotation.cellable_port.watershed import WatershedError, run_watershed_3d
from annotation.label_paths import working_label_rel_path
from annotation.models import AnnotationTask
from annotation.visualization import slice_io
from core.choices import LabelType, TaskType, UserRole
from projects.services import create_project
from volumes.models import Volume

User = get_user_model()
_TMP = tempfile.mkdtemp(prefix="mito-cellable-port-test-")


@override_settings(MITO_DATA_ROOT=_TMP)
class EfficientSamRuntimeUnitTests(TestCase):
    """Thread-count resolution (ORT affinity-spam fix) and the on-disk
    embedding cache — no ONNX session needed for either.

    ``MITO_DATA_ROOT`` overridden to the shared tempdir: ``embed_cache``
    resolves paths under this setting, and writing cache files under the
    *real* data root from a test is exactly the mistake
    `progress/history/04-incident-data-safety.md` exists to prevent.
    """

    def test_thread_count_prefers_slurm_env(self):
        from annotation.cellable_port.ai.efficient_sam import _resolve_thread_count

        with unittest.mock.patch.dict(os.environ, {"SLURM_CPUS_PER_TASK": "3"}):
            self.assertEqual(_resolve_thread_count(), 3)

    def test_thread_count_caps_at_max(self):
        from annotation.cellable_port.ai.efficient_sam import (
            _MAX_INTRA_OP_THREADS,
            _resolve_thread_count,
        )

        with unittest.mock.patch.dict(os.environ, {"SLURM_CPUS_PER_TASK": "999"}):
            self.assertEqual(_resolve_thread_count(), _MAX_INTRA_OP_THREADS)

    def test_thread_count_ignores_garbage_slurm_value(self):
        from annotation.cellable_port.ai.efficient_sam import _resolve_thread_count

        with unittest.mock.patch.dict(os.environ, {"SLURM_CPUS_PER_TASK": "not-a-number"}):
            self.assertGreaterEqual(_resolve_thread_count(), 1)

    def test_embed_cache_round_trip(self):
        from annotation.cellable_port.ai import embed_cache

        path = embed_cache.cache_path_for(1, "z", 5, "vits", 12345.0)
        self.assertIsNone(embed_cache.load(path))  # nothing written yet
        arr = np.random.rand(1, 4, 5, 5).astype(np.float32)
        embed_cache.save(path, arr)
        loaded = embed_cache.load(path)
        self.assertIsNotNone(loaded)
        np.testing.assert_array_equal(loaded, arr)

    def test_embed_cache_key_changes_with_variant_and_mtime(self):
        from annotation.cellable_port.ai import embed_cache

        a = embed_cache.cache_path_for(1, "z", 5, "vits", 100.0)
        b = embed_cache.cache_path_for(1, "z", 5, "vitt", 100.0)
        c = embed_cache.cache_path_for(1, "z", 5, "vits", 200.0)
        self.assertNotEqual(a, b)
        self.assertNotEqual(a, c)


class WatershedUnitTests(TestCase):
    """Pure numpy tests for the ported segmentation core — no Django/HTTP."""

    def test_splits_dumbbell_into_two_labels(self):
        # A "dumbbell": two 4x4x4 blobs joined by a thin 1-voxel-wide neck,
        # all currently one instance id (5). Seeding one point in each lobe
        # should split the neck at the watershed ridge.
        mask = np.zeros((10, 10, 10), dtype=np.int32)
        mask[1:5, 1:5, 1:5] = 5
        mask[1:5, 1:5, 8:9] = 5  # bridge/neck (thin)
        mask[1:5, 1:5, 9:10] = 0
        mask[1:5, 1:5, 6:10] = 5  # second lobe + neck, connected

        result = run_watershed_3d(mask, target_label=5, seeds_zyx=[(2, 2, 2), (2, 2, 8)])
        self.assertEqual(result["target_label"], 5)
        self.assertEqual(len(result["new_label_ids"]), 1)
        new_id = result["new_label_ids"][0]
        remaining_ids = set(int(v) for v in np.unique(mask)) - {0}
        self.assertEqual(remaining_ids, {5, new_id})

    def test_missing_label_raises(self):
        mask = np.zeros((4, 4, 4), dtype=np.int32)
        with self.assertRaises(WatershedError):
            run_watershed_3d(mask, target_label=9, seeds_zyx=[(0, 0, 0)])

    def test_seed_outside_label_raises(self):
        mask = np.zeros((4, 4, 4), dtype=np.int32)
        mask[0, 0, 0] = 3
        with self.assertRaises(WatershedError):
            run_watershed_3d(mask, target_label=3, seeds_zyx=[(3, 3, 3)])


class LabelsSummaryAndPreviewUnitTests(TestCase):
    def setUp(self):
        self.path_str = os.path.join(_TMP, "unit_labels.tif")
        vol = np.zeros((6, 8, 8), dtype=np.uint16)
        vol[0:2, 0:3, 0:3] = 1
        vol[3:6, 4:8, 4:8] = 2
        tifffile.imwrite(self.path_str, vol)
        # tifffile.memmap needs a real Path-like with .exists()/.stat()
        from pathlib import Path

        self.path = Path(self.path_str)

    def test_label_summary_counts_and_z_range(self):
        summary = label_summary(self.path)
        by_id = {row["id"]: row for row in summary["labels"]}
        self.assertEqual(set(by_id), {1, 2})
        self.assertEqual(by_id[1]["voxel_count"], 2 * 3 * 3)
        self.assertEqual((by_id[1]["z_start"], by_id[1]["z_end"]), (0, 1))
        self.assertEqual(by_id[2]["voxel_count"], 3 * 4 * 4)
        self.assertEqual((by_id[2]["z_start"], by_id[2]["z_end"]), (3, 5))

    def test_preview_grid_nonempty_for_present_labels(self):
        preview = labels_3d_preview(self.path, [1, 2])
        self.assertIn(1, preview["grids"])
        self.assertIn(2, preview["grids"])
        self.assertTrue(preview["grids"][1].any())

    def test_preview_empty_for_absent_label(self):
        preview = labels_3d_preview(self.path, [999])
        self.assertEqual(preview["grids"], {})


@override_settings(MITO_DATA_ROOT=_TMP)
class CellablePortApiTests(TestCase):
    def setUp(self):
        slice_io.clear_caches()
        self.manager = self._user("mgr2", UserRole.MANAGER)
        self.annotator = self._user("ann2", UserRole.ANNOTATOR, annotator=True)
        self.requester = self._user("req2", UserRole.REQUESTER)

        self.project = create_project(title="P2", created_by=self.requester, reviewed=True)
        rel = "images/task2.tif"
        path = os.path.join(_TMP, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # A bright square on a dark background — gives EfficientSAM a real
        # object to find if the model is available.
        image = np.full((6, 32, 32), 20, dtype=np.uint8)
        image[:, 8:24, 8:24] = 220
        tifffile.imwrite(path, image)
        self.volume = Volume.objects.create(
            project=self.project, name="v2", image_path=rel,
            label_type=LabelType.NONE, shape_z=6, shape_y=32, shape_x=32,
        )
        owned = os.path.join(_TMP, working_label_rel_path(self.volume))
        if os.path.exists(owned):
            os.remove(owned)
        self.task = AnnotationTask.objects.create(
            project=self.project, volume=self.volume, assigned_to=self.annotator,
            z_start=0, z_end=6, y_end=32, x_end=32,
            task_type=TaskType.MANUAL_ANNOTATION,
        )

    def _user(self, name, role, annotator=False):
        user = User.objects.create_user(name, password="x")
        UserProfile.objects.filter(user=user).update(role=role)
        if annotator:
            AnnotatorProfile.objects.create(user=user, is_active_annotator=True)
        return User.objects.get(pk=user.pk)

    def _client(self, user):
        c = APIClient()
        c.force_authenticate(user=user)
        return c

    def _paint_instance(self, label_id, z, y0, y1, x0, x1, *, origin="manual"):
        """Paint a rectangle of ``label_id`` directly into the working copy
        via the same service the editor's PUT uses, so watershed/summary
        tests have real data without going through the paint API."""
        from annotation.services import get_label_slice_ids, set_label_slice_ids
        from annotation.visualization.slice_io import decode_label_rle, encode_label_rle

        current = get_label_slice_ids(self.volume, "z", z)
        arr = decode_label_rle(current["runs"], tuple(current["shape"]))
        arr[y0:y1, x0:x1] = label_id
        set_label_slice_ids(self.volume, "z", z, list(arr.shape), encode_label_rle(arr), origin=origin)

    def _lifecycle_row(self, label_id):
        resp = self._client(self.manager).get(f"/api/tasks/{self.task.id}/labels-summary/")
        rows = {row["id"]: row for row in resp.json()["labels"]}
        return rows.get(label_id)

    def test_requester_cannot_predict_mask(self):
        resp = self._client(self.requester).post(
            f"/api/tasks/{self.task.id}/predict-mask/",
            {"axis": "z", "index": 2, "mode": "points", "points": [[16, 16]], "point_labels": [1]},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_predict_mask_unavailable_reports_503_not_500(self):
        with override_settings(MITO_CELLABLE_MODELS_ROOT="/nonexistent/path"):
            # Force a fresh load attempt regardless of any earlier test run.
            from annotation.cellable_port.ai import registry

            registry._model = None
            registry._load_error = None
            resp = self._client(self.annotator).post(
                f"/api/tasks/{self.task.id}/predict-mask/",
                {"axis": "z", "index": 2, "mode": "points", "points": [[16, 16]], "point_labels": [1]},
                format="json",
            )
            self.assertEqual(resp.status_code, 503)
            registry._model = None
            registry._load_error = None

    @unittest.skipUnless(
        os.path.exists(
            os.path.join(
                getattr(settings, "MITO_CELLABLE_MODELS_ROOT", ""),
                f"efficient_sam_{getattr(settings, 'MITO_EFFICIENT_SAM_VARIANT', 'vitt')}_encoder.onnx",
            )
        ),
        "EfficientSAM ONNX weights not available in this environment",
    )
    def test_predict_mask_from_point_finds_bright_square(self):
        resp = self._client(self.annotator).post(
            f"/api/tasks/{self.task.id}/predict-mask/",
            {"axis": "z", "index": 2, "mode": "points", "points": [[16, 16]], "point_labels": [1]},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()
        runs = body["runs"]
        total_on = sum(count for value, count in runs if value == 1)
        # The bright square is 16x16 = 256px; a real point-prompt mask
        # should land roughly in that ballpark, not empty or the whole image.
        self.assertGreater(total_on, 50)
        self.assertLess(total_on, 32 * 32)

    @unittest.skipUnless(
        os.path.exists(
            os.path.join(
                getattr(settings, "MITO_CELLABLE_MODELS_ROOT", ""),
                f"efficient_sam_{getattr(settings, 'MITO_EFFICIENT_SAM_VARIANT', 'vits')}_encoder.onnx",
            )
        ),
        "EfficientSAM ONNX weights not available in this environment",
    )
    def test_warm_embedding_populates_disk_cache_and_predict_still_works(self):
        from annotation.cellable_port.ai import embed_cache
        from annotation.services import _ai_embedding_cache_path

        cache_path = _ai_embedding_cache_path(self.volume, "z", 2)
        self.assertIsNone(embed_cache.load(cache_path))

        resp = self._client(self.annotator).post(
            f"/api/tasks/{self.task.id}/warm-embedding/", {"axis": "z", "index": 2}, format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertTrue(resp.json()["warmed"])
        self.assertIsNotNone(embed_cache.load(cache_path))

        # A predict against the now-warmed slice still returns a sane mask
        # (i.e. the disk-cached embedding is actually usable, not just present).
        resp2 = self._client(self.annotator).post(
            f"/api/tasks/{self.task.id}/predict-mask/",
            {"axis": "z", "index": 2, "mode": "points", "points": [[16, 16]], "point_labels": [1]},
            format="json",
        )
        self.assertEqual(resp2.status_code, 200, resp2.content)
        total_on = sum(count for value, count in resp2.json()["runs"] if value == 1)
        self.assertGreater(total_on, 50)

    def test_warm_embedding_unavailable_reports_200_not_error(self):
        with override_settings(MITO_CELLABLE_MODELS_ROOT="/nonexistent/path"):
            from annotation.cellable_port.ai import registry

            registry._model = None
            registry._load_error = None
            resp = self._client(self.annotator).post(
                f"/api/tasks/{self.task.id}/warm-embedding/", {"axis": "z", "index": 2}, format="json",
            )
            self.assertEqual(resp.status_code, 200, resp.content)
            self.assertFalse(resp.json()["warmed"])
            registry._model = None
            registry._load_error = None

    def test_watershed_requires_seed_inside_label(self):
        self._paint_instance(7, 2, 4, 20, 4, 20)
        resp = self._client(self.annotator).post(
            f"/api/tasks/{self.task.id}/watershed/",
            {"label": 7, "seeds": [{"z": 2, "y": 0, "x": 0}]},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_watershed_splits_and_persists_to_working_copy_only(self):
        # Two blobs that touch (one instance id 7) at z=2, seeded apart.
        self._paint_instance(7, 2, 2, 10, 2, 10)
        self._paint_instance(7, 2, 2, 10, 12, 20)
        for z in (0, 1, 3, 4, 5):
            self._paint_instance(7, z, 2, 10, 2, 10)
            self._paint_instance(7, z, 2, 10, 12, 20)
        resp = self._client(self.annotator).post(
            f"/api/tasks/{self.task.id}/watershed/",
            {"label": 7, "seeds": [{"z": 2, "y": 5, "x": 5}, {"z": 2, "y": 5, "x": 16}]},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        result = resp.json()
        self.assertEqual(len(result["new_label_ids"]), 1)
        self.volume.refresh_from_db()
        # Never promotes to the official label — staging rule unchanged.
        self.assertEqual(self.volume.label_path, "")

    def test_labels_summary_reflects_painted_instances(self):
        self._paint_instance(3, 1, 0, 4, 0, 4)
        resp = self._client(self.manager).get(f"/api/tasks/{self.task.id}/labels-summary/")
        self.assertEqual(resp.status_code, 200, resp.content)
        ids = {row["id"] for row in resp.json()["labels"]}
        self.assertIn(3, ids)

    def test_labels_3d_binary_response_has_expected_header(self):
        import struct

        self._paint_instance(4, 1, 0, 4, 0, 4)
        resp = self._client(self.manager).get(
            f"/api/tasks/{self.task.id}/labels-3d/?labels=4"
        )
        self.assertEqual(resp.status_code, 200)
        dz, dy, dx, num_labels = struct.unpack_from("<IIII", resp.content, 0)
        self.assertEqual(num_labels, 1)
        self.assertGreater(dz * dy * dx, 0)
        expected_len = 16 + 4 + dz * dy * dx
        self.assertEqual(len(resp.content), expected_len)

    # --- Label lifecycle (Proposed/Edited/Verified) -------------------------

    def test_new_manual_label_starts_edited(self):
        self._paint_instance(11, 1, 0, 4, 0, 4, origin="manual")
        row = self._lifecycle_row(11)
        self.assertEqual(row["state"], "edited")
        self.assertEqual(row["origin"], "manual")
        self.assertFalse(row["can_revert"])

    def test_new_ai_label_starts_proposed_with_snapshot(self):
        self._paint_instance(12, 1, 0, 4, 0, 4, origin="ai")
        row = self._lifecycle_row(12)
        self.assertEqual(row["state"], "proposed")
        self.assertEqual(row["origin"], "ai")
        self.assertTrue(row["can_revert"])

    def test_repainting_a_verified_label_marks_it_edited_again(self):
        self._paint_instance(13, 1, 0, 4, 0, 4, origin="manual")
        resp = self._client(self.annotator).post(
            f"/api/tasks/{self.task.id}/labels/13/lifecycle/", {"action": "verify"}, format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(self._lifecycle_row(13)["state"], "verified")

        # Expand the same label on a new slice — an existing tracked id is
        # always marked EDITED on further changes, even from VERIFIED.
        self._paint_instance(13, 2, 0, 4, 0, 4, origin="manual")
        self.assertEqual(self._lifecycle_row(13)["state"], "edited")

    def test_verify_then_unverify(self):
        self._paint_instance(14, 1, 0, 4, 0, 4, origin="manual")
        c = self._client(self.annotator)
        c.post(f"/api/tasks/{self.task.id}/labels/14/lifecycle/", {"action": "verify"}, format="json")
        self.assertEqual(self._lifecycle_row(14)["state"], "verified")

        resp = c.post(f"/api/tasks/{self.task.id}/labels/14/lifecycle/", {"action": "unverify"}, format="json")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(self._lifecycle_row(14)["state"], "edited")

    def test_unverify_when_not_verified_is_400(self):
        self._paint_instance(15, 1, 0, 4, 0, 4, origin="manual")
        resp = self._client(self.annotator).post(
            f"/api/tasks/{self.task.id}/labels/15/lifecycle/", {"action": "unverify"}, format="json"
        )
        self.assertEqual(resp.status_code, 400)

    def test_revert_restores_only_the_original_snapshot_slice(self):
        self._paint_instance(16, 1, 0, 4, 0, 4, origin="ai")
        # Grow the same id onto a second slice before reverting.
        self._paint_instance(16, 2, 0, 4, 0, 4, origin="manual")

        resp = self._client(self.annotator).post(
            f"/api/tasks/{self.task.id}/labels/16/lifecycle/", {"action": "revert"}, format="json"
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["state"], "proposed")

        from annotation.services import get_label_slice_ids

        slice1 = get_label_slice_ids(self.volume, "z", 1)
        slice2 = get_label_slice_ids(self.volume, "z", 2)
        self.assertTrue(any(v == 16 for v, _c in slice1["runs"]))
        self.assertFalse(any(v == 16 for v, _c in slice2["runs"]))
        self.assertEqual(self._lifecycle_row(16)["state"], "proposed")

    def test_revert_without_snapshot_is_400(self):
        self._paint_instance(17, 1, 0, 4, 0, 4, origin="manual")
        resp = self._client(self.annotator).post(
            f"/api/tasks/{self.task.id}/labels/17/lifecycle/", {"action": "revert"}, format="json"
        )
        self.assertEqual(resp.status_code, 400)

    def test_reject_deletes_every_voxel_and_metadata(self):
        self._paint_instance(18, 1, 0, 4, 0, 4, origin="manual")
        self._paint_instance(18, 2, 0, 4, 0, 4, origin="manual")
        resp = self._client(self.annotator).post(
            f"/api/tasks/{self.task.id}/labels/18/lifecycle/", {"action": "reject"}, format="json"
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertTrue(resp.json()["removed"])
        self.assertIsNone(self._lifecycle_row(18))

    def test_requester_cannot_change_label_lifecycle(self):
        self._paint_instance(19, 1, 0, 4, 0, 4, origin="manual")
        resp = self._client(self.requester).post(
            f"/api/tasks/{self.task.id}/labels/19/lifecycle/", {"action": "verify"}, format="json"
        )
        self.assertEqual(resp.status_code, 403)

    def test_watershed_registers_new_label_as_proposed_no_snapshot(self):
        self._paint_instance(20, 2, 2, 10, 2, 10, origin="manual")
        self._paint_instance(20, 2, 2, 10, 12, 20, origin="manual")
        self._client(self.annotator).post(
            f"/api/tasks/{self.task.id}/watershed/",
            {"label": 20, "seeds": [{"z": 2, "y": 5, "x": 5}, {"z": 2, "y": 5, "x": 16}]},
            format="json",
        )
        resp = self._client(self.manager).get(f"/api/tasks/{self.task.id}/labels-summary/")
        rows = {row["id"]: row for row in resp.json()["labels"]}
        new_ids = [lid for lid in rows if lid > 20]
        self.assertEqual(len(new_ids), 1)
        new_row = rows[new_ids[0]]
        self.assertEqual(new_row["state"], "proposed")
        self.assertEqual(new_row["origin"], "watershed")
        self.assertFalse(new_row["can_revert"])
        # The target label's shape changed too — marked edited.
        self.assertEqual(rows[20]["state"], "edited")
