#!/usr/bin/env python3
"""
scripts/build_index.py

Chunk the markdown docs in data/docs/, embed with Voyage AI voyage-3.5,
and store in data/embeddings.db.  Idempotent: drops and rebuilds the
chunks table on every run.

Run from the project root:
    python scripts/build_index.py
"""
import os
import re
import sys
import sqlite3
import struct
from pathlib import Path

try:
    import numpy as np
except ImportError:
    print("ERROR: numpy not installed. Run: pip install numpy", file=sys.stderr)
    sys.exit(1)

try:
    import voyageai
except ImportError:
    print("ERROR: voyageai not installed. Run: pip install voyageai", file=sys.stderr)
    sys.exit(1)

ROOT        = Path(__file__).parent.parent
DOCS_DIR    = ROOT / "data" / "docs"
DB_PATH     = ROOT / "data" / "embeddings.db"
VOYAGE_MODEL = "voyage-3.5"
MAX_CHARS   = 1800   # ~450 tokens @ ~4 chars/token
OVERLAP_CHARS = 200  # ~50-token overlap
BATCH_SIZE  = 128    # Voyage API batch limit


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

def split_text(text: str, max_chars: int, overlap_chars: int) -> list[str]:
    """Split a long string into overlapping chunks, breaking at paragraph/sentence boundaries."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + max_chars
        if end >= len(text):
            tail = text[start:].strip()
            if tail:
                chunks.append(tail)
            break
        # Try to break at a paragraph boundary first, then newline, then sentence
        for sep in ['\n\n', '\n', '. ', ' ']:
            pos = text.rfind(sep, start + overlap_chars, end)
            if pos > start:
                end = pos + len(sep)
                break
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        # Next chunk starts overlap_chars before where we ended
        start = end - overlap_chars
        if start <= 0:
            start = end  # safeguard against infinite loop on very short text
    return chunks


def chunk_markdown(text: str, source: str) -> list[dict]:
    """
    Heading-aware markdown chunker.
    Returns a list of dicts: {source, heading, text}
    """
    heading_re = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)
    matches = list(heading_re.finditer(text))

    if not matches:
        # No headings — chunk the whole file
        return [
            {'source': source, 'heading': '', 'text': chunk}
            for chunk in split_text(text, MAX_CHARS, OVERLAP_CHARS)
        ]

    # Collect sections: [(level, heading_text, section_body), ...]
    sections = []

    # Preamble (text before first heading)
    if matches[0].start() > 0:
        preamble = text[:matches[0].start()].strip()
        if preamble:
            sections.append((0, '', preamble))

    for i, m in enumerate(matches):
        body_start = m.end()
        body_end   = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        section_text = text[body_start:body_end].strip()
        # Include the heading line itself in the section text
        full_text = m.group(0) + ('\n\n' + section_text if section_text else '')
        sections.append((len(m.group(1)), m.group(2), full_text))

    chunks = []
    heading_stack: list[tuple[int, str]] = []

    for level, heading, content in sections:
        if level > 0:
            # Pop headings of equal or deeper level
            heading_stack = [(l, h) for l, h in heading_stack if l < level]
            heading_stack.append((level, heading))
        heading_path = ' > '.join(h for _, h in heading_stack)

        if not content.strip():
            continue

        if len(content) <= MAX_CHARS:
            chunks.append({'source': source, 'heading': heading_path, 'text': content})
        else:
            for piece in split_text(content, MAX_CHARS, OVERLAP_CHARS):
                chunks.append({'source': source, 'heading': heading_path, 'text': piece})

    return chunks


# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------

def embed_texts(texts: list[str], vo: "voyageai.Client") -> list[list[float]]:
    """Embed a list of texts in batches, returning a list of float vectors."""
    all_embeddings: list[list[float]] = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i: i + BATCH_SIZE]
        result = vo.embed(batch, model=VOYAGE_MODEL, input_type="document")
        all_embeddings.extend(result.embeddings)
        print(f"    Embedded {min(i + BATCH_SIZE, len(texts))}/{len(texts)} chunks...")
    return all_embeddings


def floats_to_blob(vec: list[float]) -> bytes:
    """Encode a float list as a packed float32 bytes blob."""
    arr = np.array(vec, dtype=np.float32)
    return arr.tobytes()


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
DROP TABLE IF EXISTS chunks;
CREATE TABLE chunks (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    source    TEXT NOT NULL,
    heading   TEXT,
    text      TEXT NOT NULL,
    embedding BLOB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chunks_source ON chunks(source);
"""


def create_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    api_key = os.environ.get("VOYAGE_API_KEY")
    if not api_key:
        print("ERROR: VOYAGE_API_KEY is not set in the environment.", file=sys.stderr)
        sys.exit(1)

    if not DOCS_DIR.exists():
        print(f"ERROR: Docs directory not found: {DOCS_DIR}", file=sys.stderr)
        sys.exit(1)

    doc_files = sorted(DOCS_DIR.glob("*.md"))
    if not doc_files:
        print(f"ERROR: No markdown files found in {DOCS_DIR}", file=sys.stderr)
        sys.exit(1)

    print(f"  Found {len(doc_files)} markdown files in {DOCS_DIR.relative_to(ROOT)}")

    # Collect all chunks
    all_chunks: list[dict] = []
    for doc_path in doc_files:
        text = doc_path.read_text(encoding='utf-8')
        file_chunks = chunk_markdown(text, doc_path.name)
        print(f"    {doc_path.name:<40} → {len(file_chunks)} chunks")
        all_chunks.extend(file_chunks)

    print(f"\n  Total chunks to embed: {len(all_chunks)}")

    # Embed
    vo = voyageai.Client(api_key=api_key)
    texts = [c['text'] for c in all_chunks]
    embeddings = embed_texts(texts, vo)

    if len(embeddings) != len(all_chunks):
        print(
            f"ERROR: Expected {len(all_chunks)} embeddings, got {len(embeddings)}",
            file=sys.stderr,
        )
        sys.exit(1)

    # Store
    print(f"\n  Writing to {DB_PATH.relative_to(ROOT)}...")
    conn = create_db(DB_PATH)
    rows = [
        (c['source'], c['heading'], c['text'], floats_to_blob(emb))
        for c, emb in zip(all_chunks, embeddings)
    ]
    conn.executemany(
        "INSERT INTO chunks (source, heading, text, embedding) VALUES (?,?,?,?)",
        rows,
    )
    conn.commit()

    count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    conn.close()

    print(f"  ✓ embeddings.db: {count} chunks stored")
    print(f"  ✓ embeddings.db created at {DB_PATH}")


if __name__ == "__main__":
    main()
