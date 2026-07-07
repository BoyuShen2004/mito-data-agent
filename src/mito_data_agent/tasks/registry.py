"""Task registry — the intent taxonomy the LLM prompt parser classifies into.

Each registered :class:`TaskSpec` (see ``tasks/builtin.py``) contributes its
``intent``, ``description``, and ``examples`` to the parser's system prompt (via
``build_intent_prompt_section``). Routing itself is decided by the LLM supervisor
at run time — the registry only defines the vocabulary of intents.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Literal

PostValidationRoute = Literal[
    "readiness_report",
    "upload_valid",
    "metadata_valid",
    "missing_fields",
]

FormatResultFn = Callable[[dict], str | None]


@dataclass(frozen=True)
class TaskSpec:
    """One routable agent task."""

    intent: str
    description: str
    entry_node: str
    examples: tuple[str, ...] = ()
    # How to route after validate_required_columns (tasks that skip validation leave None).
    post_validation: PostValidationRoute | None = None
    # If True, post_validation is used even when validation fails (e.g. readiness check).
    post_validation_always: bool = False
    # Linear edges from entry_node → … → END (for simple tasks).
    terminal_edges: tuple[tuple[str, str], ...] = ()
    # Skip pseudo_upload_to_hf for metadata-only style tasks.
    skip_hf_upload: bool = False
    # Custom chat formatting; None uses default runner formatting.
    format_result: FormatResultFn | None = field(default=None, compare=False)


_REGISTRY: dict[str, TaskSpec] = {}


def register_task(spec: TaskSpec) -> TaskSpec:
    if spec.intent in _REGISTRY:
        raise ValueError(f"Task already registered: {spec.intent!r}")
    _REGISTRY[spec.intent] = spec
    return spec


def get_task(intent: str) -> TaskSpec | None:
    return _REGISTRY.get(intent)


def get_all_tasks() -> list[TaskSpec]:
    return list(_REGISTRY.values())


def get_registered_intents() -> list[str]:
    return sorted(_REGISTRY.keys())


def get_parse_routes() -> dict[str, str]:
    """Map intent → first node after parse_user_prompt."""
    return {spec.intent: spec.entry_node for spec in _REGISTRY.values()}


def resolve_post_validation(intent: str, validation_success: bool) -> str:
    """Return the route key after validate_required_columns."""
    spec = get_task(intent)
    if spec is None:
        return "missing_fields"
    if spec.post_validation is None:
        return "missing_fields"
    if spec.post_validation_always:
        return spec.post_validation
    if validation_success:
        return spec.post_validation
    return "missing_fields"


def should_skip_hf_upload(intent: str) -> bool:
    spec = get_task(intent)
    return bool(spec and spec.skip_hf_upload)


def build_intent_prompt_section() -> str:
    """Generate LLM intent documentation from registered tasks."""
    lines = ["Classify intent as one of:"]
    for spec in get_all_tasks():
        lines.append(f"- {spec.intent} — {spec.description}")
    lines.append("- unsupported_request — out-of-scope (online search, training, external download, …)")
    lines.append("")
    lines.append("Intent examples:")
    for spec in get_all_tasks():
        for example in spec.examples:
            lines.append(f'- "{example}" => {spec.intent}')
    lines.append('- "find datasets online", "train model" => unsupported_request')
    return "\n".join(lines)


def clear_registry() -> None:
    """Test helper."""
    _REGISTRY.clear()
