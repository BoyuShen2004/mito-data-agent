from django.test import TestCase

from core.choices import LabelType, TaskType
from projects.services import create_project
from volumes.services import (
    create_tasks_from_volume,
    infer_task_type,
    register_volume,
    split_volume_by_frames,
)


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

        tasks = create_tasks_from_volume(volume, z_step=16, payment_amount="2.50")
        self.assertEqual(len(tasks), 2)
        t = tasks[0]
        self.assertEqual((t.y_start, t.y_end), (0, 384))
        self.assertEqual((t.x_start, t.x_end), (0, 512))
        self.assertEqual(t.task_type, TaskType.MANUAL_ANNOTATION)
        self.assertEqual(str(t.payment_amount), "2.50")

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
