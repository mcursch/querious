"""RAG pipeline: chunking, Voyage AI embeddings, cosine similarity retrieval."""
import os
import re
import sqlite3
import struct
from pathlib import Path
from typing import Any

import numpy as np

EMBEDDINGS_DB_PATH = Path("data/embeddings.db")
DOCS_DIR = Path("data/docs")
CHUNK_TARGET_TOKENS = 500
CHUNK_OVERLAP_TOKENS = 50
TOP_K = 5


# ---------------------------------------------------------------------------
# Embedding helpers
# ---------------------------------------------------------------------------

def _get_voyage_client():
    import voyageai  # lazy import so tests can mock
    return voyageai.Client()


def embed_query(text: str) -> list[float]:
    vc = _get_voyage_client()
    result = vc.embed([text], model="voyage-3.5", input_type="query")
    return result.embeddings[0]


def embed_documents(texts: list[str]) -> list[list[float]]:
    vc = _get_voyage_client()
    result = vc.embed(texts, model="voyage-3.5", input_type="document")
    return result.embeddings


# ---------------------------------------------------------------------------
# Embedding storage (float32 numpy bytes)
# ---------------------------------------------------------------------------

def _vec_to_blob(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def _blob_to_vec(blob: bytes) -> np.ndarray:
    n = len(blob) // 4
    return np.array(struct.unpack(f"{n}f", blob), dtype=np.float32)


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

def _rough_token_count(text: str) -> int:
    """Very rough approximation: ~4 chars per token."""
    return len(text) // 4


def chunk_markdown(source: str, text: str) -> list[dict[str, Any]]:
    """Split markdown into heading-aware chunks."""
    lines = text.split("\n")
    chunks: list[dict[str, Any]] = []
    current_heading = ""
    current_lines: list[str] = []

    def flush(heading: str, lines: list[str]) -> None:
        content = "\n".join(lines).strip()
        if not content:
            return
        # split further if too large
        if _rough_token_count(content) > CHUNK_TARGET_TOKENS * 1.5:
            # simple sentence-based split
            sentences = re.split(r"(?<=[.!?])\s+", content)
            buf: list[str] = []
            for sent in sentences:
                buf.append(sent)
                if _rough_token_count(" ".join(buf)) >= CHUNK_TARGET_TOKENS:
                    chunks.append({"source": source, "heading": heading, "text": " ".join(buf)})
                    # overlap: keep last sentence
                    buf = buf[-1:] if buf else []
            if buf:
                chunks.append({"source": source, "heading": heading, "text": " ".join(buf)})
        else:
            chunks.append({"source": source, "heading": heading, "text": content})

    for line in lines:
        heading_match = re.match(r"^(#{1,4})\s+(.*)", line)
        if heading_match:
            flush(current_heading, current_lines)
            current_heading = heading_match.group(2)
            current_lines = [line]
        else:
            current_lines.append(line)

    flush(current_heading, current_lines)
    return chunks


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------

def embeddings_db_exists() -> bool:
    return EMBEDDINGS_DB_PATH.exists()


def retrieve(query: str, top_k: int = TOP_K) -> list[dict[str, Any]]:
    """Return top-k chunks most similar to query."""
    query_vec = np.array(embed_query(query), dtype=np.float32)
    query_norm = np.linalg.norm(query_vec)
    if query_norm == 0:
        return []

    conn = sqlite3.connect(EMBEDDINGS_DB_PATH)
    try:
        rows = conn.execute(
            "SELECT id, source, heading, text, embedding FROM chunks"
        ).fetchall()
    finally:
        conn.close()

    scored: list[tuple[float, dict]] = []
    for row in rows:
        doc_vec = _blob_to_vec(row[4])
        doc_norm = np.linalg.norm(doc_vec)
        if doc_norm == 0:
            continue
        cosine = float(np.dot(query_vec, doc_vec) / (query_norm * doc_norm))
        scored.append((cosine, {"source": row[1], "heading": row[2], "text": row[3]}))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored[:top_k]]
