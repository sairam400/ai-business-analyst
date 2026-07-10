import sqlite3
import tempfile
import unittest
from pathlib import Path

from src.csv_loader import load_directory
from src.generate_sample_data import generate


class TestSampleData(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.counts = generate(self.tmp, seed=42)

    def test_row_counts_match_across_generators_with_same_seed(self):
        again = generate(self.tmp / "again", seed=42)
        self.assertEqual(self.counts, again)

    def test_generates_all_four_tables_with_expected_scale(self):
        self.assertEqual(self.counts["customers"], 650)
        self.assertEqual(self.counts["products"], 216)
        self.assertEqual(self.counts["orders"], 5000)
        self.assertGreater(self.counts["returns"], 300)

    def test_referential_integrity(self):
        import csv

        def read(name):
            with (self.tmp / name).open(newline="", encoding="utf-8") as f:
                return list(csv.DictReader(f))

        customer_ids = {r["customer_id"] for r in read("customers.csv")}
        product_ids = {r["product_id"] for r in read("products.csv")}
        order_ids = set()
        for row in read("orders.csv"):
            order_ids.add(row["order_id"])
            self.assertIn(row["customer_id"], customer_ids)
            self.assertIn(row["product_id"], product_ids)
        for row in read("returns.csv"):
            self.assertIn(row["order_id"], order_ids)

    def test_load_directory_into_sqlite(self):
        db_path = self.tmp / "test.db"
        row_counts = load_directory(self.tmp, db_path)
        self.assertEqual(row_counts["orders"], 5000)
        conn = sqlite3.connect(db_path)
        try:
            actual = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
            self.assertEqual(actual, 5000)
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertEqual(tables, {"customers", "products", "orders", "returns"})
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
