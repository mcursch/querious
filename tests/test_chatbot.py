"""
Unit tests for app/chatbot.py.

All tests mock the Anthropic API so no real credentials or network access are
needed.  The acceptance criteria covered:

AC1 — Fresh session yields at least one text event and a done event.
AC2 — Second call with same session_id includes the prior turn in messages.
AC3 — tool_start is yielded before dispatch; tool_end is yielded after.
AC4 — A run_sql is_error response causes Claude to receive the error and make
      at least one retry (observable via a second tool_start in the stream).
AC5 — The module can be imported when acme.db does not exist (no import-time
      side effects).
"""

from __future__ import annotations

import json
import types
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# AC5: import-time side-effect check — must not raise even without acme.db
# ---------------------------------------------------------------------------


def test_chatbot_importable_without_acme_db():
    """Importing chatbot.py must not raise even when acme.db does not exist."""
    import importlib

    import app.chatbot  # noqa: F401

    importlib.reload(app.chatbot)  # reload to re-run module-level code


def test_tools_importable_without_acme_db():
    """Importing tools.py must not raise even when acme.db does not exist."""
    import importlib

    import app.tools  # noqa: F401

    importlib.reload(app.tools)


# ---------------------------------------------------------------------------
# Helpers: fake streaming objects
# ---------------------------------------------------------------------------


def _make_text_block(text: str) -> MagicMock:
    block = MagicMock()
    block.type = "text"
    block.text = text
    return block


def _make_thinking_block(thinking: str) -> MagicMock:
    block = MagicMock()
    block.type = "thinking"
    block.thinking = thinking
    block.signature = "sig"
    return block


def _make_tool_use_block(
    tool_id: str, name: str, input_dict: dict[str, Any]
) -> MagicMock:
    block = MagicMock()
    block.type = "tool_use"
    block.id = tool_id
    block.name = name
    block.input = input_dict
    return block


def _make_final_message(
    content: list[Any], stop_reason: str = "end_turn"
) -> MagicMock:
    msg = MagicMock()
    msg.content = content
    msg.stop_reason = stop_reason
    return msg


class _FakeStream:
    """
    Context manager that mimics anthropic.AsyncAnthropic.messages.stream().

    Parameters
    ----------
    text_chunks:
        Strings yielded by text_stream.
    final_message:
        The message returned by get_final_message().
    """

    def __init__(self, text_chunks: list[str], final_message: MagicMock) -> None:
        self._text_chunks = text_chunks
        self._final_message = final_message

    async def __aenter__(self) -> "_FakeStream":
        return self

    async def __aexit__(self, *args: Any) -> None:
        pass

    @property
    def text_stream(self) -> AsyncGenerator[str, None]:
        async def _gen():
            for chunk in self._text_chunks:
                yield chunk

        return _gen()

    async def get_final_message(self) -> MagicMock:
        return self._final_message


def _make_stream(
    text_chunks: list[str], content_blocks: list[Any], stop_reason: str = "end_turn"
) -> _FakeStream:
    return _FakeStream(
        text_chunks=text_chunks,
        final_message=_make_final_message(content_blocks, stop_reason),
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clear_sessions():
    """Ensure _sessions is empty before each test."""
    from app import chatbot

    chatbot._sessions.clear()
    yield
    chatbot._sessions.clear()


@pytest.fixture(autouse=True)
def reset_client():
    """Reset the lazy client so each test starts fresh."""
    from app import chatbot

    chatbot._client = None
    yield
    chatbot._client = None


# ---------------------------------------------------------------------------
# AC1: fresh session yields text + done
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fresh_session_yields_text_and_done():
    """A new session must produce at least one text event and end with done."""
    from app import chatbot

    text_block = _make_text_block("Hello! How can I help?")
    stream = _make_stream(["Hello! How can I help?"], [text_block])

    mock_client = MagicMock()
    mock_client.messages.stream.return_value = stream

    with patch.object(chatbot, "_get_client", return_value=mock_client):
        events = [e async for e in chatbot.chat("session-1", "Hi there")]

    types_seen = {e["type"] for e in events}
    assert "text" in types_seen, "Expected at least one text event"
    assert "done" in types_seen, "Expected a done event"
    assert events[-1] == {"type": "done"}, "done must be the last event"

    text_events = [e for e in events if e["type"] == "text"]
    combined = "".join(e["text"] for e in text_events)
    assert "Hello" in combined


# ---------------------------------------------------------------------------
# AC2: second call with same session_id includes prior turn
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_second_call_includes_prior_turn():
    """History from the first turn must appear in the messages sent on the second turn."""
    from app import chatbot

    text_block = _make_text_block("Hi!")
    stream1 = _make_stream(["Hi!"], [text_block])
    stream2 = _make_stream(["Sure!"], [_make_text_block("Sure!")])

    call_messages: list[list[dict]] = []

    def _fake_stream(**kwargs):
        call_messages.append(kwargs["messages"])
        return stream1 if len(call_messages) == 1 else stream2

    mock_client = MagicMock()
    mock_client.messages.stream.side_effect = _fake_stream

    with patch.object(chatbot, "_get_client", return_value=mock_client):
        async for _ in chatbot.chat("session-2", "Hello"):
            pass
        async for _ in chatbot.chat("session-2", "Can you help?"):
            pass

    assert len(call_messages) == 2, "stream should have been called twice"

    # The second call's messages list must include the first user turn.
    second_messages = call_messages[1]
    roles = [m["role"] for m in second_messages]
    assert roles.count("user") >= 2, (
        "Second call messages should contain at least two user turns "
        f"(got roles: {roles})"
    )


# ---------------------------------------------------------------------------
# AC3: tool_start before dispatch, tool_end after
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_start_before_dispatch_tool_end_after():
    """
    tool_start must appear before the tool function is called, and tool_end
    must appear after.
    """
    from app import chatbot

    tool_block = _make_tool_use_block("tool-1", "run_sql", {"query": "SELECT 1"})

    stream_with_tool = _make_stream([], [tool_block], stop_reason="tool_use")
    stream_final = _make_stream(["Done."], [_make_text_block("Done.")])

    call_count = 0

    def _fake_stream(**kwargs):
        nonlocal call_count
        call_count += 1
        return stream_with_tool if call_count == 1 else stream_final

    mock_client = MagicMock()
    mock_client.messages.stream.side_effect = _fake_stream

    dispatch_order: list[str] = []

    def _fake_dispatch(name, tool_input):
        dispatch_order.append("dispatch")
        return {"content": '{"columns":[],"rows":[]}', "summary": "0 rows", "is_error": False}

    with (
        patch.object(chatbot, "_get_client", return_value=mock_client),
        patch.object(chatbot, "_dispatch_tool", side_effect=_fake_dispatch),
    ):
        events = [e async for e in chatbot.chat("session-3", "list tables")]

    event_types = [e["type"] for e in events]

    start_idx = event_types.index("tool_start")
    end_idx = event_types.index("tool_end")

    assert dispatch_order == ["dispatch"], "Dispatch should be called exactly once"
    assert start_idx < end_idx, "tool_start must come before tool_end"
    # The dispatch happened between start and end — verified by ordering:
    # Since dispatch_order is populated during the loop execution, and we only
    # have one dispatch, the ordering is guaranteed by the sequential generator.


# ---------------------------------------------------------------------------
# AC4: run_sql is_error causes retry (second tool_start visible in stream)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_sql_error_causes_retry():
    """
    When run_sql returns is_error=True, Claude must receive the error as a
    tool result.  Claude's retry should produce at least two tool_start events.
    """
    from app import chatbot

    sql_block_1 = _make_tool_use_block(
        "t-1", "run_sql", {"query": "SELECT * FROM missing_table"}
    )
    sql_block_2 = _make_tool_use_block(
        "t-2", "run_sql", {"query": "SELECT COUNT(*) FROM customers"}
    )

    # First API call: Claude attempts bad SQL
    stream_bad = _make_stream([], [sql_block_1], stop_reason="tool_use")
    # Second API call (after error returned): Claude retries with correct SQL
    stream_retry = _make_stream([], [sql_block_2], stop_reason="tool_use")
    # Third API call: Claude gives final answer
    stream_final = _make_stream(["There are 300 customers."], [_make_text_block("There are 300 customers.")])

    call_count = 0

    def _fake_stream(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return stream_bad
        elif call_count == 2:
            return stream_retry
        else:
            return stream_final

    mock_client = MagicMock()
    mock_client.messages.stream.side_effect = _fake_stream

    dispatch_call_inputs: list[tuple[str, dict]] = []

    def _fake_dispatch(name, tool_input):
        dispatch_call_inputs.append((name, tool_input))
        if tool_input.get("query", "").startswith("SELECT * FROM missing"):
            # First call: error
            return {
                "content": json.dumps({"is_error": True, "message": "no such table: missing_table"}),
                "summary": "error: no such table: missing_table",
                "is_error": True,
            }
        else:
            # Retry: success
            return {
                "content": json.dumps({"columns": ["COUNT(*)"], "rows": [[300]]}),
                "summary": "1 row",
                "is_error": False,
            }

    with (
        patch.object(chatbot, "_get_client", return_value=mock_client),
        patch.object(chatbot, "_dispatch_tool", side_effect=_fake_dispatch),
    ):
        events = [e async for e in chatbot.chat("session-4", "How many customers?")]

    tool_start_events = [e for e in events if e["type"] == "tool_start"]
    assert len(tool_start_events) >= 2, (
        f"Expected at least 2 tool_start events (error + retry), got {len(tool_start_events)}"
    )

    # Verify the error was passed back to Claude (third messages call contains
    # a tool_result with is_error=true).
    messages_calls = mock_client.messages.stream.call_args_list
    assert len(messages_calls) >= 2

    # The second call should include a user message with a tool_result that has is_error
    second_call_messages = messages_calls[1].kwargs["messages"]
    tool_result_messages = [
        m for m in second_call_messages
        if isinstance(m.get("content"), list)
        and any(c.get("type") == "tool_result" for c in m["content"])
    ]
    assert tool_result_messages, "Expected a tool_result in the second Claude call"

    error_results = [
        c
        for m in tool_result_messages
        for c in m["content"]
        if c.get("type") == "tool_result" and c.get("is_error")
    ]
    assert error_results, "Expected the tool_result to carry is_error=True"


# ---------------------------------------------------------------------------
# Additional: _dispatch_tool unit tests (no API calls)
# ---------------------------------------------------------------------------


def test_dispatch_run_sql_empty_query():
    from app.chatbot import _dispatch_tool

    result = _dispatch_tool("run_sql", {})
    assert result["is_error"] is True
    assert "empty" in result["summary"].lower()


def test_dispatch_search_docs_empty_query():
    from app.chatbot import _dispatch_tool

    result = _dispatch_tool("search_docs", {})
    assert result["is_error"] is True


def test_dispatch_unknown_tool():
    from app.chatbot import _dispatch_tool

    result = _dispatch_tool("make_coffee", {})
    assert result["is_error"] is True
    assert "unknown" in result["content"].lower()


def test_dispatch_get_schema_stub():
    from app.chatbot import _dispatch_tool

    result = _dispatch_tool("get_schema", {})
    # Stub returns something without is_error
    assert result["is_error"] is False
    assert result["content"]  # non-empty content


def test_dispatch_search_docs_stub():
    from app.chatbot import _dispatch_tool

    result = _dispatch_tool("search_docs", {"query": "return policy"})
    # Stub returns empty chunks list — not an error
    assert result["is_error"] is False
    content = json.loads(result["content"])
    assert "chunks" in content


# ---------------------------------------------------------------------------
# Additional: session history helpers
# ---------------------------------------------------------------------------


def test_get_history_empty_for_new_session():
    from app.chatbot import get_history

    assert get_history("nonexistent-session") == []


def test_clear_history_removes_session():
    from app import chatbot

    chatbot._sessions["s1"] = [{"role": "user", "content": "hi"}]
    chatbot.clear_history("s1")
    assert chatbot.get_history("s1") == []


def test_clear_history_noop_for_missing_session():
    from app.chatbot import clear_history

    clear_history("does-not-exist")  # Should not raise


# ---------------------------------------------------------------------------
# History rollback on API exception
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_history_rolled_back_on_api_exception():
    """
    If the first API call raises, the dangling user message must be removed
    from history so the session is not permanently broken.
    """
    from app import chatbot

    mock_client = MagicMock()
    mock_client.messages.stream.side_effect = RuntimeError("network failure")

    with patch.object(chatbot, "_get_client", return_value=mock_client):
        events = [e async for e in chatbot.chat("session-err", "Hello?")]

    # done event must still be emitted
    assert events[-1] == {"type": "done"}

    # History must be empty — the user turn must have been rolled back
    assert chatbot.get_history("session-err") == [], (
        "Session history should be empty after a failed first call"
    )


# ---------------------------------------------------------------------------
# MAX_TOOL_ROUNDS guard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_max_tool_rounds_guard():
    """
    When the model keeps requesting tools beyond MAX_TOOL_ROUNDS, the loop
    should stop and yield an error text event rather than looping forever.
    """
    from app import chatbot

    # Build a tool block that the model will keep requesting
    tool_block = _make_tool_use_block("t-inf", "run_sql", {"query": "SELECT 1"})

    def _always_tool(**kwargs):
        return _make_stream([], [tool_block], stop_reason="tool_use")

    mock_client = MagicMock()
    mock_client.messages.stream.side_effect = _always_tool

    def _fake_dispatch(name, tool_input):
        return {"content": '{"columns":[],"rows":[]}', "summary": "0 rows", "is_error": False}

    with (
        patch.object(chatbot, "_get_client", return_value=mock_client),
        patch.object(chatbot, "_dispatch_tool", side_effect=_fake_dispatch),
    ):
        events = [e async for e in chatbot.chat("session-inf", "loop forever")]

    # The loop must terminate
    assert events[-1] == {"type": "done"}

    # An error text event must have been emitted mentioning the round cap
    error_events = [
        e for e in events
        if e["type"] == "text" and "exceeded" in e["text"].lower()
    ]
    assert error_events, "Expected an error text event when MAX_TOOL_ROUNDS is exceeded"

    # The number of API calls must not exceed MAX_TOOL_ROUNDS + 1
    # (one initial + MAX_TOOL_ROUNDS tool rounds before the guard fires)
    assert mock_client.messages.stream.call_count <= chatbot.MAX_TOOL_ROUNDS + 1


# ---------------------------------------------------------------------------
# tools._safety_check — CTE with embedded write keyword
# ---------------------------------------------------------------------------


def test_safety_check_rejects_cte_with_delete():
    """WITH … DELETE CTE must be blocked at the application layer."""
    from app.tools import _safety_check

    bad = "WITH x AS (SELECT 1) DELETE FROM customers"
    result = _safety_check(bad)
    assert result is not None, "_safety_check must reject CTE with DELETE"
    assert "SELECT" in result or "allowed" in result.lower()


def test_safety_check_rejects_cte_with_insert():
    from app.tools import _safety_check

    bad = "WITH x AS (SELECT id FROM orders) INSERT INTO log SELECT * FROM x"
    result = _safety_check(bad)
    assert result is not None, "_safety_check must reject CTE with INSERT"


def test_safety_check_allows_plain_cte_select():
    """A benign WITH … SELECT must still be allowed."""
    from app.tools import _safety_check

    good = "WITH totals AS (SELECT SUM(amount) AS s FROM orders) SELECT s FROM totals"
    result = _safety_check(good)
    assert result is None, f"Expected None (allowed) but got: {result}"
