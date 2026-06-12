"""
Unit tests for the SQL safety / validation layer in app/db.py.

These tests do NOT require a live database — they check the query-validation
logic which runs before any connection is opened.
"""

import pytest

from app.db import _validate_query, _enforce_limit


# ---------------------------------------------------------------------------
# _validate_query
# ---------------------------------------------------------------------------


class TestValidateQuery:
    def test_simple_select_is_ok(self):
        assert _validate_query("SELECT * FROM customers") is None

    def test_select_with_trailing_semicolon_is_ok(self):
        assert _validate_query("SELECT id FROM orders;") is None

    def test_cte_with_select_is_ok(self):
        q = "WITH t AS (SELECT id FROM customers) SELECT * FROM t"
        assert _validate_query(q) is None

    def test_insert_rejected(self):
        err = _validate_query("INSERT INTO customers VALUES (1,'x','x@x.com')")
        assert err is not None
        assert "INSERT" in err or "allowed" in err.lower()

    def test_update_rejected(self):
        err = _validate_query("UPDATE customers SET name='evil' WHERE id=1")
        assert err is not None

    def test_delete_rejected(self):
        err = _validate_query("DELETE FROM customers WHERE id=1")
        assert err is not None

    def test_drop_rejected(self):
        err = _validate_query("DROP TABLE customers")
        assert err is not None

    def test_pragma_rejected(self):
        err = _validate_query("PRAGMA table_info(customers)")
        assert err is not None

    def test_attach_rejected(self):
        err = _validate_query("ATTACH DATABASE 'evil.db' AS evil")
        assert err is not None

    def test_multiple_statements_rejected(self):
        # Query has a semicolon mid-statement followed by a DROP — rejected on
        # either the blocked-keyword check or the multiple-statement check.
        err = _validate_query("SELECT 1; DROP TABLE customers")
        assert err is not None

    def test_multiple_statements_no_blocked_keyword_rejected(self):
        # Two bare SELECTs separated by a semicolon should still be rejected.
        err = _validate_query("SELECT 1; SELECT 2")
        assert err is not None
        assert "multiple" in err.lower() or "semicolon" in err.lower()

    def test_with_without_select_rejected(self):
        err = _validate_query("WITH t AS (UPDATE customers SET name='x')")
        assert err is not None

    def test_not_starting_with_select_or_with(self):
        err = _validate_query("EXPLAIN SELECT * FROM customers")
        assert err is not None


# ---------------------------------------------------------------------------
# _enforce_limit
# ---------------------------------------------------------------------------


class TestEnforceLimit:
    def test_adds_limit_when_absent(self):
        result = _enforce_limit("SELECT * FROM customers")
        assert "LIMIT 200" in result.upper()

    def test_does_not_double_add_limit(self):
        q = "SELECT * FROM customers LIMIT 50"
        result = _enforce_limit(q)
        assert result.upper().count("LIMIT") == 1

    def test_limit_case_insensitive_check(self):
        q = "SELECT * FROM customers limit 10"
        result = _enforce_limit(q)
        assert result.upper().count("LIMIT") == 1

    def test_strips_trailing_semicolon(self):
        result = _enforce_limit("SELECT * FROM customers;")
        assert not result.rstrip().endswith(";")

    def test_cte_gets_limit(self):
        q = "WITH t AS (SELECT id FROM customers) SELECT * FROM t"
        result = _enforce_limit(q)
        assert "LIMIT 200" in result.upper()
