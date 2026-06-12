"""
Tool definitions for the Querious chatbot agentic loop.

Exports
-------
TOOL_DEFINITIONS : list[dict]
    Tool schemas passed to the Claude API (input_schema format).

execute_tool(name, input_dict) -> dict
    Async dispatcher that runs a tool by name and returns a result dict:
      - ``content``  : str  — text to send back to Claude as the tool result
      - ``summary``  : str  — one-liner for the ``tool_end`` SSE event
      - ``is_error`` : bool — True means Claude should self-correct
"""

import asyncio
from typing import Any

from app import db, rag

# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "search_docs",
        "description": (
            "Search the Acme Outfitters internal documentation for policies, procedures, "
            "product information, or any other unstructured company knowledge. "
            "Use this for questions about returns, shipping, warranties, employee policies, "
            "product specifications, SLAs, and similar topics covered in markdown docs. "
            "Returns the most relevant document excerpts with source attribution."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "A natural-language search query capturing what information you need. "
                        "Be specific — e.g. 'return policy for used tents' rather than 'returns'."
                    ),
                }
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_schema",
        "description": (
            "Retrieve the full database schema for the Acme Outfitters SQLite database: "
            "CREATE TABLE statements and current row counts for every table. "
            "Call this before writing a SQL query whenever you are unsure of table or column names, "
            "especially at the start of a conversation or when handling a new type of question."
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
            "Execute a read-only SQL SELECT query against the Acme Outfitters SQLite database. "
            "The connection is opened in read-only mode; writes are impossible. "
            "Results are capped at 200 rows. "
            "Only SELECT and WITH … SELECT (CTE) statements are accepted — no DML, DDL, or PRAGMA. "
            "If the query fails (syntax error, missing table, etc.) the error is returned to you "
            "so you can fix and retry. Always show the SQL you ran when summarising results."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "A valid SQLite SELECT statement (or WITH … SELECT CTE). "
                        "Do not include multiple semicolon-separated statements. "
                        "A LIMIT clause is recommended; if absent, one will be added automatically."
                    ),
                }
            },
            "required": ["query"],
        },
    },
]

# ---------------------------------------------------------------------------
# Tool dispatcher
# ---------------------------------------------------------------------------


async def execute_tool(name: str, input_dict: dict[str, Any]) -> dict[str, Any]:
    """
    Dispatch a tool call by name.

    Always returns a dict with keys:
      ``content``  (str)  — result text for Claude
      ``summary``  (str)  — short human-readable summary for the UI
      ``is_error`` (bool) — whether this represents a failure Claude should fix
    """
    if name == "search_docs":
        return await asyncio.to_thread(_run_search_docs, input_dict)
    elif name == "get_schema":
        return await asyncio.to_thread(_run_get_schema)
    elif name == "run_sql":
        return await asyncio.to_thread(_run_sql, input_dict)
    else:
        return {
            "content": f"Unknown tool: '{name}'.",
            "summary": f"error: unknown tool '{name}'",
            "is_error": True,
        }


# ---------------------------------------------------------------------------
# Sync implementations (run via asyncio.to_thread)
# ---------------------------------------------------------------------------


def _run_search_docs(input_dict: dict[str, Any]) -> dict[str, Any]:
    query = (input_dict.get("query") or "").strip()
    if not query:
        return {
            "content": "No query provided to search_docs.",
            "summary": "error: empty query",
            "is_error": True,
        }

    result = rag.search_docs(query)
    is_error = result.get("is_error", False)
    chunk_count = result.get("chunk_count", 0)

    if is_error:
        summary = f"error: {result['content'][:80]}"
    else:
        summary = f"{chunk_count} chunk{'s' if chunk_count != 1 else ''} retrieved"

    return {
        "content": result["content"],
        "summary": summary,
        "is_error": is_error,
    }


def _run_get_schema() -> dict[str, Any]:
    result = db.get_schema()
    is_error = result.get("is_error", False)

    if is_error:
        summary = f"error: {result['content'][:80]}"
    else:
        # Count the number of tables by counting occurrences of "-- " prefix lines
        table_count = result["content"].count("\n-- ") + (
            1 if result["content"].startswith("-- ") else 0
        )
        summary = f"schema for {table_count} table{'s' if table_count != 1 else ''}"

    return {
        "content": result["content"],
        "summary": summary,
        "is_error": is_error,
    }


def _run_sql(input_dict: dict[str, Any]) -> dict[str, Any]:
    query = (input_dict.get("query") or "").strip()
    if not query:
        return {
            "content": "No SQL query provided to run_sql.",
            "summary": "error: empty query",
            "is_error": True,
        }

    result = db.execute_query(query)
    is_error = result.get("is_error", False)
    row_count = result.get("row_count", 0)

    if is_error:
        summary = f"error: {result['content'][:80]}"
    else:
        summary = f"{row_count} row{'s' if row_count != 1 else ''}"

    return {
        "content": result["content"],
        "summary": summary,
        "is_error": is_error,
    }
