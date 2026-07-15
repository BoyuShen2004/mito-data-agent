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


class WorkflowType(models.TextChoices):
    """The high-level pipeline requested for a dataset.

    * ``annotation``   — labels are created from raw/unlabeled data.
    * ``proofreading`` — existing predictions/labels are corrected.
    * ``segmentation`` — a processing/model-inference job generates a result,
      which may be delivered directly or optionally continue into proofreading.

    These share one dataset registration, volume metadata, task assignment,
    submission, review, and result-tracking implementation; they differ only in
    configuration and service-layer branching, not in duplicated pipelines.
    """

    ANNOTATION = "annotation", "Annotation"
    PROOFREADING = "proofreading", "Proofreading"
    SEGMENTATION = "segmentation", "Segmentation"


# Maps the (older, more specific) annotation_type to a workflow_type. Used to
# backfill workflow_type and to default it when only annotation_type is given.
ANNOTATION_TYPE_TO_WORKFLOW = {
    AnnotationType.SEMANTIC: WorkflowType.ANNOTATION,
    AnnotationType.INSTANCE: WorkflowType.ANNOTATION,
    AnnotationType.PROOFREADING: WorkflowType.PROOFREADING,
}


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


# --- Processing / HPC jobs --------------------------------------------------

class ProcessingBackend(models.TextChoices):
    LOCAL = "local", "Local / mock"
    SLURM = "slurm", "SLURM"


class ProcessingJobStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    SUBMITTED = "submitted", "Submitted"
    RUNNING = "running", "Running"
    SUCCEEDED = "succeeded", "Succeeded"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"


# Job statuses that are still active (a dispatcher should keep polling them).
ACTIVE_JOB_STATUSES = (
    ProcessingJobStatus.SUBMITTED,
    ProcessingJobStatus.RUNNING,
)
TERMINAL_JOB_STATUSES = (
    ProcessingJobStatus.SUCCEEDED,
    ProcessingJobStatus.FAILED,
    ProcessingJobStatus.CANCELLED,
)


class ProcessingJobType(models.TextChoices):
    INSPECT = "inspect", "Inspect"
    INGEST = "ingest", "Ingest"
    PREDICT = "predict", "Predict"
    SEED = "seed", "Seed"
    GENERATE_TASKS = "generate_tasks", "Generate tasks"
    QUALITY_CONTROL = "quality_control", "Quality control"
    CONVERT_VISUALIZATION = "convert_visualization", "Convert for visualization"
    GENERATE_MESH = "generate_mesh", "Generate mesh"
    PUBLISH = "publish", "Publish"


# Maps a volume's label state to the task type produced when splitting it.
# ``partial`` defaults to manual annotation but the manager may override.
LABEL_TYPE_TO_TASK_TYPE = {
    LabelType.NONE: TaskType.MANUAL_ANNOTATION,
    LabelType.PREDICTION: TaskType.PREDICTION_PROOFREADING,
    LabelType.PROOFREAD: TaskType.FINAL_REVIEW,
    LabelType.PARTIAL: TaskType.MANUAL_ANNOTATION,
}
