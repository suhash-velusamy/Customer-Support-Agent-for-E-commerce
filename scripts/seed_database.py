"""Seed the SQLite database. Usage: python scripts/seed_database.py"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config.settings import get_settings  # noqa: E402
from app.database.db import get_connection  # noqa: E402
from app.database.seed import seed  # noqa: E402

if __name__ == "__main__":
    path = get_settings().database_path
    with get_connection(path) as conn:
        counts = seed(conn)
    print(f"Seeded {path}")
    for table, n in counts.items():
        print(f"  {table:12} {n}")
