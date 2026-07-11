"""Runs the pipeline as a background job keyed by run_id, with progress
written to a status.json in the run directory rather than kept in memory --
so status survives a worker restart and multiple uvicorn workers could, in
principle, share it via the mounted runs/ volume.
"""
import json
from pathlib import Path

from src.demo_cli import demo_mock_provider
from src.pipeline.analyst import run_analyst
from src.pipeline.profiler import profile_dataset
from src.pipeline.verifier import run_verifier
from src.pipeline.writer import run_writer
from src.providers import get_provider
from src.report.render import RenderError, render_html, render_pdf
from src.run_context import RunContext

STATUS_FILENAME = "status.json"


def _status_path(run_dir: Path) -> Path:
    return run_dir / STATUS_FILENAME


def write_status(ctx: RunContext, status: dict) -> None:
    _status_path(ctx.run_dir).write_text(json.dumps(status, indent=2), encoding="utf-8")


def read_status(run_dir: Path) -> dict:
    path = _status_path(run_dir)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def execute_pipeline(ctx: RunContext, tools: dict, provider_name: str) -> None:
    write_status(ctx, {"status": "running", "stage": "profiler"})
    try:
        provider = demo_mock_provider() if provider_name == "mock" else get_provider(provider_name)

        profile = profile_dataset(tools, provider)

        write_status(ctx, {"status": "running", "stage": "analyst"})
        artifact = run_analyst(profile, provider, tools)
        (ctx.run_dir / "analyst_artifact.json").write_text(artifact.model_dump_json(indent=2), encoding="utf-8")

        write_status(ctx, {"status": "running", "stage": "writer"})
        draft = run_writer(artifact, provider)

        write_status(ctx, {"status": "running", "stage": "verifier"})
        verified = run_verifier(draft, artifact, tools, provider)
        (ctx.run_dir / "verified_report.json").write_text(verified.model_dump_json(indent=2), encoding="utf-8")

        write_status(ctx, {"status": "running", "stage": "render"})
        (ctx.run_dir / "report.html").write_text(render_html(verified, ctx), encoding="utf-8")
        pdf_ready = True
        try:
            render_pdf(verified, ctx)
        except RenderError:
            pdf_ready = False

        write_status(ctx, {
            "status": "done",
            "findings": len(artifact.findings),
            "failed_tasks": artifact.failed_tasks,
            "citations_checked": len(verified.verdicts),
            "citations_passed": sum(1 for v in verified.verdicts if v.passed),
            "removed_claims": len(verified.removed_claims),
            "pdf_ready": pdf_ready,
        })
    except Exception as exc:
        write_status(ctx, {"status": "failed", "error": str(exc)})
