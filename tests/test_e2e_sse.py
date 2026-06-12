"""End-to-end SSE smoke test.

Spins up the FastAPI application through Starlette's TestClient and
sends a simple SQL question.  The Anthropic API is mocked so that the
agentic loop exercises all four SSE event types without hitting external
services.

Verified event types: ``tool_start``, ``tool_end``, ``text``, ``done``
Also verifies: ``GET /health`` returns 200 and reports both DB files present.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from tests.conftest import _parse_sse, _resp, _text_block, _tool_block


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_anthropic_simple():
    """Mock Anthropic with a three-step SQL scenario.

    Step 1 — LLM decides to inspect the schema.
    Step 2 — LLM runs a COUNT query.
    Step 3 — LLM returns a text answer.
    """
    scripted = [
        _resp([_tool_block("get_schema", {}, "ts_1")], "tool_use"),
        _resp(
            [_tool_block("run_sql", {"query": "SELECT COUNT(*) AS total FROM customers"}, "ts_2")],
            "tool_use",
        ),
        _resp([_text_block("We currently have 3 customers in the database.")], "end_turn"),
    ]

    with patch("anthropic.Anthropic") as MockCls:
        mock_client = MagicMock()
        MockCls.return_value = mock_client
        mock_client.messages.create.side_effect = scripted
        yield MockCls


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_sse_all_event_types_present(mock_anthropic_simple, setup_test_data):
    """All four SSE event types appear in the stream for a simple SQL question."""
    from app.main import app  # deferred import so QUERIOUS_DATA_DIR is already set

    client = TestClient(app, raise_server_exceptions=True)

    with client.stream(
        "POST",
        "/chat",
        json={"session_id": "e2e_smoke_001", "message": "How many customers do we have?"},
    ) as resp:
        assert resp.status_code == 200
        body = resp.read().decode()

    events = _parse_sse(body)
    assert events, "Expected at least one SSE event but got none"

    found_types = {e["type"] for e in events}

    assert "tool_start" in found_types, f"Missing 'tool_start'. Got: {found_types}"
    assert "tool_end" in found_types, f"Missing 'tool_end'. Got: {found_types}"
    assert "text" in found_types, f"Missing 'text'. Got: {found_types}"
    assert "done" in found_types, f"Missing 'done'. Got: {found_types}"


def test_health_both_dbs_present(setup_test_data):
    """GET /health returns 200 and reports both DB files as present."""
    from app.main import app

    client = TestClient(app)
    resp = client.get("/health")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["acme_db"] is True, f"Expected acme_db=true, got: {body}"
    assert body["embeddings_db"] is True, f"Expected embeddings_db=true, got: {body}"
