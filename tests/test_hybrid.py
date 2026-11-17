"""Tests for the lexical ranking and the rank fusion of the hybrid search (offline)."""

from __future__ import annotations

from oncology_assistant import hybrid


def chunk(chunk_id: str, text: str) -> dict:
    return {"id": chunk_id, "text": text, "metadata": {"title": ""}}


def test_tokens_drop_stop_words_and_split_symbols():
    assert hybrid.tokens("What is the PD-L1 CPS of HER2?") == ["pd", "l1", "cps", "her2"]


def test_bm25_ranks_the_chunk_that_shares_the_rare_symbol_first():
    chunks = [
        chunk("a", "Subjects must have adequate bone marrow function"),
        chunk("b", "Tumor positive for CLDN18.2 staining intensity"),
        chunk("c", "Subjects must sign the informed consent form"),
    ]
    ranked = hybrid.bm25_rank("CLDN18.2 threshold", chunks, k=3)
    assert [c["id"] for c in ranked] == ["b"]  # chunks with score 0 are dropped


def test_bm25_on_no_chunks_is_empty():
    assert hybrid.bm25_rank("anything", [], k=3) == []


def test_fusion_prefers_chunks_ranked_well_by_both_searches():
    vector = [chunk("x", ""), chunk("y", ""), chunk("z", "")]
    lexical = [chunk("y", ""), chunk("w", "")]
    fused = hybrid.fuse([vector, lexical], k=3)
    assert fused[0]["id"] == "y"
    assert {c["id"] for c in fused} <= {"x", "y", "z", "w"}
    assert [c["distance"] for c in fused] == sorted(c["distance"] for c in fused)
