"""
Acceptance tests for the SQL-only and aggregation chatbot paths.

Questions covered
-----------------
Q2  "How many customers do we have in California?"
      → simple COUNT; answer must include a plausible number (20–60 out of ~300)

Q3  "List all overdue invoices over $500 with the customer name and state"
      → requires JOIN (invoices ⋈ orders ⋈ customers) and a WHERE clause
        that filters on the 'overdue' status

Q5  "What's our best-selling product category by revenue this year?"
      → GROUP BY aggregation; answer must name a known product category
        and contain a revenue figure

All three tests inspect the raw SSE event stream for ``tool_start`` /
``tool_end`` events whose ``name`` field equals ``run_sql``, confirming the
chatbot chose the SQL path.  The ``ask`` helper uses a fresh session UUID per
call so tests are independent.

Usage
-----
    pytest tests/test_acceptance_sql.py

Prerequisites
-------------
The test module imports ``app.main.app`` (FastAPI instance) and connects to
the real SQLite database seeded by ``scripts/init_db.py``.  Both
``data/acme.db`` and ``data/embeddings.db`` must exist and the environment
variables ANTHROPIC_API_KEY / VOYAGE_API_KEY must be set (or loaded from
``.env``) before running.
"""

from __future__ import annotations

import json
import re
import uuid
from typing import List, Tuple

import httpx
import pytest

from app.main import app  # available only in a fully set-up environment

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Known product categories as defined in the schema (§3 of SPEC.md).
PRODUCT_CATEGORIES: frozenset[str] = frozenset(
    {"Camping", "Hiking", "Climbing", "Apparel", "Accessories"}
)

# ---------------------------------------------------------------------------
# Shared async client fixture
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def http_client() -> httpx.Client:
    """
    Synchronous httpx client wired to the FastAPI ASGI app.

    Using ``httpx.ASGITransport`` avoids the starlette TestClient deprecation
    warning (starlette ≥ 1.3 requires ``httpx2`` for its TestClient) and gives
    us clean streaming support for SSE.
    """
    transport = httpx.ASGITransport(app=app)
    with httpx.Client(transport=transport, base_url="http://testserver") as client:
        yield client


# ---------------------------------------------------------------------------
# SSE stream helpers
# ---------------------------------------------------------------------------


def _parse_events(lines) -> List[dict]:
    """
    Parse an SSE byte/text stream into a list of normalised event dicts.

    Handles two common SSE conventions used by FastAPI / sse-starlette:

    Convention A — type embedded in the JSON payload::

        data: {"type": "tool_start", "name": "run_sql", "input": {...}}

    Convention B — SSE ``event:`` field plus separate ``data:`` line::

        event: tool_start
        data: {"name": "run_sql", "input": {...}}

    Both produce a dict with at least a ``type`` key.
    """
    events: List[dict] = []
    pending_type: str | None = None
    pending_data: str = ""

    for raw in lines:
        line: str = raw if isinstance(raw, str) else raw.decode("utf-8", errors="replace")
        line = line.rstrip("\r\n")

        if line.startswith("event:"):
            pending_type = line[len("event:"):].strip()
        elif line.startswith("data:"):
            pending_data = line[len("data:"):].strip()
        elif line == "":
            # blank line → dispatch accumulated frame
            if pending_data:
                try:
                    payload = json.loads(pending_data)
                except json.JSONDecodeError:
                    payload = {"raw": pending_data}
                # merge SSE event-field into payload when absent
                if pending_type and "type" not in payload:
                    payload["type"] = pending_type
                events.append(payload)
            pending_type = None
            pending_data = ""

    # flush any trailing frame that was not newline-terminated
    if pending_data:
        try:
            payload = json.loads(pending_data)
        except json.JSONDecodeError:
            payload = {"raw": pending_data}
        if pending_type and "type" not in payload:
            payload["type"] = pending_type
        events.append(payload)

    return events


def ask(client: httpx.Client, question: str) -> Tuple[List[dict], str]:
    """
    POST *question* to ``/chat``, consume the full SSE stream, and return
    ``(events, full_text)``.

    Parameters
    ----------
    client:
        The shared ``httpx.Client`` fixture.
    question:
        Natural-language question to send to the chatbot.

    Returns
    -------
    events:
        Every parsed SSE event in emission order.
    full_text:
        Concatenated assistant text deltas (all events with ``type == "text"``).
    """
    session_id = str(uuid.uuid4())
    payload = {"session_id": session_id, "message": question}

    with client.stream("POST", "/chat", json=payload, timeout=180) as response:
        assert response.status_code == 200, (
            f"POST /chat returned HTTP {response.status_code}"
        )
        events = _parse_events(response.iter_lines())

    full_text = "".join(
        e.get("delta", "") for e in events if e.get("type") == "text"
    )
    return events, full_text


def _run_sql_starts(events: List[dict]) -> List[dict]:
    """Return all ``tool_start`` events whose ``name`` is ``run_sql``."""
    return [
        e for e in events
        if e.get("type") == "tool_start" and e.get("name") == "run_sql"
    ]


# ---------------------------------------------------------------------------
# Module-level result cache — one real LLM call per acceptance question
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def q2_result(http_client: httpx.Client) -> Tuple[List[dict], str]:
    """Q2: California customer count."""
    return ask(http_client, "How many customers do we have in California?")


@pytest.fixture(scope="module")
def q3_result(http_client: httpx.Client) -> Tuple[List[dict], str]:
    """Q3: Overdue invoices with JOIN."""
    return ask(
        http_client,
        "List all overdue invoices over $500 with the customer name and state",
    )


@pytest.fixture(scope="module")
def q5_result(http_client: httpx.Client) -> Tuple[List[dict], str]:
    """Q5: Best-selling product category by revenue."""
    return ask(
        http_client,
        "What's our best-selling product category by revenue this year?",
    )


# ---------------------------------------------------------------------------
# Q2 — California customer count
# ---------------------------------------------------------------------------


class TestQ2CaliforniaCustomerCount:
    """Question 2: simple ``COUNT(*) … WHERE state = 'CA'``."""

    def test_triggers_run_sql(self, q2_result):
        """The chatbot must issue at least one ``run_sql`` tool call."""
        events, _ = q2_result
        sql_starts = _run_sql_starts(events)
        assert len(sql_starts) >= 1, (
            "Expected at least one tool_start event with name='run_sql'; "
            f"all tool_start events: "
            f"{[e for e in events if e.get('type') == 'tool_start']!r}"
        )

    def test_answer_contains_plausible_ca_count(self, q2_result):
        """
        With ~300 total customers distributed across all 50 US states, a
        plausible California share is roughly 20–60 rows.  The seeder uses
        ``Faker.seed(42)`` so the value is deterministic; the range avoids
        brittleness if neighbouring tasks adjust seeder row counts slightly.
        """
        _, text = q2_result
        numbers = [int(m) for m in re.findall(r"\b(\d+)\b", text)]
        assert any(20 <= n <= 60 for n in numbers), (
            "Expected a number between 20 and 60 (plausible CA customer count) "
            f"in the answer; extracted numbers: {numbers!r}\n\nFull response:\n{text}"
        )


# ---------------------------------------------------------------------------
# Q3 — Overdue invoices with JOIN and WHERE
# ---------------------------------------------------------------------------


class TestQ3OverdueInvoices:
    """Question 3: invoices query requiring a JOIN and a status filter."""

    def test_triggers_run_sql(self, q3_result):
        """The chatbot must issue at least one ``run_sql`` tool call."""
        events, _ = q3_result
        sql_starts = _run_sql_starts(events)
        assert len(sql_starts) >= 1, (
            "Expected at least one tool_start event with name='run_sql'; "
            f"tool_start events seen: "
            f"{[e for e in events if e.get('type') == 'tool_start']!r}"
        )

    def test_sql_contains_join(self, q3_result):
        """
        Fetching the customer ``name`` and ``state`` from an invoices row
        requires at least one JOIN to the customers table (reached directly or
        through orders).
        """
        events, _ = q3_result
        sqls = [
            e.get("input", {}).get("query", "")
            for e in _run_sql_starts(events)
        ]
        assert any("JOIN" in sql.upper() for sql in sqls), (
            "Expected at least one run_sql call containing a JOIN clause; "
            "SQL(s) issued:\n" + "\n---\n".join(sqls or ["<none>"])
        )

    def test_sql_filters_on_overdue_status(self, q3_result):
        """
        The issued SQL must include a WHERE clause (or HAVING) that filters on
        the literal string ``'overdue'`` so that only invoices with
        ``status = 'overdue'`` are returned.
        """
        events, _ = q3_result
        sqls = [
            e.get("input", {}).get("query", "")
            for e in _run_sql_starts(events)
        ]
        assert any(
            "WHERE" in sql.upper() and "overdue" in sql.lower()
            for sql in sqls
        ), (
            "Expected a SQL with WHERE … 'overdue' to filter invoice status; "
            "SQL(s) issued:\n" + "\n---\n".join(sqls or ["<none>"])
        )


# ---------------------------------------------------------------------------
# Q5 — Best-selling product category by revenue
# ---------------------------------------------------------------------------


class TestQ5BestSellingCategoryByRevenue:
    """Question 5: GROUP BY aggregation over order_items × products."""

    def test_triggers_run_sql(self, q5_result):
        """The chatbot must issue at least one ``run_sql`` tool call."""
        events, _ = q5_result
        sql_starts = _run_sql_starts(events)
        assert len(sql_starts) >= 1, (
            "Expected at least one tool_start event with name='run_sql'; "
            f"tool_start events seen: "
            f"{[e for e in events if e.get('type') == 'tool_start']!r}"
        )

    def test_answer_names_a_product_category(self, q5_result):
        """
        The response must mention at least one of the five canonical product
        categories defined in the schema: Camping, Hiking, Climbing, Apparel,
        or Accessories.
        """
        _, text = q5_result
        mentioned = [
            cat for cat in PRODUCT_CATEGORIES if cat.lower() in text.lower()
        ]
        assert mentioned, (
            f"Expected at least one product category from "
            f"{sorted(PRODUCT_CATEGORIES)} to appear in the answer.\n\n"
            f"Full response:\n{text}"
        )

    def test_answer_contains_revenue_figure(self, q5_result):
        """
        A revenue summary should include a dollar-denominated figure.

        Matches patterns such as ``$12,345.67`` or ``$98765`` (explicit dollar
        sign) and also falls back to any bare large number (≥ 4 digits) in
        case the model elides the currency symbol while still reporting a
        dollar amount.
        """
        _, text = q5_result
        dollar_pattern = r"\$\s*[\d,]+(?:\.\d{1,2})?"
        large_number_pattern = r"\b\d{4,}(?:,\d{3})*(?:\.\d{1,2})?\b"
        has_revenue = bool(re.search(dollar_pattern, text)) or bool(
            re.search(large_number_pattern, text)
        )
        assert has_revenue, (
            "Expected a revenue figure (e.g. '$12,345.67') in the answer; "
            f"none found.\n\nFull response:\n{text}"
        )
