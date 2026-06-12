"""Create the acme.db schema and populate it via the Faker seeder."""

import os
import sys
import sqlite3

# Allow `from data.seed import seed` when run from the project root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DB_PATH = "data/acme.db"

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS customers (
    id          INTEGER PRIMARY KEY,
    name        TEXT    NOT NULL,
    email       TEXT    NOT NULL UNIQUE,
    phone       TEXT,
    city        TEXT,
    state       TEXT,
    signup_date TEXT,
    tier        TEXT
);

CREATE TABLE IF NOT EXISTS users (
    id         INTEGER PRIMARY KEY,
    name       TEXT    NOT NULL,
    email      TEXT    NOT NULL UNIQUE,
    department TEXT,
    role       TEXT,
    hire_date  TEXT,
    is_active  INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS products (
    id               INTEGER PRIMARY KEY,
    sku              TEXT    NOT NULL UNIQUE,
    name             TEXT    NOT NULL,
    category         TEXT,
    price            REAL,
    cost             REAL,
    stock_qty        INTEGER,
    is_discontinued  INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS orders (
    id           INTEGER PRIMARY KEY,
    customer_id  INTEGER NOT NULL REFERENCES customers(id),
    order_date   TEXT,
    status       TEXT,
    sales_rep_id INTEGER REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS order_items (
    id         INTEGER PRIMARY KEY,
    order_id   INTEGER NOT NULL REFERENCES orders(id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    quantity   INTEGER,
    unit_price REAL
);

CREATE TABLE IF NOT EXISTS invoices (
    id              INTEGER PRIMARY KEY,
    order_id        INTEGER NOT NULL UNIQUE REFERENCES orders(id),
    invoice_number  TEXT    NOT NULL UNIQUE,
    issue_date      TEXT,
    due_date        TEXT,
    amount          REAL,
    status          TEXT
);

CREATE TABLE IF NOT EXISTS payments (
    id           INTEGER PRIMARY KEY,
    invoice_id   INTEGER NOT NULL REFERENCES invoices(id),
    payment_date TEXT,
    amount       REAL,
    method       TEXT
);

CREATE TABLE IF NOT EXISTS support_tickets (
    id          INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    order_id    INTEGER REFERENCES orders(id),
    assigned_to INTEGER REFERENCES users(id),
    created_at  TEXT,
    subject     TEXT,
    status      TEXT,
    priority    TEXT
);
"""


def create_schema(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    conn.close()


def verify_fk_integrity(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    conn.close()
    if violations:
        print(f"WARNING: {len(violations)} FK violation(s) detected:")
        for v in violations[:10]:
            print(" ", v)
    else:
        print("FK integrity: OK (PRAGMA foreign_key_check returned 0 rows)")


def main() -> None:
    os.makedirs("data", exist_ok=True)

    # Remove stale DB so every run starts from a clean slate.
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    print(f"Creating schema in {DB_PATH} ...")
    create_schema(DB_PATH)
    print("Schema created.")

    print("Seeding data ...")
    from data.seed import seed
    seed(DB_PATH)
    print("Seeding complete.")

    verify_fk_integrity(DB_PATH)


if __name__ == "__main__":
    main()
