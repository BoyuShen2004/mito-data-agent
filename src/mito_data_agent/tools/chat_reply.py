"""Conversational reply tool — lets the agent chat (ChatGPT-style) via the LLM.

Used by ``chat_agent`` when the user's message is casual / general rather than a
data task. The agent stays pure flow; the actual LLM call lives here.
"""

from __future__ import annotations

from mito_data_agent.llm.llm_client import get_llm_client

_SYSTEM_PROMPT = """\
You are the Mito Data Agent — a friendly, helpful assistant. You can chat about \
anything the user brings up, like a general-purpose assistant.

You also have a specialty: preparing annotated mitochondria (electron-microscopy) \
volumes for MitoVerse — parsing free-form metadata, inspecting raw/label TIFFs, \
validating and recording metadata to a local store, and preparing dry-run Hugging \
Face / MitoVerse uploads (all writes are dry-run).

Reply naturally and concisely to the user's message. If they ask what you can do, \
briefly mention both that you can chat generally and your MitoVerse metadata \
skills. For greetings, small talk, or general/unrelated questions, just answer \
conversationally — do not force the conversation toward MitoVerse.
"""


def generate_chat_reply(
    user_prompt: str, history: list[dict[str, str]] | None = None
) -> str:
    """Return a natural-language reply to a casual/general user message.

    ``history`` is the prior turns of the conversation (oldest-first), so the
    reply follows the thread instead of answering each message in isolation.
    """
    return get_llm_client().complete_text(_SYSTEM_PROMPT, user_prompt, history).strip()
