"""Build the policy RAG index. Usage: python scripts/ingest_policy.py"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.rag.ingest import INDEX_PATH, ingest  # noqa: E402

if __name__ == "__main__":
    chunks = ingest()
    print(f"Indexed {len(chunks)} policy rules -> {INDEX_PATH}")
    for c in chunks:
        print(f"  {c.citation}")
