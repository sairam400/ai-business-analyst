"""Generates a deterministic, realistic e-commerce dataset (customers,
products, orders, returns) so the demo works with zero user effort.

Seeded on purpose: eval ground truth is computed by independent reference
queries against this exact data, so the numbers can't drift between runs.

Includes intentional imperfections a real export would have -- a few missing
emails/regions, a handful of bad-entry negative quantities, and one seeded
category/month demand anomaly -- so the profiler and analyst have something
real to notice instead of a spotless toy table.
"""
import csv
import datetime
import random
from pathlib import Path

SEED = 42

CATEGORIES = {
    "Electronics": ["Wireless Earbuds", "Bluetooth Speaker", "Laptop Stand", "USB-C Hub", "Webcam", "Power Bank"],
    "Home & Kitchen": ["Ceramic Mug Set", "Cast Iron Skillet", "Knife Block", "Air Fryer", "Throw Blanket", "Cutting Board"],
    "Apparel": ["Cotton T-Shirt", "Fleece Hoodie", "Running Shorts", "Wool Socks", "Denim Jacket", "Rain Jacket"],
    "Sports & Outdoors": ["Yoga Mat", "Hiking Backpack", "Water Bottle", "Camping Tent", "Resistance Bands", "Bike Helmet"],
    "Beauty": ["Facial Cleanser", "Vitamin C Serum", "Hair Dryer", "Body Lotion", "Lip Balm Set", "Makeup Brush Set"],
    "Toys & Games": ["Board Game", "Puzzle 1000pc", "Building Blocks", "RC Car", "Card Game Deck", "Plush Animal"],
    "Office Supplies": ["Notebook 3-Pack", "Desk Organizer", "Ergonomic Mouse", "Standing Desk Mat", "Pen Set", "Whiteboard"],
    "Grocery": ["Organic Coffee Beans", "Trail Mix", "Olive Oil", "Green Tea Box", "Protein Powder", "Granola Bars"],
}

FIRST_NAMES = ["James", "Maria", "Robert", "Linda", "Michael", "Patricia", "David", "Jennifer", "William", "Elizabeth",
               "Carlos", "Aisha", "Wei", "Fatima", "Noah", "Olivia", "Liam", "Sophia", "Ethan", "Ava",
               "Priya", "Jamal", "Anna", "Lucas", "Mia", "Yuki", "Omar", "Grace", "Diego", "Chen"]
LAST_NAMES = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez",
              "Lee", "Walker", "Hall", "Allen", "Young", "King", "Wright", "Scott", "Torres", "Nguyen",
              "Patel", "Kim", "Ali", "Chen", "Wang", "Kumar", "Silva", "Cohen", "Muller", "Rossi"]
REGIONS = ["Northeast", "Southeast", "Midwest", "Southwest", "West"]
CHANNELS = ["web", "mobile", "marketplace", "phone"]
RETURN_REASONS = ["defective", "wrong item shipped", "no longer needed", "damaged in transit", "other"]

START_DATE = datetime.date(2023, 1, 1)
END_DATE = datetime.date(2024, 12, 31)
TOTAL_DAYS = (END_DATE - START_DATE).days

N_CUSTOMERS = 650
N_PRODUCTS = 220
N_ORDERS = 5000

ANOMALY_CATEGORY = "Electronics"
ANOMALY_MONTH = datetime.date(2024, 3, 1)
ANOMALY_MULTIPLIER = 3.2


def _random_date(rng: random.Random, start: datetime.date, end: datetime.date) -> datetime.date:
    span = (end - start).days
    return start + datetime.timedelta(days=rng.randint(0, max(span, 0)))


def _seasonal_weight(day: datetime.date) -> float:
    trend = 1.0 + 0.15 * ((day - START_DATE).days / TOTAL_DAYS)
    holiday = 1.6 if day.month in (11, 12) else 1.0
    summer_dip = 0.85 if day.month in (6, 7) else 1.0
    return trend * holiday * summer_dip


def generate_customers(rng: random.Random):
    rows = []
    for i in range(1, N_CUSTOMERS + 1):
        first = rng.choice(FIRST_NAMES)
        last = rng.choice(LAST_NAMES)
        customer_id = f"C{i:05d}"
        email = f"{first.lower()}.{last.lower()}{i}@example.com"
        if rng.random() < 0.03:
            email = ""
        region = rng.choice(REGIONS)
        if rng.random() < 0.02:
            region = ""
        signup = _random_date(rng, START_DATE - datetime.timedelta(days=365), END_DATE)
        rows.append({
            "customer_id": customer_id,
            "first_name": first,
            "last_name": last,
            "email": email,
            "region": region,
            "signup_date": signup.isoformat(),
        })
    return rows


def generate_products(rng: random.Random):
    rows = []
    pid = 1
    for category, names in CATEGORIES.items():
        for _ in range(N_PRODUCTS // len(CATEGORIES)):
            name = rng.choice(names)
            variant = rng.choice(["Standard", "Pro", "Mini", "XL", "Classic", "V2"])
            cost = round(rng.uniform(4.0, 120.0), 2)
            markup = rng.uniform(1.4, 2.3)
            price = round(cost * markup, 2)
            rows.append({
                "product_id": f"P{pid:05d}",
                "name": f"{variant} {name}",
                "category": category,
                "unit_cost": cost,
                "unit_price": price,
            })
            pid += 1
    return rows


def generate_orders(rng: random.Random, customers, products):
    customer_ids = [c["customer_id"] for c in customers]
    by_category = {}
    for p in products:
        by_category.setdefault(p["category"], []).append(p)

    days = [START_DATE + datetime.timedelta(days=d) for d in range(TOTAL_DAYS + 1)]
    weights = [_seasonal_weight(d) for d in days]

    rows = []
    order_id = 1
    while len(rows) < N_ORDERS:
        day = rng.choices(days, weights=weights, k=1)[0]
        category = rng.choice(list(by_category.keys()))
        weight = 1.0
        if category == ANOMALY_CATEGORY and day.month == ANOMALY_MONTH.month and day.year == ANOMALY_MONTH.year:
            weight = ANOMALY_MULTIPLIER
        if rng.random() > min(weight, 1.0) and weight <= 1.0:
            continue
        product = rng.choice(by_category[category])
        quantity = rng.choices([1, 2, 3, 4, 5], weights=[45, 25, 15, 10, 5])[0]
        if rng.random() < 0.001:
            quantity = -quantity
        price_variation = rng.uniform(0.92, 1.05)
        unit_price = round(product["unit_price"] * price_variation, 2)
        status = "cancelled" if rng.random() < 0.03 else "completed"
        rows.append({
            "order_id": f"O{order_id:06d}",
            "customer_id": rng.choice(customer_ids),
            "product_id": product["product_id"],
            "order_date": day.isoformat(),
            "quantity": quantity,
            "unit_price": unit_price,
            "channel": rng.choice(CHANNELS),
            "status": status,
        })
        order_id += 1
        if weight > 1.0:
            # give the anomaly month extra draws so the spike actually lands
            for _ in range(int(weight) - 1):
                if len(rows) >= N_ORDERS:
                    break
                rows.append({
                    "order_id": f"O{order_id:06d}",
                    "customer_id": rng.choice(customer_ids),
                    "product_id": product["product_id"],
                    "order_date": day.isoformat(),
                    "quantity": rng.choices([1, 2, 3, 4, 5], weights=[45, 25, 15, 10, 5])[0],
                    "unit_price": unit_price,
                    "channel": rng.choice(CHANNELS),
                    "status": status,
                })
                order_id += 1
    return rows[:N_ORDERS]


def generate_returns(rng: random.Random, orders):
    rows = []
    return_id = 1
    for order in orders:
        if order["status"] != "completed" or order["quantity"] <= 0:
            continue
        if rng.random() >= 0.09:
            continue
        order_date = datetime.date.fromisoformat(order["order_date"])
        return_date = order_date + datetime.timedelta(days=rng.randint(1, 30))
        if return_date > END_DATE:
            continue
        order_value = round(order["quantity"] * order["unit_price"], 2)
        refund = order_value if rng.random() >= 0.2 else round(order_value * rng.uniform(0.5, 0.9), 2)
        rows.append({
            "return_id": f"R{return_id:05d}",
            "order_id": order["order_id"],
            "return_date": return_date.isoformat(),
            "reason": rng.choice(RETURN_REASONS),
            "refund_amount": refund,
        })
        return_id += 1
    return rows


def _write_csv(path: Path, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def generate(out_dir: Path, seed: int = SEED) -> dict[str, int]:
    rng = random.Random(seed)
    customers = generate_customers(rng)
    products = generate_products(rng)
    orders = generate_orders(rng, customers, products)
    returns = generate_returns(rng, orders)

    _write_csv(out_dir / "customers.csv", customers)
    _write_csv(out_dir / "products.csv", products)
    _write_csv(out_dir / "orders.csv", orders)
    _write_csv(out_dir / "returns.csv", returns)

    return {"customers": len(customers), "products": len(products), "orders": len(orders), "returns": len(returns)}


if __name__ == "__main__":
    from src.config import SETTINGS
    counts = generate(SETTINGS.sample_data_dir)
    print(f"wrote sample data to {SETTINGS.sample_data_dir}: {counts}")
