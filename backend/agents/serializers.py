from rest_framework import serializers

from .models import AgentPlan


class AgentPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentPlan
        fields = [
            "id",
            "project",
            "plan_type",
            "plan_json",
            "status",
            "created_by",
            "approved_by",
            "created_at",
            "approved_at",
        ]
        read_only_fields = [
            "project",
            "status",
            "created_by",
            "approved_by",
            "created_at",
            "approved_at",
        ]
