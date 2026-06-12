"""
Claude agentic loop with SSE event streaming.

Exported interface
------------------
    async def get_response_stream(
        history: list[dict],
        user_message: str,
    ) -> AsyncIterator[dict[str, str]]:

Yields dicts shaped for sse-starlette:
    {"event": "text",       "data": '{"text": "..."}'}
    {"event": "tool_start", "data": '{"name": "...", "input": {...}}'}
    {"event": "tool_end",   "data": '{"name": "...", "summary": "..."}'}
    {"event": "done",       "data": "{}"}
"""

from __future__ import annotations

import json
import os
from typing import Any, AsyncIterator

import anthropic

from app import tools

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
# Public API
# ---------------------------------------------------------------------------


async def get_response_stream(
    history: list[dict],
    user_message: str,
) -> AsyncIterator[dict[str, str]]:
    """
    Add *user_message* to *history*, run the agentic Claude loop, and yield
    SSE event dicts until the turn is fully complete.

    *history* is mutated in-place so the caller's reference stays up-to-date.
    """
    history.append({"role": "user", "content": user_message})

    client = anthropic.AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    while True:
        # ------------------------------------------------------------------ #
        # Stream one Claude turn                                               #
        # ------------------------------------------------------------------ #
        async with client.messages.stream(
            model=MODEL,
            system=SYSTEM_PROMPT,
            messages=history,
            tools=tools.TOOL_DEFINITIONS,
            max_tokens=MAX_TOKENS,
            thinking={"type": "enabled", "budget_tokens": 8000},
        ) as stream:
            async for event in stream:
                if (
                    event.type == "content_block_delta"
                    and event.delta.type == "text_delta"
                ):
                    yield {
                        "event": "text",
                        "data": json.dumps({"text": event.delta.text}),
                    }

            final_message = await stream.get_final_message()

        # ------------------------------------------------------------------ #
        # Persist assistant turn in history                                    #
        # ------------------------------------------------------------------ #
        history.append(
            {
                "role": "assistant",
                "content": _blocks_to_history(final_message.content),
            }
        )

        # ------------------------------------------------------------------ #
        # Determine whether the turn ended with tool calls                     #
        # ------------------------------------------------------------------ #
        if final_message.stop_reason != "tool_use":
            yield {"event": "done", "data": "{}"}
            return

        # ------------------------------------------------------------------ #
        # Execute tool calls and stream progress events                        #
        # ------------------------------------------------------------------ #
        tool_use_blocks = [
            b for b in final_message.content if b.type == "tool_use"
        ]
        tool_results: list[dict] = []

        for block in tool_use_blocks:
            tool_input: dict[str, Any] = block.input  # type: ignore[assignment]

            # Notify UI that a tool is starting
            yield {
                "event": "tool_start",
                "data": json.dumps({"name": block.name, "input": tool_input}),
            }

            # Execute
            result = await tools.execute_tool(block.name, tool_input)
            is_error = isinstance(result, dict) and result.get("is_error", False)

            # Notify UI that the tool finished
            summary = tools.summarise_result(block.name, result)
            yield {
                "event": "tool_end",
                "data": json.dumps({"name": block.name, "summary": summary}),
            }

            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": (
                        result
                        if isinstance(result, str)
                        else json.dumps(result)
                    ),
                    **({"is_error": True} if is_error else {}),
                }
            )

        # Feed tool results back so the loop continues
        history.append({"role": "user", "content": tool_results})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _blocks_to_history(content_blocks: list) -> list[dict]:
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
