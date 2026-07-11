import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

from src.csv_loader import load_directory
from src.generate_sample_data import generate
from src.pipeline.profiler import (
    _deterministic_quality_notes,
    _detect_relationships,
    _profile_table,
    profile_dataset,
)
from src.providers.mock_provider import MockProvider
from src.run_context import RunContext
from src.tools import build_tools


def _make_tools_over(tmp: Path, db_name: str) -> dict:
    db_path = tmp / db_name
    ctx = RunContext(run_id="p1", db_path=db_path, run_dir=tmp / "run", charts_dir=tmp / "run" / "charts", sandbox_dir=tmp / "sandbox")
    ctx.charts_dir.mkdir(parents=True, exist_ok=True)
    ctx.sandbox_dir.mkdir(parents=True, exist_ok=True)
    return build_tools(ctx), db_path


class TestProfilerOnCraftedTable(unittest.TestCase):
    """Deterministic checks against a hand-built table, so the assertions
    don't depend on the sample generator's randomness."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.tools, self.db_path = _make_tools_over(self.tmp, "crafted.db")
        conn = sqlite3.connect(self.db_path)
        conn.execute("CREATE TABLE widgets (widget_id INTEGER, name TEXT, qty INTEGER, region TEXT)")
        conn.executemany(
            "INSERT INTO widgets VALUES (?, ?, ?, ?)",
            [(1, "a", 5, "east"), (2, "b", -3, "west"), (3, "c", 7, None), (4, "d", -1, None), (5, "e", 2, None)],
        )
        conn.execute("CREATE TABLE widget_orders (order_id INTEGER, widget_id INTEGER)")
        conn.executemany("INSERT INTO widget_orders VALUES (?, ?)", [(1, 1), (2, 2)])
        conn.commit()
        conn.close()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_profile_table_stats(self):
        profile = _profile_table("widgets", self.tools)
        self.assertEqual(profile.row_count, 5)
        qty_col = next(c for c in profile.columns if c.name == "qty")
        self.assertEqual(qty_col.sql_type, "integer")
        self.assertEqual(qty_col.null_count, 0)
        region_col = next(c for c in profile.columns if c.name == "region")
        self.assertEqual(region_col.null_count, 3)
        self.assertAlmostEqual(region_col.null_pct, 0.6)
        widget_id_col = next(c for c in profile.columns if c.name == "widget_id")
        self.assertTrue(widget_id_col.is_id_like)

    def test_detect_relationships(self):
        widgets = _profile_table("widgets", self.tools)
        orders = _profile_table("widget_orders", self.tools)
        relationships = _detect_relationships([widgets, orders])
        self.assertIn("widget_orders.widget_id -> widgets.widget_id", relationships)

    def test_negative_values_flagged(self):
        widgets = _profile_table("widgets", self.tools)
        notes = _deterministic_quality_notes([widgets], self.tools)
        self.assertTrue(any("qty" in n and "negative" in n for n in notes))

    def test_high_null_column_flagged(self):
        widgets = _profile_table("widgets", self.tools)
        notes = _deterministic_quality_notes([widgets], self.tools)
        self.assertTrue(any("region" in n and "missing" in n for n in notes))


class TestProfileDatasetOnSampleData(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        generate(self.tmp / "sample", seed=42)
        self.tools, self.db_path = _make_tools_over(self.tmp, "sample.db")
        load_directory(self.tmp / "sample", self.db_path)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_profile_dataset_end_to_end_with_mock_llm(self):
        provider = MockProvider(completions=[
            '{"suggested_analyses": ["monthly revenue trend", "top products by revenue"], '
            '"data_quality_notes": ["a few order dates look duplicated"]}'
        ])
        profile = profile_dataset(self.tools, provider)
        table_names = {t.name for t in profile.tables}
        self.assertEqual(table_names, {"customers", "products", "orders", "returns"})
        self.assertEqual(sorted(profile.detected_relationships), sorted([
            "orders.customer_id -> customers.customer_id",
            "orders.product_id -> products.product_id",
            "returns.order_id -> orders.order_id",
        ]))
        self.assertEqual(profile.suggested_analyses, ["monthly revenue trend", "top products by revenue"])
        self.assertIn("a few order dates look duplicated", profile.data_quality_notes)


if __name__ == "__main__":
    unittest.main()
