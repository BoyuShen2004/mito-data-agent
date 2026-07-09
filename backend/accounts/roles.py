"""Role helpers and view decorators.

Role is read from the user's :class:`UserProfile`. Superusers are always
treated as managers so the admin-created superuser can drive the workflow.
"""

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

from core.choices import UserRole


def get_role(user) -> str | None:
    if not user.is_authenticated:
        return None
    if user.is_superuser:
        return UserRole.MANAGER
    profile = getattr(user, "profile", None)
    return profile.role if profile else None


def is_manager(user) -> bool:
    return get_role(user) == UserRole.MANAGER


def is_annotator(user) -> bool:
    role = get_role(user)
    # Managers can also view annotator pages; annotators cannot view manager pages.
    return role in (UserRole.ANNOTATOR, UserRole.MANAGER)


def manager_required(view_func):
    @wraps(view_func)
    @login_required
    def _wrapped(request, *args, **kwargs):
        if not is_manager(request.user):
            raise PermissionDenied("Manager access required.")
        return view_func(request, *args, **kwargs)

    return _wrapped


def annotator_required(view_func):
    @wraps(view_func)
    @login_required
    def _wrapped(request, *args, **kwargs):
        if not is_annotator(request.user):
            raise PermissionDenied("Annotator access required.")
        return view_func(request, *args, **kwargs)

    return _wrapped
