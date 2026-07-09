from rest_framework import serializers

from .models import AnnotationSubmission, AnnotationTask, ReviewRecord


class AnnotationTaskSerializer(serializers.ModelSerializer):
    project_title = serializers.CharField(source="project.title", read_only=True)
    volume_name = serializers.CharField(source="volume.name", read_only=True)
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

    class Meta:
        model = AnnotationTask
        fields = [
            "id",
            "project",
            "project_title",
            "volume",
            "volume_name",
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
            "payment_amount",
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
            "notes",
            "qc_status",
            "qc_report",
            "reviews",
            "submitted_at",
        ]


class SubmitTaskSerializer(serializers.Serializer):
    label_file = serializers.FileField()
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class ReviewSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(
        choices=["approved", "rejected", "revision_requested"]
    )
    comments = serializers.CharField(required=False, allow_blank=True, default="")
