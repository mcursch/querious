"""RAG pipeline: Voyage AI embeddings and SQLite vector store."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import List

import numpy as np
import voyageai

# Voyage model to use for all embeddings
_MODEL = "voyage-3.5"
# Maximum texts per Voyage API request (well within Voyage's limit of 128)
_BATCH_SIZE = 128
# Default path for the vector store database
_DEFAULT_DB_PATH = "data/embeddings.db"


def _get_client() -> voyageai.Client:
    """Return a Voyage AI client (reads VOYAGE_API_KEY from the environment)."""
    return voyageai.Client()


def embed_chunks(chunks: List[dict]) -> List[np.ndarray]:
    """Embed a list of chunk dicts using Voyage AI with input_type='document'.

    Each dict must contain at least a 'text' key.
    Returns a list of float32 numpy arrays, one per chunk, in the same order.
    """
    client = _get_client()
    texts = [c["text"] for c in chunks]
    embeddings: List[np.ndarray] = []

    for start in range(0, len(texts), _BATCH_SIZE):
        batch = texts[start : start + _BATCH_SIZE]
        result = client.embed(batch, model=_MODEL, input_type="document")
        for vec in result.embeddings:
            embeddings.append(np.array(vec, dtype=np.float32))

    return embeddings


def embed_query(text: str) -> np.ndarray:
    """Embed a single query string using Voyage AI with input_type='query'.

    Returns a float32 numpy array.
    """
    client = _get_client()
    result = client.embed([text], model=_MODEL, input_type="query")
    return np.array(result.embeddings[0], dtype=np.float32)


def store_chunks(
    chunks: List[dict],
    embeddings: List[np.ndarray],
    db_path: str = _DEFAULT_DB_PATH,
) -> None:
    """Create (or replace) an SQLite database at *db_path* and persist chunks.

    The *chunks* list is a list of dicts with keys: source, heading, text.
    The *embeddings* list contains the corresponding float32 numpy arrays.

    The table schema is:
        chunks(id INTEGER PRIMARY KEY, source TEXT, heading TEXT,
               text TEXT, embedding BLOB)

    Embeddings are stored as raw little-endian float32 bytes so they can be
    round-tripped via ``np.frombuffer(blob, dtype=np.float32)``.
    """
    if len(chunks) != len(embeddings):
        raise ValueError(
            f"chunks and embeddings must have the same length "
            f"(got {len(chunks)} and {len(embeddings)})"
        )

    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db_path) as conn:
        conn.execute("DROP TABLE IF EXISTS chunks")
        conn.execute(
            """
            CREATE TABLE chunks (
                id        INTEGER PRIMARY KEY,
                source    TEXT,
                heading   TEXT,
                text      TEXT,
                embedding BLOB
            )
            """
        )

        rows = [
            (
                chunk.get("source", ""),
                chunk.get("heading", ""),
                chunk.get("text", ""),
                emb.astype(np.float32).tobytes(),
            )
            for chunk, emb in zip(chunks, embeddings)
        ]
        conn.executemany(
            "INSERT INTO chunks (source, heading, text, embedding) VALUES (?, ?, ?, ?)",
            rows,
        )
        conn.commit()
