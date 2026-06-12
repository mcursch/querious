"""Self-correction acceptance test.

Sends a question that references a deliberately wrong table name (``orderz``).
The Anthropic API is mocked to simulate Claude's self-correction behaviour:

  1. Claude calls ``get_schema`` to inspect available tables.
  2. Claude calls ``run_sql`` with the bad table name → real SQLite returns
     an ``OperationalError`` which the loop feeds back as an error tool result.
  3. Claude reads the error, corrects the table name, and calls ``run_sql``
     again with the right table → real SQLite returns rows.
  4. Claude returns a coherent text answer.

Assertions
----------
- At least 2 ``tool_start`` events with ``name == "run_sql"`` appear in the
  SSE stream (confirming the retry actually happened).
- The final assistant text does not contain phrases like "I cannot" or begin
  with "error" (confirming a coherent answer was produced).
- Standalone verification that ``run_sql("SELECT * FROM orderz …")`` really
  does fail and ``run_sql("SELECT * FROM orders …")`` really does succeed,
  confirming the infrastructure returns errors to the LLM rather than raising.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from tests.conftest import _parse_sse, _resp, _text_block, _tool_block


# ---------------------------------------------------------------------------
# Fixture — scripted self-correction scenario
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_anthropic_selfcorrect():
    """Mock Anthropic to simulate a self-correction loop over a bad table name.

    Call 1: get_schema  (Claude checks available tables)
    Call 2: run_sql with wrong table 'orderz' → real SQLite returns error
    Call 3: run_sql with correct table 'orders' → real SQLite returns rows
    Call 4: text answer (coherent, no error phrases)
    """
    scripted = [
        # Claude inspects the schema first
        _resp([_tool_block("get_schema", {}, "sc_1")], "tool_use"),
        # Claude tries the table name from the user's (wrong) question
        _resp(
            [_tool_block("run_sql", {"query": "SELECT * FROM orderz LIMIT 5"}, "sc_2")],
            "tool_use",
        ),
        # Claude self-corrects after reading the error tool result
        _resp(
            [_tool_block("run_sql", {"query": "SELECT * FROM orders LIMIT 5"}, "sc_3")],
            "tool_use",
        ),
        # Claude synthesises the final answer
        _resp(
            [_text_block(
                "I found the orders. The database contains 3 recent orders with "
                "statuses: delivered, shipped, and pending."
            )],
            "end_turn",
        ),
    ]

    with patch("anthropic.Anthropic") as MockCls:
        mock_client = MagicMock()
        MockCls.return_value = mock_client
        mock_client.messages.create.side_effect = scripted
        yield MockCls


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_selfcorrect_emits_two_run_sql_events(mock_anthropic_selfcorrect, setup_test_data):
    """At least 2 run_sql tool_start events appear — confirming the retry path."""
    from app.main import app  # deferred so QUERIOUS_DATA_DIR is already set

    client = TestClient(app, raise_server_exceptions=True)

    with client.stream(
        "POST",
        "/chat",
        json={
            "session_id": "selfcorrect_001",
            "message": "Show me recent rows from the orderz table",
        },
    ) as resp:
        assert resp.status_code == 200
        body = resp.read().decode()

    events = _parse_sse(body)

    run_sql_starts = [
        e for e in events
        if e["type"] == "tool_start" and (e.get("data") or {}).get("name") == "run_sql"
    ]

    assert len(run_sql_starts) >= 2, (
        f"Expected ≥2 run_sql tool_start events (self-correction), "
        f"but got {len(run_sql_starts)}.\n"
        f"All event types: {[e['type'] for e in events]}\n"
        f"tool_start events: {[e for e in events if e['type'] == 'tool_start']}"
    )


def test_selfcorrect_final_answer_is_coherent(mock_anthropic_selfcorrect, setup_test_data):
    """Final assistant response does not contain error phrases."""
    from app.main import app

    client = TestClient(app, raise_server_exceptions=True)

    with client.stream(
        "POST",
        "/chat",
        json={
            "session_id": "selfcorrect_002",
            "message": "Show me recent rows from the orderz table",
        },
    ) as resp:
        assert resp.status_code == 200
        body = resp.read().decode()

    events = _parse_sse(body)
    text_events = [e for e in events if e["type"] == "text"]
    assert text_events, "Expected at least one 'text' event with the assistant's answer"

    combined = " ".join((e.get("data") or {}).get("text", "") for e in text_events).lower()

    assert "i cannot" not in combined, (
        f"Final response should not contain 'I cannot'. Got:\n{combined}"
    )
    assert not combined.strip().startswith("error"), (
        f"Final response should not start with 'error'. Got:\n{combined}"
    )


def test_run_sql_returns_error_for_bad_table(setup_test_data):
    """run_sql returns an error dict for a non-existent table, not an exception.

    This confirms the infrastructure surfaces SQL errors as tool results so
    the LLM can self-correct rather than crashing the agentic loop.
    """
    from app.tools import run_sql

    bad = run_sql("SELECT * FROM orderz LIMIT 5")
    assert bad.get("is_error"), (
        f"Expected is_error=True for non-existent table 'orderz', got: {bad}"
    )
    assert "orderz" in bad.get("error", "").lower() or "no such table" in bad.get("error", "").lower(), (
        f"Error message should mention the missing table. Got: {bad.get('error')}"
    )


def test_run_sql_succeeds_for_correct_table(setup_test_data):
    """run_sql returns rows for the real 'orders' table after self-correction."""
    from app.tools import run_sql

    good = run_sql("SELECT * FROM orders LIMIT 5")
    assert not good.get("is_error"), (
        f"Expected success for table 'orders', got error: {good}"
    )
    assert "row_count" in good, f"Expected row_count in result, got: {good}"
    assert good["row_count"] > 0, "Expected at least one row in orders table"
