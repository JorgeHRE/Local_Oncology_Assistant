"""Tests for the beta RAG with a fake embedder and a fake LLM (no model, no network)."""

from __future__ import annotations

import hashlib
import json
import re

import pytest

from oncology_assistant import index, rag
from oncology_assistant.chunking import load_documents

DIM = 256

TRIAL = "NCT03504397"  # SPOTLIGHT


def fake_embedder(texts: list[str]) -> list[list[float]]:
    """Hashed bag of words: deterministic and offline."""
    vectors = []
    for text in texts:
        vector = [0.0] * DIM
        for word in re.findall(r"[a-z0-9.]+", text.lower()):
            vector[int(hashlib.sha256(word.encode()).hexdigest(), 16) % DIM] += 1.0
        vectors.append(vector)
    return vectors


@pytest.fixture(scope="module")
def chroma(tmp_path_factory):
    path = tmp_path_factory.mktemp("chroma_rag")
    docs = [d for d in load_documents() if d.source == "clinicaltrials.gov"]
    index.build_index("structural", docs=docs, path=path, embedder=fake_embedder)
    return path


def test_trial_filter():
    assert rag.trial_filter("what is the ECOG of nct03504397?") == {"doc_id": "ct:NCT03504397"}
    both = rag.trial_filter("compare NCT03653507 and NCT03504397")
    assert both == {"doc_id": {"$in": ["ct:NCT03504397", "ct:NCT03653507"]}}
    assert rag.trial_filter("what is the CLDN18.2 threshold?") is None


def test_retrieve_is_restricted_to_the_trial_named_in_the_question(chroma):
    hits = rag.retrieve(f"CLDN18.2 threshold in {TRIAL}", k=5, embedder=fake_embedder, path=chroma)
    assert hits
    assert {h["metadata"]["doc_id"] for h in hits} == {f"ct:{TRIAL}"}


def test_build_messages_numbers_the_passages_with_their_source(chroma):
    hits = rag.retrieve(f"ECOG {TRIAL}", k=2, embedder=fake_embedder, path=chroma)
    system, user = rag.build_messages("ECOG?", hits)
    assert system["role"] == "system" and "ONLY" in system["content"]
    assert f"[1] ct:{TRIAL}" in user["content"] and "[2] " in user["content"]
    assert user["content"].endswith("Question: ECOG?")


def _llm_citing(passage: int, quote: str):
    def llm(_messages):
        payload = {"answer": "an answer", "citations": [{"passage": passage, "quote": quote}]}
        return json.dumps(payload)

    return llm


def test_a_literal_quote_is_verified(chroma):
    hits = rag.retrieve(f"ECOG {TRIAL}", k=3, embedder=fake_embedder, path=chroma)
    quote = hits[0]["text"][:30]
    result = rag.ask(
        f"ECOG {TRIAL}", k=3, llm=_llm_citing(1, quote), embedder=fake_embedder, path=chroma
    )
    assert result.grounded
    assert result.citations[0].doc_id == f"ct:{TRIAL}"


def test_a_made_up_quote_is_flagged_not_trusted(chroma):
    result = rag.ask(
        f"ECOG {TRIAL}",
        k=3,
        llm=_llm_citing(1, "this sentence is not in any passage"),
        embedder=fake_embedder,
        path=chroma,
    )
    assert not result.grounded
    assert "do not trust" in rag.format_answer(result)


def test_a_citation_to_a_missing_passage_is_unverified(chroma):
    result = rag.ask(
        f"ECOG {TRIAL}",
        k=2,
        llm=_llm_citing(9, "anything here"),
        embedder=fake_embedder,
        path=chroma,
    )
    assert result.citations[0].doc_id is None and not result.citations[0].verified


def test_an_answer_without_citations_is_warned(chroma):
    def llm(_messages):
        return json.dumps({"answer": "a guess", "citations": []})

    result = rag.ask(f"ECOG {TRIAL}", k=2, llm=llm, embedder=fake_embedder, path=chroma)
    assert not result.grounded
    assert "no citations" in rag.format_answer(result)


def test_not_found_is_accepted_without_citations(chroma):
    def llm(_messages):
        return json.dumps({"answer": rag.NOT_FOUND, "citations": []})

    result = rag.ask(f"ECOG {TRIAL}", k=2, llm=llm, embedder=fake_embedder, path=chroma)
    assert "Warning" not in rag.format_answer(result)


def test_invalid_json_from_the_model_does_not_crash(chroma):
    result = rag.ask(
        f"ECOG {TRIAL}", k=2, llm=lambda _m: "not json", embedder=fake_embedder, path=chroma
    )
    assert result.answer == "not json" and not result.grounded


def test_unknown_strategy_is_rejected():
    with pytest.raises(ValueError):
        rag.retrieve("x", strategy="nope")


def test_quote_check_ignores_spacing_but_not_wording():
    passage = "positive staining (rate \\>=40% and intensity \\>=2+) . If the subject"
    assert rag.quote_in_passage(passage, "staining (rate >=40% and intensity >=2+).")
    assert not rag.quote_in_passage(passage, "staining (rate >=50% and intensity >=2+).")
    assert not rag.quote_in_passage(passage, "STAINING (rate >=40% and intensity >=2+).")
    assert not rag.quote_in_passage(passage, "short")


def test_a_comparison_gets_evidence_from_every_named_trial(chroma):
    hits = rag.retrieve(
        "compare NCT03653507 and NCT03504397", k=3, embedder=fake_embedder, path=chroma
    )
    assert {h["metadata"]["doc_id"] for h in hits} == {"ct:NCT03504397", "ct:NCT03653507"}
    assert len(hits) == 6
    assert hits == sorted(hits, key=lambda h: h["distance"])


def test_rewrite_query_uses_the_model_and_falls_back_to_the_question():
    assert (
        rag.rewrite_query("q?", lambda _m: json.dumps({"query": " expanded query "}))
        == "expanded query"
    )
    assert rag.rewrite_query("q?", lambda _m: "not json") == "q?"
    assert rag.rewrite_query("q?", lambda _m: json.dumps({"query": "  "})) == "q?"

    def down(_messages):
        raise RuntimeError("no server")

    assert rag.rewrite_query("q?", down) == "q?"


def test_extra_queries_are_fused_into_one_ranking(chroma):
    plain = rag.retrieve(f"ECOG {TRIAL}", k=4, embedder=fake_embedder, path=chroma)
    fused = rag.retrieve(
        f"ECOG {TRIAL}",
        k=4,
        embedder=fake_embedder,
        path=chroma,
        extra_queries=["exclusion criteria hepatitis"],
    )
    assert len(fused) == len(plain) == 4
    assert {h["metadata"]["doc_id"] for h in fused} == {f"ct:{TRIAL}"}
    assert [h["id"] for h in fused] != [h["id"] for h in plain]


def test_ask_with_rewrite_records_the_search_query(chroma):
    result = rag.ask(
        f"ECOG {TRIAL}",
        k=3,
        llm=lambda _m: json.dumps({"answer": rag.NOT_FOUND, "citations": []}),
        embedder=fake_embedder,
        path=chroma,
        rewrite=True,
        rewriter=lambda _m: json.dumps({"query": "performance status"}),
    )
    assert result.search_query == "performance status"
    assert "performance status" in rag.format_answer(result, show_passages=True)


def test_retry_replaces_a_made_up_quote_with_a_literal_one(chroma):
    good = rag.retrieve(f"ECOG {TRIAL}", k=3, embedder=fake_embedder, path=chroma)[0]["text"][:30]
    replies = iter(
        [
            json.dumps(
                {"answer": "a", "citations": [{"passage": 1, "quote": "not in the passage at all"}]}
            ),
            json.dumps({"answer": "a", "citations": [{"passage": 1, "quote": good}]}),
        ]
    )
    seen = []

    def llm(messages):
        seen.append(messages)
        return next(replies)

    result = rag.ask(f"ECOG {TRIAL}", k=3, llm=llm, embedder=fake_embedder, path=chroma)
    assert result.grounded and result.retried
    assert len(seen) == 2 and "NOT exact copies" in seen[1][-1]["content"]
    assert "not in the passage at all" in seen[1][-1]["content"]


def test_retry_that_does_not_improve_keeps_the_first_answer(chroma):
    bad = json.dumps(
        {"answer": "first", "citations": [{"passage": 1, "quote": "invented text here"}]}
    )
    result = rag.ask(f"ECOG {TRIAL}", k=3, llm=lambda _m: bad, embedder=fake_embedder, path=chroma)
    assert not result.grounded and not result.retried and result.answer == "first"


def test_no_retry_when_disabled_or_when_all_quotes_are_literal(chroma):
    calls = []

    def llm(_messages):
        calls.append(1)
        return json.dumps(
            {"answer": "a", "citations": [{"passage": 1, "quote": "invented text here"}]}
        )

    rag.ask(f"ECOG {TRIAL}", k=3, llm=llm, embedder=fake_embedder, path=chroma, retry=False)
    assert len(calls) == 1
