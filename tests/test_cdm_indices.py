"""The local OMOP database must have the official CDM v5.4 indices (etl/create_indices.R).

Without them every vocabulary lookup scans concept_relationship (~34M rows) or concept_ancestor
(~29M rows); the cohort queries and oncology_assistant.synthea_codes depend on these.
"""

from __future__ import annotations

import psycopg
import pytest

# (table, index) pairs used by concept lookups, "Maps to" resolution, descendant expansion of
# concept sets and per-patient measurement queries.
REQUIRED_INDICES: list[tuple[str, str]] = [
    ("concept", "idx_concept_code"),
    ("concept", "idx_concept_vocabulary_id"),
    ("concept_relationship", "idx_concept_relationship_id_1"),
    ("concept_relationship", "idx_concept_relationship_id_2"),
    ("concept_ancestor", "idx_concept_ancestor_id_1"),
    ("concept_ancestor", "idx_concept_ancestor_id_2"),
    ("measurement", "idx_measurement_person_id_1"),
    ("measurement", "idx_measurement_concept_id_1"),
    ("drug_exposure", "idx_drug_concept_id_1"),
    ("condition_occurrence", "idx_condition_concept_id_1"),
]


@pytest.mark.db
@pytest.mark.parametrize(("table", "index"), REQUIRED_INDICES, ids=[i for _, i in REQUIRED_INDICES])
def test_required_index_exists(omop_conn: psycopg.Connection, table: str, index: str) -> None:
    row = omop_conn.execute(
        "SELECT 1 FROM pg_indexes WHERE schemaname = 'cdm' AND tablename = %s AND indexname = %s",
        (table, index),
    ).fetchone()
    assert row is not None, f"missing index cdm.{index} on {table}; run etl/create_indices.R"
