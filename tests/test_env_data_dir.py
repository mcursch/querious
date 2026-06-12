"""
Regression tests for LIN-198 — QUERIOUS_DATA_DIR must be honoured.

The ``setup_test_data`` (session-scoped, autouse) fixture in conftest.py
writes a temp-dir path to os.environ['QUERIOUS_DATA_DIR'] and populates it
with minimal SQLite databases.  These tests verify that the actual DB access
functions in app/db.py read from that directory rather than from the
production data/ directory.
"""

import os
import pytest

from app.db import _get_db_path, open_ro_connection, get_schema, execute_query
from app.rag import _get_embeddings_db


# ---------------------------------------------------------------------------
# _get_db_path / _get_embeddings_db respect QUERIOUS_DATA_DIR
# ---------------------------------------------------------------------------

class TestGetDbPathRespectsEnvVar:
    def test_db_path_uses_env_var(self, setup_test_data):
        """_get_db_path() should return a path inside QUERIOUS_DATA_DIR."""
        expected_dir = os.environ["QUERIOUS_DATA_DIR"]
        db_path = _get_db_path()
        assert str(db_path).startswith(expected_dir), (
            f"Expected db path under {expected_dir!r}, got {db_path!r}"
        )

    def test_embeddings_db_uses_env_var(self, setup_test_data):
        """_get_embeddings_db() should return a path inside QUERIOUS_DATA_DIR."""
        expected_dir = os.environ["QUERIOUS_DATA_DIR"]
        emb_path = _get_embeddings_db()
        assert str(emb_path).startswith(expected_dir), (
            f"Expected embeddings path under {expected_dir!r}, got {emb_path!r}"
        )


# ---------------------------------------------------------------------------
# Actual DB operations use the temp fixture DB (not production data/)
# ---------------------------------------------------------------------------

class TestDbOperationsUseFixtureDb:
    def test_open_ro_connection_uses_test_db(self, setup_test_data):
        """open_ro_connection() must connect to the temp DB set by the fixture."""
        conn = open_ro_connection()
        try:
            cur = conn.cursor()
            # The fixture seeds exactly 3 customers; production data will differ.
            cur.execute("SELECT COUNT(*) FROM customers")
            count = cur.fetchone()[0]
            assert count == 3, (
                f"Expected 3 customers from the test fixture DB, got {count}. "
                "DB operations may be targeting the production data/ directory."
            )
        finally:
            conn.close()

    def test_execute_query_uses_test_db(self, setup_test_data):
        """execute_query() must return rows from the fixture's hermetic DB."""
        rows = execute_query("SELECT email FROM customers ORDER BY id")
        emails = [r["email"] for r in rows]
        assert emails == [
            "alice@example.com",
            "bob@example.com",
            "carol@example.com",
        ], (
            f"Unexpected customer emails: {emails}. "
            "DB operations may be targeting the production data/ directory."
        )

    def test_get_schema_uses_test_db(self, setup_test_data):
        """get_schema() must describe the fixture DB tables."""
        schema = get_schema()
        # The fixture creates a 'customers' table; confirm it appears in the schema.
        assert "customers" in schema, (
            "Expected 'customers' table in schema output — "
            "get_schema() may be targeting the production data/ directory."
        )
