"""Split the policy markdown into citable chunks and write them to the index directory.

Each chunk is the body under a level-4 heading (a single rule), labelled with its
heading path, e.g. "Returns > Eligibility > 30-day return window".
"""

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from app.config.settings import PROJECT_ROOT

POLICY_PATH = PROJECT_ROOT / "app" / "rag" / "documents" / "ecommerce_policy.md"
INDEX_PATH = PROJECT_ROOT / "data" / "index" / "policy_chunks.json"

_HEADING = re.compile(r"^(#{2,4})\s+(.+?)\s*$")


@dataclass(frozen=True)
class PolicyChunk:
    chunk_id: str
    section: str
    subsection: str
    title: str
    text: str

    @property
    def citation(self) -> str:
        return f"Policy: {self.section} > {self.subsection} > {self.title}"


def chunk_markdown(markdown: str) -> list[PolicyChunk]:
    path: dict[int, str] = {}
    chunks: list[PolicyChunk] = []
    body: list[str] = []

    def flush() -> None:
        text = " ".join(line.strip() for line in body if line.strip())
        if text and 4 in path:
            chunks.append(PolicyChunk(f"policy-{len(chunks) + 1:03d}", path[2], path[3], path[4], text))
        body.clear()

    for line in markdown.splitlines():
        match = _HEADING.match(line)
        if match:
            flush()
            level = len(match.group(1))
            path[level] = match.group(2)
            for deeper in [lvl for lvl in path if lvl > level]:
                del path[deeper]
        elif not line.startswith("# "):
            body.append(line)
    flush()
    return chunks


def ingest(policy_path: Path = POLICY_PATH, index_path: Path = INDEX_PATH) -> list[PolicyChunk]:
    chunks = chunk_markdown(policy_path.read_text(encoding="utf-8"))
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps([asdict(c) for c in chunks], indent=2), encoding="utf-8")
    return chunks


def load_chunks(index_path: Path = INDEX_PATH, policy_path: Path = POLICY_PATH) -> list[PolicyChunk]:
    """Load chunks from the index, (re)building it if missing or older than the policy document."""
    if not index_path.exists() or index_path.stat().st_mtime < policy_path.stat().st_mtime:
        return ingest(policy_path, index_path)
    return [PolicyChunk(**c) for c in json.loads(index_path.read_text(encoding="utf-8"))]
