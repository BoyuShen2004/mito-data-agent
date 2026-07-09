from django.contrib import admin

from .models import AgentPlan


@admin.register(AgentPlan)
class AgentPlanAdmin(admin.ModelAdmin):
    list_display = ("id", "project", "plan_type", "status", "created_by", "created_at")
    list_filter = ("status", "plan_type")
