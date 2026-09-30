"""Check that every code emitted by a Synthea GMF module survives ETL-Synthea.

ETL-Synthea v2.1.1 inner-joins source codes against the standard-concept map, so a code that is
neither standard nor mapped ("Maps to") to a standard concept is dropped without any error (see
ADR-0001, phase 2). This module finds such codes before any data is generated.

It also checks coded observation values (``value_code``) against the post-ETL map in
``etl/post_etl/01_value_as_concept.sql``: a value that is not in that map ends up with
``value_as_concept_id = 0``.

Usage::

    python -m oncology_assistant.synthea_codes synthea/modules/gastric_cancer.json [...]
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg

from oncology_assistant.db import REPO_ROOT, connect

logger = logging.getLogger(__name__)

VALUE_MAP_SQL = REPO_ROOT / "etl" / "post_etl" / "01_value_as_concept.sql"

# Synthea system name -> OMOP vocabulary_id. Anything else cannot be verified and is reported.
SYSTEM_TO_VOCABULARY: dict[str, str] = {
    "SNOMED-CT": "SNOMED",
    "LOINC": "LOINC",
    "RxNorm": "RxNorm",
    "CVX": "CVX",
}

_VALUE_MAP_ROW = re.compile(r"\(\s*'([^']+)'\s*,\s*'([^']+)'\s*\)")


@dataclass(frozen=True)
class ModuleCode:
    """A code found in a GMF module, with where it appears."""

    system: str
    code: str
    display: str
    is_value: bool
    location: str


@dataclass(frozen=True)
class CodeProblem:
    """A module code that would be lost or left unmapped after the ETL."""

    module_code: ModuleCode
    reason: str


def extract_codes(module: Any, location: str = "") -> Iterator[ModuleCode]:
    """Yield every ``{system, code, display}`` object in a GMF module, recursively.

    Covers state codes, ``value_code`` of observations and codes inside guards/conditions, without
    depending on the list of GMF state types.
    """
    if isinstance(module, dict):
        if "system" in module and "code" in module:
            yield ModuleCode(
                system=str(module["system"]),
                code=str(module["code"]),
                display=str(module.get("display", "")),
                is_value=location.endswith("/value_code"),
                location=location,
            )
        for key, value in module.items():
            yield from extract_codes(value, f"{location}/{key}")
    elif isinstance(module, list):
        for index, item in enumerate(module):
            yield from extract_codes(item, f"{location}[{index}]")


def load_value_map(path: Path = VALUE_MAP_SQL) -> dict[str, str]:
    """Return the post-ETL value map (value text -> SNOMED code) parsed from its SQL file."""
    text = path.read_text(encoding="utf-8")
    values_block = text.split("INSERT INTO value_concept_map", 1)[1].split(";", 1)[0]
    return {match[0]: match[1] for match in _VALUE_MAP_ROW.findall(values_block)}


def _standard_status(
    conn: psycopg.Connection, keys: set[tuple[str, str]]
) -> dict[tuple[str, str], str | None]:
    """Map each (vocabulary_id, code) to None if it survives the ETL, else to a reason.

    A code survives if it is a standard concept or has a valid "Maps to" a standard concept. All
    codes are resolved in one query: the vocabulary tables have no secondary indexes, so one query
    per code would scan concept_relationship (~34M rows) each time.
    """
    if not keys:
        return {}
    vocabularies, codes = zip(*sorted(keys))
    rows = conn.execute(
        """
        WITH wanted AS (
            SELECT * FROM unnest(%s::text[], %s::text[]) AS w(vocabulary_id, concept_code)
        ),
        src AS (
            SELECT w.vocabulary_id, w.concept_code, c.concept_id, c.standard_concept,
                   c.invalid_reason
            FROM wanted w
            JOIN cdm.concept c USING (vocabulary_id, concept_code)
        )
        SELECT src.vocabulary_id, src.concept_code, src.standard_concept, src.invalid_reason,
               count(std.concept_id) AS n_standard_targets
        FROM src
        LEFT JOIN cdm.concept_relationship r
               ON r.concept_id_1 = src.concept_id
              AND r.relationship_id = 'Maps to'
              AND r.invalid_reason IS NULL
        LEFT JOIN cdm.concept std
               ON std.concept_id = r.concept_id_2
              AND std.standard_concept = 'S'
        GROUP BY 1, 2, 3, 4
        """,
        (list(vocabularies), list(codes)),
    ).fetchall()
    status: dict[tuple[str, str], str | None] = {key: "not found in the vocabulary" for key in keys}
    for vocabulary_id, code, standard_concept, invalid_reason, n_targets in rows:
        if standard_concept == "S" or n_targets > 0:
            status[(vocabulary_id, code)] = None
        else:
            status[(vocabulary_id, code)] = (
                f"not standard (standard_concept={standard_concept!r}, "
                f"invalid_reason={invalid_reason!r}) and no 'Maps to' a standard concept"
            )
    return status


def check_codes(
    conn: psycopg.Connection,
    codes: Iterable[ModuleCode],
    value_map: dict[str, str] | None = None,
) -> list[CodeProblem]:
    """Return the codes that ETL-Synthea would drop or that the post-ETL step would not map.

    A problem is reported for every location where a failing code appears.
    """
    value_map = load_value_map() if value_map is None else value_map
    codes = list(codes)
    problems: list[CodeProblem] = []
    supported: list[tuple[ModuleCode, tuple[str, str]]] = []
    for module_code in codes:
        vocabulary_id = SYSTEM_TO_VOCABULARY.get(module_code.system)
        if vocabulary_id is None:
            problems.append(CodeProblem(module_code, f"unsupported system {module_code.system!r}"))
        else:
            supported.append((module_code, (vocabulary_id, module_code.code)))

    status = _standard_status(conn, {key for _, key in supported})
    for module_code, key in supported:
        if status[key] is not None:
            problems.append(CodeProblem(module_code, status[key]))
            continue
        if module_code.is_value:
            # Synthea writes the display text to the CSV; it reaches value_source_value as is.
            text = module_code.display
            mapped_code = value_map.get(text)
            if mapped_code is None:
                problems.append(
                    CodeProblem(
                        module_code, f"value text {text!r} is not in the post-ETL value map"
                    )
                )
            elif mapped_code != module_code.code:
                problems.append(
                    CodeProblem(
                        module_code,
                        f"value text {text!r} maps to SNOMED {mapped_code} in the post-ETL map, "
                        f"but the module uses {module_code.code}",
                    )
                )
    return problems


def check_module_files(conn: psycopg.Connection, paths: Iterable[Path]) -> list[CodeProblem]:
    """Check every code in the given module JSON files."""
    value_map = load_value_map()
    problems: list[CodeProblem] = []
    for path in paths:
        module = json.loads(path.read_text(encoding="utf-8"))
        codes = list(extract_codes(module, location=path.name))
        logger.info("%s: %d codes", path, len(codes))
        problems.extend(check_codes(conn, codes, value_map))
    return problems


def main(argv: list[str] | None = None) -> int:
    """CLI entry point; returns 1 if any code would be lost or left unmapped."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("modules", nargs="+", type=Path, help="GMF module JSON files")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    with connect() as conn:
        problems = check_module_files(conn, args.modules)
    for problem in problems:
        mc = problem.module_code
        logger.error(
            "%s %s (%s) at %s: %s", mc.system, mc.code, mc.display, mc.location, problem.reason
        )
    logger.info("%d problem(s)", len(problems))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
