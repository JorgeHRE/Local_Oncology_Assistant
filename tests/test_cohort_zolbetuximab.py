"""The SQL attrition table of the zolbetuximab pilot cohort must match an independent
re-computation from the Synthea CSVs (pandas, no SQL, no OMOP concept ids).

Needs the OMOP database loaded (marker `db`) and the generated CSVs in
data/raw/synthea/output_gastric/csv; skipped otherwise.
"""

from __future__ import annotations

import pandas as pd
import psycopg
import pytest

from oncology_assistant.db import REPO_ROOT

pytestmark = pytest.mark.db

CSV_DIR = REPO_ROOT / "data" / "raw" / "synthea" / "output_gastric" / "csv"
SQL_FILES = [REPO_ROOT / "sql" / "01_concept_sets.sql", REPO_ROOT / "sql" / "02_cohorte.sql"]

GASTRIC_DX = {"408647009", "187732006"}
# Systemic anticancer ingredients (docs/features.md). Matched by name in the CSV description,
# so products added by other Synthea modules (e.g. FOLFOX for colorectal cancer) count too, as
# they do in the SQL through the ingredient's descendants.
SYSTEMIC_INGREDIENTS = (
    "oxaliplatin",
    "capecitabine",
    "fluorouracil",
    "leucovorin",
    "docetaxel",
    "trastuzumab",
    "zolbetuximab",
    "nivolumab",
)
WINDOW_DAYS = 30
WASHOUT_DAYS = 180


@pytest.fixture(scope="module")
def attrition(omop_conn: psycopg.Connection) -> list[tuple[int, int]]:
    """Build the cohort views (twice: the scripts must be re-runnable) and read the table."""
    for _ in range(2):
        for path in SQL_FILES:
            omop_conn.execute(path.read_text(encoding="utf-8"))
    rows = omop_conn.execute(
        "SELECT step, n_remaining FROM results.gc_zolbetuximab_attrition ORDER BY step"
    ).fetchall()
    return [(step, n) for step, n in rows]


def _day(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series.str[:10])


def expected_remaining() -> list[int]:
    """Cumulative number of patients left after each criterion, computed from the CSVs."""

    def read(name: str) -> pd.DataFrame:
        return pd.read_csv(CSV_DIR / name, dtype=str)

    patients, conditions = read("patients.csv"), read("conditions.csv")
    obs, meds = read("observations.csv"), read("medications.csv")
    obs["day"] = _day(obs["DATE"])
    meds["day"] = _day(meds["START"])

    everyone = set(patients["Id"])
    has_dx = set(conditions.loc[conditions["CODE"].isin(GASTRIC_DX), "PATIENT"])
    dx_day = (
        conditions[conditions["CODE"].isin(GASTRIC_DX)]
        .assign(day=lambda d: _day(d["START"]))
        .groupby("PATIENT")["day"]
        .min()
    )
    stage4 = obs[(obs["CODE"] == "42100-8") & (obs["VALUE"] == "Stage 4 (qualifier value)")]
    index = stage4.groupby("PATIENT")["day"].min()
    advanced = {p for p in index.index if p in dx_day.index and dx_day[p] <= index[p]}

    birth = pd.to_datetime(patients.set_index("Id")["BIRTHDATE"])
    adult = {p for p in advanced if (index[p] - birth[p]).days / 365.25 >= 18}

    def in_window(code: str, ok) -> set[str]:
        rows = obs[obs["CODE"] == code]
        rows = rows[rows["PATIENT"].isin(index.index)]
        near = (rows["day"] - rows["PATIENT"].map(index)).abs() <= pd.Timedelta(days=WINDOW_DAYS)
        rows = rows[near & ok(rows["VALUE"])]
        return set(rows["PATIENT"])

    ecog = in_window("89247-1", lambda v: pd.to_numeric(v) <= 1)
    her2_neg = in_window("18474-7", lambda v: v == "Negative (qualifier value)")
    cldn_pos = in_window("105011-1", lambda v: v == "Positive (qualifier value)")

    is_systemic = (
        meds["DESCRIPTION"].str.lower().str.contains("|".join(SYSTEMIC_INGREDIENTS), na=False)
    )
    drugs = meds[is_systemic & meds["PATIENT"].isin(index.index)]
    gap = (drugs["PATIENT"].map(index) - drugs["day"]).dt.days
    recent = set(drugs.loc[(gap > 0) & (gap <= WASHOUT_DAYS), "PATIENT"])  # strictly before index

    steps = [
        everyone,
        has_dx,
        advanced,
        adult,
        ecog,
        None,  # washout: everyone except `recent`
        her2_neg,
        cldn_pos,
    ]
    remaining: list[int] = []
    current = set(everyone)
    for step, members in enumerate(steps):
        if step == 0:
            current = set(everyone)
        elif step == 5:
            current = current - recent
        else:
            current = current & members
        remaining.append(len(current))
    return remaining


@pytest.mark.skipif(not CSV_DIR.exists(), reason="Synthea CSVs not generated (make generate)")
def test_attrition_matches_independent_computation(attrition: list[tuple[int, int]]) -> None:
    assert [n for _, n in attrition] == expected_remaining()


def test_attrition_is_monotone_and_has_every_step(attrition: list[tuple[int, int]]) -> None:
    assert [step for step, _ in attrition] == list(range(8))
    counts = [n for _, n in attrition]
    assert counts == sorted(counts, reverse=True)


def test_cohort_view_equals_last_step(
    omop_conn: psycopg.Connection, attrition: list[tuple[int, int]]
) -> None:
    (n_cohort,) = omop_conn.execute(
        "SELECT count(*) FROM results.gc_zolbetuximab_cohort"
    ).fetchone()
    assert n_cohort == attrition[-1][1]
