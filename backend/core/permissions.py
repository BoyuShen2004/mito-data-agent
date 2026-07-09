"""DRF permission classes keyed off the user's role.

Role is resolved via :mod:`accounts.roles`, which treats superusers as
managers so an admin-created superuser can drive the full workflow.
"""

from rest_framework.permissions import BasePermission

from accounts.roles import is_annotator, is_manager


class IsManager(BasePermission):
    message = "Manager access required."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated) and is_manager(
            request.user
        )


class IsAnnotator(BasePermission):
    message = "Annotator access required."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated) and is_annotator(
            request.user
        )
