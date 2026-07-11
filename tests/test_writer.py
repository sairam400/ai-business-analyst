import json
import unittest

from src.artifacts import AnalystArtifact, DatasetProfile, Finding
from src.pipeline.writer import (
    WriterError,
    _footnote_ids_in,
    _unfootnoted_metric_sentences,
    run_writer,
)
from src.providers.mock_provider import MockProvider

FINDINGS = [
    Finding(id="F1", question="total revenue", method="sql", query="SELECT SUM(...)", value=125430.55, unit="USD"),
    Finding(id="F2", question="return rate", method="sql", query="SELECT ...", value=8.4, unit="%"),
]


def _artifact():
    return AnalystArtifact(profile=DatasetProfile(tables=[]), findings=FINDINGS)


class TestFootnoteHelpers(unittest.TestCase):
    def test_extracts_footnote_ids(self):
        self.assertEqual(_footnote_ids_in("Revenue was $1,234 [F1] and returns were 8% [F2]."), {"F1", "F2"})

    def test_flags_sentence_with_metric_and_no_footnote(self):
        violations = _unfootnoted_metric_sentences("Revenue was $125,430.55. Return rate was 8.4% [F2].")
        self.assertEqual(len(violations), 1)
        self.assertIn("125,430.55", violations[0])

    def test_small_bare_integers_are_not_flagged(self):
        violations = _unfootnoted_metric_sentences("We analyzed 4 tables across 2 years.")
        self.assertEqual(violations, [])


class TestRunWriter(unittest.TestCase):
    def test_valid_draft_accepted_on_first_attempt(self):
        draft_json = json.dumps({
            "executive_summary": "Revenue reached $125,430.55 this period [F1], with an 8.4% return rate [F2].",
            "sections": [{"heading": "Revenue", "body": "Total revenue was $125,430.55 [F1]."}],
        })
        provider = MockProvider(completions=[draft_json])
        draft = run_writer(_artifact(), provider)
        self.assertIn("[F1]", draft.executive_summary)
        self.assertEqual(len(draft.sections), 1)

    def test_unknown_footnote_id_triggers_retry_then_succeeds(self):
        bad = json.dumps({
            "executive_summary": "Revenue was $125,430.55 [F99].",
            "sections": [{"heading": "Revenue", "body": "See summary [F1]."}],
        })
        good = json.dumps({
            "executive_summary": "Revenue was $125,430.55 [F1].",
            "sections": [{"heading": "Revenue", "body": "Return rate was 8.4% [F2]."}],
        })
        provider = MockProvider(completions=[bad, good])
        draft = run_writer(_artifact(), provider, max_attempts=2)
        self.assertIn("[F1]", draft.executive_summary)

    def test_unfootnoted_metric_triggers_retry(self):
        bad = json.dumps({
            "executive_summary": "Revenue was $125,430.55.",
            "sections": [{"heading": "Revenue", "body": "Return rate was 8.4% [F2]."}],
        })
        good = json.dumps({
            "executive_summary": "Revenue was $125,430.55 [F1].",
            "sections": [{"heading": "Revenue", "body": "Return rate was 8.4% [F2]."}],
        })
        provider = MockProvider(completions=[bad, good])
        draft = run_writer(_artifact(), provider, max_attempts=2)
        self.assertIn("[F1]", draft.executive_summary)

    def test_exhausting_attempts_raises_writer_error(self):
        bad = json.dumps({
            "executive_summary": "Revenue was $125,430.55 [F99].",
            "sections": [{"heading": "Revenue", "body": "See summary."}],
        })
        provider = MockProvider(completions=[bad, bad])
        with self.assertRaises(WriterError):
            run_writer(_artifact(), provider, max_attempts=2)

    def test_no_findings_produces_draft_without_fabricated_claims(self):
        clean = json.dumps({
            "executive_summary": "No analyses could be completed for this dataset.",
            "sections": [{"heading": "Notes", "body": "The uploaded data did not support any of the suggested analyses."}],
        })
        provider = MockProvider(completions=[clean])
        artifact = AnalystArtifact(profile=DatasetProfile(tables=[]), findings=[])
        draft = run_writer(artifact, provider)
        self.assertEqual(draft.sections[0].heading, "Notes")


if __name__ == "__main__":
    unittest.main()
