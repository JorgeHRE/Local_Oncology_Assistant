"""Tests for the ChromaDB index, with a fake offline embedder (no model download)."""

from __future__ import annotations

import hashlib
import re

import pytest

from oncology_assistant import index
from oncology_assistant.chunking import STRATEGIES, load_documents

DIM = 256


def fake_embedder(texts: list[str]) -> list[list[float]]:
    """Hashed bag of words: deterministic, offline, and close for texts sharing words."""
    vectors = []
    for text in texts:
        vector = [0.0] * DIM
        for word in re.findall(r"[a-z0-9.]+", text.lower()):
            vector[int(hashlib.sha256(word.encode()).hexdigest(), 16) % DIM] += 1.0
        vectors.append(vector)
    return vectors


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    path = tmp_path_factory.mktemp("chroma")
    docs = [d for d in load_documents() if d.source == "clinicaltrials.gov"]
    counts = {
        s: index.build_index(s, docs=docs, path=path, embedder=fake_embedder) for s in STRATEGIES
    }
    return path, counts


def test_build_indexes_every_chunk_of_both_strategies(built):
    _, counts = built
    assert counts["whole"] == 49
    assert counts["structural"] > 1000


def test_rebuild_is_idempotent(built):
    path, counts = built
    docs = [d for d in load_documents() if d.source == "clinicaltrials.gov"]
    again = index.build_index("whole", docs=docs, path=path, embedder=fake_embedder)
    assert again == counts["whole"]


def test_query_finds_the_claudin_criterion_of_spotlight_and_glow(built):
    path, _ = built
    hits = index.query(
        "structural",
        "tumor expresses CLDN18.2 in at least 75% of tumor cells, moderate to strong membranous staining",
        k=5,
        path=path,
        embedder=fake_embedder,
    )
    assert {"NCT03504397", "NCT03653507"} & {h["metadata"]["identifier"] for h in hits}
    assert hits == sorted(hits, key=lambda h: h["distance"])


def test_query_can_filter_by_metadata(built):
    path, _ = built
    hits = index.query(
        "structural",
        "prior systemic chemotherapy",
        k=10,
        where={"$and": [{"section": "exclusion"}, {"role": {"$ne": "distractor"}}]},
        path=path,
        embedder=fake_embedder,
    )
    assert hits
    assert all(
        h["metadata"]["section"] == "exclusion" and h["metadata"]["role"] != "distractor"
        for h in hits
    )


def test_unknown_strategy_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="unknown strategy"):
        index.build_index("semantic", docs=[], path=tmp_path, embedder=fake_embedder)
