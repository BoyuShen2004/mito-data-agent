from rest_framework import serializers

from .models import PaymentRecord


class PaymentRecordSerializer(serializers.ModelSerializer):
    annotator_username = serializers.CharField(
        source="annotator.username", read_only=True
    )
    project_title = serializers.CharField(
        source="task.project.title", read_only=True, default=""
    )
    task_type = serializers.CharField(source="task.task_type", read_only=True)

    class Meta:
        model = PaymentRecord
        fields = [
            "id",
            "annotator",
            "annotator_username",
            "task",
            "task_type",
            "project_title",
            "amount",
            "status",
            "created_at",
            "paid_at",
        ]
