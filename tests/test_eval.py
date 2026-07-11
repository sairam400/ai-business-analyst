import shutil
import tempfile
import unittest
from pathlib import Path

from src.artifacts import AnalystArtifact, DatasetProfile, Finding, VerifiedReport, VerifierVerdict
from src.csv_loader import load_directory
from src.eval.metrics import coverage, groundedness
from src.eval.reference import ReferenceFact, compute_reference_facts
from src.eval.run_eval import run_once, summarize
from src.generate_sample_data import generate
from src.run_context import RunContext
from src.tools import build_tools


class TestReferenceFacts(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        generate(self.tmp / "sample", seed=42)
        self.db_path = self.tmp / "sample.db"
        load_directory(self.tmp / "sample", self.db_path)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_facts_are_deterministic_for_a_fixed_seed(self):
        first = compute_reference_facts(self.db_path)
        second = compute_reference_facts(self.db_path)
        self.assertEqual([f.value for f in first], [f.value for f in second])

    def test_expected_fact_names_present(self):
        facts = compute_reference_facts(self.db_path)
        names = {f.name for f in facts}
        self.assertIn("total_completed_revenue", names)
        self.assertIn("completed_order_count", names)
        self.assertIn("top_category_by_revenue", names)


class TestGroundedness(unittest.TestCase):
    def test_pass_rate_computed_from_verdicts(self):
        report = VerifiedReport(
            executive_summary="", sections=[], findings=[],
            verdicts=[
                VerifierVerdict(finding_id="F1", claimed_value=1, recomputed_value=1, passed=True),
                VerifierVerdict(finding_id="F2", claimed_value=2, recomputed_value=3, passed=False, reason="mismatch"),
            ],
        )
        result = groundedness(report)
        self.assertEqual(result, {"citations_checked": 2, "citations_passed": 1, "citations_removed": 0, "pass_rate": 0.5})

    def test_no_citations_gives_none_pass_rate_not_divide_by_zero(self):
        report = VerifiedReport(executive_summary="", sections=[], findings=[], verdicts=[])
        result = groundedness(report)
        self.assertIsNone(result["pass_rate"])


class TestCoverage(unittest.TestCase):
    def _artifact(self, findings):
        return AnalystArtifact(profile=DatasetProfile(tables=[]), findings=findings)

    def test_numeric_fact_matched_within_tolerance(self):
        facts = [ReferenceFact("total_completed_revenue", 100.00, "desc")]
        findings = [Finding(id="F1", question="q", method="sql", query="SELECT 1", value=100.005, unit="USD")]
        result = coverage(self._artifact(findings), facts)
        self.assertEqual(result["facts_covered"], 1)
        self.assertTrue(result["detail"][0]["found"])

    def test_string_fact_matched_case_insensitively(self):
        facts = [ReferenceFact("top_category_by_revenue", "Electronics", "desc")]
        findings = [Finding(id="F1", question="q", method="sql", query="SELECT 1", value="electronics", unit="")]
        result = coverage(self._artifact(findings), facts)
        self.assertEqual(result["facts_covered"], 1)

    def test_uncovered_fact_reported_as_not_found(self):
        facts = [ReferenceFact("total_completed_revenue", 100.00, "desc")]
        findings = [Finding(id="F1", question="q", method="sql", query="SELECT 1", value=999.0, unit="USD")]
        result = coverage(self._artifact(findings), facts)
        self.assertEqual(result["facts_covered"], 0)
        self.assertFalse(result["detail"][0]["found"])


class TestRunOnce(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        generate(self.tmp / "sample", seed=42)
        db_path = self.tmp / "sample.db"
        load_directory(self.tmp / "sample", db_path)
        self.ctx = RunContext(run_id="e1", db_path=db_path, run_dir=self.tmp / "run", charts_dir=self.tmp / "run" / "charts", sandbox_dir=self.tmp / "sandbox")
        self.ctx.charts_dir.mkdir(parents=True, exist_ok=True)
        self.ctx.sandbox_dir.mkdir(parents=True, exist_ok=True)
        self.tools = build_tools(self.ctx)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_mock_provider_end_to_end_produces_scored_result(self):
        result = run_once("mock", self.ctx, self.tools)
        self.assertNotIn("error", result)
        self.assertIn("groundedness", result)
        self.assertIn("coverage", result)
        self.assertEqual(set(result["timings"]), {"profiler_s", "analyst_s", "writer_s", "verifier_s"})

    def test_provider_error_is_captured_not_raised(self):
        result = run_once("openai", self.ctx, self.tools)  # no OPENAI_API_KEY set in test env
        self.assertIn("error", result)
        self.assertEqual(result["run_id"], "e1")


class TestSummarize(unittest.TestCase):
    def test_averages_ignore_errored_runs(self):
        results = [
            {"groundedness": {"pass_rate": 1.0}, "coverage": {"coverage_rate": 0.5}},
            {"groundedness": {"pass_rate": 0.0}, "coverage": {"coverage_rate": 0.5}},
            {"error": "boom"},
        ]
        summary = summarize(results)
        self.assertEqual(summary["runs"], 3)
        self.assertEqual(summary["errors"], 1)
        self.assertEqual(summary["mean_pass_rate"], 0.5)
        self.assertEqual(summary["mean_coverage_rate"], 0.5)


if __name__ == "__main__":
    unittest.main()
