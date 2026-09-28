"""TF-IDF policy retriever returning chunks with section citations."""

import re
from functools import lru_cache

from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel

from app.rag.ingest import PolicyChunk, load_chunks

MIN_SCORE = 0.05
_SUFFIXES = ("ing", "ed", "es", "s")


def _stem(word: str) -> str:
    """Crude suffix stripping so 'refunds'/'refunded'/'refund' match."""
    for suffix in _SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            return word[: -len(suffix)]
    return word


def _tokenize(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)?", text.lower())
    return [_stem(w) for w in words if w not in ENGLISH_STOP_WORDS]


class PolicyRetriever:
    def __init__(self, chunks: list[PolicyChunk]):
        self.chunks = chunks
        # Headings are repeated so a query matching a rule's title ranks it highly.
        docs = [f"{c.section} {c.subsection} {c.title} {c.title} {c.text}" for c in chunks]
        self.vectorizer = TfidfVectorizer(
            tokenizer=_tokenize, token_pattern=None, lowercase=False, ngram_range=(1, 2), sublinear_tf=True
        )
        self.matrix = self.vectorizer.fit_transform(docs)

    def search(self, query: str, k: int = 3, min_score: float = MIN_SCORE) -> list[dict]:
        """Top-k matching policy rules. An empty list means no policy evidence was found."""
        scores = linear_kernel(self.vectorizer.transform([query]), self.matrix).ravel()
        ranked = scores.argsort()[::-1][:k]
        return [
            {
                "chunk_id": self.chunks[i].chunk_id,
                "citation": self.chunks[i].citation,
                "text": self.chunks[i].text,
                "score": round(float(scores[i]), 3),
            }
            for i in ranked
            if scores[i] >= min_score
        ]


@lru_cache
def get_retriever() -> PolicyRetriever:
    return PolicyRetriever(load_chunks())


def search_policy(query: str, k: int = 3) -> list[dict]:
    return get_retriever().search(query, k=k)
