"""Deterministic seed data.

All dates are relative to REFERENCE_DATE (not "today") so tests are reproducible.
Hand-written scenario orders come first; generated filler orders bring the total to TOTAL_ORDERS.
"""

import random
import sqlite3
from datetime import date, datetime, time, timedelta

from app.database.db import init_schema

REFERENCE_DATE = date(2026, 9, 28)
TOTAL_ORDERS = 80
SEED = 42

CUSTOMERS = [
    ("CUST-001", "Asha Raman", "asha.raman@example.com"),
    ("CUST-002", "Daniel Okafor", "daniel.okafor@example.com"),
    ("CUST-003", "Mei Lin", "mei.lin@example.com"),
    ("CUST-004", "Lucas Moreau", "lucas.moreau@example.com"),
    ("CUST-005", "Priya Nair", "priya.nair@example.com"),
    ("CUST-006", "Tom Becker", "tom.becker@example.com"),
    ("CUST-007", "Sofia Rossi", "sofia.rossi@example.com"),
    ("CUST-008", "Kenji Sato", "kenji.sato@example.com"),
    ("CUST-009", "Fatima Zahra", "fatima.zahra@example.com"),
    ("CUST-010", "Noah Williams", "noah.williams@example.com"),
]

# (product_id, name, category, price). Category drives policy eligibility later.
PRODUCTS = [
    ("P-100", "Trail Running Shoes", "footwear", 89.99),
    ("P-101", "Leather Sneakers", "footwear", 74.50),
    ("P-200", "Wireless Earbuds", "electronics", 59.99),
    ("P-201", "Smartwatch Series 3", "electronics", 199.00),
    ("P-202", "USB-C Charger 65W", "electronics", 34.99),
    ("P-300", "Cotton T-Shirt", "apparel", 19.99),
    ("P-301", "Denim Jacket", "apparel", 64.00),
    ("P-302", "Swimwear Set", "swimwear", 39.99),
    ("P-400", "Ceramic Mug Set", "home", 24.99),
    ("P-401", "Desk Lamp", "home", 42.00),
    ("P-500", "Digital Gift Card", "gift_card", 50.00),
    ("P-600", "Face Serum", "personal_care", 29.99),
    ("P-700", "Baby Stroller Lite", "baby", 249.00),
]
PRODUCT_BY_ID = {p[0]: p for p in PRODUCTS}

CARRIERS = {"Example Express": "EXX", "BlueDart": "BD", "FedEx": "FX", "DHL": "DH"}
CITIES = ["Chennai", "Mumbai", "Bengaluru", "Delhi", "Hyderabad", "Pune", "Kolkata"]

# Hand-crafted scenarios. days_ago is order age; shipment offsets are days relative to REFERENCE_DATE.
SCENARIOS = [
    # CUST-001 (demo customer): current delayed order plus two previously late deliveries
    dict(order_id="10245", customer="CUST-001", days_ago=12, status="delayed", items=[("P-201", 1)],
         shipment=dict(carrier="Example Express", status="delayed", location="Chennai", eta_offset=2)),
    dict(order_id="10231", customer="CUST-001", days_ago=40, status="delivered", items=[("P-300", 2)],
         shipment=dict(carrier="Example Express", status="delivered", location="Chennai",
                       eta_offset=-33, delivered_offset=-30)),
    dict(order_id="10238", customer="CUST-001", days_ago=25, status="delivered", items=[("P-400", 1)],
         shipment=dict(carrier="BlueDart", status="delivered", location="Chennai",
                       eta_offset=-19, delivered_offset=-15)),
    # Shoes bought last week, delivered: eligible return
    dict(order_id="10250", customer="CUST-001", days_ago=7, status="delivered", items=[("P-100", 1)],
         shipment=dict(carrier="FedEx", status="delivered", location="Chennai",
                       eta_offset=-3, delivered_offset=-3)),
    # Refund pending for 10 days
    dict(order_id="10260", customer="CUST-001", days_ago=30, status="delivered", items=[("P-301", 1)],
         shipment=dict(carrier="DHL", status="delivered", location="Chennai",
                       eta_offset=-25, delivered_offset=-25),
         refund=dict(status="pending", requested_days_ago=10),
         returns=[dict(return_id="RET-5001", status="received", reason="Wrong size", days_ago=12)]),
    # Completed refund
    dict(order_id="10261", customer="CUST-001", days_ago=45, status="delivered", items=[("P-202", 1)],
         shipment=dict(carrier="BlueDart", status="delivered", location="Chennai",
                       eta_offset=-40, delivered_offset=-40),
         refund=dict(status="completed", requested_days_ago=30), payment="refunded",
         returns=[dict(return_id="RET-5002", status="refunded", reason="Defective", days_ago=32)]),
    # Outside the return window
    dict(order_id="10270", customer="CUST-001", days_ago=65, status="delivered", items=[("P-101", 1)],
         shipment=dict(carrier="FedEx", status="delivered", location="Chennai",
                       eta_offset=-60, delivered_offset=-60)),
    # Non-returnable categories, recently delivered
    dict(order_id="10271", customer="CUST-001", days_ago=6, status="delivered",
         items=[("P-302", 1), ("P-500", 1)],
         shipment=dict(carrier="DHL", status="delivered", location="Chennai",
                       eta_offset=-2, delivered_offset=-2)),
    # Processing (no shipment yet), in transit, cancelled
    dict(order_id="10280", customer="CUST-001", days_ago=1, status="processing", items=[("P-401", 1)]),
    dict(order_id="10281", customer="CUST-001", days_ago=3, status="shipped", items=[("P-200", 1)],
         shipment=dict(carrier="BlueDart", status="in_transit", location="Bengaluru", eta_offset=2)),
    dict(order_id="10282", customer="CUST-001", days_ago=9, status="cancelled", items=[("P-700", 1)],
         refund=dict(status="completed", requested_days_ago=8), payment="refunded"),
    # Other customers' orders (privacy tests)
    dict(order_id="10300", customer="CUST-002", days_ago=5, status="shipped", items=[("P-201", 1)],
         shipment=dict(carrier="FedEx", status="in_transit", location="Mumbai", eta_offset=1)),
    dict(order_id="10301", customer="CUST-003", days_ago=14, status="delayed", items=[("P-100", 2)],
         shipment=dict(carrier="Example Express", status="delayed", location="Delhi", eta_offset=3)),
]


def _iso(d: date) -> str:
    return d.isoformat()


def _ts(d: date, hour: int = 9) -> str:
    return datetime.combine(d, time(hour, 0)).isoformat()


def _days(offset: int) -> date:
    return REFERENCE_DATE + timedelta(days=offset)


def _insert_order(conn: sqlite3.Connection, spec: dict, rng: random.Random) -> None:
    order_id = spec["order_id"]
    items = [(PRODUCT_BY_ID[pid], qty) for pid, qty in spec["items"]]
    total = round(sum(p[3] * qty for p, qty in items), 2)
    ship = spec.get("shipment")
    shipment_id = f"SHP-{order_id}" if ship else None
    refund = spec.get("refund")

    conn.execute(
        "INSERT INTO orders VALUES (?,?,?,?,?,?,?,?,?)",
        (
            order_id, spec["customer"], _iso(_days(-spec["days_ago"])), spec["status"], total, shipment_id,
            spec.get("payment", "paid"),
            refund["status"] if refund else "none",
            _iso(_days(-refund["requested_days_ago"])) if refund else None,
        ),
    )
    for n, (product, qty) in enumerate(items, start=1):
        conn.execute(
            "INSERT INTO order_items VALUES (?,?,?,?,?,?,?)",
            (f"{order_id}-{n}", order_id, product[0], product[1], product[2], qty, product[3]),
        )
    if ship:
        delivered = ship.get("delivered_offset")
        conn.execute(
            "INSERT INTO shipments VALUES (?,?,?,?,?,?,?,?,?)",
            (
                shipment_id, order_id, ship["carrier"],
                f"{CARRIERS[ship['carrier']]}{rng.randint(10**9, 10**10 - 1)}",
                ship["status"], ship["location"],
                _iso(_days(ship["eta_offset"])),
                _iso(_days(delivered)) if delivered is not None else None,
                _ts(_days(delivered if delivered is not None else 0), hour=rng.randint(7, 20)),
            ),
        )
    for r in spec.get("returns", []):
        conn.execute(
            "INSERT INTO returns VALUES (?,?,?,?,?,?)",
            (r["return_id"], order_id, f"{order_id}-1", r["reason"], r["status"], _ts(_days(-r["days_ago"]))),
        )


def _generated_specs(rng: random.Random, count: int) -> list[dict]:
    """Filler orders for other customers with a realistic status mix."""
    statuses = ["delivered"] * 5 + ["shipped"] * 2 + ["processing", "delayed", "cancelled"]
    other_customers = [c[0] for c in CUSTOMERS[1:]]
    specs = []
    for i in range(count):
        status = rng.choice(statuses)
        days_ago = {
            "processing": rng.randint(0, 2),
            "shipped": rng.randint(2, 5),
            "delayed": rng.randint(8, 15),
            "cancelled": rng.randint(3, 30),
        }.get(status, rng.randint(5, 90))
        items = [(p[0], rng.randint(1, 2)) for p in rng.sample(PRODUCTS, rng.randint(1, 3))]
        spec = dict(order_id=str(10400 + i), customer=rng.choice(other_customers),
                    days_ago=days_ago, status=status, items=items)
        carrier = rng.choice(list(CARRIERS))
        city = rng.choice(CITIES)
        if status == "delivered":
            offset = min(-days_ago + rng.randint(2, 5), 0)
            spec["shipment"] = dict(carrier=carrier, status="delivered", location=city,
                                    eta_offset=offset, delivered_offset=offset)
            if rng.random() < 0.15:
                refund_status = rng.choice(["pending", "completed"])
                spec["refund"] = dict(status=refund_status, requested_days_ago=rng.randint(1, max(1, -offset)))
                spec["payment"] = "refunded" if refund_status == "completed" else "paid"
        elif status == "shipped":
            spec["shipment"] = dict(carrier=carrier, status=rng.choice(["in_transit", "out_for_delivery"]),
                                    location=city, eta_offset=rng.randint(0, 3))
        elif status == "delayed":
            spec["shipment"] = dict(carrier=carrier, status="delayed", location=city, eta_offset=rng.randint(1, 4))
        elif status == "cancelled":
            spec["refund"] = dict(status="completed", requested_days_ago=max(0, days_ago - 1))
            spec["payment"] = "refunded"
        specs.append(spec)
    return specs


def seed(conn: sqlite3.Connection) -> dict[str, int]:
    """Drop and recreate all tables, then insert deterministic seed data. Returns row counts."""
    rng = random.Random(SEED)
    conn.executescript(
        "DROP TABLE IF EXISTS returns; DROP TABLE IF EXISTS shipments; "
        "DROP TABLE IF EXISTS order_items; DROP TABLE IF EXISTS orders; DROP TABLE IF EXISTS customers;"
    )
    init_schema(conn)
    conn.executemany("INSERT INTO customers VALUES (?,?,?)", CUSTOMERS)
    for spec in SCENARIOS + _generated_specs(rng, TOTAL_ORDERS - len(SCENARIOS)):
        _insert_order(conn, spec, rng)
    conn.commit()
    tables = ("customers", "orders", "order_items", "shipments", "returns")
    return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}
