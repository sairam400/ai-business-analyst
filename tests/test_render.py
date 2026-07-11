import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path

from src.artifacts import Finding, RemovedClaim, ReportSection, VerifiedReport, VerifierVerdict
from src.report.render import RenderError, build_context, render_html, render_pdf
from src.run_context import RunContext


def _ctx(tmp: Path) -> RunContext:
    run_dir = tmp / "run"
    charts_dir = run_dir / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)
    return RunContext(run_id="r1", db_path=tmp / "db.sqlite", run_dir=run_dir, charts_dir=charts_dir, sandbox_dir=tmp / "sandbox")


class TestBuildContext(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.ctx = _ctx(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _report(self, **overrides):
        defaults = dict(
            executive_summary="Revenue was $100.00 [F1].",
            sections=[ReportSection(heading="Revenue", body="Total was $100.00 [F1].")],
            findings=[Finding(id="F1", question="total revenue", method="sql", query="SELECT 1", value=100.0, unit="USD")],
            verdicts=[VerifierVerdict(finding_id="F1", claimed_value=100.0, recomputed_value=100.0, passed=True)],
        )
        defaults.update(overrides)
        return VerifiedReport(**defaults)

    def test_only_cited_findings_become_sources(self):
        report = self._report(findings=[
            Finding(id="F1", question="total revenue", method="sql", query="SELECT 1", value=100.0, unit="USD"),
            Finding(id="F2", question="uncited finding", method="sql", query="SELECT 2", value=5, unit=""),
        ])
        ctx_data = build_context(report, self.ctx)
        self.assertEqual([s["id"] for s in ctx_data["sources"]], ["F1"])

    def test_footnote_marker_becomes_anchor_link(self):
        html = render_html(self._report(), self.ctx)
        self.assertIn('<a href="#fn-F1">[F1]</a>', html)
        self.assertIn('id="fn-F1"', html)

    def test_llm_authored_markup_is_escaped_not_executed(self):
        report = self._report(executive_summary='Revenue was <script>alert(1)</script> $100.00 [F1].')
        html = render_html(report, self.ctx)
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_chart_included_only_for_cited_finding_with_existing_png(self):
        (self.ctx.charts_dir / "chart_abc.png").write_bytes(b"\x89PNG")
        report = self._report(findings=[
            Finding(id="F1", question="q", method="sql", query="SELECT 1", value=100.0, unit="USD", chart_id="chart_abc"),
        ])
        ctx_data = build_context(report, self.ctx)
        self.assertEqual(len(ctx_data["charts"]), 1)
        self.assertTrue(ctx_data["charts"][0]["uri"].startswith("file:"))

    def test_chart_omitted_when_png_missing(self):
        report = self._report(findings=[
            Finding(id="F1", question="q", method="sql", query="SELECT 1", value=100.0, unit="USD", chart_id="does_not_exist"),
        ])
        ctx_data = build_context(report, self.ctx)
        self.assertEqual(ctx_data["charts"], [])

    def test_removed_claim_count_surfaces_in_context(self):
        report = self._report(removed_claims=[RemovedClaim(finding_id="F2", reason="mismatch")])
        ctx_data = build_context(report, self.ctx)
        self.assertEqual(ctx_data["removed_claim_count"], 1)


class TestRenderPdf(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.ctx = _ctx(self.tmp)
        self.report = VerifiedReport(
            executive_summary="Revenue was $100.00 [F1].",
            sections=[],
            findings=[Finding(id="F1", question="total revenue", method="sql", query="SELECT 1", value=100.0, unit="USD")],
            verdicts=[VerifierVerdict(finding_id="F1", claimed_value=100.0, recomputed_value=100.0, passed=True)],
        )

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_writes_pdf_via_weasyprint_html(self):
        calls = {}

        class FakeHTML:
            def __init__(self, string, base_url):
                calls["string"] = string
                calls["base_url"] = base_url

            def write_pdf(self, path):
                calls["path"] = path
                Path(path).write_bytes(b"%PDF-fake")

        fake_module = types.ModuleType("weasyprint")
        fake_module.HTML = FakeHTML
        sys.modules["weasyprint"] = fake_module
        try:
            out_path = self.ctx.run_dir / "report.pdf"
            result = render_pdf(self.report, self.ctx, out_path=out_path)
        finally:
            del sys.modules["weasyprint"]

        self.assertEqual(result, out_path)
        self.assertTrue(out_path.exists())
        self.assertIn("Business Analytics Report", calls["string"])
        self.assertEqual(calls["base_url"], str(self.ctx.run_dir))

    def test_missing_native_libs_raises_render_error(self):
        sys.modules["weasyprint"] = None
        try:
            with self.assertRaises(RenderError):
                render_pdf(self.report, self.ctx)
        finally:
            del sys.modules["weasyprint"]


if __name__ == "__main__":
    unittest.main()
