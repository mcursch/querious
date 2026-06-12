"""
RAG pipeline — chunking, Voyage AI embedding, cosine retrieval.
"""

from __future__ import annotations

import json
import os
import sqlite3
import struct
from pathlib import Path
from typing import TypedDict

import numpy as np

EMBEDDINGS_DB = Path("data/embeddings.db")


class Chunk(TypedDict):
    source: str
    heading: str
    text: str
    score: float


def search(query: str, top_k: int = 5) -> list[Chunk]:
    """
    Embed *query* with Voyage AI and return the top-k most similar chunks
    from embeddings.db, ranked by cosine similarity.
    """
    if not EMBEDDINGS_DB.exists():
        raise FileNotFoundError(
            f"Embeddings database not found: {EMBEDDINGS_DB}. "
            "Run scripts/build_index.py first."
        )

    query_vec = _embed_query(query)

    conn = sqlite3.connect(EMBEDDINGS_DB)
    try:
        cur = conn.cursor()
        cur.execute("SELECT source, heading, text, embedding FROM chunks")
        rows = cur.fetchall()
    finally:
        conn.close()

    if not rows:
        return []

    # Build matrix of all chunk embeddings
    sources, headings, texts, embeddings = [], [], [], []
    for source, heading, text, emb_blob in rows:
        sources.append(source)
        headings.append(heading or "")
        texts.append(text)
        embeddings.append(_blob_to_vec(emb_blob))

    matrix = np.array(embeddings, dtype=np.float32)
    query_arr = np.array(query_vec, dtype=np.float32)

    # Cosine similarity (vectors are already L2-normalised by Voyage)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1e-9, norms)
    normed = matrix / norms
    q_norm = query_arr / (np.linalg.norm(query_arr) or 1e-9)
    scores = normed @ q_norm

    top_indices = np.argsort(scores)[::-1][:top_k]
    return [
        Chunk(
            source=sources[i],
            heading=headings[i],
            text=texts[i],
            score=float(scores[i]),
        )
        for i in top_indices
    ]


# ---------------------------------------------------------------------------
# Embedding helpers
# ---------------------------------------------------------------------------

def _embed_query(text: str) -> list[float]:
    import voyageai  # type: ignore[import]

    api_key = os.environ.get("VOYAGE_API_KEY")
    client = voyageai.Client(api_key=api_key)
    result = client.embed([text], model="voyage-3.5", input_type="query")
    return result.embeddings[0]


def _blob_to_vec(blob: bytes) -> list[float]:
    n = len(blob) // 4
    return list(struct.unpack(f"{n}f", blob))
