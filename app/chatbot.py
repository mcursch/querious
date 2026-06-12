"""Agentic chatbot loop.

Drives the conversation with Claude using a manual tool-use loop so that
every tool invocation can be streamed to the UI as SSE events before the
next LLM call.
"""

import json
from typing import Generator

import anthropic

from app import tools as _tools

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are Querious, the internal AI assistant for Acme Outfitters, an outdoor-gear retailer.

Guidelines:
- For questions about company policy, the employee handbook, or product specifications,
  call `search_docs`.
- For questions that require data (counts, lists, look-ups, aggregations), first call
  `get_schema` if you have not already seen the schema this conversation, then use
  `run_sql` to execute a SELECT query.
- Always show the SQL you ran when summarising query results.
- If a SQL query returns an error, read the error carefully, fix the query, and retry
  rather than telling the user you cannot answer.
- Cite document source files when answering from docs.
- Be concise and helpful.
"""

# ---------------------------------------------------------------------------
# Tool definitions (Anthropic tool-use schema)
# ---------------------------------------------------------------------------

TOOLS_DEFINITION: list[dict] = [
    {
        "name": "search_docs",
        "description": (
            "Search Acme Outfitters documentation for policy, handbook, and product information."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural-language search query"}
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_schema",
        "description": (
            "Return the CREATE TABLE statements and row counts for every table in the "
            "Acme Outfitters database."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "run_sql",
        "description": (
            "Execute a read-only SELECT query against the Acme Outfitters SQLite database. "
            "Errors (e.g. wrong table name) are returned as tool results so you can fix "
            "and retry the query."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "A single SELECT (or WITH…SELECT) SQL statement.",
                }
            },
            "required": ["query"],
        },
    },
]

# ---------------------------------------------------------------------------
# In-memory session store
# ---------------------------------------------------------------------------

_sessions: dict[str, list] = {}


def get_or_create_history(session_id: str) -> list:
    if session_id not in _sessions:
        _sessions[session_id] = []
    return _sessions[session_id]


def clear_session(session_id: str) -> None:
    _sessions.pop(session_id, None)


# ---------------------------------------------------------------------------
# Tool dispatch
# ---------------------------------------------------------------------------

def _dispatch(name: str, tool_input: dict) -> dict:
    if name == "search_docs":
        return _tools.search_docs(tool_input.get("query", ""))
    if name == "get_schema":
        return _tools.get_schema()
    if name == "run_sql":
        return _tools.run_sql(tool_input.get("query", ""))
    return {"is_error": True, "error": f"Unknown tool: {name}"}


def _summarise(name: str, result: dict) -> str:
    if result.get("is_error"):
        return f"Error: {result.get('error', 'unknown')}"
    if name == "run_sql":
        n = result.get("row_count", 0)
        return f"{n} row{'s' if n != 1 else ''} returned"
    if name == "get_schema":
        n = result.get("schema", "").count("CREATE TABLE")
        return f"{n} table{'s' if n != 1 else ''} found"
    if name == "search_docs":
        n = len(result.get("chunks", []))
        return f"{n} chunk{'s' if n != 1 else ''} found"
    return "done"


# ---------------------------------------------------------------------------
# Main agentic loop
# ---------------------------------------------------------------------------

EventType = str
EventData = dict

MAX_ITERATIONS = 10


def chat_stream(
    session_id: str, message: str
) -> Generator[tuple[EventType, EventData], None, None]:
    """Drive the agentic loop and yield ``(event_type, event_data)`` tuples.

    Event types: ``"text"``, ``"tool_start"``, ``"tool_end"``, ``"done"``
    """
    history = get_or_create_history(session_id)
    history.append({"role": "user", "content": message})

    client = anthropic.Anthropic()

    for _ in range(MAX_ITERATIONS):
        response = client.messages.create(
            model="claude-opus-4-8",
            max_tokens=8192,
            system=SYSTEM_PROMPT,
            tools=TOOLS_DEFINITION,
            messages=history,
        )

        assistant_content: list[dict] = []
        tool_results: list[dict] = []

        for block in response.content:
            if block.type == "text":
                yield ("text", {"text": block.text})
                assistant_content.append({"type": "text", "text": block.text})

            elif block.type == "tool_use":
                yield ("tool_start", {"name": block.name, "input": block.input})

                result = _dispatch(block.name, block.input)
                summary = _summarise(block.name, result)

                yield ("tool_end", {"name": block.name, "summary": summary})

                assistant_content.append(
                    {
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    }
                )

                tool_result: dict = {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result),
                }
                if result.get("is_error"):
                    tool_result["is_error"] = True
                tool_results.append(tool_result)

        # Update history with assistant turn
        history.append({"role": "assistant", "content": assistant_content})

        if response.stop_reason == "end_turn":
            break

        # Feed tool results back and continue loop
        if tool_results:
            history.append({"role": "user", "content": tool_results})

    yield ("done", {})
