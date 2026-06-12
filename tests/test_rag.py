"""Unit tests for app/rag.py — embedding helpers and vector store."""

from __future__ import annotations

import sqlite3
import types
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from app.rag import embed_chunks, embed_query, store_chunks


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _make_voyage_result(vectors: list[list[float]]) -> MagicMock:
    """Build a mock that mimics the EmbeddingsObject returned by voyageai."""
    result = MagicMock()
    result.embeddings = vectors
    return result


SAMPLE_CHUNKS = [
    {"source": "return_refund_policy.md", "heading": "Overview", "text": "30-day returns."},
    {"source": "shipping_policy.md", "heading": "Zones", "text": "Free shipping over $50."},
]

SAMPLE_VECTORS = [
    [0.1, 0.2, 0.3],
    [0.4, 0.5, 0.6],
]


# ---------------------------------------------------------------------------
# embed_chunks
# ---------------------------------------------------------------------------

class TestEmbedChunks:
    def test_calls_embed_with_document_input_type(self):
        mock_result = _make_voyage_result(SAMPLE_VECTORS)

        with patch("app.rag.voyageai.Client") as MockClient:
            instance = MockClient.return_value
            instance.embed.return_value = mock_result

            result = embed_chunks(SAMPLE_CHUNKS)

        instance.embed.assert_called_once_with(
            ["30-day returns.", "Free shipping over $50."],
            model="voyage-3.5",
            input_type="document",
        )

    def test_returns_float32_numpy_arrays(self):
        mock_result = _make_voyage_result(SAMPLE_VECTORS)

        with patch("app.rag.voyageai.Client") as MockClient:
            instance = MockClient.return_value
            instance.embed.return_value = mock_result

            result = embed_chunks(SAMPLE_CHUNKS)

        assert len(result) == len(SAMPLE_CHUNKS)
        for arr, expected in zip(result, SAMPLE_VECTORS):
            assert isinstance(arr, np.ndarray)
            assert arr.dtype == np.float32
            np.testing.assert_array_almost_equal(arr, expected)

    def test_batches_large_input(self):
        """More than 128 chunks should be split into two API calls."""
        n = 130
        big_chunks = [{"text": f"chunk {i}"} for i in range(n)]
        # Return a 3-dim vector per text in each batch
        batch1_vecs = [[float(i)] * 3 for i in range(128)]
        batch2_vecs = [[float(i)] * 3 for i in range(2)]

        mock_result1 = _make_voyage_result(batch1_vecs)
        mock_result2 = _make_voyage_result(batch2_vecs)

        with patch("app.rag.voyageai.Client") as MockClient:
            instance = MockClient.return_value
            instance.embed.side_effect = [mock_result1, mock_result2]

            result = embed_chunks(big_chunks)

        assert instance.embed.call_count == 2
        assert len(result) == n


# ---------------------------------------------------------------------------
# embed_query
# ---------------------------------------------------------------------------

class TestEmbedQuery:
    def test_calls_embed_with_query_input_type(self):
        mock_result = _make_voyage_result([[0.7, 0.8, 0.9]])

        with patch("app.rag.voyageai.Client") as MockClient:
            instance = MockClient.return_value
            instance.embed.return_value = mock_result

            result = embed_query("What is the return policy?")

        instance.embed.assert_called_once_with(
            ["What is the return policy?"],
            model="voyage-3.5",
            input_type="query",
        )

    def test_returns_float32_numpy_array(self):
        vec = [0.7, 0.8, 0.9]
        mock_result = _make_voyage_result([vec])

        with patch("app.rag.voyageai.Client") as MockClient:
            instance = MockClient.return_value
            instance.embed.return_value = mock_result

            result = embed_query("test")

        assert isinstance(result, np.ndarray)
        assert result.dtype == np.float32
        np.testing.assert_array_almost_equal(result, vec)


# ---------------------------------------------------------------------------
# store_chunks
# ---------------------------------------------------------------------------

class TestStoreChunks:
    def test_creates_db_with_correct_schema(self, tmp_path):
        db_path = str(tmp_path / "embeddings.db")
        embeddings = [np.array(v, dtype=np.float32) for v in SAMPLE_VECTORS]

        store_chunks(SAMPLE_CHUNKS, embeddings, db_path=db_path)

        with sqlite3.connect(db_path) as conn:
            # Verify table exists with the right columns
            cursor = conn.execute("PRAGMA table_info(chunks)")
            cols = {row[1]: row[2] for row in cursor.fetchall()}

        assert "id" in cols
        assert "source" in cols
        assert "heading" in cols
        assert "text" in cols
        assert "embedding" in cols
        assert cols["embedding"].upper() == "BLOB"

    def test_stores_correct_number_of_rows(self, tmp_path):
        db_path = str(tmp_path / "embeddings.db")
        embeddings = [np.array(v, dtype=np.float32) for v in SAMPLE_VECTORS]

        store_chunks(SAMPLE_CHUNKS, embeddings, db_path=db_path)

        with sqlite3.connect(db_path) as conn:
            (count,) = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()

        assert count == len(SAMPLE_CHUNKS)

    def test_blob_round_trip(self, tmp_path):
        """Embeddings stored as BLOB can be retrieved and decoded as float32 arrays."""
        db_path = str(tmp_path / "embeddings.db")
        original = [np.array(v, dtype=np.float32) for v in SAMPLE_VECTORS]

        store_chunks(SAMPLE_CHUNKS, original, db_path=db_path)

        with sqlite3.connect(db_path) as conn:
            rows = conn.execute(
                "SELECT source, heading, text, embedding FROM chunks ORDER BY id"
            ).fetchall()

        assert len(rows) == len(SAMPLE_CHUNKS)
        for row, chunk, expected_vec in zip(rows, SAMPLE_CHUNKS, original):
            source, heading, text, blob = row
            assert source == chunk["source"]
            assert heading == chunk["heading"]
            assert text == chunk["text"]
            recovered = np.frombuffer(blob, dtype=np.float32)
            np.testing.assert_array_equal(recovered, expected_vec)

    def test_replaces_existing_table(self, tmp_path):
        """Calling store_chunks twice replaces the old data (idempotent rebuild)."""
        db_path = str(tmp_path / "embeddings.db")
        embeddings = [np.array(v, dtype=np.float32) for v in SAMPLE_VECTORS]

        store_chunks(SAMPLE_CHUNKS, embeddings, db_path=db_path)

        # Second call with only one chunk
        new_chunk = [{"source": "new.md", "heading": "H1", "text": "new text"}]
        new_emb = [np.array([0.9, 0.8], dtype=np.float32)]
        store_chunks(new_chunk, new_emb, db_path=db_path)

        with sqlite3.connect(db_path) as conn:
            (count,) = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()

        assert count == 1

    def test_raises_on_length_mismatch(self, tmp_path):
        db_path = str(tmp_path / "embeddings.db")
        embeddings = [np.array([0.1, 0.2], dtype=np.float32)]  # only 1, but 2 chunks

        with pytest.raises(ValueError, match="same length"):
            store_chunks(SAMPLE_CHUNKS, embeddings, db_path=db_path)

    def test_creates_parent_directory(self, tmp_path):
        """store_chunks creates the parent directory if it doesn't exist."""
        db_path = str(tmp_path / "subdir" / "nested" / "embeddings.db")
        embeddings = [np.array(v, dtype=np.float32) for v in SAMPLE_VECTORS]

        store_chunks(SAMPLE_CHUNKS, embeddings, db_path=db_path)

        with sqlite3.connect(db_path) as conn:
            (count,) = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()

        assert count == len(SAMPLE_CHUNKS)
