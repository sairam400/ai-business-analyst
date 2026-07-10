import shutil
import tempfile
import unittest
from pathlib import Path

from src.csv_loader import load_directory
from src.generate_sample_data import generate
from src.run_context import RunContext
from src.tools import ToolError, build_tools, make_chart, run_python, run_sql


class TestRunSQL(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        generate(cls.tmp / "sample", seed=42)
        cls.db_path = cls.tmp / "test.db"
        load_directory(cls.tmp / "sample", cls.db_path)
        cls.ctx = RunContext(
            run_id="t1", db_path=cls.db_path,
            run_dir=cls.tmp / "run", charts_dir=cls.tmp / "run" / "charts", sandbox_dir=cls.tmp / "sandbox",
        )
        cls.ctx.charts_dir.mkdir(parents=True, exist_ok=True)
        cls.ctx.sandbox_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_select_works(self):
        result = run_sql("SELECT COUNT(*) FROM orders", self.ctx)
        self.assertEqual(result["rows"][0][0], 5000)

    def test_rejects_non_select(self):
        with self.assertRaises(ToolError):
            run_sql("UPDATE orders SET quantity = 0", self.ctx)

    def test_rejects_smuggled_mutation_after_semicolon(self):
        with self.assertRaises(ToolError):
            run_sql("SELECT 1; DROP TABLE orders", self.ctx)

    def test_rejects_smuggled_mutation_lowercase(self):
        with self.assertRaises(ToolError):
            run_sql("select * from orders; delete from orders", self.ctx)

    def test_bad_sql_raises_tool_error_not_crash(self):
        with self.assertRaises(ToolError):
            run_sql("SELECT * FROM not_a_real_table", self.ctx)


class TestRunPython(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.ctx = RunContext(
            run_id="t2", db_path=cls.tmp / "unused.db",
            run_dir=cls.tmp / "run", charts_dir=cls.tmp / "run" / "charts", sandbox_dir=cls.tmp / "sandbox",
        )
        cls.ctx.sandbox_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_computes_and_returns_result(self):
        out = run_python("result = sum(input_data)", self.ctx, input_data=[1, 2, 3, 4])
        self.assertEqual(out["result"], 10)

    def test_missing_result_variable_raises(self):
        with self.assertRaises(ToolError):
            run_python("x = 1", self.ctx)

    def test_network_access_is_blocked(self):
        code = (
            "import socket\n"
            "try:\n"
            "    socket.socket().connect(('example.com', 80))\n"
            "    result = 'reached network'\n"
            "except RuntimeError as e:\n"
            "    result = str(e)\n"
        )
        out = run_python(code, self.ctx)
        self.assertIn("disabled", out["result"])

    def test_syntax_error_raises_tool_error_with_stderr(self):
        with self.assertRaises(ToolError) as cm:
            run_python("this is not python(", self.ctx)
        self.assertIn("SyntaxError", str(cm.exception))


class TestMakeChart(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.ctx = RunContext(
            run_id="t3", db_path=cls.tmp / "unused.db",
            run_dir=cls.tmp / "run", charts_dir=cls.tmp / "run" / "charts", sandbox_dir=cls.tmp / "sandbox",
        )
        cls.ctx.charts_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_bar_chart_creates_png(self):
        out = make_chart("bar", "Revenue by category", ["A", "B", "C"], [{"name": "revenue", "values": [10, 20, 15]}], self.ctx)
        self.assertTrue(Path(out["path"]).exists())

    def test_line_chart_with_multiple_series_and_legend(self):
        out = make_chart(
            "line", "Orders over time", [1, 2, 3],
            [{"name": "2023", "values": [10, 12, 14]}, {"name": "2024", "values": [11, 15, 20]}],
            self.ctx,
        )
        self.assertTrue(Path(out["path"]).exists())

    def test_bar_rejects_multiple_series(self):
        with self.assertRaises(ToolError):
            make_chart("bar", "x", ["A"], [{"name": "a", "values": [1]}, {"name": "b", "values": [2]}], self.ctx)


class TestBuildTools(unittest.TestCase):
    def test_build_tools_wires_context(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            generate(tmp / "sample", seed=42)
            db_path = tmp / "test.db"
            load_directory(tmp / "sample", db_path)
            ctx = RunContext(
                run_id="t4", db_path=db_path,
                run_dir=tmp / "run", charts_dir=tmp / "run" / "charts", sandbox_dir=tmp / "sandbox",
            )
            ctx.charts_dir.mkdir(parents=True, exist_ok=True)
            ctx.sandbox_dir.mkdir(parents=True, exist_ok=True)
            tools = build_tools(ctx)
            result = tools["run_sql"](query="SELECT COUNT(*) FROM customers")
            self.assertEqual(result["rows"][0][0], 650)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
