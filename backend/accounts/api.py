"""Authentication + current-user endpoints.

Token auth is used so the React SPA can store the token and avoid CSRF.
"""

from django.contrib.auth import authenticate
from rest_framework import generics, status
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.choices import UserRole
from core.permissions import IsManager

from .models import AnnotatorProfile
from .roles import get_role, is_annotator, is_requester
from .serializers import (
    CurrentUserSerializer,
    LoginSerializer,
    RegisterSerializer,
)


def _portal_allows(portal: str, user) -> bool:
    """Whether ``user`` may sign in through the given login tab.

    The requester tab is for requesters; the annotator tab is for annotators
    and managers (managers have no separate tab of their own).
    """
    if portal == "requester":
        return is_requester(user)
    if portal == "annotator":
        return is_annotator(user)  # annotators + managers
    return True


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(
            request,
            username=serializer.validated_data["username"],
            password=serializer.validated_data["password"],
        )
        if user is None:
            return Response(
                {"detail": "Invalid username or password."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        portal = serializer.validated_data.get("portal") or ""
        if portal and not _portal_allows(portal, user):
            label = "Requester" if portal == "requester" else "Annotator"
            return Response(
                {
                    "detail": (
                        f"This account cannot sign in through the {label} "
                        "login. Please use the correct login tab."
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        token, _ = Token.objects.get_or_create(user=user)
        return Response(
            {"token": token.key, "user": CurrentUserSerializer(user).data}
        )


class RegisterView(APIView):
    """Public account creation for annotators and requesters."""

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        token, _ = Token.objects.get_or_create(user=user)
        return Response(
            {"token": token.key, "user": CurrentUserSerializer(user).data},
            status=status.HTTP_201_CREATED,
        )


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        Token.objects.filter(user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(CurrentUserSerializer(request.user).data)


class AnnotatorListView(APIView):
    """List annotators for manager assignment dropdowns. Managers only."""

    permission_classes = [IsManager]

    def get(self, request):
        profiles = (
            AnnotatorProfile.objects.select_related("user")
            .filter(user__is_active=True)
            .order_by("user__username")
        )
        data = [
            {
                "id": p.user_id,
                "username": p.user.get_username(),
                "is_active_annotator": p.is_active_annotator,
                "max_active_tasks": p.max_active_tasks,
            }
            for p in profiles
            if get_role(p.user) in (UserRole.ANNOTATOR,)
        ]
        return Response(data)
