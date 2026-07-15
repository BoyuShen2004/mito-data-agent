from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from accounts.roles import is_manager
from annotation.services import calculate_annotator_workload
from core.lifecycle import (
    Lifecycle,
    filter_projects_by_lifecycle,
    project_lifecycle_counts,
)
from core.permissions import CanRegisterData

from .models import Project
from .serializers import ProjectSerializer
from .services import calculate_project_progress, create_project, mark_project_reviewed


class ProjectViewSet(viewsets.ModelViewSet):
    """CRUD for projects plus a progress/summary action.

    Managers see and manage every project. Requesters see and manage only the
    projects they created. Editing/deleting is restricted to managers and the
    owning requester (enforced by the per-object queryset below).
    """

    serializer_class = ProjectSerializer
    permission_classes = [CanRegisterData]

    def get_queryset(self):
        qs = Project.objects.select_related("institution", "created_by").all()
        if not is_manager(self.request.user):
            # Requesters (Institutions) only see their own projects.
            qs = qs.filter(created_by=self.request.user)
        # Optional lifecycle filter: ?lifecycle=new|to_proofread|done.
        lifecycle = self.request.query_params.get("lifecycle")
        if lifecycle in Lifecycle.values:
            qs = filter_projects_by_lifecycle(qs, lifecycle)
        return qs

    def perform_create(self, serializer):
        data = serializer.validated_data
        project = create_project(
            title=data["title"],
            created_by=self.request.user,
            institution=data.get("institution"),
            description=data.get("description", ""),
            annotation_target=data.get("annotation_target", "mitochondria"),
            annotation_type=data.get("annotation_type"),
            workflow_type=data.get("workflow_type"),
            deadline=data.get("deadline"),
            status=data.get("status"),
            dataset=data.get("dataset", ""),
            metadata=data.get("metadata"),
            # Manager-created projects are reviewed on creation.
            reviewed=is_manager(self.request.user),
        )
        serializer.instance = project

    @action(detail=False, methods=["get"], url_path="lifecycle-counts")
    def lifecycle_counts(self, request):
        """Return {new, to_proofread, done} counts over the caller's projects.

        Respects the same visibility rules as the list endpoint: managers see
        every project, Institutions see only their own.
        """
        # Bypass any ?lifecycle= filter so every bucket is counted.
        qs = Project.objects.select_related("institution", "created_by")
        if not is_manager(request.user):
            qs = qs.filter(created_by=request.user)
        return Response(project_lifecycle_counts(qs))

    @action(detail=True, methods=["get"])
    def summary(self, request, pk=None):
        project = self.get_object()
        payload = {
            "project": ProjectSerializer(project).data,
            "progress": calculate_project_progress(project),
        }
        # Workload is manager-facing detail; requesters just see progress.
        if is_manager(request.user):
            payload["workload"] = calculate_annotator_workload(project=project)
        return Response(payload)

    @action(detail=True, methods=["post"])
    def review(self, request, pk=None):
        """Manager marks a project reviewed (or not), enabling assignment."""
        if not is_manager(request.user):
            return Response(
                {"detail": "Manager access required."},
                status=status.HTTP_403_FORBIDDEN,
            )
        project = self.get_object()
        reviewed = request.data.get("reviewed", True)
        mark_project_reviewed(project, reviewer=request.user, reviewed=bool(reviewed))
        return Response(ProjectSerializer(project).data)
