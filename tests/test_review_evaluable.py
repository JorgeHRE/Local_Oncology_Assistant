"""Tests for the evaluable review helper (it only lists; it never edits the ground truth)."""

from __future__ import annotations

import pytest

from oncology_assistant import review_evaluable as rv


@pytest.mark.parametrize(
    ("concept", "evaluable", "expected"),
    [
        ("measurable lesion", True, "true-but-guide-says-no"),
        ("pregnancy or lactation", True, "true-but-guide-says-no"),
        ("central nervous system metastases", True, "true-but-guide-says-no"),
        ("left ventricular ejection fraction", True, "true-but-guide-says-no"),
        ("disease progression", True, "true-not-in-features"),
        ("HER2", True, None),
        ("ECOG", True, None),
        ("prior anti-cancer therapy", True, None),
        ("age", True, None),
        ("informed consent", False, None),
        ("expected survival", False, None),
        ("age", False, "false-but-guide-says-yes"),
    ],
)
def test_classify(concept, evaluable, expected):
    assert rv.classify(concept, evaluable) == expected


def test_review_lists_without_touching_the_ground_truth(tmp_path):
    from oncology_assistant.ground_truth import GROUND_TRUTH_PATH

    before = GROUND_TRUTH_PATH.read_bytes()
    flags = rv.review()
    assert all(f.category for f in flags)
    out = tmp_path / "r.md"
    rv.write_report(out, flags)
    assert "true-but-guide-says-no" in out.read_text(encoding="utf-8")
    assert GROUND_TRUTH_PATH.read_bytes() == before
