#!/usr/bin/env python3
"""
Build (or rebuild) the RAG vector index.

Reads every *.md file from data/docs/, chunks and embeds the text with
Voyage AI, then writes data/embeddings.db.

The script is idempotent: the chunks table is dropped and recreated on
every run, so running it twice always produces the same row count.

Usage:
    VOYAGE_API_KEY=<key> python scripts/build_index.py
"""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

# Resolve project root so the script can be run from any CWD.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = PROJECT_ROOT / "data" / "docs"
DB_PATH = PROJECT_ROOT / "data" / "embeddings.db"

# Add project root to sys.path so we can import app.rag regardless of
# whether the package is installed.
sys.path.insert(0, str(PROJECT_ROOT))

from app.rag import (  # noqa: E402
    chunk_markdown,
    drop_and_recreate,
    embed_documents,
    insert_chunks,
)

# Voyage AI embed() accepts up to 128 texts per call; stay well within that.
EMBED_BATCH_SIZE = 64


def build_index(docs_dir: Path = DOCS_DIR, db_path: Path = DB_PATH) -> int:
    """
    Chunk all markdown files in *docs_dir*, embed them, and write to *db_path*.

    Returns the total number of chunks written.
    """
    md_files = sorted(docs_dir.glob("*.md"))
    if not md_files:
        print(f"[build_index] WARNING: no .md files found in {docs_dir}", file=sys.stderr)

    # ── Collect all chunks ─────────────────────────────────────────────────
    all_chunks: list[dict] = []
    for md_file in md_files:
        text = md_file.read_text(encoding="utf-8")
        chunks = chunk_markdown(md_file.name, text)
        all_chunks.extend(chunks)
        print(f"[build_index] {md_file.name}: {len(chunks)} chunk(s)")

    print(f"[build_index] Total chunks to embed: {len(all_chunks)}")

    # ── Embed in batches ───────────────────────────────────────────────────
    texts = [c["text"] for c in all_chunks]
    embeddings: list = []
    for batch_start in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[batch_start : batch_start + EMBED_BATCH_SIZE]
        batch_embeddings = embed_documents(batch)
        embeddings.extend(batch_embeddings)
        print(
            f"[build_index] Embedded {min(batch_start + EMBED_BATCH_SIZE, len(texts))}"
            f" / {len(texts)} chunks"
        )

    # Attach embedding vectors to chunk dicts.
    for chunk, vec in zip(all_chunks, embeddings):
        chunk["embedding"] = vec

    # ── Write to database (drop + recreate for idempotency) ────────────────
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        drop_and_recreate(conn)
        insert_chunks(conn, all_chunks)
    finally:
        conn.close()

    print(f"[build_index] Wrote {len(all_chunks)} chunks to {db_path}")
    return len(all_chunks)


if __name__ == "__main__":
    build_index()
