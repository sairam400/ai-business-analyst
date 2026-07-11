"""Eval harness: runs the full pipeline against the fixed sample dataset
and scores it on groundedness and coverage (see src/eval/metrics.py). No
golden Q&A pairing is needed -- the analyst picks its own questions; what's
measured is whether whatever it picks holds up under the verifier, and
whether it finds what's actually in the data.

    python -m src.eval.run_eval --provider mock      # deterministic smoke test
    python -m src.eval.run_eval --provider anthropic --runs 3

A run that raises anywhere in the pipeline is recorded with an "error"
field rather than crashing the whole harness -- one bad run (especially
likely with a real, non-deterministic provider) shouldn't lose the rest.
"""
import argparse
import json
import time
from pathlib import Path

from src.config import SETTINGS
from src.csv_loader import load_directory
from src.demo_cli import demo_mock_provider
from src.eval.metrics import coverage, groundedness
from src.eval.reference import compute_reference_facts
from src.generate_sample_data import SEED, generate
from src.pipeline.analyst import run_analyst
from src.pipeline.profiler import profile_dataset
from src.pipeline.verifier import run_verifier
from src.pipeline.writer import run_writer
from src.providers import get_provider
from src.run_context import RunContext, create_run
from src.tools import build_tools


def run_once(provider_name: str, ctx: RunContext, tools: dict) -> dict:
    timings = {}
    try:
        provider = demo_mock_provider() if provider_name == "mock" else get_provider(provider_name)
        facts = compute_reference_facts(ctx.db_path)

        t0 = time.monotonic()
        profile = profile_dataset(tools, provider)
        timings["profiler_s"] = round(time.monotonic() - t0, 2)

        t0 = time.monotonic()
        artifact = run_analyst(profile, provider, tools)
        timings["analyst_s"] = round(time.monotonic() - t0, 2)

        t0 = time.monotonic()
        draft = run_writer(artifact, provider)
        timings["writer_s"] = round(time.monotonic() - t0, 2)

        t0 = time.monotonic()
        verified = run_verifier(draft, artifact, tools, provider)
        timings["verifier_s"] = round(time.monotonic() - t0, 2)
    except Exception as exc:
        return {"run_id": ctx.run_id, "provider": provider_name, "timings": timings, "error": str(exc)}

    return {
        "run_id": ctx.run_id,
        "provider": provider_name,
        "timings": timings,
        "suggested_analyses": profile.suggested_analyses,
        "findings": len(artifact.findings),
        "failed_tasks": len(artifact.failed_tasks),
        "groundedness": groundedness(verified),
        "coverage": coverage(artifact, facts),
    }


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 3) if values else None


def summarize(results: list[dict]) -> dict:
    errors = [r for r in results if "error" in r]
    pass_rates = [r["groundedness"]["pass_rate"] for r in results if "groundedness" in r and r["groundedness"]["pass_rate"] is not None]
    coverage_rates = [r["coverage"]["coverage_rate"] for r in results if "coverage" in r and r["coverage"]["coverage_rate"] is not None]
    return {
        "runs": len(results),
        "errors": len(errors),
        "mean_pass_rate": _mean(pass_rates),
        "mean_coverage_rate": _mean(coverage_rates),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", default="mock", choices=["mock", "anthropic", "openai"])
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--min-pass-rate", type=float, default=0.8)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    generate(SETTINGS.sample_data_dir, seed=args.seed)
    load_directory(SETTINGS.sample_data_dir, SETTINGS.db_path)

    results = []
    for _ in range(args.runs):
        ctx = create_run()
        tools = build_tools(ctx)
        results.append(run_once(args.provider, ctx, tools))

    summary = summarize(results)

    print(f"=== eval: {args.provider}, {summary['runs']} run(s) ===")
    for r in results:
        if "error" in r:
            print(f"  run {r['run_id']}: ERROR - {r['error']}")
            continue
        g, c = r["groundedness"], r["coverage"]
        print(
            f"  run {r['run_id']}: {r['findings']} findings, "
            f"groundedness {g['citations_passed']}/{g['citations_checked']}, "
            f"coverage {c['facts_covered']}/{c['facts_total']}"
        )
    print(f"\nerrors: {summary['errors']}/{summary['runs']}")
    print(f"mean pass rate: {summary['mean_pass_rate']}")
    print(f"mean coverage rate: {summary['mean_coverage_rate']}")

    out_path = Path(args.out) if args.out else SETTINGS.runs_dir / "eval" / f"eval_{args.provider}_{int(time.time())}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"summary": summary, "results": results}, indent=2), encoding="utf-8")
    print(f"\nwrote {out_path}")

    if summary["mean_pass_rate"] is not None and summary["mean_pass_rate"] < args.min_pass_rate:
        raise SystemExit(
            f"FAIL: mean pass rate {summary['mean_pass_rate']} below threshold {args.min_pass_rate}"
        )


if __name__ == "__main__":
    main()
