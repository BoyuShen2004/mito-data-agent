from rest_framework import serializers

from .models import Project


class ProjectSerializer(serializers.ModelSerializer):
    institution_name = serializers.CharField(
        source="institution.name", read_only=True, default=""
    )
    created_by_username = serializers.CharField(
        source="created_by.username", read_only=True, default=""
    )
    volume_count = serializers.IntegerField(source="volumes.count", read_only=True)
    task_count = serializers.IntegerField(source="tasks.count", read_only=True)

    class Meta:
        model = Project
        fields = [
            "id",
            "title",
            "institution",
            "institution_name",
            "description",
            "annotation_target",
            "annotation_type",
            "status",
            "deadline",
            "created_by",
            "created_by_username",
            "volume_count",
            "task_count",
            "created_at",
        ]
        read_only_fields = ["created_by", "created_at"]
