from rest_framework import serializers

from core.choices import LabelType

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
            "source_volume",
            "chunk_id",
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
    task_type = serializers.CharField(required=False, allow_blank=True)
    priority = serializers.IntegerField(required=False, default=0)
    instructions = serializers.CharField(required=False, allow_blank=True, default="")


class HpcScanSerializer(serializers.Serializer):
    hpc_directory = serializers.CharField()


class RegisterDataFileSerializer(serializers.Serializer):
    path = serializers.CharField(required=False, allow_blank=True, default="")
    name = serializers.CharField(required=False, allow_blank=True, default="")
    chunk_id = serializers.CharField(required=False, allow_blank=True, default="")


class RegisterDataPairSerializer(serializers.Serializer):
    image = serializers.CharField()
    mask = serializers.CharField(required=False, allow_blank=True, default="")
    chunk_id = serializers.CharField(required=False, allow_blank=True, default="")


# Optional, non-image-derived biomedical metadata (see Mitoverse). Resolution,
# shape, and mitochondria counts are derived from the files, never entered here.
METADATA_FIELDS = [
    "organism",
    "tissue",
    "cell_type",
    "imaging_modality",
    "imaging_instrument",
    "experimental_condition",
    "sample_condition",
    "dataset_source",
    "publication",
    "description",
    "notes",
]


class RegisterDataSerializer(serializers.Serializer):
    """Shared payload used by requesters and managers to register data."""

    dataset = serializers.CharField()
    volume = serializers.CharField()
    hpc_directory = serializers.CharField()
    project = serializers.IntegerField(required=False, allow_null=True)
    annotation_type = serializers.CharField(required=False, allow_blank=True)
    # Image+mask pairs (preferred) and/or image-only files. When both are
    # omitted the directory is auto-scanned and all detected pairs registered.
    pairs = RegisterDataPairSerializer(many=True, required=False)
    files = RegisterDataFileSerializer(many=True, required=False)
    label_type = serializers.ChoiceField(
        choices=[c.value for c in LabelType], required=False, allow_blank=True
    )
    metadata = serializers.DictField(required=False)

    def validate_dataset(self, value):
        if not value.strip():
            raise serializers.ValidationError("A dataset name is required.")
        return value

    def validate_volume(self, value):
        if not value.strip():
            raise serializers.ValidationError("A volume name is required.")
        return value
