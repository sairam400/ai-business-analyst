"""Runs each suggested analysis through a tool-use loop and finalizes it as
a typed Finding. Same retry shape as the tool layer's own guarantees:
a hard cap on steps, a hard stop after consecutive tool errors (the error
gets fed back to the model first, so most failures self-correct before
that), and a task that can't finish is skipped rather than allowed to
crash the whole report.
"""
import json

from src.artifacts import AnalystArtifact, DatasetProfile, Finding
from src.config import SETTINGS
from src.providers.base import Provider
from src.tools import TOOL_SPECS, ToolError

SYSTEM_PROMPT = (
    "You are the analyst stage of a business analytics pipeline. You'll be given "
    "one specific analysis task and tools to compute it against the loaded dataset: "
    "run_sql (read-only), run_python (for computation SQL can't express), and "
    "make_chart (to visualize a trend or comparison, in the report's house style).\n\n"
    "Work the task with tools, then finish with a final message that is JSON only "
    "(no prose, no markdown fences):\n"
    '{"question": "<what this answers, restated>", "method": "sql" or "python", '
    '"query": "<the exact SQL or python code that produced value>", '
    '"value": <the number or short string answer>, "unit": "<e.g. USD, %, orders, or empty>", '
    '"chart_id": "<chart_id if you made one relevant to this finding, else null>"}\n\n'
    "The query field must be the literal, re-runnable query or code that produces "
    "value -- it gets independently re-executed to verify your claim, so it must "
    "actually be the source of the number, not a paraphrase."
)


class AnalystError(Exception):
    pass


def _parse_final(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.split("\n", 1)[1] if "\n" in text else text
    return json.loads(text)


def run_analysis_task(task: str, provider: Provider, tools: dict) -> dict:
    history = [{"role": "user", "content": f"Analysis task: {task}"}]
    consecutive_errors = 0

    for _ in range(SETTINGS.max_steps):
        action = provider.next_action(SYSTEM_PROMPT, history, TOOL_SPECS)

        if action["type"] == "final":
            try:
                return _parse_final(action["text"])
            except (json.JSONDecodeError, KeyError) as exc:
                raise AnalystError(f"task '{task}': final answer was not valid finding JSON: {exc}") from exc

        tool_name = action["name"]
        if tool_name not in tools:
            raise AnalystError(f"task '{task}': model called unknown tool '{tool_name}'")

        history.append({"role": "assistant", "tool_call": {"id": action["id"], "name": tool_name, "args": action["args"]}})
        try:
            result = tools[tool_name](**action["args"])
            consecutive_errors = 0
            history.append({"role": "tool_result", "tool_call_id": action["id"], "content": result, "error": False})
        except (ToolError, TypeError) as exc:
            consecutive_errors += 1
            history.append({"role": "tool_result", "tool_call_id": action["id"], "content": str(exc), "error": True})
            if consecutive_errors >= SETTINGS.max_consecutive_errors:
                raise AnalystError(f"task '{task}' failed after {consecutive_errors} consecutive tool errors: {exc}") from exc

    raise AnalystError(f"task '{task}' exceeded {SETTINGS.max_steps} steps without finalizing")


def run_analyst(profile: DatasetProfile, provider: Provider, tools: dict) -> AnalystArtifact:
    findings = []
    failed_tasks = []

    for i, task in enumerate(profile.suggested_analyses, start=1):
        try:
            data = run_analysis_task(task, provider, tools)
            findings.append(Finding(
                id=f"F{i}",
                question=data["question"],
                method=data["method"],
                query=data["query"],
                value=data["value"],
                unit=data.get("unit", ""),
                chart_id=data.get("chart_id"),
            ))
        except AnalystError as exc:
            failed_tasks.append(str(exc))

    return AnalystArtifact(profile=profile, findings=findings, failed_tasks=failed_tasks)
