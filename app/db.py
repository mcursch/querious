"""
SQLite access helpers — read-only URI connection for the bot.
"""

import os
import re
import sqlite3
from pathlib import Path

# Anchor to the project root regardless of CWD
_ROOT = Path(__file__).parent.parent


def _get_db_path() -> Path:
    """Return the path to acme.db, respecting QUERIOUS_DATA_DIR if set."""
    data_dir = os.environ.get("QUERIOUS_DATA_DIR")
    if data_dir:
        return Path(data_dir) / "acme.db"
    return _ROOT / "data" / "acme.db"


# Module-level alias kept for backwards-compatibility with any code that
# imported DB_PATH directly.  Note: this value is frozen at import time and
# will NOT reflect QUERIOUS_DATA_DIR changes; prefer _get_db_path() internally.
DB_PATH = _get_db_path()


def open_ro_connection() -> sqlite3.Connection:
    """Open acme.db in read-only mode via SQLite URI."""
    db_path = _get_db_path()
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")
    uri = f"file:{db_path}?mode=ro"
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


def get_schema_structured() -> list[dict]:
    """Return the schema as structured data for the UI sidebar.

    [{"table": str, "row_count": int, "columns": [{"name": str, "type": str}]}]
    """
    conn = open_ro_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name"
        )
        tables = [row["name"] for row in cur.fetchall()]

        result: list[dict] = []
        for name in tables:
            cur.execute(f"PRAGMA table_info([{name}])")
            columns = [
                {"name": r["name"], "type": r["type"] or ""} for r in cur.fetchall()
            ]
            cur.execute(f"SELECT COUNT(*) FROM [{name}]")  # noqa: S608
            row_count = cur.fetchone()[0]
            result.append(
                {"table": name, "row_count": row_count, "columns": columns}
            )
        return result
    finally:
        conn.close()


def execute_query(sql: str, timeout_seconds: int = 5) -> list[dict]:
    """
    Execute a read-only SELECT and return rows as a list of dicts (≤ 200 rows).

    Raises ValueError for unsafe queries; raises sqlite3.Error on DB errors.
    """
    _validate_sql(sql)
    # Strip a trailing semicolon before wrapping; otherwise _enforce_limit
    # produces "SELECT * FROM (… ;) _q LIMIT 200", which is a syntax error.
    # (Models habitually terminate SQL with ';'.)
    sql = sql.strip().rstrip(";").strip()
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

def _validate_query(sql: str) -> str | None:
    """
    Validate *sql* for safety.

    Returns ``None`` if the query is acceptable, or an error-message string
    describing the problem if it is not.  Does not raise.
    """
    stripped = sql.strip().rstrip(";")

    # Only single statements
    if ";" in stripped:
        return "Multiple statements are not allowed."

    upper = stripped.upper()

    # Must start with SELECT or a CTE (WITH ... SELECT)
    if not (upper.startswith("SELECT") or upper.startswith("WITH")):
        return "Only SELECT (or WITH … SELECT) queries are allowed."

    # Reject dangerous keywords (use word-boundary regex so that keywords
    # attached to punctuation such as "(UPDATE" are still caught).
    forbidden = {"PRAGMA", "ATTACH", "DETACH", "DROP", "INSERT", "UPDATE", "DELETE"}
    for kw in forbidden:
        if re.search(r"\b" + kw + r"\b", upper):
            return f"Keyword {kw!r} is not allowed."

    return None


def _validate_sql(sql: str) -> None:
    """Reject anything that isn't a plain SELECT or CTE SELECT (raises ValueError)."""
    error = _validate_query(sql)
    if error is not None:
        raise ValueError(error)


def _enforce_limit(sql: str) -> str:
    """Wrap the query with LIMIT 200 if it doesn't already have one."""
    upper = sql.upper()
    if "LIMIT" not in upper:
        return f"SELECT * FROM ({sql}) _q LIMIT 200"
    return sql
