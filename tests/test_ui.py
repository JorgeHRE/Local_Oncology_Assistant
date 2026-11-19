"""Tests for the pure presentation helpers of ``oncology_assistant.ui``.

These tests run without Streamlit, Ollama or Postgres so they execute in CI (``pytest -m "not db"``).
"""

from __future__ import annotations

import urllib.error
from datetime import date

from oncology_assistant import assistant, cohorts, rag, ui


def test_route_badge_for_cohort_routes() -> None:
    cohort_resp = assistant.Response(route="cohort", text="ok")
    assert ui.route_badge(cohort_resp) == ui.RouteBadge("Cohorte OMOP (SQL)", "green")

    missing_resp = assistant.Response(route="cohort-missing", text="missing")
    assert ui.route_badge(missing_resp) == ui.RouteBadge("Cohorte no definida", "orange")

    down_resp = assistant.Response(route="cohort-unavailable", text="down")
    assert ui.route_badge(down_resp) == ui.RouteBadge("Base OMOP no disponible", "red")


def test_route_badge_for_rag_grounding_states() -> None:
    grounded = rag.Answer(
        question="q",
        answer="CPS >= 5.",
        citations=[
            rag.Citation(passage=1, doc_id="ct:NCT06346197", quote="CPS >= 5", verified=True)
        ],
    )
    assert ui.route_badge(assistant.Response("rag", "ok", answer=grounded)) == ui.RouteBadge(
        "RAG (citas verificadas)", "blue"
    )

    ungrounded = rag.Answer(
        question="q",
        answer="CPS >= 5.",
        citations=[rag.Citation(passage=1, doc_id="ct:NCT06346197", quote="wrong", verified=False)],
    )
    assert ui.route_badge(assistant.Response("rag", "ok", answer=ungrounded)) == ui.RouteBadge(
        "RAG (citas no verificadas)", "orange"
    )

    not_found = rag.Answer(question="q", answer=rag.NOT_FOUND)
    assert ui.route_badge(assistant.Response("rag", "ok", answer=not_found)) == ui.RouteBadge(
        "RAG (sin evidencia en el corpus)", "orange"
    )


def test_attrition_and_sample_dataframes() -> None:
    result = cohorts.CohortResult(
        trial="NCT06177041",
        count=71,
        attrition=[
            cohorts.AttritionStep(1, "Gastric cancer", 200, 0),
            cohorts.AttritionStep(2, "HER2 negative", 71, 129),
        ],
        sample=[(101, date(2024, 5, 1)), (202, date(2024, 6, 15))],
    )

    attr_df = ui.attrition_dataframe(result)
    assert list(attr_df.columns) == [
        "Paso",
        "Filtro aplicado",
        "Pacientes restantes",
        "Descartados",
    ]
    assert len(attr_df) == 2
    assert attr_df.iloc[1]["Pacientes restantes"] == 71
    assert attr_df.iloc[1]["Descartados"] == 129

    sample_df = ui.sample_dataframe(result)
    assert list(sample_df.columns) == ["person_id", "Fecha índice"]
    assert sample_df.iloc[0].to_dict() == {"person_id": 101, "Fecha índice": "2024-05-01"}


def test_citation_rows_and_passage_summary() -> None:
    answer = rag.Answer(
        question="q",
        answer="HER2 negative.",
        citations=[
            rag.Citation(1, "ct:NCT06123494", "HER2 negative", True),
            rag.Citation(2, None, "hallucinated", False),
        ],
    )
    rows = ui.citation_rows(answer)
    assert rows[0]["verified"] is True
    assert rows[0]["doc_id"] == "ct:NCT06123494"
    assert rows[1]["verified"] is False
    assert rows[1]["doc_id"] == "desconocido"

    summary = ui.passage_summary(
        1,
        {
            "id": "ct:NCT06123494#0",
            "distance": 0.1234,
            "metadata": {"doc_id": "ct:NCT06123494", "section": "inclusion"},
            "text": "HER2 negative gastric cancer.",
        },
    )
    assert summary == {
        "number": 1,
        "doc_id": "ct:NCT06123494",
        "section": "inclusion",
        "distance": 0.1234,
        "text": "HER2 negative gastric cancer.",
    }


def test_format_runtime_error_messages() -> None:
    url_err = urllib.error.URLError("connection refused")
    assert "make llm-up" in ui.format_runtime_error(url_err)

    missing_err = FileNotFoundError("index missing")
    assert "make index-embed" in ui.format_runtime_error(missing_err)

    other_err = RuntimeError("boom")
    assert "boom" in ui.format_runtime_error(other_err)


def test_example_prompts_cover_both_routes() -> None:
    kinds = {item.kind for item in ui.EXAMPLE_PROMPTS}
    assert kinds == {"RAG", "Cohorte OMOP"}
    for item in ui.EXAMPLE_PROMPTS:
        assert item.question.strip()
        if item.kind == "Cohorte OMOP":
            assert cohorts.is_cohort_question(item.question)
            assert assistant.trials_named(item.question)
        else:
            assert not cohorts.is_cohort_question(item.question)


def test_trial_catalog_loads_manifest_and_marks_omop_cohorts() -> None:
    cohort_ids = ui.cohort_trial_ids()
    assert len(cohort_ids) == 8
    assert "NCT03504397" in cohort_ids
    assert "NCT06177041" in cohort_ids

    catalog = ui.trial_catalog_dataframe()
    assert len(catalog) == 49
    assert list(catalog.columns) == ["NCT", "Título", "Cohorte OMOP", "Nota", "Rol"]
    assert int((catalog["Cohorte OMOP"] == "Sí").sum()) == 8
    # Trials with OMOP cohorts are sorted first so they are immediately visible.
    assert catalog.iloc[0]["Cohorte OMOP"] == "Sí"


def test_filter_trial_catalog_by_query_and_cohort() -> None:
    catalog = ui.trial_catalog_dataframe()

    only_cohorts = ui.filter_trial_catalog(catalog, only_with_cohort=True)
    assert len(only_cohorts) == 8
    assert set(only_cohorts["Cohorte OMOP"]) == {"Sí"}

    toga = ui.filter_trial_catalog(catalog, query="ToGA")
    assert "NCT01041404" in set(toga["NCT"])

    by_id = ui.filter_trial_catalog(catalog, query="nct06177041", only_with_cohort=True)
    assert list(by_id["NCT"]) == ["NCT06177041"]
