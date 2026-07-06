"""Task registry package."""

from mito_data_agent.tasks.builtin import register_builtin_tasks
from mito_data_agent.tasks.registry import (
    TaskSpec,
    build_intent_prompt_section,
    get_all_tasks,
    get_parse_routes,
    get_registered_intents,
    get_task,
    register_task,
    resolve_post_validation,
    should_skip_hf_upload,
)

register_builtin_tasks()

__all__ = [
    "TaskSpec",
    "build_intent_prompt_section",
    "get_all_tasks",
    "get_parse_routes",
    "get_registered_intents",
    "get_task",
    "register_builtin_tasks",
    "register_task",
    "resolve_post_validation",
    "should_skip_hf_upload",
]
