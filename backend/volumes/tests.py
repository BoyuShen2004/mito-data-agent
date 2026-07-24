import os
import tempfile

from django.test import TestCase, override_settings

from core.choices import LabelType, TaskType
from projects.services import create_project
import json

from volumes.services import (
    DataRegistrationError,
    case_key,
    create_tasks_from_volume,
    detect_volume_pairs,
    infer_task_type,
    pair_by_case,
    register_dataset,
    register_volume,
    scan_data_sources,
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


@override_settings(MITO_DATA_ROOT=_TMP_ROOT)
class VoxelAutodetectTests(TestCase):
    """Registration reads shape *and* voxel size from the image headers."""

    def test_registration_detects_voxel_size(self):
        import numpy as np
        import tifffile

        directory = os.path.join(_TMP_ROOT, "voxel_ds")
        os.makedirs(directory, exist_ok=True)
        path = os.path.join(directory, "sample_0000.tiff")
        # x spacing 0.5µm (xres 2 px/µm), y 0.25µm (yres 4), z spacing 0.2µm.
        tifffile.imwrite(
            path,
            np.zeros((8, 16, 32), dtype=np.uint8),
            imagej=True,
            resolution=(2.0, 4.0),
            metadata={"spacing": 0.2, "unit": "um", "axes": "ZYX"},
        )

        project = create_project(title="Voxel", reviewed=True)
        _project, volumes = register_dataset(
            created_by=None,
            dataset="VoxelDS",
            volume="vol",
            project=project,
            image_directory=directory,
            files=[{"name": "sample_0000.tiff"}],
        )
        vol = volumes[0]
        self.assertEqual((vol.shape_z, vol.shape_y, vol.shape_x), (8, 16, 32))
        self.assertAlmostEqual(vol.voxel_size_z, 0.2, places=5)
        self.assertAlmostEqual(vol.voxel_size_y, 0.25, places=5)
        self.assertAlmostEqual(vol.voxel_size_x, 0.5, places=5)


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
        # Metadata belongs to the dataset, not the project that contains it.
        dataset = project.datasets.get(name="DatasetY")
        self.assertEqual(dataset.metadata.get("organism"), "mouse")
        self.assertEqual(volumes[0].dataset_id, dataset.id)

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


class CaseKeyTests(TestCase):
    """Pairing hinges on the case id, so pin down how it is derived."""

    def test_channel_suffix_stripped_from_images(self):
        self.assertEqual(case_key("case_00_0000.tiff"), "case_00")
        self.assertEqual(case_key("jrc_mus-kidney_crop129_0000.nii.gz"), "jrc_mus-kidney_crop129")

    def test_label_without_suffix_yields_same_key(self):
        self.assertEqual(case_key("case_00.tiff"), case_key("case_00_0000.tiff"))

    def test_non_channel_digits_are_kept(self):
        # Only a 4-digit trailing group is a channel; crop ids must survive.
        self.assertEqual(case_key("crop_12.tif"), "crop_12")
        self.assertEqual(case_key("Dataset001_ME2-Beta__high_c1.nii.gz"),
                         "Dataset001_ME2-Beta__high_c1")


class PairByCaseTests(TestCase):
    """Cross-directory pairing: names come from two separate folders."""

    def test_pairs_nnunet_images_and_labels(self):
        pairs, un_img, un_mask, extras = pair_by_case(
            ["case_00_0000.tiff", "case_01_0000.tiff"],
            ["case_00.tiff", "case_01.tiff"],
        )
        self.assertEqual([(p["image"], p["mask"]) for p in pairs], [
            ("case_00_0000.tiff", "case_00.tiff"),
            ("case_01_0000.tiff", "case_01.tiff"),
        ])
        self.assertEqual((un_img, un_mask, extras), ([], [], []))

    def test_leftovers_on_both_sides_are_surfaced(self):
        pairs, un_img, un_mask, _ = pair_by_case(
            ["a_0000.tif", "orphan_0000.tif"], ["a.tif", "stray.tif"]
        )
        self.assertEqual(len(pairs), 1)
        self.assertEqual(un_img, ["orphan_0000.tif"])
        self.assertEqual(un_mask, ["stray.tif"])

    def test_extra_channels_reported_not_dropped(self):
        pairs, un_img, un_mask, extras = pair_by_case(
            ["m_0000.tif", "m_0001.tif"], ["m.tif"]
        )
        # Channel 0 represents the volume; the second channel is surfaced.
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0]["image"], "m_0000.tif")
        self.assertEqual(extras, ["m_0001.tif"])
        self.assertEqual(un_img, [])


class SingleDirectoryPairingTests(TestCase):
    """The nnU-Net convention also shows up flattened into one folder."""

    def test_channel_suffix_convention_in_one_folder(self):
        pairs, unpaired = detect_volume_pairs(["vol1_0000.tiff", "vol1.tiff"])
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0]["image"], "vol1_0000.tiff")
        self.assertEqual(pairs[0]["mask"], "vol1.tiff")
        self.assertEqual(unpaired, [])

    def test_token_convention_still_works(self):
        pairs, _ = detect_volume_pairs(["cortex_image.tif", "cortex_mask.tif"])
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0]["mask"], "cortex_mask.tif")


@override_settings(MITO_DATA_ROOT=_TMP_ROOT)
class SeparateDirectoryRegistrationTests(TestCase):
    """Images and masks in different folders — the nnU-Net layout."""

    def setUp(self):
        self.root = tempfile.mkdtemp(dir=_TMP_ROOT)
        self.images = os.path.join(self.root, "imagesTr")
        self.labels = os.path.join(self.root, "labelsTr")
        self.instance = os.path.join(self.root, "labelsTr-instance")
        for d in (self.images, self.labels, self.instance):
            os.makedirs(d)
        for case in ("case_00", "case_01"):
            self._touch(self.images, f"{case}_0000.tiff")
            self._touch(self.labels, f"{case}.tiff")
            self._touch(self.instance, f"{case}.tiff")

    def _touch(self, directory, name):
        with open(os.path.join(directory, name), "wb") as fh:
            fh.write(b"x")

    def _write_manifest(self, mask_dir="labelsTr"):
        manifest = {
            "name": "Demo",
            "description": "demo dataset",
            "reference": "a paper",
            "labels": {"background": 0, "mitochondria": 1},
            "channel_names": {"0": "EM"},
            "training": [
                {"image": f"./imagesTr/{c}_0000.tiff", "label": f"./{mask_dir}/{c}.tiff"}
                for c in ("case_00", "case_01")
            ],
        }
        with open(os.path.join(self.root, "dataset.json"), "w") as fh:
            json.dump(manifest, fh)

    def test_scan_pairs_across_directories(self):
        result = scan_data_sources(self.images, self.labels)
        self.assertEqual(len(result["pairs"]), 2)
        self.assertEqual(result["unmatched_images"], [])
        self.assertEqual(result["unmatched_masks"], [])
        self.assertEqual(result["pairing_source"], "filename")
        self.assertEqual(result["split"], "train")

    def test_register_stores_label_from_the_mask_directory(self):
        project, volumes = register_dataset(
            created_by=None,
            dataset="D",
            volume="v",
            image_directory=self.images,
            mask_directory=self.labels,
        )
        self.assertEqual(len(volumes), 2)
        for v in volumes:
            self.assertIn("imagesTr", v.image_path)
            self.assertIn("labelsTr", v.label_path)
            self.assertEqual(v.label_type, LabelType.PREDICTION)
            self.assertEqual(v.metadata.get("split"), "train")
        # Volumes are named by case id, not by raw filename.
        self.assertEqual(sorted(v.name for v in volumes), ["case_00", "case_01"])

    def test_manifest_supplies_pairs_and_metadata(self):
        self._write_manifest()
        result = scan_data_sources(self.images, self.labels)
        self.assertEqual(result["pairing_source"], "dataset.json")
        self.assertEqual(len(result["pairs"]), 2)
        self.assertEqual(result["dataset_metadata"]["description"], "demo dataset")
        self.assertEqual(result["dataset_metadata"]["publication"], "a paper")
        self.assertEqual(result["dataset_metadata"]["label_classes"]["mitochondria"], 1)

    def test_manifest_ignored_for_a_different_label_set(self):
        # The manifest documents labelsTr; the user picked labelsTr-instance,
        # so it must not be treated as authoritative for that folder.
        self._write_manifest(mask_dir="labelsTr")
        result = scan_data_sources(self.images, self.instance)
        self.assertEqual(result["pairing_source"], "filename")
        self.assertEqual(len(result["pairs"]), 2)
        for pair in result["pairs"]:
            self.assertTrue(pair["mask"].endswith(".tiff"))

    def test_stale_manifest_falls_back_to_filenames(self):
        manifest = {
            "training": [{"image": "./imagesTr/gone_0000.tiff", "label": "./labelsTr/gone.tiff"}]
        }
        with open(os.path.join(self.root, "dataset.json"), "w") as fh:
            json.dump(manifest, fh)
        result = scan_data_sources(self.images, self.labels)
        self.assertEqual(result["pairing_source"], "filename")
        self.assertEqual(len(result["pairs"]), 2)

    def test_suggestions_offer_sibling_label_sets(self):
        result = scan_data_sources(self.images, self.labels)
        names = {s["name"] for s in result["suggestions"]["masks"]}
        self.assertEqual(names, {"labelsTr", "labelsTr-instance"})

    def test_image_directory_required(self):
        with self.assertRaises(DataRegistrationError):
            register_dataset(created_by=None, dataset="D", volume="v")

    def test_mask_directory_traversal_rejected(self):
        with self.assertRaises(DataRegistrationError):
            register_dataset(
                created_by=None,
                dataset="D",
                volume="v",
                image_directory=self.images,
                mask_directory=self.labels,
                # Only basenames are honoured, so this cannot escape labelsTr.
                pairs=[{"image": "case_00_0000.tiff", "mask": "../imagesTr/case_00_0000.tiff"}],
            )
