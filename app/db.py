"""
app/db.py — Read-only SQLite access for Querious.

Public API
----------
get_connection() -> sqlite3.Connection
    Opens acme.db via the read-only URI so no write can succeed.

get_schema() -> str
    Returns a human-readable string with the CREATE TABLE statement and
    current row count for every table in the database.
"""

import sqlite3
from pathlib import Path

_DB_PATH = Path(__file__).parent.parent / "data" / "acme.db"
_DB_URI = f"file:{_DB_PATH}?mode=ro"


def get_connection() -> sqlite3.Connection:
    """Return a read-only connection to acme.db.

    The connection is opened with ``uri=True`` and ``mode=ro``, so any
    attempt to write (INSERT / UPDATE / DELETE / CREATE …) will raise
    ``sqlite3.OperationalError: attempt to write a readonly database``.
    """
    conn = sqlite3.connect(_DB_URI, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def get_schema() -> str:
    """Return the CREATE TABLE DDL and row count for every user table.

    Returns a single string formatted as::

        === customers (312 rows) ===
        CREATE TABLE customers (
            ...
        );

        === orders (802 rows) ===
        ...

    Tables are listed in the order SQLite stores them in sqlite_master.
    """
    conn = get_connection()
    try:
        cursor = conn.execute(
            "SELECT name, sql FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
            "ORDER BY rowid"
        )
        tables = cursor.fetchall()

        parts: list[str] = []
        for row in tables:
            name: str = row["name"]
            ddl: str = row["sql"]
            (count,) = conn.execute(f"SELECT COUNT(*) FROM [{name}]").fetchone()
            parts.append(f"=== {name} ({count} rows) ===\n{ddl};")

        return "\n\n".join(parts)
    finally:
        conn.close()


if __name__ == "__main__":
    print(get_schema())
