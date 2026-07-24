"""Provider selection for SAM2 tracking (``settings.MITO_TRACKING_PROVIDER``)."""

from __future__ import annotations

from django.conf import settings
from django.utils.module_loading import import_string

from .interfaces import TrackingProvider

TRACKING_PROVIDERS: dict[str, str] = {
    "local": "annotation.tracking.adapters.local.LocalTrackingProvider",
    "sam2": "annotation.tracking.adapters.sam2.Sam2TrackingProvider",
}

DEFAULT_TRACKING_PROVIDER = "local"


def get_tracking_provider(name: str | None = None) -> TrackingProvider:
    name = name or getattr(
        settings, "MITO_TRACKING_PROVIDER", DEFAULT_TRACKING_PROVIDER
    )
    try:
        dotted = TRACKING_PROVIDERS[name]
    except KeyError as exc:
        raise ValueError(
            f"Unknown tracking provider '{name}'. Known: {sorted(TRACKING_PROVIDERS)}"
        ) from exc
    return import_string(dotted)()
