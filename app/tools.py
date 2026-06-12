"""Tool definitions and implementations for the Querious chatbot."""
import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from app.rag import retrieve
from app.db import get_connection, DB_PATH

# ---------------------------------------------------------------------------
# Tool schemas (for Claude API)
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS = [
    {
        "name": "search_docs",
        "description": (
            "Search internal Acme Outfitters documentation (policies, handbooks, "
            "product guides) using semantic similarity. Use this for policy, "
            "procedure, or product-spec questions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural-language query to search for in the documentation.",
                }
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_schema",
        "description": (
            "Return the CREATE TABLE statements and approximate row counts for "
            "all tables in acme.db. Call this before writing SQL if you have not "
            "yet seen the schema in this conversation."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "run_sql",
        "description": (
            "Execute a read-only SELECT query against acme.db and return the results "
            "as JSON rows (up to 200 rows). Use get_schema first if you need to know "
            "the table structure. SQL errors are returned so you can fix and retry."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "A SELECT statement (or WITH...SELECT CTE) to execute.",
                }
            },
            "required": ["query"],
        },
    },
]


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def search_docs(query: str) -> dict[str, Any]:
    """Embed query and return top-5 chunks with source attribution."""
    chunks = retrieve(query)
    if not chunks:
        return {"result": "No relevant documentation found.", "sources": []}

    parts: list[str] = []
    sources: list[str] = []
    for i, chunk in enumerate(chunks, 1):
        parts.append(
            f"[{i}] Source: {chunk['source']}\n"
            f"Section: {chunk['heading']}\n"
            f"{chunk['text']}"
        )
        if chunk["source"] not in sources:
            sources.append(chunk["source"])

    return {"result": "\n\n---\n\n".join(parts), "sources": sources}


def get_schema() -> dict[str, Any]:
    """Return CREATE TABLE statements + row counts."""
    conn = get_connection()
    try:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()

        parts: list[str] = []
        for (tname,) in tables:
            ddl = conn.execute(
                f"SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (tname,)
            ).fetchone()[0]
            count = conn.execute(f"SELECT COUNT(*) FROM \"{tname}\"").fetchone()[0]
            parts.append(f"{ddl};\n-- {count} rows")

        return {"schema": "\n\n".join(parts)}
    finally:
        conn.close()


_DANGEROUS_PATTERN = re.compile(
    r";\s*\S|PRAGMA\b|ATTACH\b|DETACH\b|DROP\b|CREATE\b|INSERT\b|UPDATE\b|DELETE\b|ALTER\b",
    re.IGNORECASE,
)

_LIMIT_PATTERN = re.compile(r"\bLIMIT\b", re.IGNORECASE)


def _add_limit(query: str, limit: int = 200) -> str:
    """Wrap query with LIMIT if not already present."""
    stripped = query.rstrip().rstrip(";")
    if not _LIMIT_PATTERN.search(stripped):
        return f"{stripped} LIMIT {limit}"
    return stripped


def run_sql(query: str) -> dict[str, Any]:
    """Safely execute a read-only SELECT and return rows as JSON."""
    normalized = query.strip()

    # Must start with SELECT or WITH
    if not re.match(r"^\s*(SELECT|WITH)\b", normalized, re.IGNORECASE):
        return {
            "is_error": True,
            "error": "Only SELECT (or WITH...SELECT) queries are permitted.",
        }

    # Block dangerous patterns (semicolon chaining, PRAGMA, DDL, DML)
    if _DANGEROUS_PATTERN.search(normalized):
        return {
            "is_error": True,
            "error": "Query contains disallowed SQL constructs.",
        }

    safe_query = _add_limit(normalized)

    try:
        conn = get_connection()
        try:
            # 5-second timeout via progress handler
            def _timeout_handler():
                return 1  # returning 1 aborts

            conn.set_progress_handler(_timeout_handler, 10_000_000)

            cursor = conn.execute(safe_query)
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
            return {"rows": rows, "row_count": len(rows), "columns": columns}
        finally:
            conn.close()
    except sqlite3.OperationalError as exc:
        return {"is_error": True, "error": str(exc)}
    except Exception as exc:
        return {"is_error": True, "error": f"Unexpected error: {exc}"}


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

def execute_tool(name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
    """Dispatch a tool call and return its result."""
    if name == "search_docs":
        return search_docs(tool_input["query"])
    elif name == "get_schema":
        return get_schema()
    elif name == "run_sql":
        return run_sql(tool_input["query"])
    else:
        return {"is_error": True, "error": f"Unknown tool: {name}"}
