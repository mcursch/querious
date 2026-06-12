"""
Unit tests for app/rag.py.

The retrieve() tests use a pre-populated in-memory SQLite database with
synthetic float32 embeddings — no Voyage API key required.
"""

from __future__ import annotations

import sqlite3
import unittest.mock as mock

import numpy as np
import pytest

from app.rag import (
    _blob_to_vec,
    _vec_to_blob,
    chunk_markdown,
    drop_and_recreate,
    insert_chunks,
    retrieve,
)


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _make_in_memory_db(chunks: list[dict]) -> str:
    """
    Populate a named shared-cache in-memory SQLite database and return the
    URI.  Using a URI with shared cache allows the same data to be accessed
    by retrieve() via sqlite3.connect().
    """
    # We use a file::memory:?cache=shared URI so both this setup connection
    # and the one opened inside retrieve() share the same data.
    uri = "file:testdb?mode=memory&cache=shared"
    conn = sqlite3.connect(uri, uri=True)
    drop_and_recreate(conn)
    insert_chunks(conn, chunks)
    # Keep the connection open so the in-memory DB isn't destroyed; we'll
    # return it and let the caller keep a reference.
    return conn, uri


def _unit_vec(v: list[float]) -> np.ndarray:
    """Return a unit-normalised float32 array."""
    a = np.array(v, dtype=np.float32)
    return a / np.linalg.norm(a)


# ──────────────────────────────────────────────────────────────────────────────
# Serialisation round-trip
# ──────────────────────────────────────────────────────────────────────────────

def test_blob_roundtrip():
    vec = np.array([0.1, 0.2, 0.3, -0.5], dtype=np.float32)
    assert np.allclose(vec, _blob_to_vec(_vec_to_blob(vec)))


# ──────────────────────────────────────────────────────────────────────────────
# chunk_markdown
# ──────────────────────────────────────────────────────────────────────────────

def test_chunk_markdown_basic():
    md = "# Title\n\nSome text here.\n\n## Section\n\nMore text."
    chunks = chunk_markdown("test.md", md)
    assert len(chunks) >= 1
    for c in chunks:
        assert c["source"] == "test.md"
        assert "text" in c
        assert "heading" in c


def test_chunk_markdown_heading_path():
    md = "# Parent\n\n## Child\n\nContent under child."
    chunks = chunk_markdown("doc.md", md)
    # The chunk under "## Child" should reference both headings.
    child_chunks = [c for c in chunks if "Child" in c["heading"]]
    assert child_chunks, "Expected a chunk whose heading includes 'Child'"
    assert "Parent" in child_chunks[0]["heading"]


def test_chunk_markdown_long_section_split():
    # Create a section whose word count exceeds CHUNK_TARGET_TOKENS (500).
    long_text = "word " * 1100
    md = f"# Big Section\n\n{long_text}"
    chunks = chunk_markdown("big.md", md)
    assert len(chunks) >= 2, "Long section should produce multiple chunks"
    for c in chunks:
        assert c["source"] == "big.md"


def test_chunk_markdown_empty():
    assert chunk_markdown("empty.md", "") == []


# ──────────────────────────────────────────────────────────────────────────────
# retrieve() — ranking correctness
# ──────────────────────────────────────────────────────────────────────────────

# We construct four chunks whose embeddings live in a 3-D space.
# The query vector is close to chunk B, then A, then C, then D.

_DIM = 3

# Chunk embeddings (unit-normalised so cosine similarity == dot product).
_VEC_A = _unit_vec([1.0, 0.5, 0.0])   # moderate match
_VEC_B = _unit_vec([1.0, 0.9, 0.1])   # best match
_VEC_C = _unit_vec([0.5, 0.0, 1.0])   # poor match
_VEC_D = _unit_vec([0.0, 0.0, 1.0])   # worst match

# Query is closest to B.
_QUERY_VEC = _unit_vec([1.0, 1.0, 0.0])

_FIXTURE_CHUNKS = [
    {"source": "a.md", "heading": "H A", "text": "chunk A text", "embedding": _VEC_A},
    {"source": "b.md", "heading": "H B", "text": "chunk B text", "embedding": _VEC_B},
    {"source": "c.md", "heading": "H C", "text": "chunk C text", "embedding": _VEC_C},
    {"source": "d.md", "heading": "H D", "text": "chunk D text", "embedding": _VEC_D},
]


@pytest.fixture()
def populated_db():
    """
    Yield a (connection, uri) tuple for an in-memory DB loaded with
    _FIXTURE_CHUNKS.  Keeps the connection alive so the data persists.
    """
    conn, uri = _make_in_memory_db(_FIXTURE_CHUNKS)
    yield conn, uri
    conn.close()


def _mock_embed_query(vec: np.ndarray):
    """Return a context-manager patch that makes embed_query return *vec*."""
    return mock.patch("app.rag.embed_query", return_value=vec)


def test_retrieve_returns_top_k(populated_db):
    conn, uri = populated_db
    with _mock_embed_query(_QUERY_VEC):
        results = retrieve("any query", uri, top_k=3)
    assert len(results) == 3


def test_retrieve_ranking_order(populated_db):
    """Results must be sorted by descending cosine score."""
    conn, uri = populated_db
    with _mock_embed_query(_QUERY_VEC):
        results = retrieve("any query", uri, top_k=4)

    scores = [r["score"] for r in results]
    assert scores == sorted(scores, reverse=True), "Results not in descending score order"


def test_retrieve_best_match_is_b(populated_db):
    """The top result should be chunk B (closest to the query vector)."""
    conn, uri = populated_db
    with _mock_embed_query(_QUERY_VEC):
        results = retrieve("any query", uri, top_k=4)

    assert results[0]["source"] == "b.md", (
        f"Expected 'b.md' as top result, got '{results[0]['source']}'"
    )


def test_retrieve_result_keys(populated_db):
    """Each result dict must have exactly the required keys."""
    conn, uri = populated_db
    with _mock_embed_query(_QUERY_VEC):
        results = retrieve("any query", uri, top_k=2)

    for r in results:
        assert set(r.keys()) >= {"source", "heading", "text", "score"}


def test_retrieve_top_k_capped_at_available(populated_db):
    """Asking for more results than rows should return only what's available."""
    conn, uri = populated_db
    with _mock_embed_query(_QUERY_VEC):
        results = retrieve("any query", uri, top_k=100)
    assert len(results) == len(_FIXTURE_CHUNKS)


def test_retrieve_empty_db():
    """retrieve() on an empty DB should return an empty list."""
    uri = "file:emptydb?mode=memory&cache=shared"
    conn = sqlite3.connect(uri, uri=True)
    drop_and_recreate(conn)
    try:
        with _mock_embed_query(_QUERY_VEC):
            results = retrieve("any query", uri, top_k=5)
        assert results == []
    finally:
        conn.close()
