"""URL configuration for the Mito Data Agent project.

The React SPA (under ``/api/``) serves annotators and requesters. Managers run
their full daily workflow through the Manager Admin at ``/admin/`` (see
``core.admin_site.ManagerAdminSite`` and ``docs/admin.md``).
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import index
from accounts.api import AnnotatorListView, LoginView, LogoutView, MeView, RegisterView
from annotation.api import (
    AssignTaskView,
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
from projects.api import ProjectViewSet
from volumes.api import (
    HpcScanView,
    ProjectVolumesView,
    RegisterDataView,
    VolumeDetailView,
    VolumeSplitView,
)

# ProjectViewSet handles /api/projects/ CRUD plus a progress summary action.
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
        "api/tasks/<int:pk>/assign/",
        AssignTaskView.as_view(),
        name="api-task-assign",
    ),
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
    # --- Project CRUD + summary (router) -----------------------------------
    path("api/", include(router.urls)),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
