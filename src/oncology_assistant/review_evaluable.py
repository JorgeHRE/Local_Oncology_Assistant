"""List the criteria whose ``evaluable`` flag may contradict the annotation guide, for the annotator.

The guide (§4) says which conditions the OMOP data of this project can check (diagnosis, stage,
HER2, CLDN18, PD-L1 CPS, MSI, ECOG, age, sex, death, drugs and dates) and which it cannot (TNM,
measurable disease, brain metastases, pregnancy, consent, lab values, comorbidities, radiotherapy,
surgery...). This tool matches the *concept* of each criterion against those two lists and writes a
review file. **It changes nothing and decides nothing**: the keyword matching is a heuristic, and the
ground truth is the annotator's (ADR-0003). A criterion can be listed by mistake, or missed.

Categories:

- ``true-but-guide-says-no``: ``evaluable=True`` and the concept matches the guide's "not evaluable" list.
- ``true-not-in-features``: ``evaluable=True`` and the concept matches nothing the data can check.
- ``false-but-guide-says-yes``: ``evaluable=False`` and the concept matches the "evaluable" list.
"""

from __future__ import annotations

import argparse
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from oncology_assistant.db import REPO_ROOT
from oncology_assistant.ground_truth import (
    GROUND_TRUTH_PATH,
    CohortRecord,
    ExtractionRecord,
    parse_records,
)

logger = logging.getLogger(__name__)

# Concepts the OMOP data can check (docs/features.md and guide §4).
EVALUABLE_TERMS = (
    "diagnosis",
    "gastric",
    "cardia",
    "adenocarcinoma",
    "stage",
    "advanced",
    "her2",
    "her-2",
    "cldn",
    "claudin",
    "pd-l1",
    "pdl1",
    "cps",
    "msi",
    "dmmr",
    "ecog",
    "performance status",
    "age",
    "sex",
    "gender",
    "death",
    "prior therapy",
    "prior treatment",
    "prior systemic",
    "prior chemotherapy",
    "prior anti",
    "prior first-line",
    "prior neoadjuvant",
    "washout",
    "trastuzumab",
    "zolbetuximab",
    "nivolumab",
    "oxaliplatin",
    "capecitabine",
    "docetaxel",
)
# Concepts the guide lists as not evaluable.
NOT_EVALUABLE_TERMS = (
    "measurable",
    "recist",
    "lesion",
    "tnm",
    "metasta",
    "brain",
    "central nervous",
    "cns",
    "pregnan",
    "lactat",
    "contracept",
    "consent",
    "beta-hcg",
    "hcg",
    "laboratory",
    "lab ",
    "organ",
    "hematologic",
    "function",
    "hepatitis",
    "hbv",
    "hcv",
    "hiv",
    "immunodeficiency",
    "infection",
    "fever",
    "pulmonary",
    "pneumonia",
    "cardiovascular",
    "myocardial",
    "qtc",
    "lvef",
    "ejection",
    "hypertension",
    "allerg",
    "toxicity",
    "effusion",
    "ascites",
    "malignanc",
    "radiotherapy",
    "surgery",
    "lauren",
    "ebv",
    "fgfr2",
    "histolog",
    "life expectancy",
    "survival",
    "other factors",
    "clinically significant",
)


@dataclass(frozen=True)
class Flag:
    """A criterion listed for review."""

    record_id: str
    split: str
    concept: str
    evaluable: bool
    category: str
    quote: str


def _has(text: str, terms: tuple[str, ...]) -> bool:
    low = text.lower()
    return any(re.search(rf"(?<![a-z]){re.escape(t)}", low) for t in terms)


def classify(concept: str, evaluable: bool) -> str | None:
    """The review category of one criterion, or None if the flag looks consistent."""
    if evaluable:
        if _has(concept, NOT_EVALUABLE_TERMS):
            return "true-but-guide-says-no"
        if not _has(concept, EVALUABLE_TERMS):
            return "true-not-in-features"
        return None
    return (
        "false-but-guide-says-yes"
        if _has(concept, EVALUABLE_TERMS) and not _has(concept, NOT_EVALUABLE_TERMS)
        else None
    )


def review(path: Path = GROUND_TRUTH_PATH, splits: tuple[str, ...] = ("dev", "test")) -> list[Flag]:
    """The criteria of the E and C records that deserve a second look."""
    records, problems = parse_records(path.read_text(encoding="utf-8").splitlines())
    if problems:
        raise ValueError(f"the ground truth has {len(problems)} problem(s); run make gt-validate")
    flags = []
    for record in records:
        if not isinstance(record, ExtractionRecord | CohortRecord) or record.split not in splits:
            continue
        for criterion in record.criteria:
            category = classify(criterion.concept, criterion.evaluable)
            if category:
                flags.append(
                    Flag(
                        record.id,
                        record.split,
                        criterion.concept,
                        criterion.evaluable,
                        category,
                        criterion.citation.quote[:90].replace("\n", " "),
                    )
                )
    return flags


def write_report(path: Path, flags: list[Flag]) -> None:
    """A Markdown file grouped by category and record."""
    lines = [
        "# Criterios para revisar (evaluable)\n",
        "Heurística por palabras clave; no cambia nada. Cada criterio lo decide el anotador con la guía §4.\n",
    ]
    for category in ("true-but-guide-says-no", "true-not-in-features", "false-but-guide-says-yes"):
        subset = [f for f in flags if f.category == category]
        lines += [
            f"## {category} ({len(subset)})",
            "",
            "| Registro | split | Concepto | Cita |",
            "|---|---|---|---|",
        ]
        lines += [f"| {f.record_id} | {f.split} | {f.concept} | {f.quote} |" for f in subset]
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    """CLI: write ``data/processed/revision_evaluable.md`` and print the counts."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--splits", nargs="+", default=["dev", "test"], choices=("dev", "test"))
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    flags = review(splits=tuple(args.splits))
    out = REPO_ROOT / "data" / "processed" / "revision_evaluable.md"
    write_report(out, flags)
    for category in ("true-but-guide-says-no", "true-not-in-features", "false-but-guide-says-yes"):
        print(f"{category}: {sum(f.category == category for f in flags)}")
    print(f"review file: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
