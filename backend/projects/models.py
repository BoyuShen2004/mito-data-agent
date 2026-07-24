from django.conf import settings
from django.db import models

from core.choices import AnnotationType, ProjectStatus, WorkflowType


class Project(models.Model):
    """An annotation project. Holds one or more datasets (see :class:`Dataset`).

    The hierarchy is project → dataset → volume: a project groups the datasets
    a requester submitted, each dataset groups the image/mask volume pairs
    registered from it.
    """

    title = models.CharField(max_length=255)
    # Legacy single-dataset name, kept so old rows and callers still read.
    # The datasets a project holds now live in the ``datasets`` relation; this
    # mirrors the first one for backwards compatibility.
    dataset = models.CharField(max_length=255, blank=True)
    institution = models.ForeignKey(
        "accounts.Institution",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="projects",
    )
    description = models.TextField(blank=True)
    # Optional biomedical EM metadata that cannot be derived from the files
    # (organism, tissue, cell type, imaging modality, instrument, conditions,
    # source, publication, notes, …). Kept flexible as structured JSON.
    metadata = models.JSONField(default=dict, blank=True)
    annotation_target = models.CharField(max_length=100, default="mitochondria")
    annotation_type = models.CharField(
        max_length=30,
        choices=AnnotationType.choices,
        default=AnnotationType.INSTANCE,
    )
    # The high-level pipeline requested for this dataset (annotation /
    # proofreading / segmentation). Shares the same models and services; drives
    # only configuration and service-layer branching, not a separate pipeline.
    workflow_type = models.CharField(
        max_length=20,
        choices=WorkflowType.choices,
        default=WorkflowType.ANNOTATION,
    )
    status = models.CharField(
        max_length=20, choices=ProjectStatus.choices, default=ProjectStatus.DRAFT
    )
    deadline = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_projects",
    )

    # Manager review gate: requester-registered data must be reviewed by a
    # manager before its volumes can be split or assigned. Manager-registered
    # data is reviewed on creation.
    manager_reviewed = models.BooleanField(default=False)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_projects",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.title


class Dataset(models.Model):
    """A dataset registered under a project, grouping its volume pairs.

    One project may hold several datasets (e.g. a CellMap set and a MitoEM set),
    and each dataset holds many image/mask volume pairs. Metadata lives here
    rather than on the project because it describes *this* data — organism,
    publication, label classes — and two datasets in one project may differ.
    """

    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="datasets"
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    # The source directories this dataset was registered from, recorded so the
    # registration can be understood (and repeated) later.
    image_directory = models.CharField(max_length=1024, blank=True)
    mask_directory = models.CharField(max_length=1024, blank=True)
    # Biomedical + provenance metadata for this dataset (organism, tissue,
    # publication, label_classes, channel_names, split, …).
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        # A dataset name identifies the data within its project.
        constraints = [
            models.UniqueConstraint(
                fields=["project", "name"], name="unique_dataset_name_per_project"
            )
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.project.title})"
