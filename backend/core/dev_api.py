"""Development-only endpoint backing the login page's "Reset dev data" button.

This is the HTTP equivalent of ``manage.py reset_dev --no-migrate``: it wipes
the development data and reseeds the standard accounts so the login page's dev
chips keep working afterwards.

It is deliberately unauthenticated — the button lives on the login page, before
anyone has signed in — so it is only routed when ``DEBUG`` is on (see
``config.urls``) and re-checks ``DEBUG`` here in case it is ever wired up
elsewhere.
"""

from django.conf import settings
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from core.dev_data import clear_dev_data, data_summary, seed_standard_data


class DevResetView(APIView):
    """POST /api/dev/reset/ — clear all dev data and reseed standard accounts."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        if not settings.DEBUG:
            return Response(
                {"detail": "Not available outside DEBUG."},
                status=status.HTTP_404_NOT_FOUND,
            )

        logs: list[str] = []
        deleted = clear_dev_data(keep_users=False, log=logs.append)
        seed_standard_data(log=logs.append)
        return Response({"deleted": deleted, "summary": data_summary()})
