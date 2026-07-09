from django.contrib import admin

from .models import AnnotatorProfile, Institution, UserProfile


@admin.register(Institution)
class InstitutionAdmin(admin.ModelAdmin):
    list_display = ("name", "institution_type", "contact_email", "created_at")
    search_fields = ("name", "contact_email")


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "institution", "created_at")
    list_filter = ("role",)
    search_fields = ("user__username", "institution_name")


@admin.register(AnnotatorProfile)
class AnnotatorProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "is_active_annotator",
        "max_active_tasks",
        "pay_rate_per_task",
        "quality_score",
    )
    list_filter = ("is_active_annotator",)
    search_fields = ("user__username",)
