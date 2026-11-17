"""Hybrid retrieval: BM25 (lexical) fused with the vector search by reciprocal rank (RRF).

Why: the general-purpose embedder is weak with symbols and abbreviations ("CLDN18.2", "PD-L1",
"HER2", "ECOG"), which are exactly what the questions are about. A lexical score matches them
exactly. The two rankings are combined by rank, not by score, so their scales do not matter.

BM25 is implemented here (no new dependency) over the chunks stored in ChromaDB; the corpus is
small (about 1 400 chunks), so it is built in memory on each call.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import chromadb

from oncology_assistant.index import INDEX_DIR, Embedder, collection_name, query

_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "that",
        "the",
        "to",
        "was",
        "were",
        "which",
        "with",
        "what",
        "who",
        "whom",
        "how",
        "do",
        "does",
        "did",
        "have",
        "has",
        "not",
        "no",
        "this",
        "these",
        "those",
        "their",
        "its",
        "if",
        "than",
        "then",
    ]
)
BM25_K1 = 1.5
BM25_B = 0.75
RRF_K = 60
CANDIDATES = 50


def tokens(text: str) -> list[str]:
    """Lowercase alphanumeric tokens without stop words ("PD-L1" gives "pd" and "l1")."""
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOP]


def bm25_rank(question: str, chunks: Sequence[dict[str, Any]], k: int) -> list[dict[str, Any]]:
    """The ``k`` chunks with the best BM25 score for the question (score 0 chunks are dropped)."""
    docs = [tokens(f"{c['metadata'].get('title', '')} {c['text']}") for c in chunks]
    if not docs:
        return []
    avg_len = sum(len(d) for d in docs) / len(docs) or 1.0
    df: Counter[str] = Counter(term for d in docs for term in set(d))
    n = len(docs)
    terms = set(tokens(question))
    scored = []
    for chunk, doc in zip(chunks, docs, strict=True):
        tf = Counter(doc)
        score = 0.0
        for term in terms & tf.keys():
            idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
            norm = (
                tf[term]
                * (BM25_K1 + 1)
                / (tf[term] + BM25_K1 * (1 - BM25_B + BM25_B * len(doc) / avg_len))
            )
            score += idf * norm
        if score > 0:
            scored.append((score, chunk))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [chunk for _, chunk in scored[:k]]


def fuse(rankings: Sequence[Sequence[dict[str, Any]]], k: int) -> list[dict[str, Any]]:
    """Reciprocal rank fusion of several rankings; returns the best ``k`` chunks."""
    scores: dict[str, float] = {}
    by_id: dict[str, dict[str, Any]] = {}
    for ranking in rankings:
        for rank, chunk in enumerate(ranking, start=1):
            scores[chunk["id"]] = scores.get(chunk["id"], 0.0) + 1.0 / (RRF_K + rank)
            by_id.setdefault(chunk["id"], chunk)
    best = sorted(scores, key=lambda cid: scores[cid], reverse=True)[:k]
    return [{**by_id[cid], "distance": 1.0 - scores[cid] * RRF_K / 2} for cid in best]


def hybrid_query(
    strategy: str,
    text: str,
    k: int = 6,
    where: dict[str, Any] | None = None,
    path: Path = INDEX_DIR,
    embedder: Embedder | None = None,
) -> list[dict[str, Any]]:
    """Vector and BM25 searches over the same (filtered) chunks, fused by rank."""
    collection = chromadb.PersistentClient(path=str(path)).get_collection(
        collection_name(strategy), embedding_function=None
    )
    stored = collection.get(where=where, include=["documents", "metadatas"])
    chunks = [
        {"id": i, "text": d, "metadata": m}
        for i, d, m in zip(stored["ids"], stored["documents"], stored["metadatas"], strict=True)
    ]
    lexical = bm25_rank(text, chunks, CANDIDATES)
    vector = query(
        strategy,
        text,
        k=min(CANDIDATES, max(len(chunks), 1)),
        where=where,
        path=path,
        embedder=embedder,
    )
    return fuse([vector, lexical], k)
