"""Persistent chat history for the web UI — one JSON file per conversation.

Each conversation is stored under ``outputs/chats/<chat_id>.json`` as::

    {"id", "title", "created_at", "updated_at", "turns": [<turn>, ...]}

A ``turn`` is UI-shaped and opaque to the store: ``{"role": "user", "text": ...}``
or ``{"role": "assistant", "result": {...}}`` (the run's final payload). The
store only manages identity, titles, timestamps, and files — never runs anything.

This lives outside ``OUTPUT_SUBDIRS`` on purpose, so ``clear`` (which wipes run
artifacts + the ledger) does **not** delete a user's chat history.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from mito_data_agent.utils.paths import get_outputs_dir


def get_chats_dir() -> Path:
    d = get_outputs_dir() / "chats"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _new_id() -> str:
    return "chat_" + datetime.now().strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:4]


def _safe_id(chat_id: str) -> str:
    """Reject anything that could escape the chats directory."""
    if not chat_id or "/" in chat_id or "\\" in chat_id or ".." in chat_id:
        raise ValueError(f"invalid chat id: {chat_id!r}")
    return chat_id


def _path(chat_id: str) -> Path:
    return get_chats_dir() / f"{_safe_id(chat_id)}.json"


def _title_from_turns(turns: list[dict], fallback: str = "New chat") -> str:
    for turn in turns:
        if turn.get("role") == "user" and turn.get("text"):
            text = " ".join(str(turn["text"]).split())
            return text[:60] + ("…" if len(text) > 60 else "")
    return fallback


def list_chats() -> list[dict[str, Any]]:
    """Summaries (no turns) for the sidebar, newest first."""
    out: list[dict[str, Any]] = []
    for path in get_chats_dir().glob("chat_*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        out.append(
            {
                "id": data.get("id", path.stem),
                "title": data.get("title") or "Untitled",
                "created_at": data.get("created_at"),
                "updated_at": data.get("updated_at"),
                "turn_count": len(data.get("turns", []) or []),
            }
        )
    out.sort(key=lambda c: c.get("updated_at") or "", reverse=True)
    return out


def get_chat(chat_id: str) -> Optional[dict[str, Any]]:
    path = _path(chat_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def save_chat(
    turns: list[dict],
    *,
    chat_id: Optional[str] = None,
    title: Optional[str] = None,
) -> dict[str, Any]:
    """Create (``chat_id=None``) or overwrite a conversation. Title defaults to the
    first user message; ``created_at`` is preserved across updates."""
    now = _now()
    if chat_id:
        created = (get_chat(chat_id) or {}).get("created_at", now)
        cid = _safe_id(chat_id)
    else:
        cid = _new_id()
        created = now

    doc = {
        "id": cid,
        "title": title or _title_from_turns(turns),
        "created_at": created,
        "updated_at": now,
        "turns": turns,
    }
    _path(cid).write_text(json.dumps(doc, indent=2, default=str), encoding="utf-8")
    return doc


def delete_chat(chat_id: str) -> bool:
    path = _path(chat_id)
    if path.exists():
        path.unlink()
        return True
    return False
