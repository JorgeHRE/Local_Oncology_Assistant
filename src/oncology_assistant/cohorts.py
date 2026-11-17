"""Cohorts of the synthetic OMOP database, one per trial (schema ``results``).

Each cohort is a pair of views created by ``make cohort``: ``gc_<trial>_cohort`` (the patients who
meet the trial's *evaluable* criteria, with their index date) and ``gc_<trial>_attrition`` (how
many patients each filter leaves). This module only **reads** them: no SQL is written by the LLM,
and the trial id is checked against the views that exist before it reaches a query.

Limits (docs/LIMITACIONES.md): the data are synthetic, and only criteria that the OMOP data can
check are applied; the others cannot be evaluated and are not part of the cohort.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date

import psycopg
from psycopg import sql

from oncology_assistant.db import connect

logger = logging.getLogger(__name__)

SCHEMA = "results"
# The pilot cohort predates the per-trial naming: it is the SPOTLIGHT cohort (docs/cohorte-zolbetuximab.md).
LEGACY_PREFIXES = {"gc_zolbetuximab": "NCT03504397"}
_VIEW = re.compile(r"^(gc_.+)_cohort$")
_TRIAL_VIEW = re.compile(r"^gc_(nct\d{8})$")


@dataclass(frozen=True)
class AttritionStep:
    """One filter of the cohort and how many patients are left after it."""

    step: int
    description: str
    n_remaining: int
    n_lost: int


@dataclass
class CohortResult:
    """A trial's cohort: size, the filters that produced it and a sample of its patients."""

    trial: str
    count: int
    attrition: list[AttritionStep] = field(default_factory=list)
    sample: list[tuple[int, date]] = field(default_factory=list)  # (person_id, index_date)


def trial_of(prefix: str) -> str | None:
    """The NCT id of a view prefix (``gc_nct06123494`` -> ``NCT06123494``), or None."""
    if prefix in LEGACY_PREFIXES:
        return LEGACY_PREFIXES[prefix]
    match = _TRIAL_VIEW.match(prefix)
    return match.group(1).upper() if match else None


def available_cohorts(conn: psycopg.Connection) -> dict[str, str]:
    """``{trial: view prefix}`` for every cohort that has both its cohort and attrition views."""
    rows = conn.execute(
        "SELECT table_name FROM information_schema.views WHERE table_schema = %s", (SCHEMA,)
    ).fetchall()
    names = {name for (name,) in rows}
    found = {}
    for name in names:
        match = _VIEW.match(name)
        if match and f"{match.group(1)}_attrition" in names:
            trial = trial_of(match.group(1))
            if trial:
                found[trial] = match.group(1)
    return dict(sorted(found.items()))


def get_cohort(
    trial: str, conn: psycopg.Connection | None = None, sample: int = 10
) -> CohortResult:
    """Read the cohort of a trial. Raises ``KeyError`` if the trial has no cohort."""
    own = conn is None
    conn = conn or connect()
    try:
        cohorts = available_cohorts(conn)
        prefix = cohorts[trial.upper()]
        cohort_view = sql.Identifier(SCHEMA, f"{prefix}_cohort")
        attrition_view = sql.Identifier(SCHEMA, f"{prefix}_attrition")
        (count,) = conn.execute(sql.SQL("SELECT count(*) FROM {}").format(cohort_view)).fetchone()
        steps = conn.execute(
            sql.SQL("SELECT step, description, n_remaining, n_lost FROM {} ORDER BY step").format(
                attrition_view
            )
        ).fetchall()
        people = conn.execute(
            sql.SQL("SELECT person_id, index_date FROM {} ORDER BY person_id LIMIT %s").format(
                cohort_view
            ),
            (sample,),
        ).fetchall()
    finally:
        if own:
            conn.close()
    return CohortResult(
        trial.upper(), int(count), [AttritionStep(*row) for row in steps], list(people)
    )


# "Which patients meet ...", "how many patients are eligible for ...", "list the cohort of ...".
# The plural is required: questions about the text use the singular ("excludes the patient from
# being eligible"), and "eligibility criteria for patients" is a question about the text too.
_GROUP = r"(?:patients|people|persons)"
_COHORT_PATTERNS = [
    re.compile(rf"\bhow many {_GROUP}\b", re.IGNORECASE),
    re.compile(rf"\bnumber of {_GROUP}\b", re.IGNORECASE),
    re.compile(rf"\b(?:which|what)\s+(?:\w+\s+)?{_GROUP}\b", re.IGNORECASE),
    re.compile(rf"\b(?:list|show|count|give me)\b[^?.]*\b{_GROUP}\b", re.IGNORECASE),
    re.compile(r"\bcohort\b", re.IGNORECASE),
]
_ABOUT_TEXT = re.compile(r"\bdiffer\w*|\bcompare\w*|\bcriteria for patients\b", re.IGNORECASE)


def is_cohort_question(question: str) -> bool:
    """True if the question asks for the patients of the database, not for the trial's text."""
    if _ABOUT_TEXT.search(question):
        return False
    return any(pattern.search(question) for pattern in _COHORT_PATTERNS)


def format_cohort(result: CohortResult) -> str:
    """Plain-text rendering: size, filters (with the patients each one removes) and a sample."""
    lines = [
        (
            f"Cohort of {result.trial} in the synthetic OMOP database: {result.count} patients "
            "meet the criteria that the data can check."
        ),
        "",
        "Filters applied (attrition):",
    ]
    for s in result.attrition:
        lost = f"  (-{s.n_lost})" if s.n_lost else ""
        lines.append(f"  {s.step}. {s.description}: {s.n_remaining}{lost}")
    if result.sample:
        shown = ", ".join(f"{pid} ({when})" for pid, when in result.sample)
        lines += ["", f"First {len(result.sample)} patients (person_id, index date): {shown}"]
    lines += [
        "",
        (
            "Note: synthetic patients; criteria the OMOP data cannot check (for example lab "
            "values or measurable disease) are not part of this cohort."
        ),
    ]
    return "\n".join(lines)


def describe_missing(trial: str, available: dict[str, str]) -> str:
    """The reply when the question names a trial that has no cohort."""
    listed = ", ".join(available) or "none"
    return f"There is no cohort defined for {trial}. Trials with a cohort: {listed}."
