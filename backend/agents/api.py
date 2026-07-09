"""Placeholder agent-plan endpoints.

These persist a proposed plan (JSON) that a manager can approve. Full
LangGraph integration is intentionally out of scope for the MVP; approving a
plan here only flips its status. Future work will have it call the
deterministic service layer.
"""

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.choices import AgentPlanStatus
from core.permissions import IsManager
from projects.models import Project

from .models import AgentPlan
from .serializers import AgentPlanSerializer


class ProjectAgentPlansView(generics.ListCreateAPIView):
    serializer_class = AgentPlanSerializer
    permission_classes = [IsManager]

    def get_queryset(self):
        return AgentPlan.objects.filter(project_id=self.kwargs["project_id"])

    def perform_create(self, serializer):
        project = get_object_or_404(Project, pk=self.kwargs["project_id"])
        serializer.save(project=project, created_by=self.request.user)


class AgentPlanDetailView(generics.RetrieveAPIView):
    queryset = AgentPlan.objects.all()
    serializer_class = AgentPlanSerializer
    permission_classes = [IsManager]


class _AgentPlanDecisionView(APIView):
    permission_classes = [IsManager]
    decision: str = ""

    def post(self, request, pk):
        plan = get_object_or_404(AgentPlan, pk=pk)
        plan.status = self.decision
        plan.approved_by = request.user
        plan.approved_at = timezone.now()
        plan.save(update_fields=["status", "approved_by", "approved_at"])
        return Response(AgentPlanSerializer(plan).data, status=status.HTTP_200_OK)


class AgentPlanApproveView(_AgentPlanDecisionView):
    decision = AgentPlanStatus.APPROVED


class AgentPlanRejectView(_AgentPlanDecisionView):
    decision = AgentPlanStatus.REJECTED
