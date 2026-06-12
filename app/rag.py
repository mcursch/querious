"""
RAG pipeline: chunking, Voyage AI embeddings, cosine similarity retrieval.

Storage: embeddings.db (SQLite) with table:
  chunks(id INTEGER PK, source TEXT, heading TEXT, text TEXT, embedding BLOB)

Embeddings are stored as raw float32 numpy bytes.
"""

import os
import struct
from pathlib import Path
from typing import Any

_BASE_DIR = Path(__file__).resolve().parent.parent
EMBEDDINGS_DB_PATH = os.environ.get(
    "EMBEDDINGS_DB_PATH", str(_BASE_DIR / "data" / "embeddings.db")
)
VOYAGE_API_KEY = os.environ.get("VOYAGE_API_KEY", "")
VOYAGE_MODEL = "voyage-3.5"
TOP_K = 5


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Pure-Python cosine similarity."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _blob_to_floats(blob: bytes) -> list[float]:
    """Deserialise a float32 numpy bytes blob."""
    n = len(blob) // 4
    return list(struct.unpack(f"{n}f", blob))


def _embed_query(text: str) -> list[float] | None:
    """Embed a single query string with Voyage AI."""
    if not VOYAGE_API_KEY:
        return None
    try:
        import voyageai  # type: ignore

        client = voyageai.Client(api_key=VOYAGE_API_KEY)
        result = client.embed([text], model=VOYAGE_MODEL, input_type="query")
        return result.embeddings[0]
    except Exception:
        return None


def search_docs(query: str, top_k: int = TOP_K) -> dict[str, Any]:
    """
    Retrieve the top-k most relevant document chunks for *query*.

    Returns:
      - ``content``: formatted string with chunk text + source attribution
      - ``is_error``: bool
      - ``chunk_count``: int
    """
    import sqlite3

    if not Path(EMBEDDINGS_DB_PATH).exists():
        return {
            "is_error": True,
            "content": (
                f"Embeddings database not found at {EMBEDDINGS_DB_PATH}. "
                "Run scripts/build_index.py first."
            ),
            "chunk_count": 0,
        }

    query_vec = _embed_query(query)
    if query_vec is None:
        # Fallback: full-text keyword search when Voyage is unavailable
        return _keyword_search(query, top_k)

    try:
        conn = sqlite3.connect(EMBEDDINGS_DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT id, source, heading, text, embedding FROM chunks").fetchall()
        conn.close()
    except Exception as exc:
        return {"is_error": True, "content": f"Failed to read embeddings: {exc}", "chunk_count": 0}

    scored: list[tuple[float, dict]] = []
    for row in rows:
        emb = _blob_to_floats(bytes(row["embedding"]))
        score = _cosine_similarity(query_vec, emb)
        scored.append((score, dict(row)))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:top_k]

    if not top:
        return {
            "is_error": False,
            "content": "No relevant documents found.",
            "chunk_count": 0,
        }

    parts: list[str] = []
    for rank, (score, chunk) in enumerate(top, start=1):
        source = chunk.get("source", "unknown")
        heading = chunk.get("heading", "")
        text = chunk.get("text", "")
        heading_str = f" › {heading}" if heading else ""
        parts.append(f"[{rank}] Source: {source}{heading_str}\n{text}")

    return {
        "is_error": False,
        "content": "\n\n---\n\n".join(parts),
        "chunk_count": len(top),
    }


def _keyword_search(query: str, top_k: int) -> dict[str, Any]:
    """
    Simple keyword-based fallback when Voyage embeddings are unavailable.
    Scores chunks by counting query-word occurrences (case-insensitive).
    """
    import sqlite3

    try:
        conn = sqlite3.connect(EMBEDDINGS_DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT id, source, heading, text FROM chunks").fetchall()
        conn.close()
    except Exception as exc:
        return {"is_error": True, "content": f"Failed to read chunks: {exc}", "chunk_count": 0}

    words = query.lower().split()
    scored: list[tuple[int, dict]] = []
    for row in rows:
        text_lower = (row["text"] or "").lower()
        score = sum(text_lower.count(w) for w in words)
        scored.append((score, dict(row)))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = [item for item in scored if item[0] > 0][:top_k]

    if not top:
        return {
            "is_error": False,
            "content": "No relevant documents found.",
            "chunk_count": 0,
        }

    parts: list[str] = []
    for rank, (_, chunk) in enumerate(top, start=1):
        source = chunk.get("source", "unknown")
        heading = chunk.get("heading", "")
        text = chunk.get("text", "")
        heading_str = f" › {heading}" if heading else ""
        parts.append(f"[{rank}] Source: {source}{heading_str}\n{text}")

    return {
        "is_error": False,
        "content": "\n\n---\n\n".join(parts),
        "chunk_count": len(top),
    }
