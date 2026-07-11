"""HTTP layer over the pipeline. CSV parsing and loading into SQLite happen
synchronously in POST /runs, so a malformed upload (bad CSV, too many rows)
is rejected immediately with a 400; the slow part -- LLM calls and PDF
render -- runs as a background task, polled via GET /runs/{run_id}.

run_id is generated server-side (RunContext) and is always 12 lowercase hex
characters; anything else in a path is rejected as 404 before it's ever
used to build a filesystem path, so a crafted run_id can't be used for
path traversal.
"""
import json
import re
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse

from src.api.runs import execute_pipeline, read_status
from src.artifacts import VerifiedReport
from src.config import SETTINGS
from src.csv_loader import CSVLoadError, load_csvs
from src.report.render import render_html
from src.run_context import RunContext, create_run
from src.tools import build_tools

MAX_UPLOAD_FILES = 10
_RUN_ID_PATTERN = re.compile(r"^[0-9a-f]{12}$")
_CHART_ID_PATTERN = re.compile(r"^chart_[0-9a-f]{8}$")
_PROVIDERS = ("mock", "anthropic", "openai")

app = FastAPI(title="AI Business Analyst")

app.add_middleware(
    CORSMiddleware,
    allow_origins=SETTINGS.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _run_dir(run_id: str) -> Path:
    if not _RUN_ID_PATTERN.match(run_id):
        raise HTTPException(404, "run not found")
    return SETTINGS.runs_dir / run_id


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/runs", status_code=202)
async def create_run_endpoint(
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    provider: str = Form("mock"),
):
    if provider not in _PROVIDERS:
        raise HTTPException(400, f"unknown provider: {provider!r}, expected one of {_PROVIDERS}")
    if not files:
        raise HTTPException(400, "at least one CSV file is required")
    if len(files) > MAX_UPLOAD_FILES:
        raise HTTPException(400, f"at most {MAX_UPLOAD_FILES} files allowed per upload")
    for f in files:
        if not (f.filename or "").lower().endswith(".csv"):
            raise HTTPException(400, f"{f.filename or '<unnamed>'} is not a .csv file")

    ctx = create_run()
    upload_dir = SETTINGS.upload_dir / ctx.run_id
    upload_dir.mkdir(parents=True, exist_ok=True)

    csv_paths = []
    for f in files:
        dest = upload_dir / Path(f.filename).name  # .name strips any directory components
        dest.write_bytes(await f.read())
        csv_paths.append(dest)

    try:
        row_counts = load_csvs(csv_paths, ctx.db_path)
    except CSVLoadError as exc:
        raise HTTPException(400, str(exc)) from exc

    tools = build_tools(ctx)
    background_tasks.add_task(execute_pipeline, ctx, tools, provider)

    return {"run_id": ctx.run_id, "status": "pending", "row_counts": row_counts}


@app.get("/runs/{run_id}")
def get_run(run_id: str):
    run_dir = _run_dir(run_id)
    status = read_status(run_dir)
    if status is None:
        raise HTTPException(404, "run not found")
    return {"run_id": run_id, **status}


@app.get("/runs/{run_id}/report")
def get_report(run_id: str):
    run_dir = _run_dir(run_id)
    report_path = run_dir / "verified_report.json"
    if not report_path.exists():
        raise HTTPException(404, "report not ready")
    return json.loads(report_path.read_text(encoding="utf-8"))


@app.get("/runs/{run_id}/report.html", response_class=HTMLResponse)
def get_report_html(run_id: str):
    run_dir = _run_dir(run_id)
    report_path = run_dir / "verified_report.json"
    if not report_path.exists():
        raise HTTPException(404, "report not ready")
    verified = VerifiedReport.model_validate_json(report_path.read_text(encoding="utf-8"))
    ctx = RunContext(run_id=run_id, db_path=run_dir / "unused.db", run_dir=run_dir, charts_dir=run_dir / "charts", sandbox_dir=run_dir)
    return render_html(verified, ctx, chart_url_base=f"/runs/{run_id}/charts")


@app.get("/runs/{run_id}/report.pdf")
def get_report_pdf(run_id: str):
    run_dir = _run_dir(run_id)
    pdf_path = run_dir / "report.pdf"
    if not pdf_path.exists():
        raise HTTPException(404, "pdf not available for this run")
    return FileResponse(pdf_path, media_type="application/pdf", filename="report.pdf")


@app.get("/runs/{run_id}/charts/{chart_id}.png")
def get_chart(run_id: str, chart_id: str):
    run_dir = _run_dir(run_id)
    if not _CHART_ID_PATTERN.match(chart_id):
        raise HTTPException(404, "chart not found")
    chart_path = run_dir / "charts" / f"{chart_id}.png"
    if not chart_path.exists():
        raise HTTPException(404, "chart not found")
    return FileResponse(chart_path, media_type="image/png")
