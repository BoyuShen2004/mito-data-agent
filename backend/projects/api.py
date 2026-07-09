from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from annotation.services import calculate_annotator_workload
from core.permissions import IsManager
from payments.services import calculate_payment_summary, payment_summary_by_annotator

from .models import Project
from .serializers import ProjectSerializer
from .services import calculate_project_progress, create_project


class ProjectViewSet(viewsets.ModelViewSet):
    """CRUD for projects plus a progress/summary action. Managers only."""

    queryset = Project.objects.select_related("institution", "created_by").all()
    serializer_class = ProjectSerializer
    permission_classes = [IsManager]

    def perform_create(self, serializer):
        data = serializer.validated_data
        project = create_project(
            title=data["title"],
            created_by=self.request.user,
            institution=data.get("institution"),
            description=data.get("description", ""),
            annotation_target=data.get("annotation_target", "mitochondria"),
            annotation_type=data.get("annotation_type"),
            deadline=data.get("deadline"),
            status=data.get("status"),
        )
        serializer.instance = project

    @action(detail=True, methods=["get"])
    def summary(self, request, pk=None):
        project = self.get_object()
        return Response(
            {
                "project": ProjectSerializer(project).data,
                "progress": calculate_project_progress(project),
                "workload": calculate_annotator_workload(project=project),
                "payment": _decimal_summary(
                    calculate_payment_summary(project=project)
                ),
            }
        )

    @action(detail=True, methods=["get"], url_path="payment-summary")
    def payment_summary(self, request, pk=None):
        project = self.get_object()
        return Response(
            {
                "totals": _decimal_summary(
                    calculate_payment_summary(project=project)
                ),
                "by_annotator": payment_summary_by_annotator(project=project),
            }
        )


def _decimal_summary(summary: dict) -> dict:
    """Coerce Decimal values in the payment summary to floats for JSON."""
    out = dict(summary)
    out["total_amount"] = float(summary["total_amount"])
    out["by_status"] = {
        key: {"count": val["count"], "amount": float(val["amount"])}
        for key, val in summary["by_status"].items()
    }
    return out
