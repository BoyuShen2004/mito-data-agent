"""URL configuration for the Mito Data Agent project.

The React SPA (under ``/api/``) serves annotators and requesters. Managers run
their full daily workflow through the Manager Admin at ``/admin/`` (see
``core.admin_site.ManagerAdminSite`` and ``progress/admin.md``).
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import index
from accounts.api import AnnotatorListView, LoginView, LogoutView, MeView, RegisterView
from annotation.api import (
    AssignmentPlanApplyView,
    AssignmentPlanPreviewView,
    AssignmentPlanRowsView,
    AssignTaskView,
    AssignTasksView,
    MyCompletedTasksView,
    MyTasksView,
    ProjectTasksView,
    ReviewSubmissionView,
    SubmissionDetailView,
    SubmissionListView,
    SubmitInappTaskView,
    SubmitTaskView,
    TaskDetailView,
    TaskLabelIdsView,
    TaskLabelLifecycleView,
    TaskLabelStateView,
    TaskLabels3DView,
    TaskLabelsSummaryView,
    TaskPredictMaskView,
    TaskProofreadingView,
    TaskTrackView,
    TaskVisualizationView,
    TaskWarmEmbeddingView,
    TaskWatershedView,
    VolumeLabelSliceView,
    VolumeMetaView,
    VolumeSliceView,
)
from processing.api import ProcessingJobViewSet
from projects.api import DatasetViewSet, ProjectViewSet
from volumes.api import (
    HpcScanView,
    ProjectVolumesView,
    RegisterDataView,
    VolumeDependentsView,
    VolumeDetailView,
    VolumeSplitView,
)

# ProjectViewSet handles /api/projects/ CRUD plus a progress summary action.
router = DefaultRouter()
router.register("projects", ProjectViewSet, basename="project")
# A project holds many datasets; a dataset holds many volume pairs.
router.register("datasets", DatasetViewSet, basename="dataset")
router.register("processing-jobs", ProcessingJobViewSet, basename="processing-job")

urlpatterns = [
    # Friendly landing page (the real UI is the React app on :5173).
    path("", index, name="index"),
    path("admin/", admin.site.urls),
    # --- Auth --------------------------------------------------------------
    path("api/auth/login/", LoginView.as_view(), name="api-login"),
    path("api/auth/logout/", LogoutView.as_view(), name="api-logout"),
    path("api/auth/me/", MeView.as_view(), name="api-me"),
    path("api/auth/register/", RegisterView.as_view(), name="api-register"),
    path("api/annotators/", AnnotatorListView.as_view(), name="api-annotators"),
    # --- Data registration (requesters + managers, shared endpoint) --------
    path("api/register-data/", RegisterDataView.as_view(), name="api-register-data"),
    path("api/hpc/scan/", HpcScanView.as_view(), name="api-hpc-scan"),
    # --- Volumes (project-nested + detail) ---------------------------------
    path(
        "api/projects/<int:project_id>/volumes/",
        ProjectVolumesView.as_view(),
        name="api-project-volumes",
    ),
    path("api/volumes/<int:pk>/", VolumeDetailView.as_view(), name="api-volume-detail"),
    path(
        "api/volumes/<int:pk>/dependents/",
        VolumeDependentsView.as_view(),
        name="api-volume-dependents",
    ),
    path(
        "api/volumes/<int:pk>/split/",
        VolumeSplitView.as_view(),
        name="api-volume-split",
    ),
    # --- Tasks -------------------------------------------------------------
    path(
        "api/projects/<int:project_id>/tasks/",
        ProjectTasksView.as_view(),
        name="api-project-tasks",
    ),
    path(
        "api/projects/<int:project_id>/assign-tasks/",
        AssignTasksView.as_view(),
        name="api-assign-tasks",
    ),
    path(
        "api/projects/<int:project_id>/assign-plan/rows/",
        AssignmentPlanRowsView.as_view(),
        name="api-assign-plan-rows",
    ),
    path(
        "api/projects/<int:project_id>/assign-plan/preview/",
        AssignmentPlanPreviewView.as_view(),
        name="api-assign-plan-preview",
    ),
    path(
        "api/projects/<int:project_id>/assign-plan/apply/",
        AssignmentPlanApplyView.as_view(),
        name="api-assign-plan-apply",
    ),
    path("api/tasks/<int:pk>/", TaskDetailView.as_view(), name="api-task-detail"),
    path(
        "api/tasks/<int:pk>/proofreading/",
        TaskProofreadingView.as_view(),
        name="api-task-proofreading",
    ),
    path(
        "api/tasks/<int:pk>/visualization/",
        TaskVisualizationView.as_view(),
        name="api-task-visualization",
    ),
    # --- Slice streaming + in-app annotation -------------------------------
    path(
        "api/volumes/<int:pk>/meta/",
        VolumeMetaView.as_view(),
        name="api-volume-meta",
    ),
    path(
        "api/volumes/<int:pk>/slice/",
        VolumeSliceView.as_view(),
        name="api-volume-slice",
    ),
    path(
        "api/volumes/<int:pk>/label-slice/",
        VolumeLabelSliceView.as_view(),
        name="api-volume-label-slice",
    ),
    path(
        "api/tasks/<int:pk>/track/",
        TaskTrackView.as_view(),
        name="api-task-track",
    ),
    path(
        "api/tasks/<int:pk>/label-state/",
        TaskLabelStateView.as_view(),
        name="api-task-label-state",
    ),
    path(
        "api/tasks/<int:pk>/label-ids/",
        TaskLabelIdsView.as_view(),
        name="api-task-label-ids",
    ),
    path(
        "api/tasks/<int:pk>/predict-mask/",
        TaskPredictMaskView.as_view(),
        name="api-task-predict-mask",
    ),
    path(
        "api/tasks/<int:pk>/warm-embedding/",
        TaskWarmEmbeddingView.as_view(),
        name="api-task-warm-embedding",
    ),
    path(
        "api/tasks/<int:pk>/watershed/",
        TaskWatershedView.as_view(),
        name="api-task-watershed",
    ),
    path(
        "api/tasks/<int:pk>/labels-summary/",
        TaskLabelsSummaryView.as_view(),
        name="api-task-labels-summary",
    ),
    path(
        "api/tasks/<int:pk>/labels-3d/",
        TaskLabels3DView.as_view(),
        name="api-task-labels-3d",
    ),
    path(
        "api/tasks/<int:pk>/labels/<int:label_id>/lifecycle/",
        TaskLabelLifecycleView.as_view(),
        name="api-task-label-lifecycle",
    ),
    path(
        "api/tasks/<int:pk>/assign/",
        AssignTaskView.as_view(),
        name="api-task-assign",
    ),
    path(
        "api/tasks/<int:pk>/submit/",
        SubmitTaskView.as_view(),
        name="api-task-submit",
    ),
    path(
        "api/tasks/<int:pk>/submit-inapp/",
        SubmitInappTaskView.as_view(),
        name="api-task-submit-inapp",
    ),
    path("api/my-tasks/", MyTasksView.as_view(), name="api-my-tasks"),
    path(
        "api/my-completed-tasks/",
        MyCompletedTasksView.as_view(),
        name="api-my-completed-tasks",
    ),
    # --- Submissions -------------------------------------------------------
    path("api/submissions/", SubmissionListView.as_view(), name="api-submissions"),
    path(
        "api/submissions/<int:pk>/",
        SubmissionDetailView.as_view(),
        name="api-submission-detail",
    ),
    path(
        "api/submissions/<int:pk>/review/",
        ReviewSubmissionView.as_view(),
        name="api-submission-review",
    ),
    # --- Project CRUD + summary (router) -----------------------------------
    path("api/", include(router.urls)),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    # Dev-only data reset, driven by the button on the login page. Not routed
    # at all in production.
    from core.dev_api import DevResetView

    urlpatterns += [
        path("api/dev/reset/", DevResetView.as_view(), name="api-dev-reset"),
    ]
