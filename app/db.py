"""
Read-only SQLite access for the Acme Outfitters database.

Safety:
- Connection opened with file:...?mode=ro URI so writes are impossible at the DB level.
- Queries validated (SELECT / WITH…SELECT only) before execution.
- LIMIT 200 enforced via query rewrite.
- 5-second timeout via SQLite progress handler.
"""

import json
import os
import re
import sqlite3
import time
from pathlib import Path
from typing import Any

_BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = os.environ.get("ACME_DB_PATH", str(_BASE_DIR / "data" / "acme.db"))

# Statements (or clause keywords) that must never appear in a query.
_BLOCKED_KEYWORDS = re.compile(
    r"\b(PRAGMA|ATTACH|DETACH|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|REPLACE|TRUNCATE)\b",
    re.IGNORECASE,
)


def _validate_query(query: str) -> str | None:
    """
    Return an error string if the query is disallowed, otherwise None.
    """
    stripped = query.strip().rstrip(";")

    upper = stripped.upper()

    # Must start with SELECT or WITH (CTE)
    if not (upper.startswith("SELECT") or upper.startswith("WITH")):
        return "Only SELECT (or WITH … SELECT) queries are allowed."

    # WITH clauses must eventually reach a SELECT
    if upper.startswith("WITH") and "SELECT" not in upper:
        return "WITH clause must contain a SELECT statement."

    # Reject PRAGMA, ATTACH, and any DML/DDL keywords
    blocked = _BLOCKED_KEYWORDS.search(stripped)
    if blocked:
        return f"Keyword '{blocked.group()}' is not allowed in read-only queries."

    # Reject multiple statements (semicolon not at the very end)
    inner = stripped.rstrip(";")
    if ";" in inner:
        return "Multiple statements are not allowed. Remove the semicolon separator."

    return None


def _enforce_limit(query: str) -> str:
    """Append LIMIT 200 if the query doesn't already have one."""
    stripped = query.strip().rstrip(";")
    if not re.search(r"\bLIMIT\b", stripped, re.IGNORECASE):
        stripped = f"{stripped} LIMIT 200"
    return stripped


def get_schema() -> dict[str, Any]:
    """
    Return a dict with:
      - ``content``: formatted string of CREATE TABLE statements + row counts
      - ``is_error``: bool
    """
    if not Path(DB_PATH).exists():
        return {
            "is_error": True,
            "content": f"Database file not found at {DB_PATH}. Run scripts/init_db.py first.",
        }

    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row

        cursor = conn.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = cursor.fetchall()

        lines: list[str] = []
        for row in tables:
            table_name = row["name"]
            ddl = row["sql"] or ""
            count_row = conn.execute(f"SELECT COUNT(*) AS n FROM [{table_name}]").fetchone()
            row_count = count_row["n"] if count_row else "?"
            lines.append(f"-- {table_name} ({row_count} rows)\n{ddl};\n")

        conn.close()
        return {"is_error": False, "content": "\n".join(lines)}

    except Exception as exc:
        return {"is_error": True, "content": f"Failed to read schema: {exc}"}


def execute_query(query: str) -> dict[str, Any]:
    """
    Validate and execute a read-only SELECT query.

    Returns a dict with:
      - ``content``: JSON string of rows (list of objects) or error message
      - ``is_error``: bool
      - ``row_count``: int (0 on error)
    """
    if not Path(DB_PATH).exists():
        return {
            "is_error": True,
            "content": f"Database file not found at {DB_PATH}. Run scripts/init_db.py first.",
            "row_count": 0,
        }

    # --- Validation ---
    error = _validate_query(query)
    if error:
        return {"is_error": True, "content": error, "row_count": 0}

    # --- Enforce LIMIT ---
    safe_query = _enforce_limit(query)

    # --- Execute ---
    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row

        deadline = time.monotonic() + 5.0

        def _progress() -> int:
            # Returning non-zero causes sqlite3 to raise OperationalError
            return 1 if time.monotonic() > deadline else 0

        conn.set_progress_handler(_progress, 1000)

        cursor = conn.execute(safe_query)
        raw_rows = cursor.fetchall()
        conn.close()

        rows = [dict(r) for r in raw_rows]
        return {
            "is_error": False,
            "content": json.dumps(rows, default=str),
            "row_count": len(rows),
        }

    except Exception as exc:
        return {"is_error": True, "content": str(exc), "row_count": 0}
