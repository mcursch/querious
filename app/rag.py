"""
RAG pipeline — chunking, Voyage AI embedding, cosine retrieval.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import struct
from pathlib import Path
from typing import TypedDict

import numpy as np

# ---------------------------------------------------------------------------
# Chunking constants and helpers
# ---------------------------------------------------------------------------

TARGET_TOKENS: int = 400   # target chunk size in approximate tokens (whitespace words)
MAX_TOKENS: int = 600      # hard ceiling; no chunk should exceed this

# Internal character-based limits derived from the token constants.
# Using ~4 chars/token keeps chunks well under the MAX_TOKENS ceiling even
# for very short words.
_TARGET_CHARS: int = TARGET_TOKENS * 4   # 1600 chars ≈ 400 tokens
_OVERLAP_CHARS: int = 100                # ~20 word overlap between consecutive chunks


def _count_tokens(text: str) -> int:
    """Estimate the token count of *text* via whitespace split (one word ≈ one token)."""
    return len(text.split())


def _split_text(text: str) -> list[str]:
    """Split *text* into overlapping chunks of at most _TARGET_CHARS characters.

    Boundaries are chosen at paragraph, newline, sentence, or word breaks to
    avoid cutting in the middle of a sentence.  The last _OVERLAP_CHARS of
    chunk N are repeated at the start of chunk N+1.
    """
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + _TARGET_CHARS
        if end >= len(text):
            tail = text[start:].strip()
            if tail:
                chunks.append(tail)
            break
        # Prefer natural break points (paragraph → newline → sentence → word)
        for sep in ["\n\n", "\n", ". ", " "]:
            pos = text.rfind(sep, start + _OVERLAP_CHARS, end)
            if pos > start:
                end = pos + len(sep)
                break
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        # Next chunk starts overlap_chars before where we ended so context is shared
        next_start = end - _OVERLAP_CHARS
        if next_start <= start:
            # Safeguard against infinite loop on pathological input
            next_start = end
        start = next_start
    return chunks


def chunk_document(text: str, source: str) -> list[dict]:
    """Heading-aware markdown chunker.

    Splits *text* into chunks respecting heading hierarchy and size limits.
    Returns a list of dicts with keys ``source``, ``heading``, and ``text``.
    """
    heading_re = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
    matches = list(heading_re.finditer(text))

    if not matches:
        # No headings — chunk the whole document as plain text
        return [
            {"source": source, "heading": "", "text": chunk}
            for chunk in _split_text(text)
        ]

    # Collect sections: (level, heading_text, full_section_content)
    sections: list[tuple[int, str, str]] = []

    # Preamble before the first heading
    if matches[0].start() > 0:
        preamble = text[: matches[0].start()].strip()
        if preamble:
            sections.append((0, "", preamble))

    for i, m in enumerate(matches):
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        section_text = text[body_start:body_end].strip()
        # Prepend the heading line so each chunk is self-contained
        full_text = m.group(0) + ("\n\n" + section_text if section_text else "")
        sections.append((len(m.group(1)), m.group(2), full_text))

    chunks: list[dict] = []
    heading_stack: list[tuple[int, str]] = []

    for level, heading, content in sections:
        if level > 0:
            # Pop headings of equal or deeper level to maintain hierarchy
            heading_stack = [(lv, h) for lv, h in heading_stack if lv < level]
            heading_stack.append((level, heading))
        heading_path = " > ".join(h for _, h in heading_stack)

        if not content.strip():
            continue

        if _count_tokens(content) <= MAX_TOKENS:
            chunks.append({"source": source, "heading": heading_path, "text": content})
        else:
            for piece in _split_text(content):
                chunks.append({"source": source, "heading": heading_path, "text": piece})

    return chunks

# Anchor to the project root regardless of CWD
_ROOT = Path(__file__).parent.parent


def _get_embeddings_db() -> Path:
    """Return the path to embeddings.db, respecting QUERIOUS_DATA_DIR if set."""
    data_dir = os.environ.get("QUERIOUS_DATA_DIR")
    if data_dir:
        return Path(data_dir) / "embeddings.db"
    return _ROOT / "data" / "embeddings.db"


# Module-level alias kept for backwards-compatibility.  Frozen at import time;
# prefer _get_embeddings_db() internally.
EMBEDDINGS_DB = _get_embeddings_db()


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
    embeddings_db = _get_embeddings_db()
    if not embeddings_db.exists():
        raise FileNotFoundError(
            f"Embeddings database not found: {embeddings_db}. "
            "Run scripts/build_index.py first."
        )

    query_vec = _embed_query(query)

    conn = sqlite3.connect(embeddings_db)
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
