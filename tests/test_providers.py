import unittest

from src.providers import get_provider
from src.providers.anthropic_provider import _build_messages as anthropic_build_messages
from src.providers.anthropic_provider import _to_anthropic_tools
from src.providers.mock_provider import MockProvider
from src.providers.openai_provider import _build_messages as openai_build_messages
from src.providers.openai_provider import _to_openai_tools
from src.tools import TOOL_SPECS


class TestMockProvider(unittest.TestCase):
    def test_next_action_returns_scripted_steps_in_order(self):
        plan = [{"type": "tool_call", "id": "1", "name": "run_sql", "args": {"query": "SELECT 1"}}, {"type": "final", "text": "done"}]
        provider = MockProvider(plan=plan)
        self.assertEqual(provider.next_action("sys", [], TOOL_SPECS)["type"], "tool_call")
        self.assertEqual(provider.next_action("sys", [], TOOL_SPECS)["type"], "final")

    def test_next_action_raises_when_plan_exhausted(self):
        provider = MockProvider(plan=[{"type": "final", "text": "x"}])
        provider.next_action("sys", [], TOOL_SPECS)
        with self.assertRaises(AssertionError):
            provider.next_action("sys", [], TOOL_SPECS)

    def test_complete_returns_scripted_text(self):
        provider = MockProvider(completions=["hello"])
        self.assertEqual(provider.complete("sys", "hi"), "hello")

    def test_get_provider_mock(self):
        provider = get_provider("mock", mock_completions=["x"])
        self.assertIsInstance(provider, MockProvider)


class TestToolSpecAdapters(unittest.TestCase):
    def test_anthropic_tool_shape(self):
        tools = _to_anthropic_tools(TOOL_SPECS)
        names = {t["name"] for t in tools}
        self.assertEqual(names, {"run_sql", "run_python", "make_chart"})
        self.assertIn("input_schema", tools[0])

    def test_openai_tool_shape(self):
        tools = _to_openai_tools(TOOL_SPECS)
        self.assertEqual(tools[0]["type"], "function")
        self.assertIn("parameters", tools[0]["function"])

    def test_anthropic_message_replay_includes_tool_result(self):
        history = [
            {"role": "user", "content": "how many orders?"},
            {"role": "assistant", "tool_call": {"id": "abc", "name": "run_sql", "args": {"query": "SELECT COUNT(*) FROM orders"}}},
            {"role": "tool_result", "tool_call_id": "abc", "content": "[[5000]]", "error": False},
        ]
        messages = anthropic_build_messages(history)
        self.assertEqual(messages[1]["content"][0]["type"], "tool_use")
        self.assertEqual(messages[2]["content"][0]["type"], "tool_result")

    def test_openai_message_replay_marks_errors(self):
        history = [
            {"role": "assistant", "tool_call": {"id": "abc", "name": "run_sql", "args": {"query": "bad"}}},
            {"role": "tool_result", "tool_call_id": "abc", "content": "syntax error", "error": True},
        ]
        messages = openai_build_messages("sys", history)
        tool_message = [m for m in messages if m.get("role") == "tool"][0]
        self.assertIn("ERROR", tool_message["content"])


if __name__ == "__main__":
    unittest.main()
