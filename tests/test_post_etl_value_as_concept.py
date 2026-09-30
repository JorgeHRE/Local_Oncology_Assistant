"""Tests for etl/post_etl/01_value_as_concept.sql against the local OMOP database.

Require the Postgres container (``docker compose up -d db``) loaded by the ETL; they are skipped
when the database is not reachable. The expected concept_ids are written by hand from the
vocabulary (Athena v5.0 29-AUG-26) so the tests do not reuse the script's own resolution logic.
"""

from __future__ import annotations

import re

import psycopg
import pytest

from oncology_assistant.db import REPO_ROOT

SCRIPT = REPO_ROOT / "etl" / "post_etl" / "01_value_as_concept.sql"

EXPECTED_VALUE_CONCEPTS: dict[str, int] = {
    "Positive (qualifier value)": 9191,
    "Negative (qualifier value)": 9189,
    "Detected (qualifier value)": 4126681,
    "Not detected (qualifier value)": 9190,
    "Stage 1 (qualifier value)": 4121054,
    "Stage 2 (qualifier value)": 4106768,
    "Stage 3 (qualifier value)": 4121176,
    "Stage 4 (qualifier value)": 4123017,
}

# Oncology measurements whose coded values the cohort depends on.
HER2_IHC = 3019066  # LOINC 18474-7
AJCC_STAGE_GROUP = 3031548  # LOINC 42100-8
ONCOLOGY_MEASUREMENTS = (HER2_IHC, AJCC_STAGE_GROUP)

# Known gap: sub-stages have no standard SNOMED concept (pending Cancer Modifier, ADR-0001).
KNOWN_UNMAPPED = re.compile(r"^Stage [1-4][A-C] \(qualifier value\)$")

pytestmark = pytest.mark.db


def _run_script(conn: psycopg.Connection) -> None:
    """Execute the post-ETL script exactly as psql would (it manages its own transaction)."""
    conn.execute(SCRIPT.read_text(encoding="utf-8"))


def _value_concept_fingerprint(conn: psycopg.Connection) -> tuple[int, int]:
    """Return (rows with a value concept, sum of their ids) to detect any change."""
    row = conn.execute(
        "SELECT count(*), COALESCE(sum(value_as_concept_id::bigint), 0) "
        "FROM cdm.measurement WHERE COALESCE(value_as_concept_id, 0) <> 0"
    ).fetchone()
    assert row is not None
    return int(row[0]), int(row[1])


@pytest.fixture(scope="module")
def conn(omop_conn: psycopg.Connection) -> psycopg.Connection:
    """OMOP connection with the post-ETL script already applied."""
    _run_script(omop_conn)
    return omop_conn


def test_mapped_texts_get_expected_standard_concept(conn: psycopg.Connection) -> None:
    rows = conn.execute(
        "SELECT value_source_value, value_as_concept_id, count(*) FROM cdm.measurement "
        "WHERE value_source_value = ANY(%s) GROUP BY 1, 2",
        (list(EXPECTED_VALUE_CONCEPTS),),
    ).fetchall()
    assert rows, "no measurement carries any mapped value text"
    wrong = [(text, got, n) for text, got, n in rows if got != EXPECTED_VALUE_CONCEPTS[text]]
    assert wrong == []


def test_value_concepts_are_standard_meas_values(conn: psycopg.Connection) -> None:
    rows = conn.execute(
        "SELECT DISTINCT m.value_as_concept_id, c.domain_id, c.standard_concept "
        "FROM cdm.measurement m LEFT JOIN cdm.concept c ON c.concept_id = m.value_as_concept_id "
        "WHERE COALESCE(m.value_as_concept_id, 0) <> 0 "
        "AND (c.concept_id IS NULL OR c.standard_concept IS DISTINCT FROM 'S' "
        "OR c.domain_id <> 'Meas Value')"
    ).fetchall()
    assert rows == []


def test_oncology_values_mapped_except_known_gap(conn: psycopg.Connection) -> None:
    rows = conn.execute(
        "SELECT DISTINCT value_source_value FROM cdm.measurement "
        "WHERE measurement_concept_id = ANY(%s) AND value_source_value IS NOT NULL "
        "AND value_as_number IS NULL AND COALESCE(value_as_concept_id, 0) = 0",
        (list(ONCOLOGY_MEASUREMENTS),),
    ).fetchall()
    unexpected = sorted(text for (text,) in rows if not KNOWN_UNMAPPED.match(text))
    assert unexpected == []


def test_script_is_idempotent(conn: psycopg.Connection) -> None:
    before = _value_concept_fingerprint(conn)
    _run_script(conn)
    assert _value_concept_fingerprint(conn) == before
