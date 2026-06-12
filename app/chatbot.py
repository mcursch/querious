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

import os
from typing import Any, AsyncIterator

import anthropic

from app.tools import execute_tool, summarise_result, TOOL_DEFINITIONS

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MODEL = "claude-opus-4-5"
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
            yield {"type": "tool_end", "name": block.name, "summary": summary}

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
