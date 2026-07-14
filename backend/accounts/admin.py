from django.contrib import admin, messages
from django.db.models import Count, F, Q
from django.utils.html import format_html

from annotation.models import AnnotationSubmission, AnnotationTask
from core.admin_common import ManagerAdminAccessMixin, count_link
from core.choices import ACTIVE_TASK_STATUSES

from .models import AnnotatorProfile, Institution, UserProfile


class AtCapacityFilter(admin.SimpleListFilter):
    title = "capacity"
    parameter_name = "capacity"

    def lookups(self, request, model_admin):
        return (("full", "At capacity"), ("available", "Has spare capacity"))

    def queryset(self, request, queryset):
        queryset = queryset.annotate(
            _active=Count(
                "user__annotation_tasks",
                filter=Q(user__annotation_tasks__status__in=ACTIVE_TASK_STATUSES),
            )
        )
        if self.value() == "full":
            return queryset.filter(_active__gte=F("max_active_tasks"))
        if self.value() == "available":
            return queryset.filter(_active__lt=F("max_active_tasks"))
        return queryset


@admin.register(Institution)
class InstitutionAdmin(ManagerAdminAccessMixin, admin.ModelAdmin):
    list_display = (
        "name",
        "institution_type",
        "contact_email",
        "member_count",
        "project_count",
        "created_at",
    )
    search_fields = ("name", "contact_email")
    ordering = ("name",)
    list_per_page = 50
    empty_value_display = "—"
    readonly_fields = ("created_at",)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            _members=Count("members", distinct=True),
            _projects=Count("projects", distinct=True),
        )

    @admin.display(description="Members", ordering="_members")
    def member_count(self, obj):
        return obj._members

    @admin.display(description="Projects", ordering="_projects")
    def project_count(self, obj):
        return obj._projects


@admin.register(UserProfile)
class UserProfileAdmin(ManagerAdminAccessMixin, admin.ModelAdmin):
    list_display = (
        "user",
        "full_name",
        "email",
        "role",
        "institution_display",
        "user_active",
        "created_at",
    )
    list_filter = (
        "role",
        ("institution", admin.RelatedOnlyFieldListFilter),
        "user__is_active",
    )
    search_fields = (
        "user__username",
        "user__email",
        "user__first_name",
        "user__last_name",
        "institution_name",
    )
    ordering = ("user__username",)
    list_select_related = ("user", "institution")
    list_per_page = 50
    empty_value_display = "—"
    readonly_fields = ("created_at",)

    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))
        # Only superusers may change a user's app role (prevents managers from
        # minting other managers).
        if not request.user.is_superuser:
            fields.append("role")
        return tuple(fields)

    @admin.display(description="Name")
    def full_name(self, obj):
        return obj.user.get_full_name() or "—"

    @admin.display(description="Email")
    def email(self, obj):
        return obj.user.email or "—"

    @admin.display(description="Institution")
    def institution_display(self, obj):
        return obj.institution.name if obj.institution else (obj.institution_name or "—")

    @admin.display(description="Active", boolean=True)
    def user_active(self, obj):
        return obj.user.is_active


@admin.register(AnnotatorProfile)
class AnnotatorProfileAdmin(ManagerAdminAccessMixin, admin.ModelAdmin):
    list_display = (
        "user",
        "email",
        "is_active_annotator",
        "max_active_tasks",
        "active_task_count",
        "quality_score",
        "work_links",
    )
    list_editable = ("is_active_annotator", "max_active_tasks")
    list_filter = ("is_active_annotator", AtCapacityFilter)
    search_fields = ("user__username", "user__email", "user__first_name", "user__last_name")
    ordering = ("user__username",)
    list_select_related = ("user",)
    list_per_page = 50
    empty_value_display = "—"
    actions = ("activate_annotators", "deactivate_annotators")

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            _active=Count(
                "user__annotation_tasks",
                filter=Q(user__annotation_tasks__status__in=ACTIVE_TASK_STATUSES),
            )
        )

    @admin.display(description="Email")
    def email(self, obj):
        return obj.user.email or "—"

    @admin.display(description="Active tasks", ordering="_active")
    def active_task_count(self, obj):
        return obj._active

    @admin.display(description="Work")
    def work_links(self, obj):
        tasks = count_link(
            AnnotationTask, "tasks", assigned_to__id__exact=obj.user_id
        )
        subs = count_link(
            AnnotationSubmission, "submissions", annotator__id__exact=obj.user_id
        )
        return format_html("{} · {}", tasks, subs)

    @admin.action(description="Activate selected annotators")
    def activate_annotators(self, request, queryset):
        updated = queryset.update(is_active_annotator=True)
        self.message_user(
            request, f"Activated {updated} annotator(s).", messages.SUCCESS
        )

    @admin.action(description="Deactivate selected annotators")
    def deactivate_annotators(self, request, queryset):
        updated = queryset.update(is_active_annotator=False)
        self.message_user(
            request, f"Deactivated {updated} annotator(s).", messages.SUCCESS
        )
