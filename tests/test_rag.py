"""Tests for policy chunking, retrieval and citations."""

import pytest

from app.rag.ingest import POLICY_PATH, chunk_markdown, ingest
from app.rag.retriever import PolicyRetriever


@pytest.fixture(scope="module")
def retriever():
    return PolicyRetriever(chunk_markdown(POLICY_PATH.read_text(encoding="utf-8")))


def test_chunk_citation_format():
    chunks = chunk_markdown("# T\n## Returns\n### Eligibility\n#### 30-day return window\nWithin 30 days.\n")
    assert len(chunks) == 1
    assert chunks[0].citation == "Policy: Returns > Eligibility > 30-day return window"
    assert chunks[0].text == "Within 30 days."


def test_knowledge_base_covers_required_topics(retriever):
    sections = {c.section for c in retriever.chunks}
    assert {"Returns", "Refunds", "Exchanges", "Warranty", "Shipping", "FAQ",
            "Damaged and defective items"} <= sections
    titles = {c.title for c in retriever.chunks}
    assert {"30-day return window", "Non-returnable product categories", "Refund processing time"} <= titles


@pytest.mark.parametrize("query, expected_title", [
    ("Can I return shoes I bought last week?", "30-day return window"),
    ("can i return a swimsuit or gift card", "Non-returnable product categories"),
    ("how long do refunds take to process", ("Refund processing time", "How long does a refund take")),
    ("my refund still hasn't arrived after 10 days", "Delayed refunds"),
    ("exchange for a different size", "Size and color exchanges"),
    ("is my smartwatch covered by warranty", "Standard warranty"),
    ("the item arrived broken and damaged", "Damaged on arrival"),
    ("my package is late, delayed shipment", "Delayed shipments"),
    ("return window for electronics earbuds", "Electronics return window"),
])
def test_retrieval_relevance(retriever, query, expected_title):
    acceptable = expected_title if isinstance(expected_title, tuple) else (expected_title,)
    titles = [r["citation"].rsplit(" > ", 1)[1] for r in retriever.search(query, k=3)]
    assert set(acceptable) & set(titles), titles


def test_results_carry_citation_and_text(retriever):
    top = retriever.search("30-day return window", k=1)[0]
    assert top["citation"].startswith("Policy: Returns > ")
    assert "30 days" in top["text"]


def test_unrelated_query_returns_no_evidence(retriever):
    assert retriever.search("quantum chromodynamics lattice") == []


def test_ingest_writes_index(tmp_path):
    out = tmp_path / "chunks.json"
    chunks = ingest(index_path=out)
    assert out.exists() and len(chunks) >= 20
