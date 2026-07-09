"""URL configuration for the Mito Data Agent project.

The user-facing app is a React SPA that talks to the REST API under ``/api/``.
Django admin remains available at ``/admin/`` for internal debugging.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import index
from accounts.api import LoginView, LogoutView, MeView
from agents.api import (
    AgentPlanApproveView,
    AgentPlanDetailView,
    AgentPlanRejectView,
    ProjectAgentPlansView,
)
from annotation.api import (
    AssignTasksView,
    MyCompletedTasksView,
    MyTasksView,
    ProjectTasksView,
    ReviewSubmissionView,
    SubmissionDetailView,
    SubmissionListView,
    SubmitTaskView,
    TaskDetailView,
)
from payments.api import MyPaymentsView, PaymentListView
from projects.api import ProjectViewSet
from volumes.api import ProjectVolumesView, VolumeDetailView, VolumeSplitView

# ProjectViewSet handles /api/projects/ CRUD plus summary & payment-summary.
router = DefaultRouter()
router.register("projects", ProjectViewSet, basename="project")

urlpatterns = [
    # Friendly landing page (the real UI is the React app on :5173).
    path("", index, name="index"),
    path("admin/", admin.site.urls),
    # --- Auth --------------------------------------------------------------
    path("api/auth/login/", LoginView.as_view(), name="api-login"),
    path("api/auth/logout/", LogoutView.as_view(), name="api-logout"),
    path("api/auth/me/", MeView.as_view(), name="api-me"),
    # --- Volumes (project-nested + detail) ---------------------------------
    path(
        "api/projects/<int:project_id>/volumes/",
        ProjectVolumesView.as_view(),
        name="api-project-volumes",
    ),
    path("api/volumes/<int:pk>/", VolumeDetailView.as_view(), name="api-volume-detail"),
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
    path("api/tasks/<int:pk>/", TaskDetailView.as_view(), name="api-task-detail"),
    path(
        "api/tasks/<int:pk>/submit/",
        SubmitTaskView.as_view(),
        name="api-task-submit",
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
    # --- Payments ----------------------------------------------------------
    path("api/payments/", PaymentListView.as_view(), name="api-payments"),
    path("api/my-payments/", MyPaymentsView.as_view(), name="api-my-payments"),
    # --- Agent plans (placeholder) -----------------------------------------
    path(
        "api/projects/<int:project_id>/agent-plans/",
        ProjectAgentPlansView.as_view(),
        name="api-project-agent-plans",
    ),
    path(
        "api/agent-plans/<int:pk>/",
        AgentPlanDetailView.as_view(),
        name="api-agent-plan-detail",
    ),
    path(
        "api/agent-plans/<int:pk>/approve/",
        AgentPlanApproveView.as_view(),
        name="api-agent-plan-approve",
    ),
    path(
        "api/agent-plans/<int:pk>/reject/",
        AgentPlanRejectView.as_view(),
        name="api-agent-plan-reject",
    ),
    # --- Project CRUD + summary (router) -----------------------------------
    path("api/", include(router.urls)),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
