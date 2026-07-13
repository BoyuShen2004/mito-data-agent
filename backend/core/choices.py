"""Shared enumerated choices used across apps.

Centralising these keeps the label-state -> task-type mapping and the task
lifecycle consistent between models, the service layer, and the service-layer
callers (DRF views, admin actions, management commands).
"""

from django.db import models


class UserRole(models.TextChoices):
    MANAGER = "manager", "Manager"
    ANNOTATOR = "annotator", "Annotator"
    REQUESTER = "requester", "Requester"
    # Legacy roles kept for backwards compatibility with existing records.
    CLIENT = "client", "Client"
    REVIEWER = "reviewer", "Reviewer"


class AnnotationType(models.TextChoices):
    SEMANTIC = "semantic_segmentation", "Semantic segmentation"
    INSTANCE = "instance_segmentation", "Instance segmentation"
    PROOFREADING = "proofreading", "Proofreading"


class ProjectStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    ACTIVE = "active", "Active"
    IN_ANNOTATION = "in_annotation", "In annotation"
    IN_REVIEW = "in_review", "In review"
    COMPLETED = "completed", "Completed"
    DELIVERED = "delivered", "Delivered"
    CANCELLED = "cancelled", "Cancelled"


class LabelType(models.TextChoices):
    NONE = "none", "No label"
    PREDICTION = "prediction", "Model prediction"
    PROOFREAD = "proofread", "Proofread"
    PARTIAL = "partial", "Partial"


class FileFormat(models.TextChoices):
    TIFF = "tiff", "TIFF"
    ZARR = "zarr", "Zarr"
    HDF5 = "hdf5", "HDF5"
    N5 = "n5", "N5"
    OTHER = "other", "Other"


class VolumeStatus(models.TextChoices):
    REGISTERED = "registered", "Registered"
    SPLIT = "split", "Split into tasks"
    IN_ANNOTATION = "in_annotation", "In annotation"
    COMPLETED = "completed", "Completed"


class TaskType(models.TextChoices):
    MANUAL_ANNOTATION = "manual_annotation", "Manual annotation"
    PREDICTION_PROOFREADING = "prediction_proofreading", "Prediction proofreading"
    FINAL_REVIEW = "final_review", "Final review"
    QC_REVIEW = "qc_review", "QC review"


class TaskStatus(models.TextChoices):
    UNASSIGNED = "unassigned", "Unassigned"
    ASSIGNED = "assigned", "Assigned"
    IN_PROGRESS = "in_progress", "In progress"
    SUBMITTED = "submitted", "Submitted"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    REVISION_REQUESTED = "revision_requested", "Revision requested"


# Statuses that count against an annotator's active-task capacity.
ACTIVE_TASK_STATUSES = (TaskStatus.ASSIGNED, TaskStatus.IN_PROGRESS)


class QCStatus(models.TextChoices):
    NOT_RUN = "not_run", "Not run"
    PASSED = "passed", "Passed"
    WARNING = "warning", "Warning"
    FAILED = "failed", "Failed"


class ReviewDecision(models.TextChoices):
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    REVISION_REQUESTED = "revision_requested", "Revision requested"


# Maps a volume's label state to the task type produced when splitting it.
# ``partial`` defaults to manual annotation but the manager may override.
LABEL_TYPE_TO_TASK_TYPE = {
    LabelType.NONE: TaskType.MANUAL_ANNOTATION,
    LabelType.PREDICTION: TaskType.PREDICTION_PROOFREADING,
    LabelType.PROOFREAD: TaskType.FINAL_REVIEW,
    LabelType.PARTIAL: TaskType.MANUAL_ANNOTATION,
}
