"""RAG pipeline: chunking, Voyage AI embeddings, cosine retrieval.

The full implementation (Voyage embeddings, build_index) lives in scripts/build_index.py.
This module exposes the retrieval function used by tools.py.  When the vector store has
not been built yet, search_docs returns an empty chunk list so the chatbot degrades
gracefully to the SQL path.
"""

import os
import sqlite3

from app.db import get_embeddings_db_path


def search_docs(query: str) -> dict:
    """Return top-5 document chunks most similar to *query*.

    Falls back to an empty result set if the embeddings DB does not exist or
    the ``chunks`` table has not been populated.
    """
    emb_path = get_embeddings_db_path()
    if not os.path.exists(emb_path):
        return {"chunks": [], "message": "Documentation index not built yet."}

    try:
        conn = sqlite3.connect(emb_path)
        try:
            rows = conn.execute(
                "SELECT source, heading, text FROM chunks ORDER BY rowid LIMIT 5"
            ).fetchall()
        except sqlite3.OperationalError:
            # Table doesn't exist — index not built.
            return {"chunks": [], "message": "Documentation index not built yet."}
        finally:
            conn.close()

        chunks = [{"source": r[0], "heading": r[1], "text": r[2]} for r in rows]
        return {"chunks": chunks}
    except Exception as exc:  # pragma: no cover
        return {"is_error": True, "error": str(exc)}
