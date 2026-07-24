from rest_framework import serializers

from .models import AnnotationSubmission, AnnotationTask, ReviewRecord


class AnnotationTaskSerializer(serializers.ModelSerializer):
    project_title = serializers.CharField(source="project.title", read_only=True)
    dataset = serializers.CharField(source="project.dataset", read_only=True)
    # The biomedical metadata every role sees: it lives on the dataset (that is
    # where registration records it), so managers, requesters, and annotators
    # all read the same source rather than the near-empty project.metadata.
    dataset_metadata = serializers.SerializerMethodField()
    # Volume-derived facts, surfaced so annotators see the scanned resolution.
    voxel_size_z = serializers.FloatField(source="volume.voxel_size_z", read_only=True)
    voxel_size_y = serializers.FloatField(source="volume.voxel_size_y", read_only=True)
    voxel_size_x = serializers.FloatField(source="volume.voxel_size_x", read_only=True)
    shape_z = serializers.IntegerField(source="volume.shape_z", read_only=True)
    shape_y = serializers.IntegerField(source="volume.shape_y", read_only=True)
    shape_x = serializers.IntegerField(source="volume.shape_x", read_only=True)
    volume_name = serializers.CharField(source="volume.name", read_only=True)
    source_volume = serializers.CharField(
        source="volume.source_volume", read_only=True
    )
    image_location = serializers.CharField(
        source="volume.image_location", read_only=True
    )
    label_location = serializers.CharField(
        source="volume.label_location", read_only=True
    )
    assigned_to_username = serializers.CharField(
        source="assigned_to.username", read_only=True, default=""
    )
    frame_label = serializers.CharField(read_only=True)

    def get_dataset_metadata(self, obj) -> dict:
        dataset = getattr(obj.volume, "dataset", None) if obj.volume_id else None
        return dataset.metadata if dataset and dataset.metadata else {}

    class Meta:
        model = AnnotationTask
        fields = [
            "id",
            "project",
            "project_title",
            "dataset",
            "dataset_metadata",
            "voxel_size_z",
            "voxel_size_y",
            "voxel_size_x",
            "shape_z",
            "shape_y",
            "shape_x",
            "volume",
            "volume_name",
            "source_volume",
            "image_location",
            "label_location",
            "assigned_to",
            "assigned_to_username",
            "z_start",
            "z_end",
            "y_start",
            "y_end",
            "x_start",
            "x_end",
            "task_type",
            "status",
            "priority",
            "difficulty",
            "instructions",
            "deadline",
            "frame_label",
            "created_at",
            "assigned_at",
            "submitted_at",
            "approved_at",
        ]
        read_only_fields = [
            "project",
            "volume",
            "created_at",
            "assigned_at",
            "submitted_at",
            "approved_at",
        ]


class ReviewRecordSerializer(serializers.ModelSerializer):
    reviewer_username = serializers.CharField(
        source="reviewer.username", read_only=True, default=""
    )

    class Meta:
        model = ReviewRecord
        fields = [
            "id",
            "submission",
            "reviewer",
            "reviewer_username",
            "decision",
            "comments",
            "reviewed_at",
        ]


class AnnotationSubmissionSerializer(serializers.ModelSerializer):
    annotator_username = serializers.CharField(
        source="annotator.username", read_only=True, default=""
    )
    task_detail = AnnotationTaskSerializer(source="task", read_only=True)
    reviews = ReviewRecordSerializer(many=True, read_only=True)

    class Meta:
        model = AnnotationSubmission
        fields = [
            "id",
            "task",
            "task_detail",
            "annotator",
            "annotator_username",
            "label_file",
            "source",
            "notes",
            "qc_status",
            "qc_report",
            "reviews",
            "submitted_at",
        ]


class SubmitTaskSerializer(serializers.Serializer):
    label_file = serializers.FileField()
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class SubmitInappTaskSerializer(serializers.Serializer):
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class ReviewSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(
        choices=["approved", "rejected", "revision_requested"]
    )
    comments = serializers.CharField(required=False, allow_blank=True, default="")


class PlanEntrySerializer(serializers.Serializer):
    """One row of a manager-edited assignment plan.

    Only ``task_id`` is required. ``annotator_id`` is applied only when the key
    is present (``None`` unassigns), and each task field is updated only when
    supplied — so the client can send just what the manager changed.
    """

    task_id = serializers.IntegerField()
    annotator_id = serializers.IntegerField(required=False, allow_null=True)
    priority = serializers.IntegerField(required=False)
    difficulty = serializers.IntegerField(required=False)
    instructions = serializers.CharField(required=False, allow_blank=True)
    deadline = serializers.DateField(required=False, allow_null=True)


class AssignmentPlanSerializer(serializers.Serializer):
    entries = PlanEntrySerializer(many=True)
