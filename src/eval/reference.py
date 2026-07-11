"""Independent reference facts computed directly against the sample
dataset via hand-written SQL -- deliberately never reusing the pipeline's
own queries, so they're something the pipeline's output gets checked
against rather than checked with. Only meaningful against the fixed,
seeded sample dataset (src/generate_sample_data.py); that generator is
seeded specifically so these numbers can't drift between eval runs.
"""
import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ReferenceFact:
    name: str
    value: float | int | str
    description: str


def compute_reference_facts(db_path: Path) -> list[ReferenceFact]:
    conn = sqlite3.connect(db_path)
    try:
        revenue, completed_orders = conn.execute(
            "SELECT ROUND(SUM(quantity*unit_price),2), COUNT(*) FROM orders WHERE status='completed'"
        ).fetchone()
        returns_count = conn.execute("SELECT COUNT(*) FROM returns").fetchone()[0]
        return_rate = round(returns_count / completed_orders * 100, 2) if completed_orders else 0.0
        top_category, top_category_revenue = conn.execute(
            "SELECT p.category, ROUND(SUM(o.quantity*o.unit_price),2) AS revenue FROM orders o "
            "JOIN products p ON o.product_id = p.product_id WHERE o.status='completed' "
            "GROUP BY p.category ORDER BY revenue DESC LIMIT 1"
        ).fetchone()
        negative_qty_orders = conn.execute("SELECT COUNT(*) FROM orders WHERE quantity < 0").fetchone()[0]
    finally:
        conn.close()

    return [
        ReferenceFact("total_completed_revenue", revenue, "total revenue across completed orders"),
        ReferenceFact("completed_order_count", completed_orders, "count of completed orders"),
        ReferenceFact("return_rate_pct", return_rate, "returns as a percent of completed orders"),
        ReferenceFact("top_category_by_revenue", top_category, "product category with the highest completed-order revenue"),
        ReferenceFact("top_category_revenue", top_category_revenue, "completed-order revenue of the top category"),
        ReferenceFact("negative_quantity_order_count", negative_qty_orders, "orders with a negative quantity (bad-entry rows)"),
    ]
