from django.contrib import admin

from .models import AnnotationSubmission, AnnotationTask, ReviewRecord


@admin.register(AnnotationTask)
class AnnotationTaskAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "project",
        "volume",
        "frame_label",
        "task_type",
        "status",
        "assigned_to",
        "priority",
        "payment_amount",
    )
    list_filter = ("status", "task_type", "project")
    search_fields = ("volume__name", "assigned_to__username")


@admin.register(AnnotationSubmission)
class AnnotationSubmissionAdmin(admin.ModelAdmin):
    list_display = ("id", "task", "annotator", "qc_status", "submitted_at")
    list_filter = ("qc_status",)
    search_fields = ("task__id", "annotator__username")


@admin.register(ReviewRecord)
class ReviewRecordAdmin(admin.ModelAdmin):
    list_display = ("id", "submission", "reviewer", "decision", "reviewed_at")
    list_filter = ("decision",)
