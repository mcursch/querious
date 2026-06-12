"""
Tool implementations and Claude API tool schemas for Querious.

Tools:
  search_docs -- semantic search over company markdown docs (stub)
  get_schema  -- return DB schema + row counts (stub)
  run_sql     -- safe, read-only SQL execution (fully implemented)
"""

import os
import re
import sqlite3
import time
from typing import Any

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DB_PATH = os.environ.get("DB_PATH", "data/acme.db")
QUERY_TIMEOUT_SECONDS = 5
ROW_LIMIT = 200

# ---------------------------------------------------------------------------
# run_sql helpers
# ---------------------------------------------------------------------------


def _strip_sql_comments(sql: str) -> str:
    """Remove SQL single-line (--) and block (/* */) comments."""
    sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)
    sql = re.sub(r"--[^\n]*", "", sql)
    return sql


def _safety_check(query: str) -> str | None:
    """
    Validate query against the run_sql safety rules.

    Returns an error message string when the query is rejected, otherwise None.
    """
    normalized = _strip_sql_comments(query).strip()

    # Tolerate a single trailing semicolon (common in copy-pasted SQL).
    if normalized.endswith(";"):
        normalized = normalized[:-1].strip()

    # Reject semicolon-chained statements.
    if ";" in normalized:
        return "Semicolon-chained statements are not allowed; send one statement at a time."

    upper = normalized.upper()
    first_token = upper.split()[0] if upper.split() else ""

    # Reject PRAGMA (information leak / state mutation).
    if first_token == "PRAGMA":
        return "PRAGMA statements are not allowed."

    # Reject ATTACH (could expose arbitrary files).
    if first_token == "ATTACH":
        return "ATTACH statements are not allowed."

    # Allow only SELECT and WITH (CTEs that lead to a SELECT).
    if first_token not in ("SELECT", "WITH"):
        return (
            f"Only SELECT statements are allowed. "
            f"Received statement starting with: {first_token or '(empty)'}"
        )

    return None


def _inject_limit(query: str) -> str:
    """
    Append 'LIMIT <ROW_LIMIT>' to *query* when no LIMIT clause is present.

    The check is performed on the comment-stripped text so that a LIMIT hiding
    inside a comment doesn't prevent injection.
    """
    if re.search(r"\bLIMIT\b", _strip_sql_comments(query), re.IGNORECASE):
        return query  # LIMIT already present – leave the query untouched.

    # Strip any trailing semicolon before appending.
    query = query.rstrip().rstrip(";").rstrip()
    return f"{query} LIMIT {ROW_LIMIT}"


# ---------------------------------------------------------------------------
# Public tool functions
# ---------------------------------------------------------------------------


def run_sql(query: str) -> dict[str, Any]:
    """
    Execute a read-only SQL SELECT query against the Acme Outfitters database.

    Safety chain (enforced in order):
      1. Connection opened via read-only SQLite URI (mode=ro) – writes impossible.
      2. Single SELECT-only statement; rejects semicolon chains, PRAGMA, ATTACH,
         and non-SELECT/WITH starters.
      3. LIMIT 200 automatically injected when absent.
      4. 5-second execution timeout enforced via SQLite progress handler.
      5. All errors are returned as {"is_error": True, "message": ...} dicts
         instead of raising exceptions.

    Successful return shape:
      {"columns": ["col1", ...], "rows": [[val, ...], ...]}
    """
    # --- Step 2: safety validation ---
    error_msg = _safety_check(query)
    if error_msg:
        return {"is_error": True, "message": error_msg}

    # --- Step 3: LIMIT injection ---
    query = _inject_limit(query)

    try:
        # --- Step 1: read-only URI connection ---
        db_uri = f"file:{DB_PATH}?mode=ro"
        conn = sqlite3.connect(db_uri, uri=True)
        try:
            # --- Step 4: 5-second timeout via progress handler ---
            deadline = time.monotonic() + QUERY_TIMEOUT_SECONDS

            def _progress_handler() -> int:
                # Returning a non-zero integer interrupts the query.
                return 1 if time.monotonic() > deadline else 0

            # Invoke the handler every 1 000 SQLite virtual-machine opcodes.
            conn.set_progress_handler(_progress_handler, 1_000)

            cursor = conn.execute(query)
            columns: list[str] = (
                [desc[0] for desc in cursor.description]
                if cursor.description
                else []
            )
            rows: list[list[Any]] = [list(row) for row in cursor.fetchall()]

            return {"columns": columns, "rows": rows}

        finally:
            conn.close()

    # --- Step 5: errors as dicts ---
    except Exception as exc:  # noqa: BLE001
        return {"is_error": True, "message": str(exc)}


def search_docs(query: str) -> dict[str, Any]:  # noqa: ARG001
    """Embed *query* and return the top-5 matching document chunks (not yet implemented)."""
    raise NotImplementedError("search_docs is not yet implemented")


def get_schema() -> dict[str, Any]:
    """Return CREATE TABLE statements and row counts for all DB tables (not yet implemented)."""
    raise NotImplementedError("get_schema is not yet implemented")


# ---------------------------------------------------------------------------
# Claude API tool schemas
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "search_docs",
        "description": (
            "Search Acme Outfitters company documentation using semantic similarity. "
            "Use this for questions about policies, the employee handbook, product guides, "
            "SLAs, shipping rules, and any other unstructured company knowledge."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural-language search query to find relevant document chunks.",
                }
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_schema",
        "description": (
            "Return the CREATE TABLE statements and approximate row counts for every table "
            "in the Acme Outfitters database. Call this before writing SQL if you have not "
            "already seen the schema in this conversation."
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
            "Execute a read-only SQL SELECT query against the Acme Outfitters database and "
            "return the results as JSON. Only SELECT statements (including CTEs) are permitted. "
            "A LIMIT of 200 rows is enforced automatically. If the query fails the error is "
            "returned as a tool result so you can inspect it, fix the query, and retry."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "A valid SQL SELECT statement to execute.",
                }
            },
            "required": ["query"],
        },
    },
]
