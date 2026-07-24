from rest_framework import serializers

from core.lifecycle import classify_project

from .models import Dataset, Project


class DatasetSerializer(serializers.ModelSerializer):
    volume_count = serializers.IntegerField(source="volumes.count", read_only=True)
    project_title = serializers.CharField(source="project.title", read_only=True)

    class Meta:
        model = Dataset
        fields = [
            "id",
            "project",
            "project_title",
            "name",
            "description",
            "image_directory",
            "mask_directory",
            "metadata",
            "volume_count",
            "created_at",
        ]
        read_only_fields = ["created_at"]


class ProjectSerializer(serializers.ModelSerializer):
    institution_name = serializers.CharField(
        source="institution.name", read_only=True, default=""
    )
    created_by_username = serializers.CharField(
        source="created_by.username", read_only=True, default=""
    )
    reviewed_by_username = serializers.CharField(
        source="reviewed_by.username", read_only=True, default=""
    )
    volume_count = serializers.IntegerField(source="volumes.count", read_only=True)
    task_count = serializers.IntegerField(source="tasks.count", read_only=True)
    datasets = DatasetSerializer(many=True, read_only=True)
    dataset_count = serializers.IntegerField(source="datasets.count", read_only=True)
    # The New / To Proofread / Done bucket, computed from the review gate and
    # task rollup (see core.lifecycle).
    lifecycle = serializers.SerializerMethodField()

    def get_lifecycle(self, obj) -> str:
        return classify_project(obj)

    class Meta:
        model = Project
        fields = [
            "id",
            "title",
            "dataset",
            "datasets",
            "dataset_count",
            "institution",
            "institution_name",
            "description",
            "metadata",
            "annotation_target",
            "annotation_type",
            "workflow_type",
            "lifecycle",
            "status",
            "deadline",
            "created_by",
            "created_by_username",
            "manager_reviewed",
            "reviewed_by",
            "reviewed_by_username",
            "reviewed_at",
            "volume_count",
            "task_count",
            "created_at",
        ]
        read_only_fields = [
            "created_by",
            "created_at",
            "manager_reviewed",
            "reviewed_by",
            "reviewed_at",
        ]
