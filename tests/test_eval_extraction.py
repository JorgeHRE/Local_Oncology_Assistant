"""Tests for the extraction scoring with synthetic records (no model, no index)."""

from __future__ import annotations

import json

from oncology_assistant import eval_extraction as ee
from oncology_assistant.ground_truth import ExtractionRecord

SECTION = "ECOG performance status 0 or 1\nHER2 negative by IHC\nAge 18 years or older"


def record() -> ExtractionRecord:
    def crit(concept, operator, value, evaluable, quote):
        return {
            "kind": "inclusion",
            "concept": concept,
            "operator": operator,
            "value": value,
            "evaluable": evaluable,
            "not_evaluable_reason": None if evaluable else "needs a lab value",
            "citation": {"doc_id": "ct:NCT00000000", "quote": quote},
        }

    return ExtractionRecord.model_validate(
        {
            "id": "E-001",
            "type": "E",
            "split": "dev",
            "source": "ct:NCT00000000",
            "question": "Extract the inclusion criteria of NCT00000000.",
            "annotator": "X",
            "annotated_on": "2026-11-17",
            "criteria": [
                crit("ECOG", "<=", "1", True, "ECOG performance status 0 or 1"),
                crit("HER2", "=", "negative", True, "HER2 negative by IHC"),
                crit("age", ">=", "18", False, "Age 18 years or older"),
            ],
        }
    )


def got(quote, operator="", value="", evaluable=True):
    return {
        "concept": "c",
        "operator": operator,
        "value": value,
        "unit": "",
        "time_window": "",
        "evaluable": evaluable,
        "quote": quote,
    }


def test_overlap_ignores_case_spacing_and_punctuation_and_needs_enough_text():
    assert ee.overlaps("ECOG performance status 0 or 1", "ecog  performance status 0 or 1.")
    assert ee.overlaps("HER2 negative by IHC", "HER2 negative by IHC (or ISH) in tumor tissue")
    assert not ee.overlaps("ECOG", "ECOG performance status")  # too short to trust
    assert not ee.overlaps("ECOG performance status 0 or 1", "HER2 negative by IHC")


def test_same_value_is_lenient_but_not_blind():
    assert ee.same_value("75", "75%") and ee.same_value("negative", "HER2-negative")
    assert ee.same_value(None, "") and not ee.same_value("1", "2") and not ee.same_value("1", None)


def test_a_perfect_extraction_scores_one_everywhere():
    rec = record()
    extracted = [
        got("ECOG performance status 0 or 1", "<=", "1", True),
        got("HER2 negative by IHC", "=", "negative", True),
        got("Age 18 years or older", ">=", "18", False),
    ]
    result = ee.score(rec, extracted, SECTION)
    assert result.quote_recall == 1.0 and result.grounded == 1.0 and result.count_ratio == 1.0
    assert result.matched == 3 and result.agree == {"operator": 3, "value": 3, "evaluable": 3}


def test_a_skipped_criterion_lowers_recall_and_a_made_up_quote_lowers_grounding():
    rec = record()
    extracted = [
        got("ECOG performance status 0 or 1", "<=", "1"),
        got("this sentence is not in the section"),
    ]
    result = ee.score(rec, extracted, SECTION)
    assert round(result.quote_recall, 2) == 0.33 and result.grounded == 0.5
    assert result.count_ratio == round(2 / 3, 10) or abs(result.count_ratio - 2 / 3) < 1e-9


def test_over_splitting_raises_the_count_ratio_and_wrong_fields_are_counted():
    rec = record()
    extracted = [
        got("ECOG performance status 0 or 1", ">=", "0"),
        got("ECOG performance status 0 or 1", "<=", "1"),
        got("HER2 negative by IHC", "=", "positive", False),
    ]
    result = ee.score(rec, extracted, SECTION)
    assert result.count_ratio == 1.0
    assert result.agree["operator"] == 2  # best candidate is chosen for ECOG; HER2 operator agrees
    assert result.agree["value"] == 1 and result.agree["evaluable"] == 1


def test_run_model_survives_invalid_json_and_summarizes():
    rec = record()
    sections = {rec.id: SECTION}
    bad = ee.run_model("fake", [rec], sections, llm=lambda _m: "not json")
    assert bad[0].json_ok is False and bad[0].extracted == []
    good_reply = json.dumps({"criteria": [got("HER2 negative by IHC", "=", "negative")]})
    good = ee.run_model("fake", [rec], sections, llm=lambda _m: good_reply)
    summary = ee.summarize("fake", good, [rec])
    assert summary["json_ok"] == 1 and summary["matched_criteria"] == "1/3"


def test_the_review_file_lists_reference_and_every_model(tmp_path):
    rec = record()
    results = ee.run_model(
        "fake", [rec], {rec.id: SECTION}, llm=lambda _m: json.dumps({"criteria": []})
    )
    out = tmp_path / "r.md"
    ee.write_review(out, {"model-a": results}, [rec])
    text = out.read_text(encoding="utf-8")
    assert "E-001" in text and "Referencia" in text and "model-a" in text
