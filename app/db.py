"""SQLite connection helpers.

DB paths are resolved lazily (at call time) from the QUERIOUS_DATA_DIR environment
variable so tests can point the app at a temporary directory without import-order issues.
"""

import os
import sqlite3


def get_data_dir() -> str:
    return os.getenv("QUERIOUS_DATA_DIR", "data")


def get_acme_db_path() -> str:
    return os.path.join(get_data_dir(), "acme.db")


def get_embeddings_db_path() -> str:
    return os.path.join(get_data_dir(), "embeddings.db")


def get_connection() -> sqlite3.Connection:
    """Open a read-only connection to acme.db via the SQLite URI interface."""
    path = get_acme_db_path()
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)
