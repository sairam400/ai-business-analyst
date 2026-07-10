"""Neutral provider interface. Tool specs and conversation history are
vendor-agnostic dicts; each provider adapts them to its own wire format.

Two entry points because the pipeline has two shapes of LLM call: agents
that use tools in a loop (Analyst) call next_action() turn by turn, agents
that just transform text (Writer, Verifier's semantic check) call complete().

History entries (neutral format):
  {"role": "user", "content": str}
  {"role": "assistant", "tool_call": {"id": str, "name": str, "args": dict}}
  {"role": "tool_result", "tool_call_id": str, "content": Any, "error": bool}

next_action() returns one of:
  {"type": "tool_call", "id": str, "name": str, "args": dict}
  {"type": "final", "text": str}
"""
from abc import ABC, abstractmethod


class Provider(ABC):
    @abstractmethod
    def complete(self, system: str, user: str) -> str:
        ...

    @abstractmethod
    def next_action(self, system: str, history: list[dict], tools: list[dict]) -> dict:
        ...
