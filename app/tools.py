"""
Tool definitions for the Claude agentic loop.

Three tools:
  search_docs  — RAG over markdown docs
  get_schema   — returns CREATE TABLE DDL + row counts
  run_sql      — validated, read-only SELECT execution
"""

from __future__ import annotations

import json
from typing import Any

from app import db, rag

# ---------------------------------------------------------------------------
# Tool schemas (passed to the Anthropic messages API)
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS: list[dict] = [
    {
        "name": "search_docs",
        "description": (
            "Search the Acme Outfitters internal document library. "
            "Use this for questions about policies, handbooks, product guides, "
            "shipping, returns, warranties, onboarding, and any unstructured "
            "company knowledge. Returns the top matching text chunks with "
            "source file attribution."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural-language search query.",
                }
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_schema",
        "description": (
            "Return the full database schema for acme.db: all CREATE TABLE "
            "statements and the current row count for each table. "
            "Call this before writing SQL if you haven't seen the schema yet "
            "in this conversation."
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
            "Execute a read-only SELECT query against acme.db and return the "
            "results as JSON. The database is opened with mode=ro so writes are "
            "impossible. Returns up to 200 rows. If the query fails, the error "
            "message is returned so you can fix and retry."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "A SQL SELECT statement (or WITH … SELECT CTE).",
                }
            },
            "required": ["query"],
        },
    },
]


# ---------------------------------------------------------------------------
# Tool executor
# ---------------------------------------------------------------------------

async def execute_tool(name: str, tool_input: dict[str, Any]) -> Any:
    """
    Dispatch a tool call and return the result.

    Returns either a plain string or a JSON-serialisable object.
    On validation / execution errors, returns a dict with ``is_error: true``
    so Claude can self-correct.
    """
    if name == "search_docs":
        return _search_docs(tool_input.get("query", ""))
    if name == "get_schema":
        return _get_schema()
    if name == "run_sql":
        return _run_sql(tool_input.get("query", ""))
    return {"is_error": True, "error": f"Unknown tool: {name!r}"}


# ---------------------------------------------------------------------------
# Individual tool implementations
# ---------------------------------------------------------------------------

def _search_docs(query: str) -> dict:
    if not query:
        return {"is_error": True, "error": "query is required"}
    try:
        chunks = rag.search(query, top_k=5)
        return {
            "chunks": [
                {
                    "source": c["source"],
                    "heading": c["heading"],
                    "text": c["text"],
                    "score": round(c["score"], 4),
                }
                for c in chunks
            ],
            "count": len(chunks),
        }
    except FileNotFoundError as exc:
        return {"is_error": True, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        return {"is_error": True, "error": f"search_docs failed: {exc}"}


def _get_schema() -> dict:
    try:
        schema_text = db.get_schema()
        return {"schema": schema_text}
    except FileNotFoundError as exc:
        return {"is_error": True, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        return {"is_error": True, "error": f"get_schema failed: {exc}"}


def _run_sql(query: str) -> dict:
    if not query:
        return {"is_error": True, "error": "query is required"}
    try:
        rows = db.execute_query(query)
        return {"rows": rows, "count": len(rows)}
    except ValueError as exc:
        # Validation error — return as is_error so Claude can self-correct
        return {"is_error": True, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        return {"is_error": True, "error": str(exc)}


# ---------------------------------------------------------------------------
# Summarise tool results for the tool_end SSE event
# ---------------------------------------------------------------------------

def summarise_result(tool_name: str, result: Any) -> str:
    """Return a short human-readable summary for the tool_end SSE event."""
    if isinstance(result, dict) and result.get("is_error"):
        return f"error: {result.get('error', 'unknown')}"

    if tool_name == "search_docs":
        count = result.get("count", 0) if isinstance(result, dict) else 0
        return f"{count} chunk{'s' if count != 1 else ''} found"

    if tool_name == "get_schema":
        return "schema retrieved"

    if tool_name == "run_sql":
        count = result.get("count", 0) if isinstance(result, dict) else 0
        return f"{count} row{'s' if count != 1 else ''} returned"

    return "done"
