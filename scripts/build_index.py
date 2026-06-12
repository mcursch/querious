#!/usr/bin/env python3
"""Chunk docs → Voyage embeddings → embeddings.db (idempotent)."""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.rag import (
    DOCS_DIR,
    EMBEDDINGS_DB_PATH,
    _vec_to_blob,
    chunk_markdown,
    embed_documents,
)


def build_index() -> None:
    # Drop and recreate
    if EMBEDDINGS_DB_PATH.exists():
        EMBEDDINGS_DB_PATH.unlink()

    all_chunks: list[dict] = []
    for md_file in sorted(DOCS_DIR.glob("*.md")):
        text = md_file.read_text(encoding="utf-8")
        chunks = chunk_markdown(md_file.name, text)
        all_chunks.extend(chunks)
        print(f"  {md_file.name}: {len(chunks)} chunks")

    print(f"Total: {len(all_chunks)} chunks — embedding with Voyage AI...")

    texts = [c["text"] for c in all_chunks]
    # Embed first; only create the DB file once we have data to write
    embeddings = embed_documents(texts)

    conn = sqlite3.connect(EMBEDDINGS_DB_PATH)
    try:
        conn.execute("""
            CREATE TABLE chunks (
                id        INTEGER PRIMARY KEY,
                source    TEXT NOT NULL,
                heading   TEXT,
                text      TEXT NOT NULL,
                embedding BLOB NOT NULL
            )
        """)
        rows = [
            (c["source"], c["heading"], c["text"], _vec_to_blob(emb))
            for c, emb in zip(all_chunks, embeddings)
        ]
        conn.executemany(
            "INSERT INTO chunks (source, heading, text, embedding) VALUES (?,?,?,?)", rows
        )
        conn.commit()
    except Exception:
        conn.close()
        EMBEDDINGS_DB_PATH.unlink(missing_ok=True)
        raise
    else:
        conn.close()

    print(f"Index built: {EMBEDDINGS_DB_PATH}")


if __name__ == "__main__":
    build_index()
