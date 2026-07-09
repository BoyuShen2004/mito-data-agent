from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.roles import is_manager
from core.choices import ACTIVE_TASK_STATUSES, TaskStatus
from core.permissions import IsAnnotator, IsManager
from projects.models import Project

from .models import AnnotationSubmission, AnnotationTask
from .serializers import (
    AnnotationSubmissionSerializer,
    AnnotationTaskSerializer,
    ReviewSerializer,
    SubmitTaskSerializer,
)
from .services import assign_tasks_rule_based, review_submission, submit_annotation


class ProjectTasksView(generics.ListAPIView):
    """List every task under a project. Managers only."""

    serializer_class = AnnotationTaskSerializer
    permission_classes = [IsManager]

    def get_queryset(self):
        qs = AnnotationTask.objects.filter(
            project_id=self.kwargs["project_id"]
        ).select_related("volume", "project", "assigned_to")
        status_param = self.request.query_params.get("status")
        if status_param:
            qs = qs.filter(status=status_param)
        return qs


class TaskDetailView(generics.RetrieveUpdateAPIView):
    """Retrieve or edit a task. Managers can edit; annotators see own tasks."""

    serializer_class = AnnotationTaskSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = AnnotationTask.objects.select_related(
            "volume", "project", "assigned_to"
        )
        if is_manager(self.request.user):
            return qs
        return qs.filter(assigned_to=self.request.user)

    def update(self, request, *args, **kwargs):
        if not is_manager(request.user):
            # Annotators may only move their own task into "in_progress".
            task = self.get_object()
            new_status = request.data.get("status")
            if new_status != TaskStatus.IN_PROGRESS:
                return Response(
                    {"detail": "Annotators may only start their tasks."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            task.status = TaskStatus.IN_PROGRESS
            task.save(update_fields=["status"])
            return Response(AnnotationTaskSerializer(task).data)
        return super().update(request, *args, **kwargs)


class AssignTasksView(APIView):
    """Run rule-based assignment for a project. Managers only."""

    permission_classes = [IsManager]

    def post(self, request, project_id):
        project = get_object_or_404(Project, pk=project_id)
        summary = assign_tasks_rule_based(project=project)
        return Response(summary)


class MyTasksView(generics.ListAPIView):
    """Tasks currently assigned to the logged-in annotator."""

    serializer_class = AnnotationTaskSerializer
    permission_classes = [IsAnnotator]

    def get_queryset(self):
        active = list(ACTIVE_TASK_STATUSES) + [TaskStatus.REVISION_REQUESTED]
        return (
            AnnotationTask.objects.filter(
                assigned_to=self.request.user, status__in=active
            )
            .select_related("volume", "project")
        )


class MyCompletedTasksView(generics.ListAPIView):
    """Submitted/approved/rejected tasks for the logged-in annotator."""

    serializer_class = AnnotationTaskSerializer
    permission_classes = [IsAnnotator]

    def get_queryset(self):
        done = [TaskStatus.SUBMITTED, TaskStatus.APPROVED, TaskStatus.REJECTED]
        return (
            AnnotationTask.objects.filter(
                assigned_to=self.request.user, status__in=done
            )
            .select_related("volume", "project")
        )


class SubmitTaskView(APIView):
    """Annotator uploads a completed label file for a task."""

    permission_classes = [IsAnnotator]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, pk):
        task = get_object_or_404(AnnotationTask, pk=pk)
        if task.assigned_to_id != request.user.id and not is_manager(request.user):
            return Response(
                {"detail": "This task is not assigned to you."},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = SubmitTaskSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        submission = submit_annotation(
            task=task,
            annotator=request.user,
            label_file=serializer.validated_data["label_file"],
            notes=serializer.validated_data.get("notes", ""),
        )
        return Response(
            AnnotationSubmissionSerializer(submission).data,
            status=status.HTTP_201_CREATED,
        )


class SubmissionListView(generics.ListAPIView):
    """List submissions. Managers see all; annotators see their own."""

    serializer_class = AnnotationSubmissionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = AnnotationSubmission.objects.select_related(
            "task", "task__volume", "annotator"
        )
        if not is_manager(self.request.user):
            qs = qs.filter(annotator=self.request.user)
        task_status = self.request.query_params.get("task_status")
        if task_status:
            qs = qs.filter(task__status=task_status)
        return qs


class SubmissionDetailView(generics.RetrieveAPIView):
    serializer_class = AnnotationSubmissionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = AnnotationSubmission.objects.select_related(
            "task", "task__volume", "annotator"
        )
        if not is_manager(self.request.user):
            qs = qs.filter(annotator=self.request.user)
        return qs


class ReviewSubmissionView(APIView):
    """Manager approves, rejects, or requests revision on a submission."""

    permission_classes = [IsManager]

    def post(self, request, pk):
        submission = get_object_or_404(AnnotationSubmission, pk=pk)
        serializer = ReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        review = review_submission(
            submission=submission,
            reviewer=request.user,
            decision=serializer.validated_data["decision"],
            comments=serializer.validated_data.get("comments", ""),
        )
        submission.refresh_from_db()
        return Response(
            {
                "review_id": review.id,
                "submission": AnnotationSubmissionSerializer(submission).data,
            }
        )
