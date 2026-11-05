"""Tests for the chunking strategies (ADR-0006).

They use only the committed ClinicalTrials.gov snapshots and small synthetic PubMed records, so
they run in CI (PubMed abstracts are local-only and absent from a clean clone).
"""

from __future__ import annotations

import json
import re
from collections import Counter

import pytest

from oncology_assistant import chunking
from oncology_assistant.chunking import (
    Document,
    build_chunks,
    chunk_document,
    split_abstract,
    split_criteria,
)
from oncology_assistant.db import REPO_ROOT

CT_DIR = REPO_ROOT / "corpus" / "clinicaltrials"
SPOTLIGHT = "NCT03504397"


def ct_document(nct: str) -> Document:
    record = json.loads((CT_DIR / f"{nct}.json").read_text(encoding="utf-8"))
    return Document(
        doc_id=f"ct:{nct}",
        source="clinicaltrials.gov",
        identifier=nct,
        title=f"Trial {nct}",
        role="candidate",
        record=record,
    )


def pubmed_document(abstract: str, pmid: str = "1") -> Document:
    return Document(
        doc_id=f"pm:{pmid}",
        source="pubmed",
        identifier=pmid,
        title="A title",
        role="reference",
        record={"abstract": abstract, "year": "2024"},
    )


def words(text: str) -> Counter[str]:
    return Counter(re.findall(r"[A-Za-z]{2,}", text.lower()))


def test_split_criteria_sections_and_nested_bullets():
    text = (
        "Inclusion Criteria:\n\n"
        "* Age >= 18\n"
        "* Female subject if either:\n"
        "  * Not of child-bearing potential OR\n"
        "  * Agrees to use contraception\n\n"
        "Exclusion Criteria:\n\n"
        "* Prior therapy\n"
    )
    assert split_criteria(text) == [
        ("inclusion", "Age >= 18"),
        (
            "inclusion",
            (
                "Female subject if either:\n"
                "* Not of child-bearing potential OR\n"
                "* Agrees to use contraception"
            ),
        ),
        ("exclusion", "Prior therapy"),
    ]


def test_split_criteria_numbered_unescapes_markdown_and_ignores_header_variants():
    text = "Key Inclusion Criteria\n1\\. Age 18\\~75\n2\\. ECOG 0-1\nExclusion criteria include:\n- Pregnancy"
    assert split_criteria(text) == [
        ("inclusion", "Age 18~75"),
        ("inclusion", "ECOG 0-1"),
        ("exclusion", "Pregnancy"),
    ]


def test_split_criteria_prose_without_bullets_is_one_criterion():
    assert split_criteria("Inclusion Criteria:\nAny adult with gastric cancer.") == [
        ("inclusion", "Any adult with gastric cancer.")
    ]


def test_oversized_criterion_is_split_at_sub_bullets_keeping_the_lead_in():
    items = "\n".join(f"  {i}. {'criterion text ' * 20}" for i in range(1, 8))
    pieces = split_criteria(f"Inclusion Criteria:\n* Must meet all of:\n{items}\n")
    assert len(pieces) == 7
    assert all(text.startswith("Must meet all of:\n") for _, text in pieces)


def test_oversized_criterion_with_inline_numbering_is_split():
    inline = " ".join(f"{i}) {'long clause ' * 40}" for i in range(1, 5))
    pieces = split_criteria(f"Inclusion Criteria:\n* {inline}\n")
    assert [text[:2] for _, text in pieces] == ["1)", "2)", "3)", "4)"]


def test_split_abstract_labels_and_continuation_lines():
    text = "BACKGROUND: Context.\nMETHODS: We did X.\nand then Y.\nRESULTS: It worked."
    assert split_abstract(text) == [
        ("background", "Context."),
        ("methods", "We did X.\nand then Y."),
        ("results", "It worked."),
    ]
    assert split_abstract("An unlabelled abstract.") == [("abstract", "An unlabelled abstract.")]


def test_structural_pubmed_chunks_carry_title_and_section():
    chunks = chunk_document(pubmed_document("BACKGROUND: a.\nMETHODS: b."), "structural")
    assert [c.metadata["section"] for c in chunks] == ["background", "methods"]
    assert all("A title" in c.embedding_text and c.text in c.embedding_text for c in chunks)


def test_spotlight_is_split_into_atomic_inclusion_and_exclusion_criteria():
    chunks = chunk_document(ct_document(SPOTLIGHT), "structural")
    sections = Counter(c.metadata["section"] for c in chunks)
    assert sections["inclusion"] >= 10 and sections["exclusion"] >= 10
    assert any(
        "CLDN18.2" in c.text and "75%" in c.text and c.metadata["section"] == "inclusion"
        for c in chunks
    )
    # An exclusion rule is never stored with the inclusion section.
    assert not any(
        c.text.lower().startswith("subject has received prior systemic chemotherapy")
        and c.metadata["section"] == "inclusion"
        for c in chunks
    )
    assert all(c.metadata["identifier"] == SPOTLIGHT for c in chunks)


def test_whole_strategy_is_one_chunk_per_document():
    docs = [ct_document(SPOTLIGHT), pubmed_document("BACKGROUND: a.\nMETHODS: b.")]
    chunks = build_chunks(docs, "whole")
    assert [c.doc_id for c in chunks] == [d.doc_id for d in docs]
    assert chunks[1].text == "BACKGROUND: a.\nMETHODS: b."


def test_unknown_strategy_is_rejected():
    with pytest.raises(ValueError, match="unknown strategy"):
        chunk_document(ct_document(SPOTLIGHT), "semantic")


@pytest.fixture(scope="module")
def ct_documents() -> list[Document]:
    return [ct_document(path.stem) for path in sorted(CT_DIR.glob("NCT*.json"))]


def test_structural_chunking_loses_no_text_in_any_committed_snapshot(ct_documents):
    """The words of all chunks equal the words of the criteria minus the section headers."""
    assert len(ct_documents) == 49
    for doc in ct_documents:
        criteria = chunking._criteria_text(doc)
        body = "\n".join(
            line
            for line in chunking._ESCAPED.sub(r"\1", criteria).splitlines()
            if line.strip()
            and (chunking._BULLET.match(line.strip()) or not chunking._HEADER.match(line.strip()))
        )
        chunked = " ".join(c.text for c in chunk_document(doc, "structural"))
        missing = words(body) - words(chunked)
        # The lead-in repeated in split criteria can only add words, never remove them.
        assert not missing, f"{doc.doc_id} lost {dict(missing)}"


def test_chunk_ids_are_unique_and_sizes_are_bounded(ct_documents):
    chunks = build_chunks(ct_documents, "structural")
    assert len({c.chunk_id for c in chunks}) == len(chunks)
    assert all(c.text.strip() for c in chunks)
    assert max(len(c.text) for c in chunks) <= 2 * chunking.MAX_CRITERION_CHARS
    assert {c.metadata["section"] for c in chunks} <= {"inclusion", "exclusion", "other"}
    assert all(isinstance(v, str | int | float | bool) for c in chunks for v in c.metadata.values())


def test_load_documents_reads_the_committed_snapshots():
    docs = chunking.load_documents()
    cts = [d for d in docs if d.source == "clinicaltrials.gov"]
    assert len(cts) == 49
    assert {d.role for d in cts} == {"pivotal", "candidate", "distractor"}
