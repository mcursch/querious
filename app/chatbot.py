"""
Claude agentic loop with event streaming.

Exported interface
------------------
    async def run_chat(
        history: list[dict],
        user_message: str,
    ) -> AsyncIterator[dict]:

Yields plain dicts:
    {"type": "text",       "text": "..."}
    {"type": "tool_start", "name": "...", "input": {...}}
    {"type": "tool_end",   "name": "...", "summary": "..."}
    {"type": "done"}
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

import anthropic

from app.tools import execute_tool, summarise_result, TOOL_DEFINITIONS

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MODEL = "claude-opus-4-8"
MAX_TOKENS = 16000  # generous headroom for thinking + long responses

SYSTEM_PROMPT = """You are Querious, the internal AI assistant for Acme Outfitters, \
an outdoor-gear retailer.

Your job is to answer questions from Acme employees accurately and thoroughly, \
drawing on two sources of information:

1. **Company documents** (policies, handbooks, product guides, etc.)
   → Use the `search_docs` tool for any question about policies, procedures, \
product specs, employee handbook rules, shipping terms, warranties, onboarding, \
or any other unstructured company knowledge.

2. **The company database** (customers, orders, products, invoices, payments, \
support tickets, employees)
   → Use `get_schema` first if you haven't seen the schema this conversation, \
then use `run_sql` to query. Always show the SQL you executed when summarising \
the results.

Guidelines:
- Cite the source file(s) when answering from documents.
- When a SQL query errors, read the error, fix the query, and retry. \
Do not give up after a single failure.
- You may call multiple tools in a single turn and combine results.
- Be concise but complete; use markdown formatting for tables and code blocks.
- Never fabricate data. If you don't know, say so and suggest how to find out."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_client() -> anthropic.AsyncAnthropic:
    """Return an AsyncAnthropic client (isolated here so tests can mock it)."""
    return anthropic.AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def run_chat(
    history: list[dict],
    user_message: str,
) -> AsyncIterator[dict]:
    """
    Add *user_message* to *history*, run the agentic Claude loop, and yield
    event dicts until the turn is fully complete.

    *history* is mutated in-place so the caller's reference stays up-to-date.
    """
    history.append({"role": "user", "content": user_message})

    client = _get_client()

    while True:
        # ------------------------------------------------------------------ #
        # Stream one Claude turn                                               #
        # ------------------------------------------------------------------ #
        async with client.messages.stream(
            model=MODEL,
            system=SYSTEM_PROMPT,
            messages=history,
            tools=TOOL_DEFINITIONS,
            max_tokens=MAX_TOKENS,
            thinking={"type": "enabled", "budget_tokens": 8000},
        ) as stream:
            async for chunk in stream.text_stream:
                if chunk:
                    yield {"type": "text", "text": chunk}

            final_message = await stream.get_final_message()

        # ------------------------------------------------------------------ #
        # Persist assistant turn in history                                    #
        # ------------------------------------------------------------------ #
        history.append(
            {
                "role": "assistant",
                "content": _content_blocks_to_dicts(final_message.content),
            }
        )

        # ------------------------------------------------------------------ #
        # Determine whether the turn ended with tool calls                     #
        # ------------------------------------------------------------------ #
        tool_use_blocks = [
            b for b in final_message.content if b.type == "tool_use"
        ]
        if not tool_use_blocks:
            yield {"type": "done"}
            return

        # ------------------------------------------------------------------ #
        # Execute tool calls and stream progress events                        #
        # ------------------------------------------------------------------ #
        tool_results: list[dict] = []

        for block in tool_use_blocks:
            tool_input: dict[str, Any] = block.input  # type: ignore[assignment]

            # Notify UI that a tool is starting
            yield {"type": "tool_start", "name": block.name, "input": tool_input}

            # Execute
            result = await execute_tool(block.name, tool_input)
            is_error = isinstance(result, dict) and result.get("is_error", False)

            # Notify UI that the tool finished
            summary = summarise_result(block.name, result)
            end_event: dict[str, Any] = {
                "type": "tool_end",
                "name": block.name,
                "summary": summary,
            }
            # Expose source filenames so callers (e.g. ChatSession) can populate
            # TurnResult.sources without having to re-invoke the tool.
            if (
                block.name == "search_docs"
                and isinstance(result, dict)
                and "chunks" in result
            ):
                end_event["sources"] = [
                    c["source"] for c in result["chunks"] if "source" in c
                ]
            yield end_event

            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": (
                        result
                        if isinstance(result, str)
                        else str(result)
                    ),
                    **({"is_error": True} if is_error else {}),
                }
            )

        # Feed tool results back so the loop continues
        history.append({"role": "user", "content": tool_results})


# ---------------------------------------------------------------------------
# Synchronous session wrapper
# ---------------------------------------------------------------------------


@dataclass
class TurnResult:
    """Holds the full output of a single chat turn.

    Attributes:
        text:       The complete assistant response text for this turn.
        sources:    Deduplicated list of document source filenames cited by
                    any ``search_docs`` tool calls made during the turn.
        tool_calls: Ordered list of tool invocations, each a dict with at
                    minimum a ``"name"`` key and an ``"input"`` key.
    """

    text: str
    sources: list[str] = field(default_factory=list)
    tool_calls: list[dict] = field(default_factory=list)


class ChatSession:
    """Synchronous wrapper around the :func:`run_chat` agentic loop.

    Maintains conversation history across turns so that each call to
    :meth:`send_message` continues the same multi-turn conversation.

    Example::

        session = ChatSession()
        result = session.send_message("What is the return policy on used tents?")
        print(result.text)
        print(result.sources)   # e.g. ['return_refund_policy.md']
    """

    def __init__(self) -> None:
        self._history: list[dict] = []

    def send_message(self, message: str) -> TurnResult:
        """Run one turn synchronously and return a :class:`TurnResult`.

        The internal conversation history is updated in-place so subsequent
        calls continue where the previous turn left off.
        """
        text_parts: list[str] = []
        tool_calls: list[dict] = []
        # Use a dict keyed by source to preserve insertion order while
        # deduplicating across multiple search_docs calls in the same turn.
        seen_sources: dict[str, None] = {}

        async def _collect() -> None:
            async for event in run_chat(self._history, message):
                if event["type"] == "text":
                    text_parts.append(event["text"])
                elif event["type"] == "tool_start":
                    tool_calls.append(
                        {"name": event["name"], "input": event.get("input", {})}
                    )
                elif event["type"] == "tool_end":
                    for src in event.get("sources", []):
                        seen_sources[src] = None

        asyncio.run(_collect())

        return TurnResult(
            text="".join(text_parts),
            sources=list(seen_sources),
            tool_calls=tool_calls,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _content_blocks_to_dicts(content_blocks: list) -> list[dict]:
    """
    Convert API response content blocks to plain dicts suitable for storing
    in the history list and re-sending to the API.

    Thinking blocks are preserved (with their signature) so that subsequent
    API calls remain valid when extended thinking is active.
    """
    result: list[dict] = []
    for block in content_blocks:
        if block.type == "text":
            result.append({"type": "text", "text": block.text})
        elif block.type == "thinking":
            entry: dict = {"type": "thinking", "thinking": block.thinking}
            # signature is required by the API when passing thinking blocks back
            if getattr(block, "signature", None):
                entry["signature"] = block.signature
            result.append(entry)
        elif block.type == "tool_use":
            result.append(
                {
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                }
            )
    return result
