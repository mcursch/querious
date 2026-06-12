"""
SQLite access helpers — read-only URI connection for the bot.
"""

import sqlite3
from pathlib import Path

DB_PATH = Path("data/acme.db")


def open_ro_connection() -> sqlite3.Connection:
    """Open acme.db in read-only mode via SQLite URI."""
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found: {DB_PATH}")
    uri = f"file:{DB_PATH}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def get_schema() -> str:
    """Return CREATE TABLE statements and row counts for all tables."""
    conn = open_ro_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT name, sql FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name"
        )
        tables = cur.fetchall()
        if not tables:
            return "No tables found."

        parts: list[str] = []
        for row in tables:
            name, ddl = row["name"], row["sql"]
            cur.execute(f"SELECT COUNT(*) FROM [{name}]")  # noqa: S608
            count = cur.fetchone()[0]
            parts.append(f"-- {count} rows\n{ddl};")

        return "\n\n".join(parts)
    finally:
        conn.close()


def execute_query(sql: str, timeout_seconds: int = 5) -> list[dict]:
    """
    Execute a read-only SELECT and return rows as a list of dicts (≤ 200 rows).

    Raises ValueError for unsafe queries; raises sqlite3.Error on DB errors.
    """
    _validate_sql(sql)
    sql = _enforce_limit(sql)

    conn = open_ro_connection()
    try:
        # SQLite progress handler fires every N instructions; use it to enforce timeout.
        import time

        deadline = time.monotonic() + timeout_seconds
        call_count = 0

        def _progress():
            nonlocal call_count
            call_count += 1
            if time.monotonic() > deadline:
                return 1  # non-zero aborts the query
            return 0

        conn.set_progress_handler(_progress, 1000)
        cur = conn.cursor()
        cur.execute(sql)
        rows = cur.fetchmany(200)
        return [dict(row) for row in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _validate_sql(sql: str) -> None:
    """Reject anything that isn't a plain SELECT or CTE SELECT."""
    stripped = sql.strip().rstrip(";")

    # Only single statements
    if ";" in stripped:
        raise ValueError("Multiple statements are not allowed.")

    upper = stripped.upper()

    # Must start with SELECT or a CTE (WITH ... SELECT)
    if not (upper.startswith("SELECT") or upper.startswith("WITH")):
        raise ValueError(
            "Only SELECT (or WITH … SELECT) queries are allowed."
        )

    # Reject dangerous keywords
    forbidden = {"PRAGMA", "ATTACH", "DETACH", "DROP", "INSERT", "UPDATE", "DELETE"}
    for kw in forbidden:
        if kw in upper.split():
            raise ValueError(f"Keyword {kw!r} is not allowed.")


def _enforce_limit(sql: str) -> str:
    """Wrap the query with LIMIT 200 if it doesn't already have one."""
    upper = sql.upper()
    if "LIMIT" not in upper:
        return f"SELECT * FROM ({sql}) _q LIMIT 200"
    return sql
