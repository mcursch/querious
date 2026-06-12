"""
RAG pipeline: chunking, embedding, and cosine retrieval.

Storage schema (embeddings.db):
    chunks(id INTEGER PK, source TEXT, heading TEXT, text TEXT, embedding BLOB)

Embeddings are stored as little-endian float32 numpy bytes.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any

import numpy as np

VOYAGE_MODEL = "voyage-3.5"

# Approximate token budget per chunk (1 token ≈ 4 chars).
CHUNK_TARGET_TOKENS = 500
CHUNK_OVERLAP_TOKENS = 50

# ──────────────────────────────────────────────────────────────────────────────
# Chunking
# ──────────────────────────────────────────────────────────────────────────────

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)", re.MULTILINE)


def _approx_tokens(text: str) -> int:
    """Very rough token count: 1 token ≈ 4 characters."""
    return max(1, len(text) // 4)


def _build_heading_path(stack: list[tuple[int, str]]) -> str:
    """Join active headings as 'H1 > H2 > H3'."""
    return " > ".join(text for _, text in stack)


def chunk_markdown(source: str, text: str) -> list[dict[str, str]]:
    """
    Split a markdown document into heading-aware chunks.

    Each chunk is a dict with keys: source, heading, text.
    Target size is ~500 tokens; long sections are split with ~50-token overlap.
    """
    lines = text.splitlines()

    # ── Phase 1: split into sections by heading ────────────────────────────
    sections: list[tuple[str, list[str]]] = []  # (heading_path, content_lines)
    heading_stack: list[tuple[int, str]] = []
    current_lines: list[str] = []

    for line in lines:
        m = _HEADING_RE.match(line)
        if m:
            # Flush the current section before starting a new one.
            if current_lines:
                heading_path = _build_heading_path(heading_stack)
                sections.append((heading_path, current_lines))
                current_lines = []

            level = len(m.group(1))
            heading_text = m.group(2).strip()

            # Pop headings that are at the same or deeper level.
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            heading_stack.append((level, heading_text))

            current_lines = [line]
        else:
            current_lines.append(line)

    if current_lines:
        sections.append((_build_heading_path(heading_stack), current_lines))

    # ── Phase 2: split sections that exceed the token budget ───────────────
    chunks: list[dict[str, str]] = []

    for heading_path, content_lines in sections:
        content = "\n".join(content_lines).strip()
        if not content:
            continue

        words = content.split()

        if len(words) <= CHUNK_TARGET_TOKENS:
            chunks.append({"source": source, "heading": heading_path, "text": content})
        else:
            # Sliding window with overlap.
            start = 0
            while start < len(words):
                end = start + CHUNK_TARGET_TOKENS
                chunk_text = " ".join(words[start:end])
                chunks.append({"source": source, "heading": heading_path, "text": chunk_text})
                if end >= len(words):
                    break
                start = end - CHUNK_OVERLAP_TOKENS

    return chunks


# ──────────────────────────────────────────────────────────────────────────────
# Embedding helpers
# ──────────────────────────────────────────────────────────────────────────────

def _get_voyage_client():
    """Return a Voyage AI client (lazy import so tests can run without the key)."""
    import voyageai  # noqa: PLC0415
    return voyageai.Client()


def embed_documents(texts: list[str]) -> list[np.ndarray]:
    """Embed a list of document strings with Voyage AI (input_type='document')."""
    client = _get_voyage_client()
    result = client.embed(texts, model=VOYAGE_MODEL, input_type="document")
    return [np.array(e, dtype=np.float32) for e in result.embeddings]


def embed_query(text: str) -> np.ndarray:
    """Embed a single query string with Voyage AI (input_type='query')."""
    client = _get_voyage_client()
    result = client.embed([text], model=VOYAGE_MODEL, input_type="query")
    return np.array(result.embeddings[0], dtype=np.float32)


# ──────────────────────────────────────────────────────────────────────────────
# Database helpers
# ──────────────────────────────────────────────────────────────────────────────

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS chunks (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    source    TEXT    NOT NULL,
    heading   TEXT    NOT NULL,
    text      TEXT    NOT NULL,
    embedding BLOB    NOT NULL
);
"""


def _vec_to_blob(vec: np.ndarray) -> bytes:
    """Serialize a float32 numpy array to raw bytes."""
    return vec.astype(np.float32).tobytes()


def _blob_to_vec(blob: bytes) -> np.ndarray:
    """Deserialize raw bytes back to a float32 numpy array."""
    return np.frombuffer(blob, dtype=np.float32)


def init_db(conn: sqlite3.Connection) -> None:
    """Create the chunks table (no-op if it already exists)."""
    conn.execute(CREATE_TABLE_SQL)
    conn.commit()


def drop_and_recreate(conn: sqlite3.Connection) -> None:
    """Drop and recreate the chunks table (used by build_index for idempotency)."""
    conn.execute("DROP TABLE IF EXISTS chunks")
    conn.execute(CREATE_TABLE_SQL)
    conn.commit()


def insert_chunks(conn: sqlite3.Connection, chunks: list[dict[str, Any]]) -> None:
    """
    Insert chunk dicts (keys: source, heading, text, embedding) into the DB.
    Each 'embedding' value must be a float32 numpy array.
    """
    rows = [
        (c["source"], c["heading"], c["text"], _vec_to_blob(c["embedding"]))
        for c in chunks
    ]
    conn.executemany(
        "INSERT INTO chunks (source, heading, text, embedding) VALUES (?, ?, ?, ?)",
        rows,
    )
    conn.commit()


# ──────────────────────────────────────────────────────────────────────────────
# Retrieval
# ──────────────────────────────────────────────────────────────────────────────

def retrieve(
    query: str,
    db_path: str,
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """
    Embed *query*, compute cosine similarity against every chunk in *db_path*,
    and return the *top_k* best matches sorted by descending score.

    Each result dict has keys: source, heading, text, score.

    Parameters
    ----------
    query:   Natural-language query string.
    db_path: Path to embeddings.db (or ':memory:' for tests).
    top_k:   Number of results to return (default 5).
    """
    # ── Load all stored chunks ─────────────────────────────────────────────
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT source, heading, text, embedding FROM chunks"
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return []

    sources = [r[0] for r in rows]
    headings = [r[1] for r in rows]
    texts = [r[2] for r in rows]
    embeddings = np.stack([_blob_to_vec(r[3]) for r in rows])  # (N, D)

    # ── Embed the query ────────────────────────────────────────────────────
    q_vec = embed_query(query)  # (D,)

    # ── Cosine similarity ──────────────────────────────────────────────────
    # cosine_sim(a, b) = dot(a, b) / (||a|| * ||b||)
    doc_norms = np.linalg.norm(embeddings, axis=1)          # (N,)
    q_norm = float(np.linalg.norm(q_vec))
    if q_norm == 0.0:
        return []

    scores = (embeddings @ q_vec) / (doc_norms * q_norm + 1e-10)  # (N,)

    # ── Select top-k ──────────────────────────────────────────────────────
    k = min(top_k, len(scores))
    top_indices = np.argpartition(scores, -k)[-k:]
    top_indices = top_indices[np.argsort(scores[top_indices])[::-1]]  # sort desc

    return [
        {
            "source": sources[i],
            "heading": headings[i],
            "text": texts[i],
            "score": float(scores[i]),
        }
        for i in top_indices
    ]
