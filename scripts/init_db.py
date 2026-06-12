#!/usr/bin/env python3
"""Initialize acme.db: create schema and run seeder."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from data.seed import main

if __name__ == "__main__":
    main()
