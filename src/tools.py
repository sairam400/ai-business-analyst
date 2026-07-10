"""The tool layer every agent stage that touches data goes through.

Read-only is enforced here, not in the prompt: run_sql rejects anything
that isn't a SELECT and scans for mutation keywords anywhere in the
string, so a smuggled statement after a semicolon still gets caught.
run_python never receives the database path or network access, so even a
script that ignores its own input_data can't reach the live data outside
what run_sql already returned to it.
"""
import json
import os
import re
import sqlite3
import subprocess
import sys
import uuid
from pathlib import Path

from src.chart_style import CATEGORICAL, STATUS, apply_style, categorical_colors
from src.config import SETTINGS
from src.run_context import RunContext

_READ_ONLY_PATTERN = re.compile(r"^\s*SELECT\b", re.IGNORECASE)
_FORBIDDEN_PATTERN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|ATTACH|PRAGMA|REPLACE|TRUNCATE|VACUUM)\b",
    re.IGNORECASE,
)
_MAX_ROWS = 1000

_NETWORK_BLOCK_PREAMBLE = """\
import socket as _socket
def _blocked(*a, **k):
    raise RuntimeError("network access is disabled in this sandbox")
_socket.socket = _blocked
_socket.create_connection = _blocked
"""


class ToolError(Exception):
    pass


def run_sql(query: str, ctx: RunContext) -> dict:
    if not _READ_ONLY_PATTERN.match(query):
        raise ToolError("run_sql only accepts queries that start with SELECT")
    if _FORBIDDEN_PATTERN.search(query):
        raise ToolError("run_sql rejected: query contains a mutating keyword")

    conn = sqlite3.connect(ctx.db_path)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.execute(query)
        columns = [d[0] for d in cursor.description] if cursor.description else []
        rows = cursor.fetchmany(_MAX_ROWS + 1)
    except sqlite3.Error as exc:
        raise ToolError(f"SQL error: {exc}") from exc
    finally:
        conn.close()

    truncated = len(rows) > _MAX_ROWS
    rows = rows[:_MAX_ROWS]
    return {
        "columns": columns,
        "rows": [list(row) for row in rows],
        "row_count": len(rows),
        "truncated": truncated,
    }


def run_python(code: str, ctx: RunContext, input_data=None) -> dict:
    scratch = ctx.sandbox_dir / uuid.uuid4().hex[:8]
    scratch.mkdir(parents=True, exist_ok=True)

    if input_data is not None:
        (scratch / "input.json").write_text(json.dumps(input_data), encoding="utf-8")

    load_input = (
        'import json\nwith open("input.json") as _f:\n    input_data = json.load(_f)\n'
        if input_data is not None
        else "input_data = None\n"
    )
    script = (
        _NETWORK_BLOCK_PREAMBLE
        + load_input
        + code
        + '\n\nimport json as _json\nwith open("output.json", "w") as _f:\n    _json.dump(result, _f)\n'
    )
    script_path = scratch / "script.py"
    script_path.write_text(script, encoding="utf-8")

    env = {"PATH": os.environ.get("PATH", "")}
    try:
        proc = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=scratch,
            env=env,
            capture_output=True,
            text=True,
            timeout=SETTINGS.run_python_timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise ToolError(f"run_python timed out after {SETTINGS.run_python_timeout_seconds}s") from exc

    if proc.returncode != 0:
        raise ToolError(f"run_python failed: {proc.stderr.strip()[-2000:]}")

    output_path = scratch / "output.json"
    if not output_path.exists():
        raise ToolError("run_python did not set a `result` variable")

    result = json.loads(output_path.read_text(encoding="utf-8"))
    return {"result": result, "stdout": proc.stdout.strip()}


def make_chart(
    kind: str,
    title: str,
    x: list,
    series: list[dict],
    ctx: RunContext,
    x_label: str = "",
    y_label: str = "",
    highlight_index: int = None,
) -> dict:
    if kind not in ("bar", "line"):
        raise ToolError(f"unsupported chart kind: {kind}")
    if not series:
        raise ToolError("make_chart requires at least one series")

    import matplotlib.pyplot as plt

    apply_style()
    fig, ax = plt.subplots(figsize=(7, 4))

    if kind == "bar":
        if len(series) > 1:
            raise ToolError("bar charts support a single series only")
        values = series[0]["values"]
        colors = [CATEGORICAL[0]] * len(values)
        if highlight_index is not None and 0 <= highlight_index < len(values):
            colors[highlight_index] = STATUS["critical"]
        ax.bar(range(len(x)), values, color=colors)
        ax.set_xticks(range(len(x)))
        ax.set_xticklabels(x, rotation=45, ha="right")
    else:
        colors = categorical_colors(len(series))
        for s, color in zip(series, colors):
            ax.plot(x, s["values"], color=color, marker="o", markersize=4, label=s["name"])
        if highlight_index is not None and 0 <= highlight_index < len(x):
            ax.axvline(x[highlight_index], color=STATUS["critical"], linestyle="--", linewidth=1)
        if len(series) > 1:
            ax.legend(frameon=False)

    ax.set_title(title)
    if x_label:
        ax.set_xlabel(x_label)
    if y_label:
        ax.set_ylabel(y_label)
    fig.tight_layout()

    chart_id = f"chart_{uuid.uuid4().hex[:8]}"
    path = ctx.charts_dir / f"{chart_id}.png"
    fig.savefig(path)
    plt.close(fig)

    return {"chart_id": chart_id, "path": str(path), "title": title}


TOOL_SPECS = [
    {
        "name": "run_sql",
        "description": "Run a read-only SELECT query against the loaded dataset and get back rows.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "A single SELECT statement."}},
            "required": ["query"],
        },
    },
    {
        "name": "run_python",
        "description": (
            "Run Python for computation SQL can't express (e.g. statistics on a result set). "
            "The script receives `input_data` (from a prior tool result you pass in) and must "
            "assign its answer to a variable named `result`. No network or database access."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Python source. Must set `result`."},
                "input_data": {"description": "JSON-serializable data the script can read as `input_data`."},
            },
            "required": ["code"],
        },
    },
    {
        "name": "make_chart",
        "description": "Render a bar or line chart in the report's house style and get back a chart_id to cite.",
        "parameters": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["bar", "line"]},
                "title": {"type": "string"},
                "x": {"type": "array", "items": {}},
                "series": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"name": {"type": "string"}, "values": {"type": "array", "items": {"type": "number"}}},
                        "required": ["name", "values"],
                    },
                },
                "x_label": {"type": "string"},
                "y_label": {"type": "string"},
                "highlight_index": {"type": "integer", "description": "Index to flag as an anomaly, if any."},
            },
            "required": ["kind", "title", "x", "series"],
        },
    },
]


def build_tools(ctx: RunContext) -> dict:
    return {
        "run_sql": lambda query: run_sql(query, ctx),
        "run_python": lambda code, input_data=None: run_python(code, ctx, input_data),
        "make_chart": lambda kind, title, x, series, x_label="", y_label="", highlight_index=None: make_chart(
            kind, title, x, series, ctx, x_label, y_label, highlight_index
        ),
    }
