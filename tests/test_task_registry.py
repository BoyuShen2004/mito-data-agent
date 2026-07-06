"""Tests for the extensible task registry (legacy pipeline)."""

from mito_data_agent.legacy_pipeline_graph import build_legacy_graph
from mito_data_agent.tasks import (
    get_parse_routes,
    get_registered_intents,
    get_task,
    register_builtin_tasks,
)
from mito_data_agent.tasks.registry import TaskSpec, clear_registry, register_task


def test_builtin_tasks_registered():
    register_builtin_tasks()
    intents = get_registered_intents()
    assert "upload_annotation" in intents
    assert get_task("check_upload_readiness").post_validation_always is True


def test_custom_task_registration():
    clear_registry()
    register_task(
        TaskSpec(
            intent="demo_task",
            description="example task for tests",
            entry_node="validate_input",
        )
    )
    assert "demo_task" in get_parse_routes()
    clear_registry()
    register_builtin_tasks()


def test_legacy_graph_still_builds():
    graph = build_legacy_graph()
    assert graph is not None
