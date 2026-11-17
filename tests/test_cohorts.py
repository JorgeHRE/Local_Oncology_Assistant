"""Tests for the cohort tool and the assistant's routing.

The routing and formatting tests run anywhere; the ones marked ``db`` read the real views of the
local OMOP database (``make db`` and ``make cohort``) and skip without it.
"""

from __future__ import annotations

from datetime import date

import psycopg
import pytest

from oncology_assistant import assistant, cohorts, rag
from oncology_assistant.ground_truth import GROUND_TRUTH_PATH, CohortRecord, parse_records


@pytest.mark.parametrize(
    "question",
    [
        'Which patients in the database meet the evaluable criteria of trial "NCT06123494"?',
        "How many patients are eligible for NCT02872116?",
        "List the patients of the cohort of NCT06123494",
        "What patients with HER2 positive meet NCT06123494?",
        "Which patients in the dataset do not meet the inclusion criteria of NCT02477826?",
    ],
)
def test_questions_about_the_patients_of_the_database_are_cohort_questions(question):
    assert cohorts.is_cohort_question(question)


@pytest.mark.parametrize(
    "question",
    [
        'Which CLDN18.2 result excludes the patient from being eligible for trial "NCT07103668"?',
        "Which Her2 result includes a patient in the clinical trial NCT06123494?",
        'Under what condition are patients with MSI-H excluded from the clinical trial "NCT05427383"?',
        "How do trials NCT05427383 and NCT06901531 differ in their eligibility criteria for patients?",
        "Extract the exclusion criteria for the clinical trial NCT07103668.",
        "What is the CLDN18.2 threshold?",
    ],
)
def test_questions_about_the_text_are_not_cohort_questions(question):
    assert not cohorts.is_cohort_question(question)


def test_trial_of_maps_view_prefixes_to_nct_ids():
    assert cohorts.trial_of("gc_nct06123494") == "NCT06123494"
    assert cohorts.trial_of("gc_zolbetuximab") == "NCT03504397"  # the SPOTLIGHT pilot cohort
    assert cohorts.trial_of("gc_other") is None


def test_format_cohort_shows_size_filters_and_sample():
    result = cohorts.CohortResult(
        "NCT00000000",
        2,
        [cohorts.AttritionStep(0, "Persons", 10, 0), cohorts.AttritionStep(1, "Stage 4", 2, 8)],
        [(4, date(2024, 7, 31)), (7, date(2022, 6, 29))],
    )
    text = cohorts.format_cohort(result)
    assert "NCT00000000" in text and "2 patients" in text
    assert "1. Stage 4: 2  (-8)" in text and "0. Persons: 10" in text
    assert "4 (2024-07-31)" in text and "synthetic" in text


def test_a_text_question_goes_to_the_rag(monkeypatch):
    monkeypatch.setattr(rag, "ask", lambda question, **kw: rag.Answer(question, "from the texts"))
    response = assistant.ask("Which CLDN18.2 result excludes the patient from NCT07103668?")
    assert response.route == "rag" and "from the texts" in response.text


def test_a_cohort_question_without_a_database_says_so(monkeypatch):
    def down():
        raise psycopg.OperationalError("refused")

    monkeypatch.setattr(cohorts, "connect", down)
    response = assistant.ask("How many patients are eligible for NCT02872116?")
    assert response.route == "cohort-unavailable" and "make db" in response.text


def test_a_cohort_question_does_not_call_the_llm(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("the LLM must not be used for cohort counts")

    monkeypatch.setattr(rag, "ask", forbidden)
    monkeypatch.setattr(
        cohorts, "connect", lambda: (_ for _ in ()).throw(psycopg.OperationalError("x"))
    )
    assert assistant.ask("How many patients are eligible for NCT02872116?").route != "rag"


@pytest.mark.db
def test_available_cohorts_are_the_eight_of_the_ground_truth(omop_conn):
    found = cohorts.available_cohorts(omop_conn)
    records, _ = parse_records(GROUND_TRUTH_PATH.read_text(encoding="utf-8").splitlines())
    expected = {r.source.removeprefix("ct:") for r in records if isinstance(r, CohortRecord)}
    assert expected <= set(found)


@pytest.mark.db
def test_every_cohort_count_matches_the_expected_count_of_the_ground_truth(omop_conn):
    records, _ = parse_records(GROUND_TRUTH_PATH.read_text(encoding="utf-8").splitlines())
    for r in (r for r in records if isinstance(r, CohortRecord)):
        result = cohorts.get_cohort(r.source.removeprefix("ct:"), omop_conn, sample=3)
        assert result.count == r.expected_count, r.id
        assert result.attrition[-1].n_remaining == result.count
        assert len(result.sample) == min(3, result.count)


@pytest.mark.db
def test_unknown_trial_raises_key_error(omop_conn):
    with pytest.raises(KeyError):
        cohorts.get_cohort("NCT00000000", omop_conn)


@pytest.mark.db
def test_the_assistant_answers_a_cohort_question_from_the_database():
    response = assistant.ask('Which patients meet the evaluable criteria of trial "NCT06123494"?')
    assert response.route == "cohort" and response.cohort.count == 119
    missing = assistant.ask("Which patients meet the criteria of NCT00000000?")
    assert missing.route == "cohort-missing" and "NCT06123494" in missing.text
