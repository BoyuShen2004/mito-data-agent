from django.contrib import admin

from .models import Project


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "institution",
        "annotation_type",
        "status",
        "deadline",
        "created_by",
        "created_at",
    )
    list_filter = ("status", "annotation_type")
    search_fields = ("title", "description")
