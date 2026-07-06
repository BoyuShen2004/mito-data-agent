"""Message-based agent state (Andrew Ng / LangGraph ReAct pattern)."""

from __future__ import annotations

import operator
from typing import Annotated, Optional, TypedDict

from langchain_core.messages import AnyMessage


class AgentState(TypedDict):
    """LangGraph state for the tool-calling agent loop."""

    messages: Annotated[list[AnyMessage], operator.add]
    run_id: str
    user_prompt: str
    artifacts: dict
    step_count: int
    execution_report_path: Optional[str]
    errors: list[str]
