from rest_framework import serializers

from .models import Volume


class VolumeSerializer(serializers.ModelSerializer):
    has_label = serializers.BooleanField(read_only=True)
    image_location = serializers.CharField(read_only=True)
    label_location = serializers.CharField(read_only=True)
    task_count = serializers.IntegerField(source="tasks.count", read_only=True)

    class Meta:
        model = Volume
        fields = [
            "id",
            "project",
            "name",
            "image_path",
            "image_file",
            "label_path",
            "label_file",
            "label_type",
            "shape_z",
            "shape_y",
            "shape_x",
            "voxel_size_z",
            "voxel_size_y",
            "voxel_size_x",
            "file_format",
            "metadata",
            "status",
            "has_label",
            "image_location",
            "label_location",
            "task_count",
            "created_at",
        ]
        read_only_fields = ["project", "status", "created_at"]


class VolumeSplitSerializer(serializers.Serializer):
    z_step = serializers.IntegerField(required=False, min_value=1)
    payment_amount = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, default=0
    )
    task_type = serializers.CharField(required=False, allow_blank=True)
    priority = serializers.IntegerField(required=False, default=0)
    instructions = serializers.CharField(required=False, allow_blank=True, default="")
