import anthropic

from src.providers.base import Provider


def _to_anthropic_tools(tools: list[dict]) -> list[dict]:
    return [
        {"name": t["name"], "description": t["description"], "input_schema": t["parameters"]}
        for t in tools
    ]


def _build_messages(history: list[dict]) -> list[dict]:
    messages = []
    for turn in history:
        if turn["role"] == "user":
            messages.append({"role": "user", "content": turn["content"]})
        elif turn["role"] == "assistant":
            call = turn["tool_call"]
            messages.append({
                "role": "assistant",
                "content": [{"type": "tool_use", "id": call["id"], "name": call["name"], "input": call["args"]}],
            })
        elif turn["role"] == "tool_result":
            messages.append({
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": turn["tool_call_id"],
                    "content": str(turn["content"]),
                    "is_error": turn.get("error", False),
                }],
            })
    return messages


class AnthropicProvider(Provider):
    def __init__(self, api_key: str, model: str):
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def complete(self, system: str, user: str) -> str:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=4096,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(block.text for block in response.content if block.type == "text")

    def next_action(self, system: str, history: list[dict], tools: list[dict]) -> dict:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=4096,
            system=system,
            messages=_build_messages(history),
            tools=_to_anthropic_tools(tools),
        )
        for block in response.content:
            if block.type == "tool_use":
                return {"type": "tool_call", "id": block.id, "name": block.name, "args": block.input}
        text = "".join(block.text for block in response.content if block.type == "text")
        return {"type": "final", "text": text}
