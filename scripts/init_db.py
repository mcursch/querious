"""
scripts/init_db.py — Create data/acme.db with the Acme Outfitters schema.

Idempotent: drops all tables (in reverse dependency order) before recreating them.
Enables foreign_keys PRAGMA so FK integrity is enforced at runtime.
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "acme.db"


def create_schema(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys = ON;")

    # Drop tables in reverse dependency order to avoid FK violations
    drop_order = [
        "support_tickets",
        "payments",
        "invoices",
        "order_items",
        "orders",
        "products",
        "users",
        "customers",
    ]
    for table in drop_order:
        conn.execute(f"DROP TABLE IF EXISTS {table};")

    conn.executescript("""
        CREATE TABLE customers (
            id          INTEGER PRIMARY KEY,
            name        TEXT    NOT NULL,
            email       TEXT    NOT NULL UNIQUE,
            phone       TEXT,
            city        TEXT,
            state       TEXT,
            signup_date TEXT,
            tier        TEXT    NOT NULL CHECK(tier IN ('standard', 'premium', 'enterprise'))
        );

        CREATE TABLE users (
            id          INTEGER PRIMARY KEY,
            name        TEXT    NOT NULL,
            email       TEXT    NOT NULL UNIQUE,
            department  TEXT,
            role        TEXT,
            hire_date   TEXT,
            is_active   INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0, 1))
        );

        CREATE TABLE products (
            id               INTEGER PRIMARY KEY,
            sku              TEXT    NOT NULL UNIQUE,
            name             TEXT    NOT NULL,
            category         TEXT,
            price            REAL    NOT NULL,
            cost             REAL    NOT NULL,
            stock_qty        INTEGER NOT NULL DEFAULT 0,
            is_discontinued  INTEGER NOT NULL DEFAULT 0 CHECK(is_discontinued IN (0, 1))
        );

        CREATE TABLE orders (
            id           INTEGER PRIMARY KEY,
            customer_id  INTEGER NOT NULL REFERENCES customers(id),
            order_date   TEXT    NOT NULL,
            status       TEXT    NOT NULL CHECK(status IN ('pending', 'shipped', 'delivered', 'cancelled', 'returned')),
            sales_rep_id INTEGER REFERENCES users(id)
        );

        CREATE TABLE order_items (
            id          INTEGER PRIMARY KEY,
            order_id    INTEGER NOT NULL REFERENCES orders(id),
            product_id  INTEGER NOT NULL REFERENCES products(id),
            quantity    INTEGER NOT NULL CHECK(quantity >= 1),
            unit_price  REAL    NOT NULL
        );

        CREATE TABLE invoices (
            id              INTEGER PRIMARY KEY,
            order_id        INTEGER NOT NULL UNIQUE REFERENCES orders(id),
            invoice_number  TEXT    NOT NULL UNIQUE,
            issue_date      TEXT    NOT NULL,
            due_date        TEXT    NOT NULL,
            amount          REAL    NOT NULL,
            status          TEXT    NOT NULL CHECK(status IN ('draft', 'sent', 'paid', 'overdue', 'void'))
        );

        CREATE TABLE payments (
            id            INTEGER PRIMARY KEY,
            invoice_id    INTEGER NOT NULL REFERENCES invoices(id),
            payment_date  TEXT    NOT NULL,
            amount        REAL    NOT NULL,
            method        TEXT    NOT NULL CHECK(method IN ('card', 'ach', 'check', 'paypal'))
        );

        CREATE TABLE support_tickets (
            id           INTEGER PRIMARY KEY,
            customer_id  INTEGER NOT NULL REFERENCES customers(id),
            order_id     INTEGER REFERENCES orders(id),
            assigned_to  INTEGER REFERENCES users(id),
            created_at   TEXT    NOT NULL,
            subject      TEXT    NOT NULL,
            status       TEXT    NOT NULL CHECK(status IN ('open', 'in_progress', 'resolved', 'closed')),
            priority     TEXT    NOT NULL CHECK(priority IN ('low', 'medium', 'high', 'urgent'))
        );
    """)

    conn.commit()


def main() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys = ON;")
        create_schema(conn)
    print(f"Database created at {DB_PATH}")

    # Verify
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys = ON;")
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"
            )
        ]
        fk_violations = conn.execute("PRAGMA foreign_key_check;").fetchall()

    expected = {
        "customers",
        "users",
        "products",
        "orders",
        "order_items",
        "invoices",
        "payments",
        "support_tickets",
    }
    missing = expected - set(tables)
    if missing:
        raise RuntimeError(f"Missing tables after creation: {missing}")
    if fk_violations:
        raise RuntimeError(f"FK violations found: {fk_violations}")

    print(f"All {len(expected)} tables present. FK check passed.")


if __name__ == "__main__":
    main()
