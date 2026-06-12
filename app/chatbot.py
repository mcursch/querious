"""
Manual Claude agentic loop with SSE streaming.

Public API
----------
run_chat(history, user_message) -> AsyncGenerator[dict, None]
    Accepts a session history list (in Claude message-array format) and a new
    user message string.  Yields typed SSE payload dicts and ALWAYS yields a
    ``done`` dict as its final item.

SSE payload shapes
------------------
{"type": "text",       "text": "..."}
{"type": "tool_start", "name": "...", "input": {...}}
{"type": "tool_end",   "name": "...", "summary": "..."}
{"type": "done"}

Agentic loop behaviour
----------------------
1. Append the new user message to the history copy.
2. Call Claude with streaming; yield text deltas as they arrive.
3. After the stream completes, inspect the response for tool_use blocks.
4. If none → yield ``done`` and return.
5. For each tool_use block:
     a. Yield ``tool_start`` with the tool name and parsed input.
     b. Execute the tool (via app.tools.execute_tool).
     c. Yield ``tool_end`` with a short summary.
     d. Collect a tool_result message for Claude (is_error=true on failure so
        Claude can self-correct rather than the error surfacing to the user).
6. Append the assistant turn and the tool-result user turn to the message list.
7. Go to step 2.
"""

import logging
import os
from collections.abc import AsyncGenerator
from typing import Any

import anthropic

from app.tools import TOOL_DEFINITIONS, execute_tool

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MODEL = "claude-opus-4-8"
MAX_TOKENS = 16000

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
# Client
# ---------------------------------------------------------------------------

_client: anthropic.AsyncAnthropic | None = None


def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(
            api_key=os.environ.get("ANTHROPIC_API_KEY"),
        )
    return _client


# ---------------------------------------------------------------------------
# Agentic loop
# ---------------------------------------------------------------------------


async def run_chat(
    history: list[dict[str, Any]],
    user_message: str,
) -> AsyncGenerator[dict[str, Any], None]:
    """
    Manual agentic loop.  Yields SSE payload dicts; always ends with ``done``.

    Parameters
    ----------
    history:
        Existing conversation messages in Claude's array format.
        Each item is ``{"role": "user"|"assistant", "content": ...}``.
        The list is not mutated; a local copy is maintained for looping.
    user_message:
        The new user turn (plain string).
    """
    client = _get_client()

    # Build a mutable local copy of the conversation
    messages: list[dict[str, Any]] = list(history) + [
        {"role": "user", "content": user_message}
    ]

    try:
        while True:
            # ------------------------------------------------------------------
            # Stream the next Claude response
            # ------------------------------------------------------------------
            async with client.messages.stream(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
                messages=messages,
                tools=TOOL_DEFINITIONS,
                thinking={"type": "adaptive"},
                extra_headers={"anthropic-beta": ", ".join(_THINKING_BETAS)},
            ) as stream:
                # Yield text deltas as they arrive (thinking deltas are ignored
                # by text_stream — only assistant prose is forwarded to the UI).
                async for text_chunk in stream.text_stream:
                    if text_chunk:
                        yield {"type": "text", "text": text_chunk}

                # Collect the fully-accumulated message after streaming ends.
                final_message = await stream.get_final_message()

            # ------------------------------------------------------------------
            # Append the assistant turn to the local history
            # ------------------------------------------------------------------
            # final_message.content is a list of content block objects; we
            # serialise each one to a plain dict for the message array.
            assistant_content = _content_blocks_to_dicts(final_message.content)
            messages.append({"role": "assistant", "content": assistant_content})

            # ------------------------------------------------------------------
            # Find tool_use blocks
            # ------------------------------------------------------------------
            tool_use_blocks = [
                b for b in final_message.content if b.type == "tool_use"
            ]

            if not tool_use_blocks:
                # Claude is done — no more tool calls requested.
                break

            # ------------------------------------------------------------------
            # Execute each tool and collect results
            # ------------------------------------------------------------------
            tool_results: list[dict[str, Any]] = []

            for tu in tool_use_blocks:
                tool_name = tu.name
                tool_input: dict[str, Any] = tu.input if isinstance(tu.input, dict) else {}

                # Signal to the UI that we are about to run this tool
                yield {"type": "tool_start", "name": tool_name, "input": tool_input}

                try:
                    result = await execute_tool(tool_name, tool_input)
                    is_error: bool = result.get("is_error", False)
                    content_str: str = result.get("content", "")
                    summary: str = result.get("summary", "done")
                except Exception as exc:
                    logger.exception("Unexpected error executing tool '%s'", tool_name)
                    is_error = True
                    content_str = f"Internal error executing {tool_name}: {exc}"
                    summary = f"error: {exc}"

                # Signal to the UI that the tool has finished
                yield {"type": "tool_end", "name": tool_name, "summary": summary}

                # Build the tool_result entry for the next Claude turn.
                # Errors are reported back to Claude (is_error=true) so it can
                # self-correct rather than surfacing the error to the user.
                tool_result: dict[str, Any] = {
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": content_str,
                }
                if is_error:
                    tool_result["is_error"] = True

                tool_results.append(tool_result)

            # ------------------------------------------------------------------
            # Feed tool results back to Claude for the next loop iteration
            # ------------------------------------------------------------------
            messages.append({"role": "user", "content": tool_results})

    except Exception as exc:
        logger.exception("Unhandled error in run_chat agentic loop")
        yield {"type": "text", "text": f"\n\n[Error: {exc}]"}

    finally:
        # Always emit done, even on exception paths
        yield {"type": "done"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _content_blocks_to_dicts(content: list[Any]) -> list[dict[str, Any]]:
    """
    Convert a list of Anthropic content block objects to plain dicts suitable
    for inclusion in the ``messages`` array on subsequent API calls.
    """
    result: list[dict[str, Any]] = []
    for block in content:
        block_type = block.type

        if block_type == "text":
            result.append({"type": "text", "text": block.text})

        elif block_type == "thinking":
            # Preserve thinking blocks so Claude maintains its chain-of-thought
            # across turns (required by the interleaved-thinking beta).
            result.append(
                {
                    "type": "thinking",
                    "thinking": block.thinking,
                    # signature is required when echoing thinking blocks back
                    **({"signature": block.signature} if hasattr(block, "signature") else {}),
                }
            )

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
            # Forward unknown block types as-is using model_dump if available
            if hasattr(block, "model_dump"):
                result.append(block.model_dump())
            elif hasattr(block, "__dict__"):
                result.append(dict(block.__dict__))

    return result
