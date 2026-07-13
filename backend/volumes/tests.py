import os
import tempfile

from django.test import TestCase, override_settings

from core.choices import LabelType, TaskType
from projects.services import create_project
from volumes.services import (
    DataRegistrationError,
    create_tasks_from_volume,
    detect_volume_pairs,
    infer_task_type,
    register_dataset,
    register_volume,
    scan_hpc_directory,
    split_volume_by_frames,
)

_TMP_ROOT = tempfile.mkdtemp(prefix="mito_reg_test_")


class FrameSplittingTests(TestCase):
    def test_exact_multiple(self):
        ranges = split_volume_by_frames(256, 16)
        self.assertEqual(len(ranges), 16)
        self.assertEqual(ranges[0], (0, 16))
        self.assertEqual(ranges[-1], (240, 256))

    def test_non_multiple_clamps_last_range(self):
        ranges = split_volume_by_frames(20, 16)
        self.assertEqual(ranges, [(0, 16), (16, 20)])

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):
            split_volume_by_frames(0, 16)
        with self.assertRaises(ValueError):
            split_volume_by_frames(100, 0)


class TaskTypeInferenceTests(TestCase):
    def test_label_type_mapping(self):
        self.assertEqual(infer_task_type(LabelType.NONE), TaskType.MANUAL_ANNOTATION)
        self.assertEqual(
            infer_task_type(LabelType.PREDICTION), TaskType.PREDICTION_PROOFREADING
        )
        self.assertEqual(infer_task_type(LabelType.PROOFREAD), TaskType.FINAL_REVIEW)
        self.assertEqual(infer_task_type(LabelType.PARTIAL), TaskType.MANUAL_ANNOTATION)

    def test_override_wins(self):
        self.assertEqual(
            infer_task_type(LabelType.NONE, TaskType.QC_REVIEW), TaskType.QC_REVIEW
        )


class CreateTasksTests(TestCase):
    def setUp(self):
        self.project = create_project(title="P")

    def _volume(self, label_type=LabelType.NONE):
        return register_volume(
            project=self.project,
            name="vol1",
            image_path="vol1.tiff",
            label_type=label_type,
            autodetect_shape=False,
        )

    def test_create_tasks_spans_full_xy(self):
        volume = self._volume()
        volume.shape_x, volume.shape_y, volume.shape_z = 512, 384, 32
        volume.save()

        tasks = create_tasks_from_volume(volume, z_step=16)
        self.assertEqual(len(tasks), 2)
        t = tasks[0]
        self.assertEqual((t.y_start, t.y_end), (0, 384))
        self.assertEqual((t.x_start, t.x_end), (0, 512))
        self.assertEqual(t.task_type, TaskType.MANUAL_ANNOTATION)

    def test_prediction_volume_makes_proofreading_tasks(self):
        volume = self._volume(LabelType.PREDICTION)
        volume.shape_x, volume.shape_y, volume.shape_z = 10, 10, 16
        volume.save()
        tasks = create_tasks_from_volume(volume)
        self.assertEqual(tasks[0].task_type, TaskType.PREDICTION_PROOFREADING)

    def test_split_without_shape_raises(self):
        volume = self._volume()
        with self.assertRaises(ValueError):
            create_tasks_from_volume(volume)


@override_settings(MITO_DATA_ROOT=_TMP_ROOT)
class RegisterDatasetTests(TestCase):
    def setUp(self):
        # Create a directory of mixed files under the data root.
        self.dir = tempfile.mkdtemp(dir=_TMP_ROOT)
        for name in ("a.tif", "b.tiff", "c.nii.gz", "notes.txt", "d.png"):
            with open(os.path.join(self.dir, name), "wb") as fh:
                fh.write(b"x")

    def test_scan_lists_only_supported_files(self):
        result = scan_hpc_directory(self.dir)
        names = {f["name"] for f in result["files"]}
        self.assertEqual(names, {"a.tif", "b.tiff", "c.nii.gz"})

    def test_register_all_supported_files_as_chunks(self):
        project, volumes = register_dataset(
            created_by=None,
            dataset="DatasetX",
            volume="big_volume",
            hpc_directory=self.dir,
        )
        self.assertEqual(project.dataset, "DatasetX")
        self.assertEqual(len(volumes), 3)
        self.assertTrue(all(v.source_volume == "big_volume" for v in volumes))
        # Chunks share the same dataset (project) and volume.
        self.assertEqual({v.project_id for v in volumes}, {project.id})

    def test_register_selected_files_with_chunk_ids(self):
        project, volumes = register_dataset(
            created_by=None,
            dataset="DatasetY",
            volume="vol1",
            hpc_directory=self.dir,
            files=[{"name": "a.tif", "chunk_id": "crop-1"}],
            metadata={"organism": "mouse"},
        )
        self.assertEqual(len(volumes), 1)
        self.assertEqual(volumes[0].chunk_id, "crop-1")
        self.assertEqual(project.metadata.get("organism"), "mouse")

    def test_missing_dataset_or_volume_rejected(self):
        with self.assertRaises(DataRegistrationError):
            register_dataset(
                created_by=None, dataset="", volume="v", hpc_directory=self.dir
            )
        with self.assertRaises(DataRegistrationError):
            register_dataset(
                created_by=None, dataset="d", volume="", hpc_directory=self.dir
            )

    def test_unsupported_extension_rejected(self):
        with self.assertRaises(DataRegistrationError):
            register_dataset(
                created_by=None,
                dataset="d",
                volume="v",
                hpc_directory=self.dir,
                files=[{"name": "notes.txt"}],
            )

    def test_missing_directory_rejected(self):
        with self.assertRaises(DataRegistrationError):
            scan_hpc_directory("does/not/exist")


class DetectPairsTests(TestCase):
    def test_pairs_image_and_mask_by_shared_base(self):
        pairs, unpaired = detect_volume_pairs(
            [
                "cortex1_image.tif",
                "cortex1_mask.tif",
                "cortex2_raw.tif",
                "cortex2_seg.tif",
                "lonely_volume.tif",
            ]
        )
        by_image = {p["image"]: p["mask"] for p in pairs}
        self.assertEqual(by_image["cortex1_image.tif"], "cortex1_mask.tif")
        self.assertEqual(by_image["cortex2_raw.tif"], "cortex2_seg.tif")
        self.assertEqual(unpaired, ["lonely_volume.tif"])

    def test_bare_name_and_label_suffix(self):
        pairs, unpaired = detect_volume_pairs(["vol.tif", "vol_label.tif"])
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0]["image"], "vol.tif")
        self.assertEqual(pairs[0]["mask"], "vol_label.tif")
        self.assertEqual(unpaired, [])


@override_settings(MITO_DATA_ROOT=_TMP_ROOT)
class RegisterPairsTests(TestCase):
    def setUp(self):
        # A folder holding two image+mask pairs plus one unrelated volume.
        self.dir = tempfile.mkdtemp(dir=_TMP_ROOT)
        for name in (
            "sampleA_image.tif",
            "sampleA_mask.tif",
            "sampleB_image.tif",
            "sampleB_mask.tif",
            "other_volume.tif",
        ):
            with open(os.path.join(self.dir, name), "wb") as fh:
                fh.write(b"x")

    def test_auto_registers_all_pairs_and_unpaired(self):
        project, volumes = register_dataset(
            created_by=None,
            dataset="D",
            volume="v",
            hpc_directory=self.dir,
        )
        # 2 pairs (with masks) + 1 unpaired image = 3 volumes.
        self.assertEqual(len(volumes), 3)
        with_mask = [v for v in volumes if v.label_path]
        self.assertEqual(len(with_mask), 2)
        for v in with_mask:
            self.assertEqual(v.label_type, LabelType.PREDICTION)

    def test_register_single_explicit_pair_from_mixed_folder(self):
        project, volumes = register_dataset(
            created_by=None,
            dataset="D2",
            volume="v",
            hpc_directory=self.dir,
            pairs=[
                {
                    "image": "sampleA_image.tif",
                    "mask": "sampleA_mask.tif",
                    "chunk_id": "A",
                }
            ],
            label_type=LabelType.PROOFREAD,
        )
        self.assertEqual(len(volumes), 1)
        v = volumes[0]
        self.assertEqual(v.chunk_id, "A")
        self.assertTrue(v.label_path.endswith("sampleA_mask.tif"))
        self.assertEqual(v.label_type, LabelType.PROOFREAD)

    def test_pair_with_missing_mask_rejected(self):
        with self.assertRaises(DataRegistrationError):
            register_dataset(
                created_by=None,
                dataset="D3",
                volume="v",
                hpc_directory=self.dir,
                pairs=[{"image": "sampleA_image.tif", "mask": "nope.tif"}],
            )
