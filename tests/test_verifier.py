import json
import unittest

from src.artifacts import AnalystArtifact, DatasetProfile, Draft, Finding, ReportSection
from src.pipeline.verifier import VerifierError, run_verifier
from src.providers.mock_provider import MockProvider
from src.tools import ToolError


def _artifact(findings):
    return AnalystArtifact(profile=DatasetProfile(tables=[]), findings=findings)


def _tools(sql_results=None, python_results=None):
    sql_results = sql_results or {}
    python_results = python_results or {}

    def run_sql(query):
        if query not in sql_results:
            raise ToolError(f"unscripted query: {query}")
        result = sql_results[query]
        if isinstance(result, Exception):
            raise result
        return result

    def run_python(code, input_data=None):
        if code not in python_results:
            raise ToolError(f"unscripted code: {code}")
        result = python_results[code]
        if isinstance(result, Exception):
            raise result
        return result

    return {"run_sql": run_sql, "run_python": run_python}


class TestMechanicalCheck(unittest.TestCase):
    def test_matching_value_passes_and_needs_no_semantic_call(self):
        findings = [Finding(id="F1", question="total revenue", method="sql", query="SELECT SUM(x)", value=125430.55, unit="USD")]
        draft = Draft(executive_summary="Revenue was $125,430.55 [F1].", sections=[])
        tools = _tools(sql_results={"SELECT SUM(x)": {"columns": ["s"], "rows": [[125430.55]], "row_count": 1, "truncated": False}})
        # no completions scripted -- semantic check must be skipped once mechanical check fails... here it passes,
        # so a semantic judgment IS needed; script one that marks it faithful.
        provider = MockProvider(completions=[json.dumps({"judgments": [{"finding_id": "F1", "faithful": True}]})])
        report = run_verifier(draft, _artifact(findings), tools, provider)
        self.assertEqual(len(report.verdicts), 1)
        self.assertTrue(report.verdicts[0].passed)
        self.assertIn("[F1]", report.executive_summary)
        self.assertEqual(report.removed_claims, [])

    def test_within_tolerance_passes(self):
        findings = [Finding(id="F1", question="q", method="sql", query="SELECT 1", value=100.0, unit="USD")]
        draft = Draft(executive_summary="Value was $100.00 [F1].", sections=[])
        tools = _tools(sql_results={"SELECT 1": {"columns": ["s"], "rows": [[100.5]], "row_count": 1, "truncated": False}})
        provider = MockProvider(completions=[json.dumps({"judgments": [{"finding_id": "F1", "faithful": True}]})])
        report = run_verifier(draft, _artifact(findings), tools, provider)
        self.assertTrue(report.verdicts[0].passed)

    def test_mismatched_value_fails_and_skips_semantic_call(self):
        findings = [Finding(id="F1", question="q", method="sql", query="SELECT 1", value=100.0, unit="USD")]
        draft = Draft(
            executive_summary="Value was $100.00 [F1]. Nothing else to report.",
            sections=[ReportSection(heading="Notes", body="See summary above.")],
        )
        tools = _tools(sql_results={"SELECT 1": {"columns": ["s"], "rows": [[999.0]], "row_count": 1, "truncated": False}})
        provider = MockProvider(completions=[])  # no semantic call should happen -- failing to script one would raise if called
        report = run_verifier(draft, _artifact(findings), tools, provider)
        verdict = report.verdicts[0]
        self.assertFalse(verdict.passed)
        self.assertEqual(len(report.removed_claims), 1)
        self.assertEqual(report.removed_claims[0].finding_id, "F1")
        self.assertNotIn("[F1]", report.executive_summary)
        self.assertIn("Nothing else to report.", report.executive_summary)

    def test_tool_error_during_recompute_fails_verdict(self):
        findings = [Finding(id="F1", question="q", method="sql", query="SELECT bad", value=100.0, unit="USD")]
        draft = Draft(executive_summary="Value was $100.00 [F1].", sections=[])
        tools = _tools(sql_results={"SELECT bad": ToolError("no such table")})
        provider = MockProvider(completions=[])
        report = run_verifier(draft, _artifact(findings), tools, provider)
        self.assertFalse(report.verdicts[0].passed)
        self.assertIn("could not recompute", report.verdicts[0].reason)


class TestSemanticCheck(unittest.TestCase):
    def test_unfaithful_sentence_is_redacted_even_when_number_matches(self):
        findings = [Finding(id="F1", question="total revenue", method="sql", query="SELECT 1", value=100.0, unit="USD")]
        draft = Draft(
            executive_summary="Profit was $100.00 [F1]. The company is thriving.",
            sections=[],
        )
        tools = _tools(sql_results={"SELECT 1": {"columns": ["s"], "rows": [[100.0]], "row_count": 1, "truncated": False}})
        provider = MockProvider(completions=[json.dumps({
            "judgments": [{"finding_id": "F1", "faithful": False, "reason": "finding is revenue, not profit"}],
        })])
        report = run_verifier(draft, _artifact(findings), tools, provider)
        self.assertFalse(report.verdicts[0].passed)
        self.assertIn("profit", report.verdicts[0].reason.lower())
        self.assertNotIn("[F1]", report.executive_summary)
        self.assertIn("The company is thriving.", report.executive_summary)


class TestMultipleCitations(unittest.TestCase):
    def test_one_failing_citation_does_not_remove_a_passing_one(self):
        findings = [
            Finding(id="F1", question="q1", method="sql", query="SELECT 1", value=100.0, unit="USD"),
            Finding(id="F2", question="q2", method="sql", query="SELECT 2", value=8.4, unit="%"),
        ]
        draft = Draft(
            executive_summary="Revenue was $100.00 [F1]. Return rate was 8.4% [F2].",
            sections=[],
        )
        tools = _tools(sql_results={
            "SELECT 1": {"columns": ["s"], "rows": [[999.0]], "row_count": 1, "truncated": False},
            "SELECT 2": {"columns": ["s"], "rows": [[8.4]], "row_count": 1, "truncated": False},
        })
        provider = MockProvider(completions=[json.dumps({"judgments": [{"finding_id": "F2", "faithful": True}]})])
        report = run_verifier(draft, _artifact(findings), tools, provider)
        self.assertNotIn("[F1]", report.executive_summary)
        self.assertIn("[F2]", report.executive_summary)
        self.assertEqual(len(report.removed_claims), 1)
        self.assertEqual(report.removed_claims[0].finding_id, "F1")


class TestSections(unittest.TestCase):
    def test_section_emptied_by_redaction_is_dropped(self):
        findings = [Finding(id="F1", question="q", method="sql", query="SELECT 1", value=100.0, unit="USD")]
        draft = Draft(
            executive_summary="See sections below.",
            sections=[ReportSection(heading="Revenue", body="Revenue was $100.00 [F1].")],
        )
        tools = _tools(sql_results={"SELECT 1": {"columns": ["s"], "rows": [[999.0]], "row_count": 1, "truncated": False}})
        provider = MockProvider(completions=[])
        report = run_verifier(draft, _artifact(findings), tools, provider)
        self.assertEqual(report.sections, [])


class TestUnknownCitation(unittest.TestCase):
    def test_citation_to_id_not_in_artifact_raises(self):
        draft = Draft(executive_summary="Revenue was $100.00 [F1].", sections=[])
        provider = MockProvider(completions=[])
        with self.assertRaises(VerifierError):
            run_verifier(draft, _artifact([]), _tools(), provider)


class TestPythonMethod(unittest.TestCase):
    def test_recomputes_via_run_python(self):
        findings = [Finding(id="F1", question="q", method="python", query="result = 42", value=42, unit="orders")]
        draft = Draft(executive_summary="There were 42 orders [F1].", sections=[])
        tools = _tools(python_results={"result = 42": {"result": 42, "stdout": ""}})
        provider = MockProvider(completions=[json.dumps({"judgments": [{"finding_id": "F1", "faithful": True}]})])
        report = run_verifier(draft, _artifact(findings), tools, provider)
        self.assertTrue(report.verdicts[0].passed)


if __name__ == "__main__":
    unittest.main()
