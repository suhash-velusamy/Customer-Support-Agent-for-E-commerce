"""Tests for the schema and deterministic seed data."""

from app.database.db import connect
from app.database.seed import seed


def _one(db, sql, *args):
    return db.execute(sql, args).fetchone()


def test_order_count_in_range(db):
    assert 50 <= _one(db, "SELECT COUNT(*) FROM orders")[0] <= 100


def test_seed_is_deterministic(tmp_path):
    dumps = []
    for name in ("a.db", "b.db"):
        conn = connect(tmp_path / name)
        seed(conn)
        dumps.append(list(conn.iterdump()))
        conn.close()
    assert dumps[0] == dumps[1]


def test_all_statuses_present(db):
    statuses = {r[0] for r in db.execute("SELECT DISTINCT status FROM orders")}
    assert statuses == {"processing", "shipped", "delayed", "delivered", "cancelled"}
    refunds = {r[0] for r in db.execute("SELECT DISTINCT refund_status FROM orders")}
    assert {"pending", "completed"} <= refunds


def test_spec_example_order_10245(db):
    order = _one(db, "SELECT * FROM orders WHERE order_id='10245'")
    assert order["customer_id"] == "CUST-001" and order["status"] == "delayed"
    ship = _one(db, "SELECT * FROM shipments WHERE order_id='10245'")
    assert ship["carrier"] == "Example Express" and ship["location"] == "Chennai"


def test_demo_customer_has_repeated_delays(db):
    n = _one(db, "SELECT COUNT(*) FROM orders o JOIN shipments s USING(order_id) "
                 "WHERE o.customer_id='CUST-001' "
                 "AND (s.status='delayed' OR s.delivered_at > s.estimated_delivery)")[0]
    assert n >= 3


def test_other_customer_order_exists_for_privacy_tests(db):
    assert _one(db, "SELECT customer_id FROM orders WHERE order_id='10300'")[0] == "CUST-002"


def test_return_scenarios(db):
    assert _one(db, "SELECT category FROM order_items WHERE order_id='10250'")[0] == "footwear"
    cats = {r[0] for r in db.execute("SELECT category FROM order_items WHERE order_id='10271'")}
    assert cats == {"swimwear", "gift_card"}
    assert _one(db, "SELECT refund_status FROM orders WHERE order_id='10260'")[0] == "pending"


def test_referential_integrity(db):
    assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    assert _one(db, "SELECT COUNT(*) FROM orders o LEFT JOIN order_items i USING(order_id) "
                    "WHERE i.item_id IS NULL")[0] == 0
    assert _one(db, "SELECT COUNT(*) FROM orders o LEFT JOIN shipments s ON s.shipment_id = o.shipment_id "
                    "WHERE o.shipment_id IS NOT NULL AND s.shipment_id IS NULL")[0] == 0
