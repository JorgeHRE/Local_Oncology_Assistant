"""Tests for the ground-truth schema and validator (ADR-0003).

Records here are synthetic test fixtures, not ground truth: the real file is written by hand
(``docs/guia-anotacion.md``).
"""

from __future__ import annotations

import json
import re

import pytest
from pydantic import ValidationError

from oncology_assistant import ground_truth as gt
from oncology_assistant.chunking import build_chunks, load_documents

SPOTLIGHT = "ct:NCT03504397"
GLOW = "ct:NCT03653507"
# As rendered on the ClinicalTrials.gov website: no Markdown, no bullet.
CLDN_QUOTE = "Subject's tumor expresses CLDN18.2 in ≥ 75% of tumor cells demonstrating moderate"
ECOG_QUOTE = "Subject has ECOG performance status 0 to 1."


def criterion(quote: str = ECOG_QUOTE, doc_id: str = SPOTLIGHT, **overrides) -> dict:
    data = {
        "kind": "inclusion",
        "concept": "ECOG",
        "operator": "<=",
        "value": "1",
        "evaluable": True,
        "citation": {"doc_id": doc_id, "quote": quote},
    }
    return {**data, **overrides}


def record(type_: str = "R", id_: str | None = None, **overrides) -> dict:
    base = {
        "split": "dev",
        "question": "A test question long enough?",
        "annotator": "tester",
        "annotated_on": "2026-11-05",
    }
    if type_ == "R":
        base |= {
            "type": "R",
            "id": id_ or "R-001",
            "topic": "cldn18",
            "reference_answer": "A reference answer for the test.",
            "relevant": [{"doc_id": SPOTLIGHT, "quote": CLDN_QUOTE}],
        }
    elif type_ == "E":
        base |= {"type": "E", "id": id_ or "E-001", "source": SPOTLIGHT, "criteria": [criterion()]}
    else:
        base |= {
            "type": "C",
            "id": id_ or "C-001",
            "source": SPOTLIGHT,
            "criteria": [criterion()],
            "reference_sql": "sql/02_cohorte.sql",
        }
    return base | overrides


def parse(*records: dict):
    parsed, problems = gt.parse_records(json.dumps(r) for r in records)
    assert not problems, problems
    return parsed


@pytest.fixture(scope="module")
def docs():
    return {d.doc_id: d for d in load_documents() if d.source == "clinicaltrials.gov"}


def test_each_type_parses_into_its_model():
    parsed = parse(record("R"), record("E"), record("C"))
    assert [type(r) for r in parsed] == [gt.RetrievalRecord, gt.ExtractionRecord, gt.CohortRecord]


@pytest.mark.parametrize(
    "bad",
    [
        record("R", id_="E-001"),  # id prefix must match the type
        record("R", topic="zolbetuximab"),  # topic outside the list
        record("R", relevant=[]),  # R needs at least one passage
        record("R", unexpected="field"),  # extra fields are rejected
        record("E", criteria=[criterion(doc_id=GLOW)]),  # E cites only its source
        record("E", criteria=[criterion(evaluable=False)]),  # not evaluable needs a reason
        record("E", criteria=[criterion(not_evaluable_reason="x")]),  # ...and only then
        record("C", criteria=[criterion(evaluable=False, not_evaluable_reason="TNM")]),
        record("C", reference_sql="cohort.sql"),  # reference SQL lives in sql/
    ],
)
def test_invalid_records_are_rejected(bad):
    _, problems = gt.parse_records([json.dumps(bad)])
    assert problems


def test_invalid_json_line_is_reported_with_its_number():
    _, problems = gt.parse_records(["", "{not json"])
    assert problems and problems[0].startswith("line 2:")


def test_quotes_from_the_website_match_the_markdown_record(docs):
    text = gt.document_text(docs[SPOTLIGHT])
    assert gt.contains_quote(text, CLDN_QUOTE)
    assert gt.contains_quote(text, "  Subject has ECOG\n performance status 0 to 1.")
    assert not gt.contains_quote(text, "Subject has ECOG performance status 0 to 2.")
    assert gt.contains_quote("1\\. Age 18\\~75 years", "Age 18~75 years")


def test_check_citations_flags_quotes_not_in_the_document(docs):
    good = parse(record("R"))
    bad = parse(record("R", relevant=[{"doc_id": GLOW, "quote": "This sentence is not in GLOW."}]))
    assert gt.check_citations(good, docs) == []
    assert gt.check_citations(bad, docs)[0].startswith("R-001: quote not found")


def test_unknown_and_missing_documents_are_told_apart(docs):
    parsed = parse(
        record("R", relevant=[{"doc_id": "pm:34102137", "quote": "a quote long enough"}]),
        record("R", id_="R-002", relevant=[{"doc_id": "pm:1", "quote": "a quote long enough"}]),
    )
    unknown, missing = gt.unverifiable_citations(parsed, docs, set(docs) | {"pm:34102137"})
    assert unknown == ["R-002: pm:1"]
    assert missing == ["R-001: pm:34102137"]


def test_duplicated_ids_are_reported():
    assert gt.check_ids(parse(record("R"), record("R"))) == ["duplicated id R-001 (2 times)"]


def test_a_source_document_cannot_be_in_both_splits():
    parsed = parse(record("E"), record("C", split="test"))
    assert gt.check_splits(parsed) == [
        f"{SPOTLIGHT} is the source of questions in both dev and test"
    ]


def test_near_identical_documents_must_share_a_split():
    parsed = parse(
        record("E"),
        record("E", id_="E-002", source=GLOW, split="test", criteria=[criterion(doc_id=GLOW)]),
    )
    assert gt.check_splits(parsed) == []
    groups = {SPOTLIGHT: "zolbetuximab", GLOW: "zolbetuximab"}
    assert gt.check_splits(parsed, groups=groups) == [
        "zolbetuximab is the source of questions in both dev and test"
    ]


def test_committed_split_groups_keep_spotlight_and_glow_together():
    groups = gt.load_split_groups()
    assert groups[SPOTLIGHT] == groups[GLOW]


def test_final_check_requires_the_quotas():
    problems = gt.check_splits(parse(record("R")), final=True)
    assert "R/dev: 1 questions, expected 6" in problems
    assert len(problems) == 6


def test_a_literal_quote_marks_relevant_chunks_in_both_strategies(docs):
    """The ground truth names no chunk ids, so it does not favour a chunking strategy."""
    spotlight = [docs[SPOTLIGHT]]
    for strategy, expected in (("structural", 1), ("whole", 1)):
        chunks = [(c.chunk_id, c.doc_id, c.text) for c in build_chunks(spotlight, strategy)]
        hits = gt.relevant_chunk_ids(CLDN_QUOTE, chunks)
        assert len(hits) == expected, strategy
        assert all(h.startswith(SPOTLIGHT) for h in hits)


def test_validate_a_file_end_to_end(tmp_path):
    path = tmp_path / "gt.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in (record("R"), record("E"))) + "\n")
    assert gt.validate(path) == []
    path.write_text(
        json.dumps(record("R", relevant=[{"doc_id": "ct:NCT00000000", "quote": "x" * 12}]))
    )
    assert gt.validate(path) == ["unknown document: R-001: ct:NCT00000000"]


def test_the_committed_ground_truth_file_is_valid():
    assert gt.GROUND_TRUTH_PATH.exists()
    assert gt.validate(gt.GROUND_TRUTH_PATH) == []


def test_bad_records_raise_with_the_model_directly():
    with pytest.raises(ValidationError):
        gt.Criterion.model_validate(criterion(kind="maybe"))


def test_the_examples_in_the_annotation_guide_follow_the_schema(tmp_path):
    """The R and E examples of docs/guia-anotacion.md parse, and are rejected only for the
    made-up document (so nobody can paste them into the real file by mistake)."""
    guide = (gt.REPO_ROOT / "docs" / "guia-anotacion.md").read_text(encoding="utf-8")
    blocks = re.findall(r"```json\n(.*?)\n```", guide, flags=re.DOTALL)
    examples = [json.loads(b) for b in blocks if '"id": "R-001"' in b or '"id": "E-001"' in b]
    assert [e["type"] for e in examples] == ["R", "E"]
    parsed = parse(*examples)
    path = tmp_path / "examples.jsonl"
    path.write_text("\n".join(json.dumps(e) for e in examples))
    problems = gt.validate(path)
    assert problems and all("unknown document" in p and "NCT00000000" in p for p in problems)
    assert len(parsed[1].criteria) == 3
