"""Tests for oncology_assistant.synthea_codes and the standard-code rule of ADR-0001.

Every code a module emits must be standard or map ("Maps to") to a standard concept, because
ETL-Synthea drops the rest silently; coded values must also be in the post-ETL value map.
"""

from __future__ import annotations

import json
from pathlib import Path

import psycopg
import pytest

from oncology_assistant.db import REPO_ROOT
from oncology_assistant.synthea_codes import (
    ModuleCode,
    check_codes,
    check_module_files,
    extract_codes,
    load_value_map,
)

MODULES_DIR = REPO_ROOT / "synthea" / "modules"
MODULE_FILES = sorted(MODULES_DIR.rglob("*.json"))

MINI_MODULE = {
    "name": "mini",
    "states": {
        "Diagnosis": {
            "type": "ConditionOnset",
            "codes": [
                {"system": "SNOMED-CT", "code": "408647009", "display": "Adenocarcinoma of stomach"}
            ],
        },
        "HER2": {
            "type": "Observation",
            "codes": [
                {"system": "LOINC", "code": "18474-7", "display": "HER2 Ag [Presence] in Tissue"}
            ],
            "value_code": {
                "system": "SNOMED-CT",
                "code": "10828004",
                "display": "Positive (qualifier value)",
            },
        },
        "Branch": {
            "type": "Simple",
            "conditional_transition": [
                {
                    "condition": {
                        "condition_type": "Observation",
                        "codes": [{"system": "LOINC", "code": "18474-7", "display": "HER2"}],
                        "operator": "==",
                        "value_code": {
                            "system": "SNOMED-CT",
                            "code": "10828004",
                            "display": "Positive (qualifier value)",
                        },
                    },
                    "transition": "Terminal",
                }
            ],
        },
    },
}


def _code(system: str, code: str, display: str = "", is_value: bool = False) -> ModuleCode:
    return ModuleCode(system=system, code=code, display=display, is_value=is_value, location="test")


# --- Without database ------------------------------------------------------------------------


def test_extract_codes_finds_states_values_and_guards() -> None:
    found = list(extract_codes(MINI_MODULE, location="mini.json"))
    assert len(found) == 5
    assert {(c.system, c.code, c.is_value) for c in found} == {
        ("SNOMED-CT", "408647009", False),
        ("LOINC", "18474-7", False),
        ("SNOMED-CT", "10828004", True),
    }
    guard_codes = [c for c in found if "conditional_transition" in c.location]
    assert len(guard_codes) == 2
    assert all(c.location.startswith("mini.json/states/") for c in found)


def test_value_map_is_parsed_from_post_etl_sql() -> None:
    value_map = load_value_map()
    assert len(value_map) == 8
    assert value_map["Positive (qualifier value)"] == "10828004"
    assert value_map["Stage 4 (qualifier value)"] == "258228008"


# --- With database ---------------------------------------------------------------------------


@pytest.mark.db
@pytest.mark.parametrize(
    ("module_code", "expected_reason"),
    [
        pytest.param(_code("SNOMED-CT", "408647009"), None, id="standard"),
        pytest.param(_code("SNOMED-CT", "393474000"), None, id="non-standard-with-maps-to"),
        pytest.param(_code("LOINC", "85319-2"), "not standard", id="non-standard-dropped-by-etl"),
        pytest.param(_code("LOINC", "99999-9"), "not found", id="not-in-vocabulary"),
        pytest.param(_code("ICD-10", "C16.9"), "unsupported system", id="unsupported-system"),
        pytest.param(
            _code("SNOMED-CT", "10828004", "Positive (qualifier value)", is_value=True),
            None,
            id="value-in-map",
        ),
        pytest.param(
            _code("SNOMED-CT", "385633008", "Improving (qualifier value)", is_value=True),
            "not in the post-ETL value map",
            id="value-not-in-map",
        ),
        pytest.param(
            _code("SNOMED-CT", "393474000", "Positive (qualifier value)", is_value=True),
            "maps to SNOMED 10828004",
            id="value-code-disagrees-with-map",
        ),
    ],
)
def test_check_codes(
    omop_conn: psycopg.Connection, module_code: ModuleCode, expected_reason: str | None
) -> None:
    problems = check_codes(omop_conn, [module_code])
    if expected_reason is None:
        assert problems == []
    else:
        assert len(problems) == 1
        assert expected_reason in problems[0].reason


@pytest.mark.db
def test_check_module_files_on_valid_module(omop_conn: psycopg.Connection, tmp_path: Path) -> None:
    path = tmp_path / "mini.json"
    path.write_text(json.dumps(MINI_MODULE), encoding="utf-8")
    assert check_module_files(omop_conn, [path]) == []


@pytest.mark.db
@pytest.mark.parametrize("module_file", MODULE_FILES, ids=lambda p: str(p.relative_to(MODULES_DIR)))
def test_project_modules_use_only_etl_safe_codes(
    omop_conn: psycopg.Connection, module_file: Path
) -> None:
    """The ADR-0001 rule, applied to every module in synthea/modules/."""
    problems = check_module_files(omop_conn, [module_file])
    assert [
        f"{p.module_code.system} {p.module_code.code} at {p.module_code.location}: {p.reason}"
        for p in problems
    ] == []
