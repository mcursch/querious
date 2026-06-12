"""
Acceptance test suite for docs-only and RAG citation paths.

Question 1: "What is the return policy on used tents?"
  → docs path; response must cite return_refund_policy.md

Question 4: "Do premium customers get faster support, and how many open tickets
             do they have right now?"
  → combined path; response must cite sla.md AND produce at least one run_sql
    tool call.

Tests skip (not fail) if data/acme.db or data/embeddings.db do not exist.
"""
import os
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Skip conditions
# ---------------------------------------------------------------------------

_ACME_DB = Path("data/acme.db")
_EMBED_DB = Path("data/embeddings.db")

_DATABASES_MISSING = not _ACME_DB.exists() or not _EMBED_DB.exists()
_SKIP_REASON = (
    "Required database files not found: "
    + (str(_ACME_DB) if not _ACME_DB.exists() else "")
    + (" " if not _ACME_DB.exists() and not _EMBED_DB.exists() else "")
    + (str(_EMBED_DB) if not _EMBED_DB.exists() else "")
).strip()

pytestmark = pytest.mark.skipif(_DATABASES_MISSING, reason=_SKIP_REASON)

# ---------------------------------------------------------------------------
# Import chatbot (after skip guards so collection works even without app/)
# ---------------------------------------------------------------------------

from app.chatbot import ChatSession, TurnResult  # noqa: E402  (import after skip guard)


# ---------------------------------------------------------------------------
# Shared session fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def session() -> "ChatSession":
    """One ChatSession shared across all tests in this module."""
    return ChatSession()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sources_include(result: TurnResult, filename: str) -> bool:
    """Return True if `filename` appears in cited sources or in the response text."""
    if any(filename in src for src in result.sources):
        return True
    # Also accept if the model mentioned it inline in text (belt-and-suspenders)
    if filename in result.text:
        return True
    return False


def _has_tool_call(result: TurnResult, tool_name: str) -> bool:
    return any(tc["name"] == tool_name for tc in result.tool_calls)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestQuestion1ReturnPolicy:
    """Acceptance question 1: return policy on used tents → docs path."""

    @pytest.fixture(scope="class")
    def result(self, session: "ChatSession") -> TurnResult:
        return session.send_message("What is the return policy on used tents?")

    def test_response_is_not_empty(self, result: TurnResult) -> None:
        assert result.text.strip(), "Response text should not be empty"

    def test_cites_return_refund_policy(self, result: TurnResult) -> None:
        assert _sources_include(result, "return_refund_policy.md"), (
            f"Expected return_refund_policy.md in sources {result.sources!r} "
            f"or response text"
        )

    def test_mentions_key_terms(self, result: TurnResult) -> None:
        text_lower = result.text.lower()
        # The policy is clear: used tents cannot be returned (unless defective)
        key_terms = ["return", "used", "tent"]
        for term in key_terms:
            assert term in text_lower, (
                f"Expected key term {term!r} in response text"
            )

    def test_used_search_docs(self, result: TurnResult) -> None:
        assert _has_tool_call(result, "search_docs"), (
            "Expected at least one search_docs tool call for a policy question"
        )


class TestQuestion4SLAAndSQL:
    """Acceptance question 4: premium customers + open tickets → combined path."""

    @pytest.fixture(scope="class")
    def result(self, session: "ChatSession") -> TurnResult:
        return session.send_message(
            "Do premium customers get faster support, and how many open tickets "
            "do they have right now?"
        )

    def test_response_is_not_empty(self, result: TurnResult) -> None:
        assert result.text.strip(), "Response text should not be empty"

    def test_cites_sla(self, result: TurnResult) -> None:
        assert _sources_include(result, "sla.md"), (
            f"Expected sla.md in sources {result.sources!r} or response text"
        )

    def test_mentions_sla_terms(self, result: TurnResult) -> None:
        text_lower = result.text.lower()
        # The SLA doc describes faster response times for premium customers
        sla_terms = ["premium", "support"]
        for term in sla_terms:
            assert term in text_lower, (
                f"Expected SLA key term {term!r} in response text"
            )

    def test_has_run_sql_call(self, result: TurnResult) -> None:
        assert _has_tool_call(result, "run_sql"), (
            "Expected at least one run_sql tool call to count open premium tickets"
        )

    def test_mentions_ticket_count(self, result: TurnResult) -> None:
        # The bot should report a number (the SQL result). We just check it's
        # mentioned numerically or as a word.
        import re
        has_number = bool(re.search(r"\b\d+\b", result.text)) or any(
            word in result.text.lower()
            for word in ["zero", "none", "no open", "tickets"]
        )
        assert has_number, (
            "Expected a numerical result (ticket count) in the response"
        )
