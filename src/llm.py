"""Groq chat-completion wrapper (OpenAI-compatible) with safe JSON helpers.

The client is created lazily so the rest of the app imports cleanly even when no
API key is present (in which case callers should branch to rule-based fallbacks
via :func:`config.llm_available`).
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any

import config


class LLMError(RuntimeError):
    """Raised when the LLM backend is unavailable or returns an unusable reply."""


@lru_cache(maxsize=4)
def _client_for(key: str):
    """Cache one Groq client per API key (so UI key changes take effect)."""
    try:
        from groq import Groq
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise LLMError("The 'groq' package is not installed.") from exc
    return Groq(api_key=key)


def _client():
    key = config.groq_key()
    if not key:
        raise LLMError("Groq API key is not configured.")
    return _client_for(key)


def chat(
    system: str,
    user: str,
    *,
    temperature: float | None = None,
    max_tokens: int | None = None,
    json_mode: bool = False,
) -> str:
    """Send a single-turn chat request and return the assistant text."""
    kwargs: dict[str, Any] = dict(
        model=config.GROQ_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=config.LLM_TEMPERATURE if temperature is None else temperature,
        max_tokens=max_tokens or config.LLM_MAX_TOKENS,
    )
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    try:
        response = _client().chat.completions.create(**kwargs)
    except Exception as exc:  # network/model errors surface as LLMError
        raise LLMError(str(exc)) from exc
    return (response.choices[0].message.content or "").strip()


def chat_json(system: str, user: str, **kwargs) -> dict[str, Any]:
    """Chat and parse the reply as JSON, tolerating code fences / stray prose."""
    raw = chat(system, user, json_mode=True, **kwargs)
    return _parse_json(raw)


def _parse_json(raw: str) -> dict[str, Any]:
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # Strip markdown fences, then grab the outermost JSON object.
    fenced = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
    match = re.search(r"\{.*\}", fenced, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise LLMError(f"Could not parse JSON from LLM reply: {exc}") from exc
    raise LLMError("LLM reply contained no JSON object.")
