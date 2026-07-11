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
from src.pipeline.verifier import run_verifier
from src.pipeline.writer import run_writer
from src.providers import get_provider
from src.providers.mock_provider import MockProvider
from src.run_context import create_run
from src.tools import build_tools


def _demo_mock_provider() -> MockProvider:
    profiler_completion = json.dumps({
        "suggested_analyses": [
            "total revenue and completed order count",
            "top product by revenue",
        ],
        "data_quality_notes": [],
    })
    plan = [
        {"type": "tool_call", "id": "c1", "name": "run_sql", "args": {
            "query": "SELECT ROUND(SUM(quantity*unit_price),2), COUNT(*) FROM orders WHERE status='completed'"}},
        {"type": "final", "text": json.dumps({
            "question": "total revenue and completed order count", "method": "sql",
            "query": "SELECT ROUND(SUM(quantity*unit_price),2), COUNT(*) FROM orders WHERE status='completed'",
            "value": 1121746.54, "unit": "USD"})},

        {"type": "tool_call", "id": "c2", "name": "run_sql", "args": {
            "query": "SELECT p.name, ROUND(SUM(o.quantity*o.unit_price),2) AS revenue FROM orders o "
                     "JOIN products p ON o.product_id = p.product_id WHERE o.status='completed' "
                     "GROUP BY p.name ORDER BY revenue DESC LIMIT 1"}},
        {"type": "final", "text": json.dumps({
            "question": "top product by revenue", "method": "sql",
            "query": "SELECT p.name, ROUND(SUM(o.quantity*o.unit_price),2) AS revenue FROM orders o "
                     "JOIN products p ON o.product_id = p.product_id WHERE o.status='completed' "
                     "GROUP BY p.name ORDER BY revenue DESC LIMIT 1",
            "value": 29324.10, "unit": "USD"})},
    ]
    writer_completion = json.dumps({
        "executive_summary": "The business generated $1,121,746.54 in revenue across completed orders this period [F1].",
        "sections": [{
            "heading": "Revenue",
            "body": "Total completed-order revenue was $1,121,746.54 [F1]. The top-performing product "
                    "contributed $29,324.10 in revenue [F2].",
        }],
    })
    verifier_completion = json.dumps({
        "judgments": [
            {"finding_id": "F1", "faithful": True},
            {"finding_id": "F2", "faithful": True},
        ],
    })
    return MockProvider(plan=plan, completions=[profiler_completion, writer_completion, verifier_completion])


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

    draft = run_writer(artifact, provider)
    print(f"\n=== draft ===\n{draft.executive_summary}\n")
    for section in draft.sections:
        print(f"-- {section.heading} --\n{section.body}\n")

    verified = run_verifier(draft, artifact, tools, provider)
    print("=== verifier ===")
    for v in verified.verdicts:
        status = "PASS" if v.passed else "FAIL"
        print(f"  [{v.finding_id}] {status}" + (f" - {v.reason}" if v.reason else ""))
    for claim in verified.removed_claims:
        print(f"  removed [{claim.finding_id}]: {claim.reason}")

    print(f"\n=== verified report ===\n{verified.executive_summary}\n")
    for section in verified.sections:
        print(f"-- {section.heading} --\n{section.body}\n")


if __name__ == "__main__":
    main()
