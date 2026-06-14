"""Shared pytest fixtures and test helpers.

The ``setup_test_data`` fixture (session-scoped, autouse) creates a pair of
minimal SQLite databases in a temporary directory and points the app at that
directory via the QUERIOUS_DATA_DIR environment variable before any test runs.
This keeps tests hermetic and avoids touching any data/ directory in the repo.
"""

import json
import os
import sqlite3
from unittest.mock import MagicMock

import pytest

# Load .env so live acceptance tests (which need ANTHROPIC_API_KEY / VOYAGE_API_KEY)
# can see the keys at collection time. No-op if python-dotenv or .env is absent.
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


# ---------------------------------------------------------------------------
# SSE helpers
# ---------------------------------------------------------------------------

def _parse_sse(raw: str) -> list[dict]:
    """Parse raw SSE text into a list of ``{"type": ..., "data": ...}`` dicts.

    Handles both LF-only and CRLF line endings (sse-starlette emits CRLF).
    """
    # Normalise to LF so the rest of the logic is uniform.
    normalised = raw.replace("\r\n", "\n")
    events: list[dict] = []
    for block in normalised.split("\n\n"):
        event_type: str | None = None
        data = None
        for line in block.strip().splitlines():
            if line.startswith("event:"):
                event_type = line[len("event:"):].strip()
            elif line.startswith("data:"):
                raw_data = line[len("data:"):].strip()
                try:
                    data = json.loads(raw_data)
                except json.JSONDecodeError:
                    data = raw_data
        if event_type is not None:
            events.append({"type": event_type, "data": data})
    return events


# ---------------------------------------------------------------------------
# Mock factory helpers
# ---------------------------------------------------------------------------

def _text_block(text: str) -> MagicMock:
    b = MagicMock()
    b.type = "text"
    b.text = text
    return b


def _tool_block(name: str, input_data: dict, tool_id: str) -> MagicMock:
    b = MagicMock()
    b.type = "tool_use"
    b.id = tool_id
    b.name = name
    b.input = input_data
    return b


def _resp(blocks: list, stop_reason: str) -> MagicMock:
    r = MagicMock()
    r.content = blocks
    r.stop_reason = stop_reason
    return r

# ---------------------------------------------------------------------------
# Minimal schema (mirrors SPEC §3, trimmed to what the tests exercise)
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """\
CREATE TABLE customers (
    id          INTEGER PRIMARY KEY,
    name        TEXT    NOT NULL,
    email       TEXT    UNIQUE NOT NULL,
    phone       TEXT,
    city        TEXT,
    state       TEXT,
    signup_date TEXT,
    tier        TEXT    DEFAULT 'standard'
);

CREATE TABLE users (
    id          INTEGER PRIMARY KEY,
    name        TEXT    NOT NULL,
    email       TEXT    UNIQUE NOT NULL,
    department  TEXT,
    role        TEXT,
    hire_date   TEXT,
    is_active   INTEGER DEFAULT 1
);

CREATE TABLE products (
    id               INTEGER PRIMARY KEY,
    sku              TEXT UNIQUE NOT NULL,
    name             TEXT NOT NULL,
    category         TEXT,
    price            REAL,
    cost             REAL,
    stock_qty        INTEGER DEFAULT 0,
    is_discontinued  INTEGER DEFAULT 0
);

CREATE TABLE orders (
    id           INTEGER PRIMARY KEY,
    customer_id  INTEGER REFERENCES customers(id),
    order_date   TEXT,
    status       TEXT DEFAULT 'pending',
    sales_rep_id INTEGER REFERENCES users(id)
);

CREATE TABLE order_items (
    id          INTEGER PRIMARY KEY,
    order_id    INTEGER REFERENCES orders(id),
    product_id  INTEGER REFERENCES products(id),
    quantity    INTEGER DEFAULT 1,
    unit_price  REAL
);

CREATE TABLE invoices (
    id             INTEGER PRIMARY KEY,
    order_id       INTEGER UNIQUE REFERENCES orders(id),
    invoice_number TEXT,
    issue_date     TEXT,
    due_date       TEXT,
    amount         REAL,
    status         TEXT DEFAULT 'draft'
);

CREATE TABLE payments (
    id           INTEGER PRIMARY KEY,
    invoice_id   INTEGER REFERENCES invoices(id),
    payment_date TEXT,
    amount       REAL,
    method       TEXT
);

CREATE TABLE support_tickets (
    id          INTEGER PRIMARY KEY,
    customer_id INTEGER REFERENCES customers(id),
    order_id    INTEGER REFERENCES orders(id),
    assigned_to INTEGER REFERENCES users(id),
    created_at  TEXT,
    subject     TEXT,
    status      TEXT DEFAULT 'open',
    priority    TEXT DEFAULT 'medium'
);
"""

_SEED_SQL = """\
INSERT INTO customers (id, name, email, state, tier) VALUES
    (1, 'Alice Smith',  'alice@example.com', 'CA', 'premium'),
    (2, 'Bob Jones',    'bob@example.com',   'TX', 'standard'),
    (3, 'Carol White',  'carol@example.com', 'CA', 'enterprise');

INSERT INTO users (id, name, email, department, role) VALUES
    (1, 'Dave Brown', 'dave@acmeoutfitters.example', 'Sales',   'Sales Rep'),
    (2, 'Eve Green',  'eve@acmeoutfitters.example',  'Support', 'Support Agent');

INSERT INTO products (id, sku, name, category, price, cost, stock_qty) VALUES
    (1, 'ACM-TENT-001', 'Trail Tent 2P',   'Camping', 299.99, 120.00, 50),
    (2, 'ACM-PACK-001', 'Summit Pack 40L', 'Hiking',  189.99,  75.00, 30);

INSERT INTO orders (id, customer_id, order_date, status) VALUES
    (1, 1, '2024-01-15 10:00:00', 'delivered'),
    (2, 2, '2024-02-20 14:30:00', 'shipped'),
    (3, 3, '2024-03-10 09:15:00', 'pending');

INSERT INTO order_items (id, order_id, product_id, quantity, unit_price) VALUES
    (1, 1, 1, 1, 299.99),
    (2, 2, 2, 1, 189.99),
    (3, 3, 1, 2, 299.99);

INSERT INTO invoices (id, order_id, invoice_number, issue_date, due_date, amount, status) VALUES
    (1, 1, 'INV-2024-00001', '2024-01-15', '2024-02-14', 299.99, 'paid'),
    (2, 2, 'INV-2024-00002', '2024-02-20', '2024-03-21', 189.99, 'sent'),
    (3, 3, 'INV-2024-00003', '2024-03-10', '2024-04-09', 599.98, 'overdue');

INSERT INTO payments (id, invoice_id, payment_date, amount, method) VALUES
    (1, 1, '2024-01-20', 299.99, 'card');

INSERT INTO support_tickets (id, customer_id, subject, status, priority) VALUES
    (1, 1, 'Order not received', 'open',     'high'),
    (2, 2, 'Wrong item shipped', 'resolved', 'medium');
"""


@pytest.fixture(scope="session", autouse=True)
def setup_test_data(tmp_path_factory):
    """Create minimal test DBs in a temp dir and configure QUERIOUS_DATA_DIR."""
    tmp_dir = tmp_path_factory.mktemp("querious_data")

    # Point the app at this temp directory for the entire test session.
    os.environ["QUERIOUS_DATA_DIR"] = str(tmp_dir)

    # acme.db — relational data
    acme_path = tmp_dir / "acme.db"
    conn = sqlite3.connect(str(acme_path))
    conn.executescript(_SCHEMA_SQL + _SEED_SQL)
    conn.commit()
    conn.close()

    # embeddings.db — just needs to exist for the health check
    emb_path = tmp_dir / "embeddings.db"
    conn = sqlite3.connect(str(emb_path))
    conn.close()

    yield str(tmp_dir)

    os.environ.pop("QUERIOUS_DATA_DIR", None)
