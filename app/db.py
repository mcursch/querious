"""Read-only SQLite access for the Querious chatbot."""
import sqlite3
from pathlib import Path

DB_PATH = Path("data/acme.db")


def get_connection() -> sqlite3.Connection:
    """Return a read-only connection to acme.db."""
    uri = f"file:{DB_PATH}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def db_exists() -> bool:
    return DB_PATH.exists()
