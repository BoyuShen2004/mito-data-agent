from django.contrib import admin

from .models import Volume


@admin.register(Volume)
class VolumeAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "project",
        "label_type",
        "file_format",
        "shape_z",
        "shape_y",
        "shape_x",
        "status",
        "created_at",
    )
    list_filter = ("label_type", "file_format", "status")
    search_fields = ("name", "image_path")
