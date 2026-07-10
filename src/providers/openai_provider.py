"""Covers OpenAI, Azure OpenAI, and any OpenAI-compatible endpoint (Groq,
vLLM, local servers). Only base_url/api_version/api_key/model differ, and
those are driven entirely by .env -- setting OPENAI_API_VERSION routes
through AzureOpenAI, otherwise it's a plain (optionally custom base_url)
OpenAI client."""
import json

import openai

from src.providers.base import Provider


def _to_openai_tools(tools: list[dict]) -> list[dict]:
    return [
        {"type": "function", "function": {"name": t["name"], "description": t["description"], "parameters": t["parameters"]}}
        for t in tools
    ]


def _build_messages(system: str, history: list[dict]) -> list[dict]:
    messages = [{"role": "system", "content": system}]
    for turn in history:
        if turn["role"] == "user":
            messages.append({"role": "user", "content": turn["content"]})
        elif turn["role"] == "assistant":
            call = turn["tool_call"]
            messages.append({
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": call["id"],
                    "type": "function",
                    "function": {"name": call["name"], "arguments": json.dumps(call["args"])},
                }],
            })
        elif turn["role"] == "tool_result":
            content = turn["content"]
            if turn.get("error"):
                content = f"ERROR: {content}"
            messages.append({"role": "tool", "tool_call_id": turn["tool_call_id"], "content": str(content)})
    return messages


class OpenAIProvider(Provider):
    def __init__(self, api_key: str, model: str, base_url: str = "", api_version: str = ""):
        self._model = model
        if api_version:
            self._client = openai.AzureOpenAI(api_key=api_key, api_version=api_version, azure_endpoint=base_url)
        else:
            self._client = openai.OpenAI(api_key=api_key, base_url=base_url or None)

    def complete(self, system: str, user: str) -> str:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        )
        return response.choices[0].message.content or ""

    def next_action(self, system: str, history: list[dict], tools: list[dict]) -> dict:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=_build_messages(system, history),
            tools=_to_openai_tools(tools),
        )
        message = response.choices[0].message
        if message.tool_calls:
            call = message.tool_calls[0]
            return {
                "type": "tool_call",
                "id": call.id,
                "name": call.function.name,
                "args": json.loads(call.function.arguments or "{}"),
            }
        return {"type": "final", "text": message.content or ""}
