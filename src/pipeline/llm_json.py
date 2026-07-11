"""Shared helper for pipeline stages that need a structured JSON response
from a plain completion call (profiler's analysis suggestions, writer's
draft). Retries once with the parse error fed back before giving up --
mirrors the tool-layer's error-feedback pattern, just for text calls."""
import json
import re

from src.providers.base import Provider

_JSON_BLOCK = re.compile(r"\{.*\}|\[.*\]", re.DOTALL)


class JSONCompletionError(Exception):
    pass


def _extract_json(text: str):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = _JSON_BLOCK.search(text)
    if match:
        return json.loads(match.group(0))
    raise json.JSONDecodeError("no JSON object found", text, 0)


def complete_json(provider: Provider, system: str, user: str, retries: int = 1):
    last_error = None
    prompt = user
    for _ in range(retries + 1):
        text = provider.complete(system, prompt)
        try:
            return _extract_json(text)
        except json.JSONDecodeError as exc:
            last_error = exc
            prompt = f"{user}\n\nYour previous response was not valid JSON ({exc}). Respond with valid JSON only, no prose."
    raise JSONCompletionError(f"model did not return valid JSON after {retries + 1} attempts: {last_error}")
