from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.roles import is_annotator, is_manager
from core.choices import ACTIVE_TASK_STATUSES, TaskStatus
from core.permissions import IsAnnotator, IsManager
from projects.models import Project

from .models import AnnotationSubmission, AnnotationTask
from .serializers import (
    AnnotationSubmissionSerializer,
    AnnotationTaskSerializer,
    AssignmentPlanSerializer,
    ReviewSerializer,
    SubmitInappTaskSerializer,
    SubmitTaskSerializer,
)
from .services import (
    apply_assignment_plan,
    assign_task_to_annotator,
    auto_assign_project,
    can_edit_task,
    can_view_task,
    can_view_volume,
    get_label_max_id,
    get_label_slice_ids,
    get_labels_3d_preview,
    get_labels_summary,
    get_task_proofreading_info,
    get_visualization_state,
    list_assignment_plan_rows,
    predict_ai_mask,
    preview_assign_project,
    review_submission,
    run_watershed_task,
    set_label_lifecycle_action,
    set_label_slice_ids,
    submit_annotation,
    submit_inapp_annotation,
    track_task_fork,
    warm_ai_embedding,
)

User = get_user_model()


class ProjectTasksView(generics.ListAPIView):
    """List every task under a project. Managers only."""

    serializer_class = AnnotationTaskSerializer
    permission_classes = [IsManager]

    def get_queryset(self):
        qs = AnnotationTask.objects.filter(
            project_id=self.kwargs["project_id"]
        ).select_related("volume", "volume__dataset", "project", "assigned_to")
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
            "volume", "volume__dataset", "project", "assigned_to"
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
    """Auto-assign a project's volumes evenly across annotators. Managers only.

    Each volume becomes one whole-volume task (no frame splitting) and the tasks
    are balanced across active annotators. Requires a manager-reviewed project.
    """

    permission_classes = [IsManager]

    def post(self, request, project_id):
        project = get_object_or_404(Project, pk=project_id)
        summary = auto_assign_project(project)
        if not summary.get("reviewed", True):
            return Response(summary, status=status.HTTP_400_BAD_REQUEST)
        return Response(summary)


class AssignmentPlanRowsView(APIView):
    """List a project's assignment-plan rows. Managers only.

    Ensures a whole-volume task per volume (so every volume shows up as an
    editable row) but never proposes annotators — see
    :class:`AssignmentPlanPreviewView` for that. This is what the plan editor
    loads on open, so a manager can start assigning without first clicking
    "Auto-fill balanced plan".
    """

    permission_classes = [IsManager]

    def post(self, request, project_id):
        project = get_object_or_404(Project, pk=project_id)
        summary = list_assignment_plan_rows(project)
        if not summary.get("reviewed", True):
            return Response(summary, status=status.HTTP_400_BAD_REQUEST)

        tasks = (
            AnnotationTask.objects.filter(project=project)
            .select_related("volume", "volume__dataset", "project", "assigned_to")
            .order_by("-priority", "created_at")
        )
        rows = [AnnotationTaskSerializer(task).data for task in tasks]
        return Response(
            {
                "created_tasks": summary["created_tasks"],
                "skipped_volumes": summary["skipped_volumes"],
                "entries": rows,
            }
        )


class AssignmentPlanPreviewView(APIView):
    """Return an editable assignment plan for a project. Managers only.

    Ensures a whole-volume task per volume, then proposes a balanced annotator
    for each unassigned task *without committing it*. The response lists every
    task (serialized) with an extra ``proposed_annotator_id`` the manager can
    accept or override before saving via :class:`AssignmentPlanApplyView`.
    """

    permission_classes = [IsManager]

    def post(self, request, project_id):
        project = get_object_or_404(Project, pk=project_id)
        summary = preview_assign_project(project)
        if not summary.get("reviewed", True):
            return Response(summary, status=status.HTTP_400_BAD_REQUEST)

        proposed = summary["proposed"]
        tasks = (
            AnnotationTask.objects.filter(project=project)
            .select_related("volume", "volume__dataset", "project", "assigned_to")
            .order_by("-priority", "created_at")
        )
        rows = []
        for task in tasks:
            data = AnnotationTaskSerializer(task).data
            # Already-assigned tasks keep their annotator; unassigned ones get
            # the proposed pick (may be null when no annotator has capacity).
            data["proposed_annotator_id"] = proposed.get(
                task.id, task.assigned_to_id
            )
            rows.append(data)

        return Response(
            {
                "created_tasks": summary["created_tasks"],
                "skipped_volumes": summary["skipped_volumes"],
                "entries": rows,
            }
        )


class AssignmentPlanApplyView(APIView):
    """Commit a manager-edited assignment plan in one transaction. Managers only.

    Accepts ``{"entries": [{task_id, annotator_id?, priority?, difficulty?,
    instructions?, deadline?}, ...]}``. Reassignment updates tasks in place; a
    null/omitted ``annotator_id`` unassigns. Requires a manager-reviewed project.
    """

    permission_classes = [IsManager]

    def post(self, request, project_id):
        project = get_object_or_404(Project, pk=project_id)
        if not project.manager_reviewed:
            return Response(
                {"detail": "Review the project before assigning its tasks."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = AssignmentPlanSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        entries = serializer.validated_data["entries"]

        # Validate every referenced annotator up front so the transaction only
        # runs on a fully-valid plan.
        annotator_ids = {
            e["annotator_id"]
            for e in entries
            if e.get("annotator_id") is not None
        }
        annotators_by_id = {}
        for uid in annotator_ids:
            user = get_object_or_404(User, pk=uid)
            if not is_annotator(user):
                return Response(
                    {"detail": f"User {user.username} is not an annotator."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            annotators_by_id[uid] = user

        try:
            summary = apply_assignment_plan(
                project, entries, annotators_by_id=annotators_by_id
            )
        except ValueError as exc:
            return Response(
                {"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST
            )
        return Response(summary)


class AssignTaskView(APIView):
    """Manually assign or reassign a single task to an annotator. Managers only.

    Reassigning updates the existing task in place (no duplicate task is
    created). Passing a null/blank ``annotator_id`` unassigns the task.
    """

    permission_classes = [IsManager]

    def post(self, request, pk):
        task = get_object_or_404(AnnotationTask, pk=pk)
        if not task.project.manager_reviewed:
            return Response(
                {"detail": "Review the project before assigning its tasks."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        annotator_id = request.data.get("annotator_id")

        if annotator_id in (None, "", "null"):
            task = assign_task_to_annotator(task, annotator=None)
            return Response(AnnotationTaskSerializer(task).data)

        annotator = get_object_or_404(User, pk=annotator_id)
        if not is_annotator(annotator):
            return Response(
                {"detail": "Selected user is not an annotator."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        task = assign_task_to_annotator(task, annotator=annotator)
        return Response(AnnotationTaskSerializer(task).data)


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
            .select_related("volume", "volume__dataset", "project")
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
            .select_related("volume", "volume__dataset", "project")
        )


class TaskProofreadingView(APIView):
    """Return launch info for a task's proofreading tool (view/edit/download).

    Accessible to managers and the annotator the task is assigned to. Delegates
    to the configured proofreading provider via the service layer.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        task = get_object_or_404(
            AnnotationTask.objects.select_related("volume", "volume__dataset", "project"), pk=pk
        )
        if not can_view_task(request.user, task):
            return Response(
                {"detail": "You do not have access to this task."},
                status=status.HTTP_403_FORBIDDEN,
            )
        # Pass the user so requesters/non-assignees are downgraded to view-only.
        return Response(get_task_proofreading_info(task, request.user))


class TaskVisualizationView(APIView):
    """Return viewer URL + state for a task's volume. Any role that can view."""

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        task = get_object_or_404(
            AnnotationTask.objects.select_related("volume", "volume__dataset", "project"), pk=pk
        )
        if not can_view_task(request.user, task):
            return Response(
                {"detail": "You do not have access to this task."},
                status=status.HTTP_403_FORBIDDEN,
            )
        state = get_visualization_state(task)
        state["editable"] = can_edit_task(request.user, task)
        return Response(state)


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


class SubmitInappTaskView(APIView):
    """Submit a task's in-app working label copy for review — no file upload.

    Requires ``can_edit_task`` (manager or the assigned annotator), same
    gating as the editor endpoints themselves — matches the intent of
    ``SubmitTaskView`` (annotator, or a manager acting for one) but keyed off
    edit access rather than assignment alone, since a manager who directly
    edited a task in-app should also be able to submit it.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        task = get_object_or_404(
            AnnotationTask.objects.select_related("volume__project", "volume__dataset"),
            pk=pk,
        )
        if not can_edit_task(request.user, task):
            return Response(
                {"detail": "You do not have edit access to this task."},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = SubmitInappTaskSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            submission = submit_inapp_annotation(
                task=task,
                annotator=request.user,
                notes=serializer.validated_data.get("notes", ""),
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
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


# --- Slice streaming + in-app annotation -----------------------------------

from django.http import HttpResponse  # noqa: E402
from volumes.models import Volume  # noqa: E402

from .cellable_port.ai.registry import AiUnavailable  # noqa: E402
from .visualization.slice_io import (  # noqa: E402
    SliceIOError,
    render_image_slice_jpeg,
    render_image_slice_png,
    render_label_slice_png,
    volume_meta,
)


def _image_response(data: bytes, content_type: str, *, max_age: int) -> HttpResponse:
    resp = HttpResponse(data, content_type=content_type)
    resp["Cache-Control"] = f"private, max-age={max_age}"
    return resp


def _slice_params(request):
    axis = request.query_params.get("axis", "z")
    try:
        index = int(request.query_params.get("index", 0))
    except (TypeError, ValueError):
        index = 0
    window = request.query_params.get("window")
    level = request.query_params.get("level")
    window = float(window) if window not in (None, "") else None
    level = float(level) if level not in (None, "") else None
    return axis, index, window, level


class VolumeMetaView(APIView):
    """Shape/axes/dtype for a volume's image. Any role that can view it."""

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        volume = get_object_or_404(Volume.objects.select_related("project"), pk=pk)
        if not can_view_volume(request.user, volume):
            return Response({"detail": "No access to this volume."}, status=403)
        try:
            meta = volume_meta(volume.image_location)
        except SliceIOError as exc:
            return Response({"detail": str(exc)}, status=400)
        meta["has_label"] = bool(volume.label_location)
        meta["volume_id"] = volume.id
        return Response(meta)


class VolumeSliceView(APIView):
    """Stream one image slice. Any role that can view.

    Default (no ``window``/``level``): JPEG, normalised against the volume's
    display range — small and fast to produce on CPU alone (libjpeg-turbo),
    which is what makes scrubbing through slices smooth on an HPC compute
    node with no GPU. Brightness/contrast are then adjusted client-side.
    Passing ``window``/``level`` explicitly still returns lossless PNG
    (back-compat for any caller that wants server-side windowing).
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        volume = get_object_or_404(Volume.objects.select_related("project"), pk=pk)
        if not can_view_volume(request.user, volume):
            return Response({"detail": "No access to this volume."}, status=403)
        axis, index, window, level = _slice_params(request)
        try:
            if window is None and level is None:
                data = render_image_slice_jpeg(volume.image_location, axis, index)
                return _image_response(data, "image/jpeg", max_age=300)
            data = render_image_slice_png(
                volume.image_location, axis, index, window=window, level=level
            )
        except SliceIOError as exc:
            return Response({"detail": str(exc)}, status=400)
        return _image_response(data, "image/png", max_age=60)


class VolumeLabelSliceView(APIView):
    """Stream one label slice as an RGBA PNG overlay. Any role that can view."""

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        volume = get_object_or_404(Volume.objects.select_related("project"), pk=pk)
        if not can_view_volume(request.user, volume):
            return Response({"detail": "No access to this volume."}, status=403)
        if not volume.label_location:
            return Response({"detail": "Volume has no label."}, status=404)
        axis, index, _window, _level = _slice_params(request)
        try:
            png = render_label_slice_png(volume.label_location, axis, index)
        except SliceIOError as exc:
            return Response({"detail": str(exc)}, status=400)
        # Short cache: unlike the intensity image, labels change as people
        # annotate, and viewers watching progress should see recent edits.
        return _image_response(png, "image/png", max_age=15)


def _decode_seeds(raw):
    """Decode ``[{z, rle:[[start,len]...], shape:[h,w]}]`` into ``{z: bool mask}``."""
    import numpy as np

    seeds = {}
    for item in raw or []:
        z = int(item["z"])
        h, w = int(item["shape"][0]), int(item["shape"][1])
        flat = np.zeros(h * w, dtype=bool)
        for start, length in item.get("rle", []):
            flat[int(start) : int(start) + int(length)] = True
        seeds[z] = flat.reshape(h, w)
    return seeds


class TaskTrackView(APIView):
    """Run fork-aware SAM2 tracking for one mito on a task. Editors only.

    Requesters are rejected here (mutation), matching the view-only UI. Body:
    ``{"seeds": [{z, rle, shape}], "z_range": [lo, hi]?}``.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        task = get_object_or_404(
            AnnotationTask.objects.select_related("volume", "project"), pk=pk
        )
        if not can_edit_task(request.user, task):
            return Response(
                {"detail": "You do not have edit access to this task."},
                status=status.HTTP_403_FORBIDDEN,
            )
        seeds = _decode_seeds(request.data.get("seeds"))
        if not seeds:
            return Response({"detail": "No seeds provided."}, status=400)
        z_range = request.data.get("z_range")
        if z_range:
            z_range = (int(z_range[0]), int(z_range[1]))
        try:
            result = track_task_fork(task, seeds, z_range=z_range)
        except (ValueError, SliceIOError) as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(result)


class TaskLabelStateView(APIView):
    """Editor bootstrap info: the next free instance id for this task's volume."""

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        task = get_object_or_404(AnnotationTask.objects.select_related("volume"), pk=pk)
        if not can_view_task(request.user, task):
            return Response(
                {"detail": "You do not have access to this task."}, status=403
            )
        try:
            max_id = get_label_max_id(task.volume)
        except SliceIOError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response({"max_label_id": max_id, "next_label_id": max_id + 1})


class TaskLabelIdsView(APIView):
    """Raw instance-id read/write for one label slice (the brush/eraser editor).

    GET returns the current ids RLE-encoded; PUT replaces the whole slice with
    client-painted ids and persists it. Editing requires ``can_edit_task``;
    viewing (so a manager/requester can watch progress) only needs view access.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        task = get_object_or_404(AnnotationTask.objects.select_related("volume"), pk=pk)
        if not can_view_task(request.user, task):
            return Response(
                {"detail": "You do not have access to this task."}, status=403
            )
        axis, index, _window, _level = _slice_params(request)
        try:
            return Response(get_label_slice_ids(task.volume, axis, index))
        except (ValueError, SliceIOError) as exc:
            return Response({"detail": str(exc)}, status=400)

    def put(self, request, pk):
        task = get_object_or_404(AnnotationTask.objects.select_related("volume"), pk=pk)
        if not can_edit_task(request.user, task):
            return Response(
                {"detail": "You do not have edit access to this task."}, status=403
            )
        axis = request.data.get("axis", "z")
        # "origin" tells the lifecycle tracker how to register a *brand new*
        # label id in this commit ("manual" — brush/erase/box-erase — or
        # "ai" — a committed Point/Box/Boundary preview); ids that already
        # have tracked state are always marked EDITED regardless. See
        # set_label_slice_ids's docstring.
        origin = request.data.get("origin", "manual")
        try:
            index = int(request.data.get("index"))
            shape = request.data["shape"]
            runs = request.data["runs"]
        except (TypeError, ValueError, KeyError):
            return Response({"detail": "axis, index, shape and runs are required."}, status=400)
        try:
            max_id = set_label_slice_ids(task.volume, axis, index, shape, runs, origin=origin)
        except (ValueError, SliceIOError) as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response({"max_label_id": max_id, "next_label_id": max_id + 1})


# --- Cellable-ported interactive AI tools (Point/Box/Boundary, Seeds) -------
# See progress/history/19-cellable-parity-annotator-brief.md and
# annotation/cellable_port/ for what these port and why.

class TaskPredictMaskView(APIView):
    """Point Mask / Box Mask / Boundary preview — ``POST
    /api/tasks/<id>/predict-mask/``. Body: ``{"axis", "index", "mode":
    "points"|"box"|"boundary", "points"?, "point_labels"?, "box"?}``.

    Read-only: returns a candidate mask (label-RLE, 0/1) for the client to
    merge locally and commit through the existing label-ids PUT — this view
    never writes to the working label copy itself. Editors only, matching
    the other mutation-adjacent slice endpoints.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        task = get_object_or_404(AnnotationTask.objects.select_related("volume"), pk=pk)
        if not can_edit_task(request.user, task):
            return Response(
                {"detail": "You do not have edit access to this task."}, status=403
            )
        axis = request.data.get("axis", "z")
        mode = request.data.get("mode")
        try:
            index = int(request.data.get("index"))
        except (TypeError, ValueError):
            return Response({"detail": "axis and index are required."}, status=400)
        try:
            result = predict_ai_mask(
                task,
                axis,
                index,
                mode,
                points=request.data.get("points"),
                point_labels=request.data.get("point_labels"),
                box=request.data.get("box"),
            )
        except AiUnavailable as exc:
            return Response({"detail": str(exc)}, status=503)
        except (ValueError, SliceIOError) as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(result)


class TaskWarmEmbeddingView(APIView):
    """``POST /api/tasks/<id>/warm-embedding/`` — body ``{"axis", "index"}``.
    Pre-computes the EfficientSAM embedding for one slice so a subsequent
    Point/Box/Boundary predict on it is decoder-only. Fire-and-forget from
    the frontend (slice-open / AI-tool entry / neighbor prefetch — see
    ``progress/history/23-cellable-parity-ort-and-prompt-ux.md``); a missing
    model is reported as ``{"warmed": false}`` with 200, not a 503 — warming
    is an optimization, not something the UI should treat as an error."""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        task = get_object_or_404(AnnotationTask.objects.select_related("volume"), pk=pk)
        if not can_edit_task(request.user, task):
            return Response(
                {"detail": "You do not have edit access to this task."}, status=403
            )
        axis = request.data.get("axis", "z")
        try:
            index = int(request.data.get("index"))
        except (TypeError, ValueError):
            return Response({"detail": "axis and index are required."}, status=400)
        try:
            warmed = warm_ai_embedding(task, axis, index)
        except AiUnavailable:
            return Response({"warmed": False})
        except SliceIOError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response({"warmed": warmed})


class TaskWatershedView(APIView):
    """3D watershed (Seeds tool) — ``POST /api/tasks/<id>/watershed/``. Body:
    ``{"label": int, "seeds": [{"z", "y", "x"}, ...]}``. Editors only; writes
    the result to the volume's *working* label copy (never the official
    one), same staging rule as tracking."""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        task = get_object_or_404(
            AnnotationTask.objects.select_related("volume", "project"), pk=pk
        )
        if not can_edit_task(request.user, task):
            return Response(
                {"detail": "You do not have edit access to this task."}, status=403
            )
        try:
            target_label = int(request.data.get("label"))
        except (TypeError, ValueError):
            return Response({"detail": "label is required."}, status=400)
        seeds_raw = request.data.get("seeds") or []
        try:
            seeds_zyx = [(int(s["z"]), int(s["y"]), int(s["x"])) for s in seeds_raw]
        except (KeyError, TypeError, ValueError):
            return Response({"detail": "seeds must be [{z, y, x}, ...]."}, status=400)
        if not seeds_zyx:
            return Response({"detail": "No seed points provided."}, status=400)
        try:
            result = run_watershed_task(task, target_label, seeds_zyx)
        except (ValueError, SliceIOError) as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(result)


class TaskLabelsSummaryView(APIView):
    """``GET /api/tasks/<id>/labels-summary/`` — per-label voxel count +
    first/last z across the whole working label volume. Backs the Labels
    panel's "All labels" scope. Any role that can view the task."""

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        task = get_object_or_404(AnnotationTask.objects.select_related("volume"), pk=pk)
        if not can_view_task(request.user, task):
            return Response(
                {"detail": "You do not have access to this task."}, status=403
            )
        return Response(get_labels_summary(task.volume))


class TaskLabels3DView(APIView):
    """``GET /api/tasks/<id>/labels-3d/?labels=1,2,3`` — a compact binary 3D
    preview grid for the requested label ids (see
    ``cellable_port/labels_3d.py`` for the format/why). Response body: a
    little-endian header ``uint32 dz, dy, dx, num_labels`` followed by
    ``num_labels`` entries of ``int32 label_id`` + ``dz*dy*dx`` bytes
    (0/1 per voxel)."""

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        import struct

        task = get_object_or_404(AnnotationTask.objects.select_related("volume"), pk=pk)
        if not can_view_task(request.user, task):
            return Response(
                {"detail": "You do not have access to this task."}, status=403
            )
        raw = request.query_params.get("labels", "")
        try:
            label_ids = [int(v) for v in raw.split(",") if v.strip() != ""]
        except ValueError:
            return Response({"detail": "labels must be a comma-separated id list."}, status=400)

        preview = get_labels_3d_preview(task.volume, label_ids)
        dz, dy, dx = preview["shape"]
        grids = preview["grids"]
        body = bytearray(struct.pack("<IIII", dz, dy, dx, len(grids)))
        for lid, grid in grids.items():
            body += struct.pack("<i", lid)
            body += grid.tobytes()
        resp = HttpResponse(bytes(body), content_type="application/octet-stream")
        resp["Cache-Control"] = "private, max-age=10"
        return resp


class TaskLabelLifecycleView(APIView):
    """``POST /api/tasks/<id>/labels/<label_id>/lifecycle/`` — Cellable-parity
    label lifecycle actions (Filters Options' Verify/Revert/Reject), body
    ``{"action": "verify"|"unverify"|"revert"|"reject"}``. Editors only —
    these mutate the working copy (revert/reject) or its metadata sidecar
    (all four). Destructive actions (revert/reject) get their confirm()
    dialog in the frontend, per `04-incident-data-safety.md`."""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk, label_id):
        task = get_object_or_404(
            AnnotationTask.objects.select_related("volume", "project"), pk=pk
        )
        if not can_edit_task(request.user, task):
            return Response(
                {"detail": "You do not have edit access to this task."}, status=403
            )
        action = request.data.get("action")
        try:
            result = set_label_lifecycle_action(task.volume, label_id, action)
        except (ValueError, SliceIOError) as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(result)
