#!/usr/bin/env python3
"""
setup.py — Querious Setup Orchestrator

Runs the full data-setup pipeline:
  1. Check required environment variables (ANTHROPIC_API_KEY, VOYAGE_API_KEY)
  2. Run scripts/init_db.py  → creates data/acme.db with schema + seed data
  3. Validate data/acme.db   → must exist and be non-empty
  4. Run scripts/build_index.py → chunks docs + embeds via Voyage AI → data/embeddings.db
  5. Validate data/embeddings.db → must exist and be non-empty
  6. Print a row-count summary for every table in both databases

Usage (from the project root):
    python setup.py

Both ANTHROPIC_API_KEY and VOYAGE_API_KEY must be present in the environment
(or in a .env file loaded before running this script).
"""
import os
import sys
import sqlite3
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SEP = "=" * 60


def header(title: str) -> None:
    print(f"\n{SEP}")
    print(f"  {title}")
    print(SEP, flush=True)


def ok(msg: str) -> None:
    print(f"  ✓ {msg}", flush=True)


def fail(msg: str) -> None:
    print(f"\nERROR: {msg}", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Step 1 — environment validation
# ---------------------------------------------------------------------------

def check_env() -> None:
    """Fail fast with a clear diagnostic if required API keys are missing.

    Called before any other output so the error is the first thing the user sees.
    """
    missing = [k for k in ("ANTHROPIC_API_KEY", "VOYAGE_API_KEY") if not os.environ.get(k)]
    if missing:
        lines = [
            "Missing required environment variables:",
            "",
        ] + [f"    {k}" for k in missing] + [
            "",
            "Set them before running setup:",
            "    export ANTHROPIC_API_KEY=sk-ant-...",
            "    export VOYAGE_API_KEY=pa-...",
            "",
            "Or copy .env.example → .env, fill in the values, and source it:",
            "    cp .env.example .env && source .env",
        ]
        print("\n".join(lines), file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Step 2 & 4 — run a child script
# ---------------------------------------------------------------------------

def run_script(script_rel: str, label: str) -> None:
    """Run a Python script as a subprocess; exit non-zero if it fails."""
    script_path = ROOT / script_rel
    if not script_path.exists():
        fail(f"Script not found: {script_path}")

    header(label)
    result = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=str(ROOT),
    )
    if result.returncode != 0:
        fail(f"{label} failed (exit code {result.returncode})")
    ok(f"{label} completed successfully")


# ---------------------------------------------------------------------------
# Step 3 & 5 — validate a database file
# ---------------------------------------------------------------------------

def validate_db(db_path: Path, label: str) -> None:
    """Assert that the SQLite file exists and has a non-zero size."""
    if not db_path.exists():
        fail(
            f"{label} was not created.\n"
            f"Expected file: {db_path}\n"
            "Check the script output above for errors."
        )
    size = db_path.stat().st_size
    if size == 0:
        fail(
            f"{label} exists but is empty (0 bytes).\n"
            "This indicates an error during database creation."
        )
    ok(f"{label} exists ({size:,} bytes)")


# ---------------------------------------------------------------------------
# Step 6 — row-count summary
# ---------------------------------------------------------------------------

def table_row_counts(db_path: Path) -> list[tuple[str, int]]:
    """Return (table_name, count) pairs for every user table in the database."""
    conn = sqlite3.connect(str(db_path))
    try:
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
        ]
        return [(t, conn.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0]) for t in tables]
    finally:
        conn.close()


def print_summary(acme_db: Path, embeddings_db: Path) -> None:
    header("Setup Summary")

    print(f"\n  {acme_db.name}")
    print(f"  {'─' * 40}")
    for table, count in table_row_counts(acme_db):
        print(f"    {table:<24} {count:>6} rows")

    print(f"\n  {embeddings_db.name}")
    print(f"  {'─' * 40}")
    for table, count in table_row_counts(embeddings_db):
        print(f"    {table:<24} {count:>6} rows")

    print()
    ok("Setup complete!")
    print()
    print("  Start the app with:")
    print("    uvicorn app.main:app --reload")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    acme_db       = ROOT / "data" / "acme.db"
    embeddings_db = ROOT / "data" / "embeddings.db"

    # 1. Validate env vars — fail fast before any output or slow work
    check_env()

    print(SEP)
    print("  Querious — Setup")
    print(SEP)
    ok("ANTHROPIC_API_KEY is set")
    ok("VOYAGE_API_KEY is set")

    # 2. Initialise the relational database
    run_script("scripts/init_db.py", "Initialising acme.db (schema + seed data)")

    # 3. Validate acme.db
    validate_db(acme_db, "data/acme.db")

    # 4. Build the RAG embedding index
    run_script("scripts/build_index.py", "Building RAG index (chunking + Voyage AI embeddings)")

    # 5. Validate embeddings.db
    validate_db(embeddings_db, "data/embeddings.db")

    # 6. Print full row-count summary
    print_summary(acme_db, embeddings_db)


if __name__ == "__main__":
    main()
