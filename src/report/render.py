"""Renders a VerifiedReport to PDF. HTML is built from a Jinja2 template
and converted with WeasyPrint -- the one stage in the pipeline that touches
native (non-Python) libraries, which is why it's isolated here and why
nothing reaches it whose numbers haven't already been recomputed by the
verifier. See KNOWN_ISSUES.md: WeasyPrint needs Pango/Cairo at the OS
level, verified inside the project's Docker image rather than natively on
Windows dev machines.
"""
import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup, escape

from src.artifacts import VerifiedReport
from src.chart_style import AXIS, CATEGORICAL, GRIDLINE, INK_MUTED, INK_PRIMARY, INK_SECONDARY, SURFACE
from src.config import SETTINGS
from src.run_context import RunContext

_FOOTNOTE_PATTERN = re.compile(r"\[F(\d+)\]")

_env = Environment(
    loader=FileSystemLoader(str(SETTINGS.report_templates_dir)),
    autoescape=select_autoescape(["html"]),
)

PALETTE = {
    "surface": SURFACE,
    "ink_primary": INK_PRIMARY,
    "ink_secondary": INK_SECONDARY,
    "ink_muted": INK_MUTED,
    "gridline": GRIDLINE,
    "axis": AXIS,
    "accent": CATEGORICAL[0],
}


class RenderError(Exception):
    pass


def _linkify_footnotes(text: str) -> Markup:
    """Escapes the LLM-authored text first, then rewrites footnote markers
    into anchors on the escaped string -- so a claim can't smuggle markup
    into the PDF, but our own generated anchor tags still render as HTML."""
    escaped = str(escape(text))

    def repl(match: re.Match) -> str:
        fid = f"F{match.group(1)}"
        return f'<sup><a href="#fn-{fid}">[{fid}]</a></sup>'

    return Markup(_FOOTNOTE_PATTERN.sub(repl, escaped))


def _cited_ids(report: VerifiedReport) -> set[str]:
    texts = [report.executive_summary] + [s.body for s in report.sections]
    ids = set()
    for text in texts:
        ids |= {f"F{n}" for n in _FOOTNOTE_PATTERN.findall(text)}
    return ids


def build_context(report: VerifiedReport, ctx: RunContext) -> dict:
    cited = _cited_ids(report)
    findings_by_id = {f.id: f for f in report.findings}
    verdicts_by_id = {v.finding_id: v for v in report.verdicts}

    sources = []
    for fid in sorted(cited, key=lambda x: int(x[1:])):
        finding = findings_by_id.get(fid)
        if finding is None:
            continue
        verdict = verdicts_by_id.get(fid)
        sources.append({
            "id": fid,
            "question": finding.question,
            "query": finding.query,
            "value": finding.value,
            "unit": finding.unit,
            "recomputed_value": verdict.recomputed_value if verdict else None,
        })

    charts = []
    for finding in report.findings:
        if not finding.chart_id or finding.id not in cited:
            continue
        chart_path = ctx.charts_dir / f"{finding.chart_id}.png"
        if chart_path.exists():
            charts.append({"finding_id": finding.id, "title": finding.question, "uri": chart_path.resolve().as_uri()})

    return {
        "run_id": ctx.run_id,
        "executive_summary": _linkify_footnotes(report.executive_summary),
        "sections": [{"heading": s.heading, "body": _linkify_footnotes(s.body)} for s in report.sections],
        "sources": sources,
        "charts": charts,
        "removed_claim_count": len(report.removed_claims),
        "palette": PALETTE,
    }


def render_html(report: VerifiedReport, ctx: RunContext) -> str:
    template = _env.get_template("report.html.jinja")
    return template.render(**build_context(report, ctx))


def render_pdf(report: VerifiedReport, ctx: RunContext, out_path: Path = None) -> Path:
    try:
        from weasyprint import HTML
    except (ImportError, OSError) as exc:
        raise RenderError(
            "weasyprint could not load its native Pango/Cairo libraries. This is expected "
            "on native Windows without a GTK3 runtime -- run inside the project's Docker "
            "image, or see KNOWN_ISSUES.md for native setup."
        ) from exc

    html = render_html(report, ctx)
    out_path = out_path or (ctx.run_dir / "report.pdf")
    HTML(string=html, base_url=str(ctx.run_dir)).write_pdf(str(out_path))
    return out_path
