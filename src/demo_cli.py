"""Runs profiler + analyst against the sample dataset and prints the
resulting artifacts. Defaults to a scripted MockProvider (no API key
needed) so the pipeline shape is checkable without network access; pass
--provider anthropic once ANTHROPIC_API_KEY is set to see a real run.
"""
import argparse
import json

from src.config import SETTINGS
from src.csv_loader import load_directory
from src.pipeline.analyst import run_analyst
from src.pipeline.profiler import profile_dataset
from src.providers import get_provider
from src.providers.mock_provider import MockProvider
from src.run_context import create_run
from src.tools import build_tools


def _demo_mock_provider() -> MockProvider:
    profiler_completion = json.dumps({
        "suggested_analyses": [
            "total revenue and completed order count",
            "top 5 products by revenue",
            "monthly order volume trend",
        ],
        "data_quality_notes": [],
    })
    plan = [
        {"type": "tool_call", "id": "c1", "name": "run_sql", "args": {
            "query": "SELECT ROUND(SUM(quantity*unit_price),2), COUNT(*) FROM orders WHERE status='completed'"}},
        {"type": "final", "text": json.dumps({
            "question": "total revenue and completed order count", "method": "sql",
            "query": "SELECT ROUND(SUM(quantity*unit_price),2), COUNT(*) FROM orders WHERE status='completed'",
            "value": "see query result", "unit": "USD"})},

        {"type": "tool_call", "id": "c2", "name": "run_sql", "args": {
            "query": "SELECT p.name, ROUND(SUM(o.quantity*o.unit_price),2) AS revenue FROM orders o "
                     "JOIN products p ON o.product_id = p.product_id WHERE o.status='completed' "
                     "GROUP BY p.name ORDER BY revenue DESC LIMIT 5"}},
        {"type": "final", "text": json.dumps({
            "question": "top 5 products by revenue", "method": "sql",
            "query": "SELECT p.name, ROUND(SUM(o.quantity*o.unit_price),2) AS revenue FROM orders o "
                     "JOIN products p ON o.product_id = p.product_id WHERE o.status='completed' "
                     "GROUP BY p.name ORDER BY revenue DESC LIMIT 5",
            "value": "see query result"})},

        {"type": "tool_call", "id": "c3", "name": "run_sql", "args": {
            "query": "SELECT strftime('%Y-%m', order_date) AS month, COUNT(*) FROM orders GROUP BY month ORDER BY month"}},
        {"type": "final", "text": json.dumps({
            "question": "monthly order volume trend", "method": "sql",
            "query": "SELECT strftime('%Y-%m', order_date) AS month, COUNT(*) FROM orders GROUP BY month ORDER BY month",
            "value": "see query result"})},
    ]
    return MockProvider(plan=plan, completions=[profiler_completion])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", default="mock", choices=["mock", "anthropic", "openai"])
    args = parser.parse_args()

    load_directory(SETTINGS.sample_data_dir, SETTINGS.db_path)
    ctx = create_run()
    tools = build_tools(ctx)
    provider = _demo_mock_provider() if args.provider == "mock" else get_provider(args.provider)

    print(f"=== run {ctx.run_id} ===")
    profile = profile_dataset(tools, provider)
    print(f"\ntables: {[t.name for t in profile.tables]}")
    print(f"relationships: {profile.detected_relationships}")
    print(f"data quality notes: {profile.data_quality_notes}")
    print(f"suggested analyses: {profile.suggested_analyses}")

    artifact = run_analyst(profile, provider, tools)
    print(f"\n{len(artifact.findings)} findings, {len(artifact.failed_tasks)} failed tasks")
    for f in artifact.findings:
        print(f"  [{f.id}] {f.question} -> {f.value} {f.unit}".rstrip())
    for failure in artifact.failed_tasks:
        print(f"  FAILED: {failure}")

    out_path = ctx.run_dir / "analyst_artifact.json"
    out_path.write_text(artifact.model_dump_json(indent=2), encoding="utf-8")
    print(f"\nwrote {out_path}")


if __name__ == "__main__":
    main()
