"""Tool implementations used by the chatbot's agentic loop.

Tools
-----
run_sql   -- execute a read-only SELECT against acme.db
get_schema -- return CREATE TABLE statements + row counts
search_docs -- RAG retrieval over data/docs/
"""

import re
import sqlite3

from app.db import get_connection
from app.rag import search_docs as _rag_search


# ---------------------------------------------------------------------------
# run_sql
# ---------------------------------------------------------------------------

_DISALLOWED = re.compile(r"\b(PRAGMA|ATTACH|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER)\b", re.IGNORECASE)
_HAS_LIMIT = re.compile(r"\bLIMIT\b", re.IGNORECASE)
_STARTS_SELECT = re.compile(r"^\s*(SELECT|WITH)\b", re.IGNORECASE)


def run_sql(query: str) -> dict:
    """Execute *query* against acme.db (read-only) and return rows as a dict.

    Returns ``{"is_error": True, "error": "..."}`` on any validation or
    execution failure so the LLM can self-correct and retry.
    """
    query = query.strip()

    # Must be SELECT or WITH … SELECT
    if not _STARTS_SELECT.match(query):
        return {"is_error": True, "error": "Only SELECT (or WITH…SELECT) queries are allowed."}

    # No semicolons — disallow statement chaining
    if ";" in query:
        return {"is_error": True, "error": "Multiple statements (';') are not allowed."}

    # Disallow DDL / DML / PRAGMA / ATTACH
    if _DISALLOWED.search(query):
        return {"is_error": True, "error": "Query contains a disallowed keyword."}

    # Enforce LIMIT ≤ 200
    if not _HAS_LIMIT.search(query):
        query = f"SELECT * FROM ({query}) _q LIMIT 200"

    try:
        conn = get_connection()
        cursor = conn.execute(query)
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        conn.close()
        return {"columns": columns, "rows": rows, "row_count": len(rows)}
    except sqlite3.OperationalError as exc:
        return {"is_error": True, "error": str(exc)}
    except Exception as exc:  # pragma: no cover
        return {"is_error": True, "error": str(exc)}


# ---------------------------------------------------------------------------
# get_schema
# ---------------------------------------------------------------------------

def get_schema() -> dict:
    """Return CREATE TABLE DDL and row counts for every table in acme.db."""
    try:
        conn = get_connection()
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()

        parts: list[str] = []
        for (tbl,) in tables:
            row = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (tbl,)
            ).fetchone()
            count = conn.execute(f'SELECT COUNT(*) FROM "{tbl}"').fetchone()[0]
            if row and row[0]:
                parts.append(f"{row[0]};\n-- Rows: {count}")

        conn.close()
        return {"schema": "\n\n".join(parts)}
    except Exception as exc:  # pragma: no cover
        return {"is_error": True, "error": str(exc)}


# ---------------------------------------------------------------------------
# search_docs
# ---------------------------------------------------------------------------

def search_docs(query: str) -> dict:
    """Embed *query* and retrieve the top-5 most relevant document chunks."""
    return _rag_search(query)
