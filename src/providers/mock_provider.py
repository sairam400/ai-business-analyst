"""Scripted provider for tests and the eval harness -- no network calls."""
from src.providers.base import Provider


class MockProvider(Provider):
    def __init__(self, plan: list[dict] = None, completions: list[str] = None):
        self._plan = list(plan or [])
        self._completions = list(completions or [])

    def complete(self, system: str, user: str) -> str:
        if not self._completions:
            raise AssertionError("MockProvider.complete called with no scripted completions left")
        return self._completions.pop(0)

    def next_action(self, system: str, history: list[dict], tools: list[dict]) -> dict:
        if not self._plan:
            raise AssertionError("MockProvider.next_action called with no scripted actions left")
        return self._plan.pop(0)
