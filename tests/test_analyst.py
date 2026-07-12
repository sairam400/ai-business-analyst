import json
import shutil
import tempfile
import unittest
from pathlib import Path

from src.artifacts import DatasetProfile
from src.config import SETTINGS
from src.csv_loader import load_directory
from src.generate_sample_data import generate
from src.pipeline.analyst import AnalystError, run_analysis_task, run_analyst
from src.providers.mock_provider import MockProvider
from src.run_context import RunContext
from src.tools import build_tools


class TestAnalyst(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        generate(self.tmp / "sample", seed=42)
        db_path = self.tmp / "sample.db"
        load_directory(self.tmp / "sample", db_path)
        self.ctx = RunContext(run_id="a1", db_path=db_path, run_dir=self.tmp / "run", charts_dir=self.tmp / "run" / "charts", sandbox_dir=self.tmp / "sandbox")
        self.ctx.charts_dir.mkdir(parents=True, exist_ok=True)
        self.ctx.sandbox_dir.mkdir(parents=True, exist_ok=True)
        self.tools = build_tools(self.ctx)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_task_completes_after_one_sql_call(self):
        plan = [
            {"type": "tool_call", "id": "c1", "name": "run_sql", "args": {"query": "SELECT COUNT(*) FROM orders"}},
            {"type": "final", "text": '{"question": "how many orders", "method": "sql", "query": "SELECT COUNT(*) FROM orders", "value": 5000, "unit": "orders"}'},
        ]
        provider = MockProvider(plan=plan)
        finding = run_analysis_task("count orders", provider, self.tools)
        self.assertEqual(finding["value"], 5000)
        self.assertEqual(finding["method"], "sql")

    def test_final_json_wrapped_in_markdown_fence_is_parsed(self):
        plan = [{"type": "final", "text": '```json\n{"question": "q", "method": "sql", "query": "SELECT 1", "value": 1}\n```'}]
        provider = MockProvider(plan=plan)
        finding = run_analysis_task("trivial", provider, self.tools)
        self.assertEqual(finding["value"], 1)

    def test_bad_final_json_raises_analyst_error(self):
        provider = MockProvider(plan=[{"type": "final", "text": "not json"}])
        with self.assertRaises(AnalystError):
            run_analysis_task("trivial", provider, self.tools)

    def test_tool_error_is_fed_back_and_task_can_recover(self):
        plan = [
            {"type": "tool_call", "id": "c1", "name": "run_sql", "args": {"query": "SELECT * FROM not_a_table"}},
            {"type": "tool_call", "id": "c2", "name": "run_sql", "args": {"query": "SELECT COUNT(*) FROM orders"}},
            {"type": "final", "text": '{"question": "q", "method": "sql", "query": "SELECT COUNT(*) FROM orders", "value": 5000}'},
        ]
        provider = MockProvider(plan=plan)
        finding = run_analysis_task("recover from bad query", provider, self.tools)
        self.assertEqual(finding["value"], 5000)

    def test_hard_stop_after_max_consecutive_errors(self):
        original = SETTINGS.max_consecutive_errors
        SETTINGS.max_consecutive_errors = 2
        try:
            plan = [
                {"type": "tool_call", "id": "c1", "name": "run_sql", "args": {"query": "SELECT * FROM nope"}},
                {"type": "tool_call", "id": "c2", "name": "run_sql", "args": {"query": "SELECT * FROM nope"}},
            ]
            provider = MockProvider(plan=plan)
            with self.assertRaises(AnalystError):
                run_analysis_task("always fails", provider, self.tools)
        finally:
            SETTINGS.max_consecutive_errors = original

    def test_hard_stop_after_max_steps_without_finalizing(self):
        original = SETTINGS.max_steps
        SETTINGS.max_steps = 3
        try:
            plan = [{"type": "tool_call", "id": f"c{i}", "name": "run_sql", "args": {"query": "SELECT 1"}} for i in range(5)]
            provider = MockProvider(plan=plan)
            with self.assertRaises(AnalystError):
                run_analysis_task("never finalizes", provider, self.tools)
        finally:
            SETTINGS.max_steps = original

    def test_run_analyst_collects_findings_and_failures(self):
        profile = DatasetProfile(tables=[], suggested_analyses=["count orders", "will fail"])
        plan = [
            {"type": "tool_call", "id": "c1", "name": "run_sql", "args": {"query": "SELECT COUNT(*) FROM orders"}},
            {"type": "final", "text": '{"question": "count orders", "method": "sql", "query": "SELECT COUNT(*) FROM orders", "value": 5000}'},
            {"type": "final", "text": "not valid json"},
        ]
        provider = MockProvider(plan=plan)
        artifact = run_analyst(profile, provider, self.tools)
        self.assertEqual(len(artifact.findings), 1)
        self.assertEqual(artifact.findings[0].id, "F1")
        self.assertEqual(len(artifact.failed_tasks), 1)

    def test_final_value_that_is_a_list_fails_task_not_whole_run(self):
        profile = DatasetProfile(tables=[], suggested_analyses=["top 10 products"])
        plan = [{"type": "final", "text": json.dumps({
            "question": "top 10 products", "method": "sql", "query": "SELECT * FROM x",
            "value": [{"product_id": "P1", "revenue": 100}, {"product_id": "P2", "revenue": 90}],
        })}]
        provider = MockProvider(plan=plan)
        artifact = run_analyst(profile, provider, self.tools)
        self.assertEqual(artifact.findings, [])
        self.assertEqual(len(artifact.failed_tasks), 1)


if __name__ == "__main__":
    unittest.main()
