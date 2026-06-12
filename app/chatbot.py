"""
Querious — manual Claude agentic tool loop with per-session history.

Public API
----------
chat(session_id, user_message) -> AsyncGenerator[dict, None]
    Accept a session identifier and a new user message string.
    Yield typed SSE payload dicts; always ends with a ``done`` dict.

Session history
---------------
Conversation histories are stored in the module-level ``_sessions`` dict,
keyed by session_id (str).  Each value is a list of message dicts in
Claude's messages-array format.  History persists for the lifetime of the
process (i.e. across turns) and is extended in place each turn.

SSE payload shapes
------------------
{"type": "text",       "text": "..."}
{"type": "tool_start", "name": "...", "input": {...}}
{"type": "tool_end",   "name": "...", "summary": "..."}
{"type": "done"}

Agentic loop behaviour
----------------------
1. Append the new user message to the session's history.
2. Call Claude with streaming; yield text deltas as they arrive.
3. After the stream completes, inspect stop_reason.
4. If stop_reason != "tool_use" → yield ``done`` and return.
5. For each tool_use block in the response:
     a. Yield ``tool_start`` with the tool name and parsed input.
     b. Execute the tool (via _dispatch_tool).
     c. Yield ``tool_end`` with a short summary.
     d. Collect a tool_result message for Claude (is_error=true on failure so
        Claude can self-correct rather than the error surfacing to the user).
6. Append the assistant turn and the tool-result user turn to the history.
7. Go to step 2.

No import-time side effects: the Anthropic client is created lazily on first
use.  Modules can be imported safely even when acme.db does not exist.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import AsyncGenerator
from typing import Any

import anthropic

from app.tools import TOOL_DEFINITIONS, get_schema, run_sql, search_docs

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MODEL = "claude-opus-4-8"
MAX_TOKENS = 16_000
MAX_TOOL_ROUNDS = 10

# Beta flag required for interleaved (thinking + tool_use) streaming
_THINKING_BETAS = ["interleaved-thinking-2025-05-14"]

SYSTEM_PROMPT = """\
You are Querious, the internal AI assistant for Acme Outfitters — an outdoor gear retailer.
You help employees get accurate answers about company policies, products, and data.

## How to answer questions

**Unstructured / policy questions** (returns, shipping, warranties, employee handbook, SLA, etc.)
→ Use the `search_docs` tool to retrieve relevant document excerpts, then answer citing sources.

**Data questions** (counts, lists, lookups, aggregations, financial summaries, etc.)
→ If you haven't seen the schema this conversation, call `get_schema` first.
  Then write a clean SQLite SELECT and call `run_sql`.
  Always show the SQL you ran when summarising the results.

**Combined questions** (policy + matching data) → use both paths in the same turn.

## Rules
- Cite source filenames when answering from documentation (e.g. "per return_refund_policy.md").
- Show the SQL query inside a code block when presenting data results.
- If a SQL query errors, read the error message, fix the query, and retry — do not give up.
- Keep answers concise and factual; avoid speculation beyond the retrieved data.
"""

# ---------------------------------------------------------------------------
# Per-session conversation history
# Key: session_id (str)
# Value: list of message dicts in Claude's messages-array format
# ---------------------------------------------------------------------------
_sessions: dict[str, list[dict[str, Any]]] = {}

# ---------------------------------------------------------------------------
# Lazy Anthropic client
# ---------------------------------------------------------------------------

_client: anthropic.AsyncAnthropic | None = None


def _get_client() -> anthropic.AsyncAnthropic:
    """Return the shared AsyncAnthropic client, creating it on first call."""
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(
            api_key=os.environ.get("ANTHROPIC_API_KEY"),
        )
    return _client


# ---------------------------------------------------------------------------
# Tool dispatcher
# ---------------------------------------------------------------------------


def _dispatch_tool(name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
    """
    Run a tool synchronously and return a normalised result dict with keys:

    - ``content`` (str)  — serialised result to pass back to Claude
    - ``summary`` (str)  — one-liner description for the ``tool_end`` SSE event
    - ``is_error`` (bool) — True if the tool failed (Claude should self-correct)
    """
    try:
        if name == "search_docs":
            query = (tool_input.get("query") or "").strip()
            if not query:
                return {
                    "content": "No query provided to search_docs.",
                    "summary": "error: empty query",
                    "is_error": True,
                }
            result = search_docs(query)
            chunks = result.get("chunks", [])
            summary = f"{len(chunks)} chunk{'s' if len(chunks) != 1 else ''} retrieved"
            return {
                "content": json.dumps(result),
                "summary": summary,
                "is_error": False,
            }

        elif name == "get_schema":
            result = get_schema()
            is_error = result.get("is_error", False)
            summary = "error: schema unavailable" if is_error else "schema retrieved"
            return {
                "content": json.dumps(result),
                "summary": summary,
                "is_error": bool(is_error),
            }

        elif name == "run_sql":
            query = (tool_input.get("query") or "").strip()
            if not query:
                return {
                    "content": "No SQL query provided to run_sql.",
                    "summary": "error: empty query",
                    "is_error": True,
                }
            result = run_sql(query)
            is_error = result.get("is_error", False)
            if is_error:
                msg = result.get("message", "unknown error")
                summary = f"error: {msg[:80]}"
            else:
                row_count = len(result.get("rows", []))
                summary = f"{row_count} row{'s' if row_count != 1 else ''}"
            return {
                "content": json.dumps(result),
                "summary": summary,
                "is_error": bool(is_error),
            }

        else:
            return {
                "content": f"Unknown tool: '{name}'.",
                "summary": f"error: unknown tool '{name}'",
                "is_error": True,
            }

    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error dispatching tool '%s'", name)
        return {
            "content": f"Internal error executing {name}: {exc}",
            "summary": f"error: {exc}",
            "is_error": True,
        }


# ---------------------------------------------------------------------------
# Content-block serialiser
# ---------------------------------------------------------------------------


def _content_blocks_to_dicts(content: list[Any]) -> list[dict[str, Any]]:
    """
    Convert Anthropic content-block objects to plain dicts suitable for the
    messages array on subsequent API calls.

    Thinking blocks are preserved so Claude maintains chain-of-thought
    continuity (required by the interleaved-thinking beta).
    """
    result: list[dict[str, Any]] = []
    for block in content:
        block_type = block.type

        if block_type == "text":
            result.append({"type": "text", "text": block.text})

        elif block_type == "thinking":
            entry: dict[str, Any] = {
                "type": "thinking",
                "thinking": block.thinking,
            }
            if hasattr(block, "signature") and block.signature:
                entry["signature"] = block.signature
            result.append(entry)

        elif block_type == "tool_use":
            result.append(
                {
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                }
            )

        else:
            # Forward unknown block types as-is
            if hasattr(block, "model_dump"):
                result.append(block.model_dump())
            elif hasattr(block, "__dict__"):
                result.append(dict(block.__dict__))

    return result


# ---------------------------------------------------------------------------
# Agentic loop
# ---------------------------------------------------------------------------


async def chat(
    session_id: str,
    user_message: str,
) -> AsyncGenerator[dict[str, Any], None]:
    """
    Manual agentic loop with per-session history.

    Accepts a *session_id* (creates a new session on first use) and a
    *user_message* string.  Yields SSE payload dicts; always ends with
    ``{"type": "done"}``.

    Parameters
    ----------
    session_id:
        Opaque string that identifies the conversation.  A new, empty history
        is created automatically on first use.  Subsequent calls with the same
        id continue the same conversation.
    user_message:
        The new user turn (plain text string).
    """
    # Retrieve (or create) the session history.
    # Snapshot the current length so we can roll back if the API call fails
    # before an assistant turn is ever appended (which would leave a dangling
    # user-only entry that the API would reject on the next call).
    history = _sessions.setdefault(session_id, [])
    snapshot = len(history)
    history.append({"role": "user", "content": user_message})

    client = _get_client()

    try:
        tool_round = 0
        while True:
            # ------------------------------------------------------------------
            # Stream the next Claude response
            # ------------------------------------------------------------------
            async with client.messages.stream(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
                messages=history,
                tools=TOOL_DEFINITIONS,
                thinking={"type": "adaptive"},
                extra_headers={"anthropic-beta": ", ".join(_THINKING_BETAS)},
            ) as stream:
                # Yield text deltas in real-time.
                # text_stream skips thinking/tool_use blocks automatically.
                async for text_chunk in stream.text_stream:
                    if text_chunk:
                        yield {"type": "text", "text": text_chunk}

                # Collect the fully-accumulated final message.
                final_message = await stream.get_final_message()

            # ------------------------------------------------------------------
            # Persist the assistant turn to session history
            # ------------------------------------------------------------------
            assistant_content = _content_blocks_to_dicts(final_message.content)
            history.append({"role": "assistant", "content": assistant_content})

            # ------------------------------------------------------------------
            # Check whether Claude wants to call tools
            # ------------------------------------------------------------------
            tool_use_blocks = [
                b for b in final_message.content if b.type == "tool_use"
            ]

            if not tool_use_blocks:
                # Claude is done — no more tool calls requested.
                break

            # ------------------------------------------------------------------
            # Guard against infinite agentic loops
            # ------------------------------------------------------------------
            tool_round += 1
            if tool_round > MAX_TOOL_ROUNDS:
                logger.warning(
                    "Exceeded MAX_TOOL_ROUNDS (%d) for session=%s; aborting loop",
                    MAX_TOOL_ROUNDS,
                    session_id,
                )
                yield {
                    "type": "text",
                    "text": f"\n\n[Error: exceeded maximum tool rounds ({MAX_TOOL_ROUNDS}); stopping.]",
                }
                break

            # ------------------------------------------------------------------
            # Execute each tool and collect results for the next Claude turn
            # ------------------------------------------------------------------
            tool_results: list[dict[str, Any]] = []

            for tu in tool_use_blocks:
                tool_name = tu.name
                tool_input: dict[str, Any] = (
                    tu.input if isinstance(tu.input, dict) else {}
                )

                # Signal to the UI that we are about to run this tool.
                yield {"type": "tool_start", "name": tool_name, "input": tool_input}

                # Run the (blocking) tool in a thread pool so we don't stall
                # other coroutines on the asyncio event loop.
                dispatched = await asyncio.to_thread(_dispatch_tool, tool_name, tool_input)
                is_error: bool = dispatched["is_error"]
                content_str: str = dispatched["content"]
                summary: str = dispatched["summary"]

                # Signal to the UI that the tool has finished.
                yield {"type": "tool_end", "name": tool_name, "summary": summary}

                # Build the tool_result entry for the next Claude turn.
                # Errors are reported back with is_error=true so Claude can
                # self-correct rather than giving up.
                tool_result: dict[str, Any] = {
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": content_str,
                }
                if is_error:
                    tool_result["is_error"] = True

                tool_results.append(tool_result)

            # ------------------------------------------------------------------
            # Feed tool results back to Claude for the next iteration
            # ------------------------------------------------------------------
            history.append({"role": "user", "content": tool_results})

    except Exception as exc:
        # Roll back any history entries added during this failed turn so the
        # session is not left in a broken state (e.g. a dangling user-only entry
        # that the API would reject on the next call).
        del history[snapshot:]
        logger.exception("Unhandled error in chat agentic loop (session=%s)", session_id)
        yield {"type": "text", "text": f"\n\n[Error: {exc}]"}

    finally:
        # Always emit done, even on exception paths.
        yield {"type": "done"}


# ---------------------------------------------------------------------------
# Session utilities
# ---------------------------------------------------------------------------


def get_history(session_id: str) -> list[dict[str, Any]]:
    """Return a copy of the current message history for *session_id*."""
    return list(_sessions.get(session_id, []))


def clear_history(session_id: str) -> None:
    """Delete the history for *session_id* (no-op if session does not exist)."""
    _sessions.pop(session_id, None)
