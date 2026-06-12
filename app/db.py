"""
app/db.py — Database access helpers for Querious.

The bot always opens acme.db in read-only mode via the SQLite URI interface
(mode=ro), so write operations are impossible at the connection level.
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "acme.db"


def get_read_only_connection() -> sqlite3.Connection:
    """Return a read-only SQLite connection to data/acme.db.

    Uses the SQLite URI ``file:...?mode=ro`` which causes the driver to raise
    ``sqlite3.OperationalError`` on any attempted write, even before SQL
    execution (the file descriptor is opened O_RDONLY at the OS level).
    """
    uri = DB_PATH.resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn
