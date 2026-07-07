"""LLM adapter for structured prompt parsing."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from typing import Any

from pydantic import ValidationError

from mito_data_agent import config
from mito_data_agent.llm.prompt_templates import build_user_message, get_system_prompt
from mito_data_agent.llm.settings_store import apply_settings_to_config, load_settings
from mito_data_agent.schemas import ParsedUserRequest
from mito_data_agent.utils.paths import normalize_stored_path
from mito_data_agent.utils.text import parse_resolution_string, parse_shape_string


class LLMClient:
    """Parse free-form user prompts into ParsedUserRequest via LLM."""

    def structured_parse_user_request(self, user_prompt: str) -> ParsedUserRequest:
        apply_settings_to_config(load_settings())
        backend = self._resolve_backend()
        if backend == "openai":
            parsed = self._parse_openai(user_prompt)
        elif backend == "codex_cli":
            parsed = self._parse_codex_cli(user_prompt)
        else:
            raise RuntimeError(f"Unsupported LLM backend: {backend}")
        return self._postprocess(parsed)

    def complete_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        """Return a JSON object from the LLM given system + user prompts.

        Used by the LLM supervisor for routing decisions. Reuses the same backend
        resolution (OpenAI / Codex CLI), API key, and model as prompt parsing.
        """
        apply_settings_to_config(load_settings())
        backend = self._resolve_backend()
        if backend == "openai":
            return self._complete_openai_json(system_prompt, user_prompt)
        if backend == "codex_cli":
            return self._complete_codex_json(system_prompt, user_prompt)
        raise RuntimeError(f"Unsupported LLM backend: {backend}")

    def _complete_openai_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError(
                "openai package is required for OpenAI LLM backend. pip install openai"
            ) from exc

        settings = load_settings()
        client = OpenAI(api_key=self._get_openai_api_key())
        completion = client.chat.completions.create(
            model=settings.llm_model or config.LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
        )
        return self._extract_json(completion.choices[0].message.content or "")

    def supports_tool_calling(self) -> bool:
        """True when the active backend can do native function/tool calling (OpenAI)."""
        apply_settings_to_config(load_settings())
        try:
            return self._resolve_backend() == "openai"
        except Exception:  # noqa: BLE001 — treat "can't resolve" as no tool-calling
            return False

    def route_via_tools(
        self, system_prompt: str, user_prompt: str, tools: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Let the LLM pick the next step via native OpenAI tool calling.

        Each entry in ``tools`` is one callable option (an agent, or ``finish``).
        With ``tool_choice="required"`` the model *must* call exactly one — that
        function's name is the chosen next agent. Returns
        ``{"name": <tool>, "arguments": {...}}``.
        """
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("openai package required for tool calling. pip install openai") from exc

        settings = load_settings()
        client = OpenAI(api_key=self._get_openai_api_key())
        completion = client.chat.completions.create(
            model=settings.llm_model or config.LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            tools=tools,
            tool_choice="required",
        )
        message = completion.choices[0].message
        tool_calls = getattr(message, "tool_calls", None)
        if not tool_calls:
            raise RuntimeError("supervisor: model returned no tool call")
        call = tool_calls[0]
        raw_args = call.function.arguments or "{}"
        try:
            arguments = json.loads(raw_args)
        except json.JSONDecodeError:
            arguments = {}
        return {"name": call.function.name, "arguments": arguments}

    def _complete_codex_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        codex = self._get_codex_path()
        if codex is None:
            raise RuntimeError(
                "Codex CLI not found. Install Codex, click Connect in the Web UI, "
                "or run `codex login` once in your terminal."
            )
        prompt = (
            f"{system_prompt}\n\n{user_prompt}\n\n"
            "Respond with ONLY valid JSON matching the requested keys. No markdown."
        )
        result = subprocess.run(
            [codex, "exec", "--full-auto", prompt],
            capture_output=True,
            text=True,
            timeout=240,
        )
        if result.returncode != 0:
            raise RuntimeError(
                "Codex CLI call failed. Open Web UI → Connection → Test & Connect, "
                "or run `codex login` in your terminal.\n"
                f"stderr: {result.stderr.strip()}"
            )
        return self._extract_json(result.stdout.strip())

    def _resolve_backend(self) -> str:
        settings = load_settings()
        if settings.llm_backend == "codex_cli" or config.USE_CODEX_CLI:
            return "codex_cli"
        if settings.llm_backend == "openai":
            api_key = self._get_openai_api_key()
            if not api_key:
                raise RuntimeError(
                    "OpenAI API key not configured. Set it in the Web UI Connection panel."
                )
            return "openai"
        raise RuntimeError(
            f"Unknown LLM backend {settings.llm_backend!r}. Use Web UI to select openai or codex_cli."
        )

    @staticmethod
    def _get_openai_api_key() -> str | None:
        settings = load_settings()
        return (
            settings.openai_api_key
            or getattr(config, "_RUNTIME_OPENAI_API_KEY", None)
            or os.getenv("OPENAI_API_KEY")
        )

    @staticmethod
    def _get_codex_path() -> str | None:
        settings = load_settings()
        return (
            settings.codex_path
            or getattr(config, "_RUNTIME_CODEX_PATH", None)
            or shutil.which("codex")
        )

    def _parse_openai(self, user_prompt: str) -> ParsedUserRequest:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError(
                "openai package is required for OpenAI LLM backend. pip install openai"
            ) from exc

        settings = load_settings()
        client = OpenAI(api_key=self._get_openai_api_key())
        system_prompt = get_system_prompt()
        user_message = build_user_message(user_prompt)

        completion = client.beta.chat.completions.parse(
            model=settings.llm_model or config.LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            response_format=ParsedUserRequest,
        )
        parsed = completion.choices[0].message.parsed
        if parsed is None:
            raise RuntimeError("OpenAI returned empty structured parse result.")
        notes = list(parsed.notes)
        notes.append(f"Parsed via OpenAI model: {settings.llm_model}")
        return parsed.model_copy(update={"notes": notes})

    def _parse_codex_cli(self, user_prompt: str) -> ParsedUserRequest:
        codex = self._get_codex_path()
        if codex is None:
            raise RuntimeError(
                "Codex CLI not found. Install Codex, click Connect in the Web UI, "
                "or run `codex login` once in your terminal."
            )

        schema_json = json.dumps(ParsedUserRequest.model_json_schema(), indent=2)
        prompt = (
            f"{get_system_prompt()}\n\n"
            f"JSON schema:\n{schema_json}\n\n"
            f"{build_user_message(user_prompt)}\n\n"
            "Respond with ONLY valid JSON matching the schema. No markdown."
        )

        result = subprocess.run(
            [codex, "exec", "--full-auto", prompt],
            capture_output=True,
            text=True,
            timeout=240,
        )
        if result.returncode != 0:
            raise RuntimeError(
                "Codex CLI call failed. Open Web UI → Connection → Test & Connect, "
                "or run `codex login` in your terminal.\n"
                f"stderr: {result.stderr.strip()}\nstdout: {result.stdout.strip()}"
            )

        raw = result.stdout.strip()
        data = self._extract_json(raw)
        notes = list(data.get("notes") or [])
        notes.append(f"Parsed via Codex CLI ({codex})")
        data["notes"] = notes
        return ParsedUserRequest.model_validate(data)

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any]:
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if not match:
                raise RuntimeError(f"Codex CLI did not return JSON. Output:\n{text[:500]}")
            return json.loads(match.group())

    @staticmethod
    def _postprocess(parsed: ParsedUserRequest) -> ParsedUserRequest:
        """Normalize LLM output; strip file-derived fields LLM must not fabricate."""
        data = parsed.model_dump()

        if isinstance(data.get("resolution_nm"), str):
            data["resolution_nm"] = parse_resolution_string(data["resolution_nm"])
        if isinstance(data.get("shape_xyz"), str):
            data["shape_xyz"] = parse_shape_string(data["shape_xyz"])

        for key in ("resolution_nm", "shape_xyz"):
            if isinstance(data.get(key), list):
                data[key] = tuple(data[key])

        if data.get("raw_file_path") or data.get("label_file_path"):
            if data.get("shape_xyz") is not None or data.get("num_mito") is not None:
                notes = list(data.get("notes") or [])
                notes.append(
                    "Cleared shape_xyz/num_mito from LLM output; file observation tools will set these."
                )
                data["notes"] = notes
            data["shape_xyz"] = None
            data["num_mito"] = None

        for path_key in ("raw_file_path", "label_file_path", "metadata_file_path"):
            if data.get(path_key):
                data[path_key] = normalize_stored_path(data[path_key])

        try:
            return ParsedUserRequest.model_validate(data)
        except ValidationError as exc:
            raise RuntimeError(f"LLM output failed schema validation: {exc}") from exc


_default_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    global _default_client
    if _default_client is None:
        _default_client = LLMClient()
    return _default_client
