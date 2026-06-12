"""
Unit tests for the chatbot agentic loop in app/chatbot.py.

Claude API calls and tool executions are fully mocked so these tests run
without any API keys or database files.
"""

import asyncio
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

from app.chatbot import run_chat, _content_blocks_to_dicts, ChatSession, TurnResult


# ---------------------------------------------------------------------------
# Helpers — fake Anthropic SDK content block objects
# ---------------------------------------------------------------------------


def _text_block(text: str) -> MagicMock:
    block = MagicMock()
    block.type = "text"
    block.text = text
    return block


def _tool_use_block(tool_id: str, name: str, input_dict: dict) -> MagicMock:
    block = MagicMock()
    block.type = "tool_use"
    block.id = tool_id
    block.name = name
    block.input = input_dict
    return block


def _thinking_block(thinking: str, signature: str = "sig") -> MagicMock:
    block = MagicMock()
    block.type = "thinking"
    block.thinking = thinking
    block.signature = signature
    return block


# ---------------------------------------------------------------------------
# Fake stream context manager
# ---------------------------------------------------------------------------


class _FakeStream:
    """Simulates client.messages.stream() for a single Claude turn."""

    def __init__(self, text_chunks: list[str], final_content: list) -> None:
        self._text_chunks = text_chunks
        self._final_content = final_content

    async def __aenter__(self) -> "_FakeStream":
        return self

    async def __aexit__(self, *_) -> None:
        pass

    @property
    def text_stream(self) -> AsyncIterator[str]:
        return self._aiter_text()

    async def _aiter_text(self) -> AsyncIterator[str]:
        for chunk in self._text_chunks:
            yield chunk

    async def get_final_message(self) -> MagicMock:
        msg = MagicMock()
        msg.content = self._final_content
        return msg


# ---------------------------------------------------------------------------
# collect_events helper
# ---------------------------------------------------------------------------


async def _collect(history, message, mock_streams, mock_tools=None):
    """
    Run run_chat and collect all yielded events.

    mock_streams: list of _FakeStream, consumed in order per loop iteration.
    mock_tools: optional dict mapping tool name to result dict.
    """
    stream_iter = iter(mock_streams)

    def _fake_stream(*args, **kwargs):
        return next(stream_iter)

    default_tool_result = {
        "content": "tool output",
        "summary": "1 result",
        "is_error": False,
    }

    async def _fake_execute_tool(name, input_dict):
        if mock_tools and name in mock_tools:
            return mock_tools[name]
        return default_tool_result

    with (
        patch("app.chatbot._get_client") as mock_client,
        patch("app.chatbot.execute_tool", side_effect=_fake_execute_tool),
    ):
        client_instance = MagicMock()
        client_instance.messages.stream.side_effect = _fake_stream
        mock_client.return_value = client_instance

        events = []
        async for event in run_chat(history, message):
            events.append(event)

    return events


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRunChatAlwaysEndWithDone:
    @pytest.mark.asyncio
    async def test_no_tools_ends_with_done(self):
        stream = _FakeStream(
            text_chunks=["Hello ", "world"],
            final_content=[_text_block("Hello world")],
        )
        events = await _collect([], "hi", [stream])

        assert events[-1] == {"type": "done"}

    @pytest.mark.asyncio
    async def test_with_tools_ends_with_done(self):
        # Turn 1: Claude calls a tool
        stream1 = _FakeStream(
            text_chunks=["Let me check…"],
            final_content=[
                _text_block("Let me check…"),
                _tool_use_block("tu1", "get_schema", {}),
            ],
        )
        # Turn 2: Claude responds with text only
        stream2 = _FakeStream(
            text_chunks=["Here is the schema."],
            final_content=[_text_block("Here is the schema.")],
        )
        events = await _collect([], "show me the schema", [stream1, stream2])

        assert events[-1] == {"type": "done"}


class TestTextEvents:
    @pytest.mark.asyncio
    async def test_text_events_emitted(self):
        stream = _FakeStream(
            text_chunks=["foo", "bar"],
            final_content=[_text_block("foobar")],
        )
        events = await _collect([], "hello", [stream])
        text_events = [e for e in events if e["type"] == "text"]
        assert [e["text"] for e in text_events] == ["foo", "bar"]

    @pytest.mark.asyncio
    async def test_empty_text_chunks_not_emitted(self):
        stream = _FakeStream(
            text_chunks=["", "hi", ""],
            final_content=[_text_block("hi")],
        )
        events = await _collect([], "hello", [stream])
        text_events = [e for e in events if e["type"] == "text"]
        # Empty strings should be filtered out
        assert all(e["text"] for e in text_events)


class TestToolEvents:
    @pytest.mark.asyncio
    async def test_tool_start_and_end_emitted(self):
        stream1 = _FakeStream(
            text_chunks=[],
            final_content=[_tool_use_block("tu1", "search_docs", {"query": "return policy"})],
        )
        stream2 = _FakeStream(
            text_chunks=["Based on the docs…"],
            final_content=[_text_block("Based on the docs…")],
        )
        events = await _collect([], "what is the return policy?", [stream1, stream2])

        tool_start_events = [e for e in events if e["type"] == "tool_start"]
        tool_end_events = [e for e in events if e["type"] == "tool_end"]

        assert len(tool_start_events) == 1
        assert tool_start_events[0]["name"] == "search_docs"
        assert tool_start_events[0]["input"] == {"query": "return policy"}

        assert len(tool_end_events) == 1
        assert tool_end_events[0]["name"] == "search_docs"

    @pytest.mark.asyncio
    async def test_tool_start_before_tool_end(self):
        stream1 = _FakeStream(
            text_chunks=[],
            final_content=[_tool_use_block("tu1", "get_schema", {})],
        )
        stream2 = _FakeStream(
            text_chunks=["Done"],
            final_content=[_text_block("Done")],
        )
        events = await _collect([], "schema please", [stream1, stream2])

        types = [e["type"] for e in events]
        start_idx = types.index("tool_start")
        end_idx = types.index("tool_end")
        assert start_idx < end_idx

    @pytest.mark.asyncio
    async def test_multiple_tools_in_one_turn(self):
        """SQL question: get_schema then run_sql both appear as tool events."""
        stream1 = _FakeStream(
            text_chunks=[],
            final_content=[
                _tool_use_block("tu1", "get_schema", {}),
                _tool_use_block("tu2", "run_sql", {"query": "SELECT COUNT(*) FROM customers"}),
            ],
        )
        stream2 = _FakeStream(
            text_chunks=["There are 300 customers."],
            final_content=[_text_block("There are 300 customers.")],
        )
        events = await _collect([], "how many customers?", [stream1, stream2])

        tool_names_started = [e["name"] for e in events if e["type"] == "tool_start"]
        assert "get_schema" in tool_names_started
        assert "run_sql" in tool_names_started

    @pytest.mark.asyncio
    async def test_tool_end_before_done(self):
        stream1 = _FakeStream(
            text_chunks=[],
            final_content=[_tool_use_block("tu1", "get_schema", {})],
        )
        stream2 = _FakeStream(
            text_chunks=["ok"],
            final_content=[_text_block("ok")],
        )
        events = await _collect([], "schema", [stream1, stream2])
        types = [e["type"] for e in events]
        assert types.index("tool_end") < types.index("done")


class TestSelfCorrection:
    @pytest.mark.asyncio
    async def test_sql_error_causes_second_run_sql_call(self):
        """
        If run_sql returns is_error=True, Claude should try again (second loop
        iteration with a second run_sql call).
        """
        # Turn 1: Claude calls run_sql with bad SQL
        stream1 = _FakeStream(
            text_chunks=[],
            final_content=[
                _tool_use_block("tu1", "run_sql", {"query": "SELECT * FORM orders"})
            ],
        )
        # Turn 2: Claude calls run_sql again with corrected SQL
        stream2 = _FakeStream(
            text_chunks=[],
            final_content=[
                _tool_use_block("tu2", "run_sql", {"query": "SELECT * FROM orders LIMIT 10"})
            ],
        )
        # Turn 3: Claude responds with text
        stream3 = _FakeStream(
            text_chunks=["Here are the orders."],
            final_content=[_text_block("Here are the orders.")],
        )

        call_count = {"run_sql": 0}

        async def _tool_side_effect(name, input_dict):
            if name == "run_sql":
                call_count["run_sql"] += 1
                if call_count["run_sql"] == 1:
                    # First call fails
                    return {
                        "content": "no such table: orders (typo: FORM)",
                        "summary": "error: no such table",
                        "is_error": True,
                    }
            return {"content": "[]", "summary": "0 rows", "is_error": False}

        with (
            patch("app.chatbot._get_client") as mock_client,
            patch("app.chatbot.execute_tool", side_effect=_tool_side_effect),
        ):
            stream_iter = iter([stream1, stream2, stream3])

            def _fake_stream(*a, **kw):
                return next(stream_iter)

            client_instance = MagicMock()
            client_instance.messages.stream.side_effect = _fake_stream
            mock_client.return_value = client_instance

            events = []
            async for event in run_chat([], "show me some orders"):
                events.append(event)

        run_sql_starts = [e for e in events if e["type"] == "tool_start" and e["name"] == "run_sql"]
        assert len(run_sql_starts) >= 2, (
            f"Expected at least 2 run_sql tool_start events (self-correction), got {len(run_sql_starts)}"
        )
        assert events[-1] == {"type": "done"}


class TestContentBlocksToDicts:
    def test_text_block(self):
        block = _text_block("hello")
        result = _content_blocks_to_dicts([block])
        assert result == [{"type": "text", "text": "hello"}]

    def test_tool_use_block(self):
        block = _tool_use_block("id1", "run_sql", {"query": "SELECT 1"})
        result = _content_blocks_to_dicts([block])
        assert result == [
            {"type": "tool_use", "id": "id1", "name": "run_sql", "input": {"query": "SELECT 1"}}
        ]

    def test_thinking_block_preserved(self):
        block = _thinking_block("some thoughts", "sig123")
        result = _content_blocks_to_dicts([block])
        assert result[0]["type"] == "thinking"
        assert result[0]["thinking"] == "some thoughts"
        assert result[0]["signature"] == "sig123"

    def test_mixed_blocks(self):
        blocks = [
            _thinking_block("think"),
            _text_block("answer"),
            _tool_use_block("tu1", "get_schema", {}),
        ]
        result = _content_blocks_to_dicts(blocks)
        types = [b["type"] for b in result]
        assert types == ["thinking", "text", "tool_use"]


# ---------------------------------------------------------------------------
# TurnResult and ChatSession
# ---------------------------------------------------------------------------


class TestTurnResult:
    def test_dataclass_fields(self):
        tr = TurnResult(text="hello", sources=["policy.md"], tool_calls=[{"name": "search_docs", "input": {}}])
        assert tr.text == "hello"
        assert tr.sources == ["policy.md"]
        assert tr.tool_calls[0]["name"] == "search_docs"

    def test_default_empty_lists(self):
        tr = TurnResult(text="hi")
        assert tr.sources == []
        assert tr.tool_calls == []


class TestChatSession:
    """Unit tests for ChatSession.send_message using the same mocking pattern."""

    def _make_session_with_streams(self, mock_streams, mock_tools=None):
        """Return a (session, call) pair.  Call session.send_message() inside
        the patch context to drive the fake streams."""
        stream_iter = iter(mock_streams)

        def _fake_stream(*args, **kwargs):
            return next(stream_iter)

        async def _fake_execute_tool(name, input_dict):
            if mock_tools and name in mock_tools:
                return mock_tools[name]
            return {"content": "tool output", "is_error": False}

        session = ChatSession()
        return session, _fake_stream, _fake_execute_tool

    def test_send_message_returns_turn_result(self):
        stream = _FakeStream(
            text_chunks=["Hello ", "world"],
            final_content=[_text_block("Hello world")],
        )
        session, fake_stream, fake_tool = self._make_session_with_streams([stream])
        with (
            patch("app.chatbot._get_client") as mock_client,
            patch("app.chatbot.execute_tool", side_effect=fake_tool),
        ):
            client_instance = MagicMock()
            client_instance.messages.stream.side_effect = fake_stream
            mock_client.return_value = client_instance
            result = session.send_message("hi")

        assert isinstance(result, TurnResult)
        assert result.text == "Hello world"
        assert result.sources == []
        assert result.tool_calls == []

    def test_send_message_collects_tool_calls(self):
        stream1 = _FakeStream(
            text_chunks=[],
            final_content=[_tool_use_block("tu1", "search_docs", {"query": "return policy"})],
        )
        stream2 = _FakeStream(
            text_chunks=["Policy says 30 days."],
            final_content=[_text_block("Policy says 30 days.")],
        )
        fake_search_result = {
            "chunks": [
                {"source": "return_refund_policy.md", "heading": "Returns", "text": "...", "score": 0.9}
            ],
            "count": 1,
        }
        session, fake_stream, _ = self._make_session_with_streams(
            [stream1, stream2], mock_tools={"search_docs": fake_search_result}
        )

        async def _fake_execute_tool(name, input_dict):
            return fake_search_result

        with (
            patch("app.chatbot._get_client") as mock_client,
            patch("app.chatbot.execute_tool", side_effect=_fake_execute_tool),
        ):
            client_instance = MagicMock()
            client_instance.messages.stream.side_effect = fake_stream
            mock_client.return_value = client_instance
            result = session.send_message("what is the return policy?")

        assert result.text == "Policy says 30 days."
        assert any(tc["name"] == "search_docs" for tc in result.tool_calls)
        assert "return_refund_policy.md" in result.sources

    def test_send_message_deduplicates_sources(self):
        """Two search_docs calls with overlapping sources yield deduplicated list."""
        stream1 = _FakeStream(
            text_chunks=[],
            final_content=[
                _tool_use_block("tu1", "search_docs", {"query": "premium SLA"}),
                _tool_use_block("tu2", "search_docs", {"query": "open tickets"}),
            ],
        )
        stream2 = _FakeStream(
            text_chunks=["Answer here."],
            final_content=[_text_block("Answer here.")],
        )
        fake_result = {
            "chunks": [{"source": "sla.md", "heading": "SLA", "text": "...", "score": 0.8}],
            "count": 1,
        }

        async def _fake_execute_tool(name, input_dict):
            return fake_result

        stream_calls = iter([stream1, stream2])

        def _fake_stream(*a, **kw):
            return next(stream_calls)

        session = ChatSession()
        with (
            patch("app.chatbot._get_client") as mock_client,
            patch("app.chatbot.execute_tool", side_effect=_fake_execute_tool),
        ):
            client_instance = MagicMock()
            client_instance.messages.stream.side_effect = _fake_stream
            mock_client.return_value = client_instance
            result = session.send_message("premium support SLA question")

        # sla.md should appear exactly once even though two search_docs calls returned it
        assert result.sources.count("sla.md") == 1

    def test_history_persists_across_turns(self):
        """History grows: the second turn sees messages from the first."""
        stream = _FakeStream(
            text_chunks=["Turn 1 response."],
            final_content=[_text_block("Turn 1 response.")],
        )
        stream2 = _FakeStream(
            text_chunks=["Turn 2 response."],
            final_content=[_text_block("Turn 2 response.")],
        )

        async def _fake_execute_tool(name, input_dict):
            return {"content": "ok", "is_error": False}

        streams = iter([stream, stream2])

        def _fake_stream(*a, **kw):
            return next(streams)

        session = ChatSession()
        with (
            patch("app.chatbot._get_client") as mock_client,
            patch("app.chatbot.execute_tool", side_effect=_fake_execute_tool),
        ):
            client_instance = MagicMock()
            client_instance.messages.stream.side_effect = _fake_stream
            mock_client.return_value = client_instance
            session.send_message("first question")
            # After first turn history has user + assistant messages
            assert len(session._history) == 2
            session.send_message("follow-up question")
            # After second turn history has 4 messages
            assert len(session._history) == 4
