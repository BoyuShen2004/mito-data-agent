"""Provider selection for proofreading (``settings.MITO_PROOFREADING_PROVIDER``)."""

from __future__ import annotations

from django.conf import settings
from django.utils.module_loading import import_string

from .interfaces import ProofreadingProvider

PROOFREADING_PROVIDERS: dict[str, str] = {
    "placeholder": "annotation.proofreading.adapters.placeholder.PlaceholderProofreadingProvider",
    "inapp": "annotation.proofreading.adapters.inapp.InAppProofreadingProvider",
    "external_tool": "annotation.proofreading.adapters.external_tool.ExternalToolProofreadingProvider",
    "neuroglancer": "annotation.proofreading.adapters.neuroglancer.NeuroglancerProofreadingProvider",
}

DEFAULT_PROOFREADING_PROVIDER = "inapp"


def get_proofreading_provider(name: str | None = None) -> ProofreadingProvider:
    name = name or getattr(
        settings, "MITO_PROOFREADING_PROVIDER", DEFAULT_PROOFREADING_PROVIDER
    )
    try:
        dotted = PROOFREADING_PROVIDERS[name]
    except KeyError as exc:
        raise ValueError(
            f"Unknown proofreading provider '{name}'. "
            f"Known: {sorted(PROOFREADING_PROVIDERS)}"
        ) from exc
    return import_string(dotted)()
