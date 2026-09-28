import pytest

from app.database.db import connect
from app.database.seed import REFERENCE_DATE, seed


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "test.db"
    conn = connect(path)
    seed(conn)
    conn.close()
    return path


@pytest.fixture
def db(db_path):
    conn = connect(db_path)
    yield conn
    conn.close()


class FakeTavily:
    """Stands in for AsyncTavilyClient; records queries and returns canned results."""

    def __init__(self, results=None, fail=False):
        self.results = results or []
        self.fail = fail
        self.queries = []

    async def search(self, query, **kwargs):
        self.queries.append(query)
        if self.fail:
            raise RuntimeError("network down")
        return {"results": self.results}


@pytest.fixture
def fake_web():
    return FakeTavily()


@pytest.fixture
def agent(db_path, fake_web):
    """Rules-only agent (no LLM, no real web calls) against a fresh seeded database."""
    from app.graph.graph import SupportAgent
    from app.tools.tavily_search import WebSearch

    return SupportAgent(db_path=db_path, customer_id="CUST-001", use_llm=False, today=lambda: REFERENCE_DATE,
                        web=WebSearch(client=fake_web))
