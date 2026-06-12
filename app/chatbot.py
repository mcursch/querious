"""Claude agentic loop for the Querious chatbot."""
import json
import os
from dataclasses import dataclass, field
from typing import Any

import anthropic

from app.tools import TOOL_DEFINITIONS, execute_tool

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MODEL = os.environ.get("QUERIOUS_MODEL", "claude-opus-4-5")
MAX_TOKENS = 4096
MAX_TOOL_ROUNDS = 10  # safety valve

SYSTEM_PROMPT = """\
You are Querious, the internal AI assistant for Acme Outfitters — an outdoor-gear retailer.

Guidelines:
- For policy, handbook, or product-documentation questions, call `search_docs` and cite the \
source files you used (e.g., "According to return_refund_policy.md, ...").
- For data questions (counts, lists, lookups, aggregations over the database), call `get_schema` \
first if you have not seen the schema this conversation, then `run_sql`.
- For combined questions, use both: retrieve relevant policy text AND query the database.
- Always cite document sources when you use `search_docs`.
- Show the SQL you ran (briefly) when summarising query results.
- If a SQL query returns an error, fix it and retry — do not give up.
- Be concise, factual, and helpful. You are answering questions from Acme Outfitters employees.
"""

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

# Maps session_id -> list of message dicts
_sessions: dict[str, list[dict]] = {}


def get_or_create_history(session_id: str) -> list[dict]:
    if session_id not in _sessions:
        _sessions[session_id] = []
    return _sessions[session_id]


def clear_session(session_id: str) -> None:
    _sessions.pop(session_id, None)


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class TurnResult:
    """Structured result from one chatbot turn."""
    text: str
    """Full assistant text (all text blocks concatenated)."""
    sources: list[str] = field(default_factory=list)
    """Document filenames cited (from search_docs results)."""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    """Tool calls made this turn: list of {"name": ..., "input": ..., "result": ...}."""


# ---------------------------------------------------------------------------
# Agentic loop (synchronous, non-streaming)
# ---------------------------------------------------------------------------

def run_turn(session_id: str, message: str) -> TurnResult:
    """
    Run one conversational turn.

    Appends the user message to the session history, drives the Claude
    agentic loop (tool calls + results) to completion, appends the final
    assistant message to history, and returns a structured TurnResult.
    """
    client = anthropic.Anthropic()
    history = get_or_create_history(session_id)

    # Append the new user message
    history.append({"role": "user", "content": message})

    all_tool_calls: list[dict[str, Any]] = []
    all_sources: list[str] = []
    final_text_parts: list[str] = []

    for _round in range(MAX_TOOL_ROUNDS):
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            tools=TOOL_DEFINITIONS,
            messages=history,
        )

        # Collect text from this response
        text_this_round = ""
        tool_use_blocks: list[anthropic.types.ToolUseBlock] = []

        for block in response.content:
            if block.type == "text":
                text_this_round += block.text
            elif block.type == "tool_use":
                tool_use_blocks.append(block)

        if text_this_round:
            final_text_parts.append(text_this_round)

        # Add the assistant turn to history (the full content list)
        history.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn" or not tool_use_blocks:
            # Done — no more tool calls
            break

        # Execute each tool call and build tool_result messages
        tool_result_contents: list[dict] = []
        for block in tool_use_blocks:
            result = execute_tool(block.name, block.input)

            # Track sources from search_docs
            if block.name == "search_docs" and "sources" in result:
                for src in result["sources"]:
                    if src not in all_sources:
                        all_sources.append(src)

            all_tool_calls.append(
                {"name": block.name, "input": block.input, "result": result}
            )

            tool_result_contents.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result),
                }
            )

        # Append tool results as a user turn
        history.append({"role": "user", "content": tool_result_contents})

    full_text = "\n".join(final_text_parts)

    return TurnResult(
        text=full_text,
        sources=all_sources,
        tool_calls=all_tool_calls,
    )


# ---------------------------------------------------------------------------
# Convenience class wrapping run_turn with a persistent session id
# ---------------------------------------------------------------------------

class ChatSession:
    """High-level wrapper around the agentic loop for a single conversation."""

    def __init__(self, session_id: str | None = None) -> None:
        import uuid

        self.session_id = session_id or str(uuid.uuid4())

    def send_message(self, message: str) -> TurnResult:
        """Send a message and return the structured turn result."""
        return run_turn(self.session_id, message)

    def reset(self) -> None:
        """Clear conversation history for this session."""
        clear_session(self.session_id)
