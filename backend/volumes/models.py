from django.db import models

from core.choices import FileFormat, LabelType, VolumeStatus
from core.storage import get_mito_storage


def volume_image_upload_to(instance, filename):
    return f"volumes/{instance.project_id}/images/{filename}"


def volume_label_upload_to(instance, filename):
    return f"volumes/{instance.project_id}/labels/{filename}"


class Volume(models.Model):
    """An image volume registered under a project.

    The image may be *registered* (a path relative to ``MITO_DATA_ROOT`` in
    ``image_path``) or *uploaded* (``image_file``). Labels are optional and
    their kind is recorded in ``label_type``, which drives task creation.
    """

    # The owning project. Denormalised from ``dataset.project`` because tasks,
    # assignment, and progress all query volumes by project; keep the two in
    # step via ``volumes.services.register_volume``/``set_volume_dataset``.
    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="volumes"
    )
    # The dataset this volume pair belongs to. Nullable only for rows created
    # before datasets existed.
    dataset = models.ForeignKey(
        "projects.Dataset",
        on_delete=models.CASCADE,
        related_name="volumes",
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=255)

    # A "volume" in the registration sense: the large original or logical
    # source volume this chunk/crop belongs to. Multiple chunks/crops may share
    # the same ``source_volume`` under the same dataset (project).
    source_volume = models.CharField(max_length=255, blank=True)
    # Optional chunk/crop identifier or name for this registered file.
    chunk_id = models.CharField(max_length=255, blank=True)

    # Registered (path relative to MITO_DATA_ROOT) or uploaded image.
    image_path = models.CharField(max_length=1024, blank=True)
    image_file = models.FileField(
        storage=get_mito_storage,
        upload_to=volume_image_upload_to,
        blank=True,
        null=True,
    )

    # Optional label. May be absent, a prediction, proofread, or partial.
    label_path = models.CharField(max_length=1024, blank=True)
    label_file = models.FileField(
        storage=get_mito_storage,
        upload_to=volume_label_upload_to,
        blank=True,
        null=True,
    )
    label_type = models.CharField(
        max_length=20, choices=LabelType.choices, default=LabelType.NONE
    )

    shape_z = models.PositiveIntegerField(null=True, blank=True)
    shape_y = models.PositiveIntegerField(null=True, blank=True)
    shape_x = models.PositiveIntegerField(null=True, blank=True)

    voxel_size_z = models.FloatField(null=True, blank=True)
    voxel_size_y = models.FloatField(null=True, blank=True)
    voxel_size_x = models.FloatField(null=True, blank=True)

    file_format = models.CharField(
        max_length=10, choices=FileFormat.choices, default=FileFormat.TIFF
    )
    metadata = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=20, choices=VolumeStatus.choices, default=VolumeStatus.REGISTERED
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.name} ({self.project.title})"

    @property
    def has_label(self) -> bool:
        return self.label_type != LabelType.NONE and bool(
            self.label_path or self.label_file
        )

    @property
    def image_location(self) -> str:
        """Path or storage name identifying the image, whichever is set."""
        if self.image_file:
            return self.image_file.name
        return self.image_path

    @property
    def label_location(self) -> str:
        if self.label_file:
            return self.label_file.name
        return self.label_path
