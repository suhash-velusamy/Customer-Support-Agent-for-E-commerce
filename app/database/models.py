"""SQLite schema definitions."""

SCHEMA = """
CREATE TABLE IF NOT EXISTS customers (
    customer_id TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    email       TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS orders (
    order_id       TEXT PRIMARY KEY,
    customer_id    TEXT NOT NULL REFERENCES customers(customer_id),
    order_date     TEXT NOT NULL,
    status         TEXT NOT NULL CHECK (status IN
                   ('processing', 'shipped', 'delayed', 'delivered', 'cancelled')),
    total_amount   REAL NOT NULL,
    shipment_id    TEXT,
    payment_status TEXT NOT NULL CHECK (payment_status IN ('paid', 'refunded', 'partially_refunded')),
    refund_status  TEXT NOT NULL DEFAULT 'none' CHECK (refund_status IN
                   ('none', 'pending', 'processing', 'completed')),
    refund_requested_at TEXT
);

CREATE TABLE IF NOT EXISTS order_items (
    item_id      TEXT PRIMARY KEY,
    order_id     TEXT NOT NULL REFERENCES orders(order_id),
    product_id   TEXT NOT NULL,
    product_name TEXT NOT NULL,
    category     TEXT NOT NULL,
    quantity     INTEGER NOT NULL CHECK (quantity > 0),
    price        REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS shipments (
    shipment_id        TEXT PRIMARY KEY,
    order_id           TEXT NOT NULL UNIQUE REFERENCES orders(order_id),
    carrier            TEXT NOT NULL,
    tracking_number    TEXT NOT NULL,
    status             TEXT NOT NULL CHECK (status IN
                       ('label_created', 'in_transit', 'out_for_delivery', 'delayed', 'delivered')),
    location           TEXT,
    estimated_delivery TEXT,
    delivered_at       TEXT,
    last_update        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS returns (
    return_id  TEXT PRIMARY KEY,
    order_id   TEXT NOT NULL REFERENCES orders(order_id),
    item_id    TEXT NOT NULL REFERENCES order_items(item_id),
    reason     TEXT NOT NULL,
    status     TEXT NOT NULL CHECK (status IN ('requested', 'approved', 'received', 'refunded', 'rejected')),
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(customer_id);
CREATE INDEX IF NOT EXISTS idx_items_order ON order_items(order_id);
CREATE INDEX IF NOT EXISTS idx_returns_order ON returns(order_id);
"""
