"""Schema, validation and splits for the evaluation ground truth (ADR-0003).

The ground truth is written by hand from the original texts (``docs/guia-anotacion.md``). No
language model drafts or corrects it; this module only checks it:

* the schema of every record (pydantic), with one model per question type (R, E, C);
* that every citation is a **literal quote** found in the cited document, so retrieval can be
  scored for any chunking strategy (a chunk is relevant if it contains the quote);
* the development/test split rules: quotas per type, and no source document of an E or C
  question in both partitions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from datetime import date
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, model_validator

from oncology_assistant.chunking import _ESCAPED, Document, load_documents
from oncology_assistant.db import REPO_ROOT

logger = logging.getLogger(__name__)

GROUND_TRUTH_DIR = REPO_ROOT / "eval" / "ground_truth"
GROUND_TRUTH_PATH = GROUND_TRUTH_DIR / "ground_truth.jsonl"
# Documents with near-identical text must share a split, or the test set leaks into development.
SPLIT_GROUPS_PATH = GROUND_TRUTH_DIR / "split_groups.json"
SYNTHEA_SUMS = REPO_ROOT / "data" / "raw" / "synthea" / "output_gastric" / "SHA256SUMS"

# Development / test quotas per type (ADR-0003 §1).
QUOTAS: dict[str, dict[str, int]] = {
    "R": {"dev": 6, "test": 14},
    "E": {"dev": 4, "test": 8},
    "C": {"dev": 2, "test": 6},
}
# Topics of the R questions: the biomarker or target (ADR-0003, open question resolved 2026-11-05).
Topic = Literal["her2", "cldn18", "pdl1_immunotherapy", "msi", "other"]
Split = Literal["dev", "test"]
Operator = Literal["=", "!=", ">", ">=", "<", "<=", "in", "present", "absent"]

_DOC_ID = r"^(ct:NCT\d{8}|pm:\d+|gl:[\w.-]+)$"
_BULLET_LINE = re.compile(r"^\s*(?:[*\-•o]|\d+[.)）]|[a-z][.)])\s+", re.MULTILINE)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Citation(_Strict):
    """A literal quote from one corpus document."""

    doc_id: str = Field(
        pattern=_DOC_ID, description="manifest id, e.g. ct:NCT03504397 or pm:34102137"
    )
    quote: str = Field(min_length=10, description="copied verbatim; whitespace may differ")


class Criterion(_Strict):
    """One atomic eligibility condition (a single condition per record)."""

    kind: Literal["inclusion", "exclusion"]
    concept: str = Field(min_length=2, description="what is tested: HER2, ECOG, prior therapy...")
    operator: Operator | None = None
    value: str | None = Field(default=None, description="literal from the text: 'negative', '1'")
    unit: str | None = None
    time_window: str | None = Field(default=None, description="literal: 'within 28 days prior'")
    evaluable: bool = Field(description="can the OMOP data of this project evaluate it?")
    not_evaluable_reason: str | None = None
    citation: Citation

    @model_validator(mode="after")
    def _reason_iff_not_evaluable(self) -> Criterion:
        if self.evaluable == bool(self.not_evaluable_reason):
            raise ValueError("not_evaluable_reason is required exactly when evaluable is false")
        return self


class _Record(_Strict):
    id: str
    split: Split
    question: str = Field(min_length=10)
    annotator: str = Field(min_length=1)
    annotated_on: date
    notes: str | None = None


class RetrievalRecord(_Record):
    """R: a clinical question about the corpus, its reference answer and the passages behind it."""

    type: Literal["R"]
    id: str = Field(pattern=r"^R-\d{3}$")
    topic: Topic
    reference_answer: str = Field(min_length=10)
    relevant: list[Citation] = Field(min_length=1)


class ExtractionRecord(_Record):
    """E: the eligibility section of one document turned into atomic criteria."""

    type: Literal["E"]
    id: str = Field(pattern=r"^E-\d{3}$")
    source: str = Field(pattern=_DOC_ID)
    criteria: list[Criterion] = Field(min_length=1)

    @model_validator(mode="after")
    def _citations_come_from_the_source(self) -> ExtractionRecord:
        others = {c.citation.doc_id for c in self.criteria} - {self.source}
        if others:
            raise ValueError(f"criteria cite documents other than the source: {sorted(others)}")
        return self


class CohortRecord(_Record):
    """C: criteria that run on OMOP, with the expected patients computed by two implementations.

    The expected patients are not typed by hand: they come from a reference SQL file and an
    independent pandas recomputation that must agree (ADR-0003 §3), stored per dataset version.
    """

    type: Literal["C"]
    id: str = Field(pattern=r"^C-\d{3}$")
    source: str = Field(pattern=_DOC_ID)
    criteria: list[Criterion] = Field(min_length=1)
    reference_sql: str = Field(pattern=r"^sql/[\w.-]+\.sql$")
    dataset_id: str | None = Field(default=None, description="sha256 of the Synthea SHA256SUMS")
    expected_count: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _all_evaluable(self) -> CohortRecord:
        if not all(c.evaluable for c in self.criteria):
            raise ValueError("a cohort question can only use evaluable criteria (see type E)")
        return self


Record = Annotated[RetrievalRecord | ExtractionRecord | CohortRecord, Field(discriminator="type")]
_RECORD = TypeAdapter(Record)


def normalize(text: str) -> str:
    """Make a quote comparable with the corpus text.

    Undo Markdown escapes, drop bullet markers at line starts and collapse whitespace, so a quote
    copied from the ClinicalTrials.gov website matches the stored record. Case is kept: a quote
    is literal.
    """
    text = _ESCAPED.sub(r"\1", text)
    text = _BULLET_LINE.sub("", text)
    return " ".join(text.split())


def contains_quote(text: str, quote: str) -> bool:
    """True if ``quote`` appears literally in ``text`` (after ``normalize``)."""
    return normalize(quote) in normalize(text)


def document_text(doc: Document) -> str:
    """The text a citation may come from: criteria for trials, title plus abstract for PubMed."""
    if doc.source == "clinicaltrials.gov":
        return doc.record["protocolSection"]["eligibilityModule"].get("eligibilityCriteria", "")
    return f"{doc.record.get('title', doc.title)}\n{doc.record.get('abstract', '')}"


def parse_records(lines: Iterable[str]) -> tuple[list[Record], list[str]]:
    """Parse JSONL lines into records; return them with the problems found (line-numbered)."""
    records: list[Record] = []
    problems: list[str] = []
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            records.append(_RECORD.validate_python(json.loads(line)))
        except (json.JSONDecodeError, ValidationError) as error:
            problems.append(f"line {number}: {error}")
    return records, problems


def citations(record: Record) -> list[Citation]:
    """Every citation in a record."""
    if isinstance(record, RetrievalRecord):
        return list(record.relevant)
    return [c.citation for c in record.criteria]


def check_citations(records: Iterable[Record], docs: Mapping[str, Document]) -> list[str]:
    """Problems with citations: unknown documents or quotes not found literally.

    A document that is in the manifest but not on disk (PubMed abstracts in a clean clone) is
    reported separately by ``unverifiable_citations``, not as an error here.
    """
    problems = []
    for record in records:
        for citation in citations(record):
            doc = docs.get(citation.doc_id)
            if doc is None:
                continue
            if not contains_quote(document_text(doc), citation.quote):
                problems.append(
                    f"{record.id}: quote not found in {citation.doc_id}: {citation.quote[:60]!r}"
                )
    return problems


def unverifiable_citations(
    records: Iterable[Record], docs: Mapping[str, Document], known_ids: set[str]
) -> tuple[list[str], list[str]]:
    """Split citations whose document is not loaded into (unknown ids, known but not on disk)."""
    unknown, missing = [], []
    for record in records:
        for citation in citations(record):
            if citation.doc_id in docs:
                continue
            (missing if citation.doc_id in known_ids else unknown).append(
                f"{record.id}: {citation.doc_id}"
            )
    return unknown, missing


def check_ids(records: Iterable[Record]) -> list[str]:
    """Problems with duplicated record ids."""
    counts = Counter(r.id for r in records)
    return [f"duplicated id {id_} ({n} times)" for id_, n in sorted(counts.items()) if n > 1]


def load_split_groups(path: Path = SPLIT_GROUPS_PATH) -> dict[str, str]:
    """Map each grouped document id to its group name (``{group: [doc_id, ...]}`` on disk)."""
    if not path.exists():
        return {}
    groups = json.loads(path.read_text(encoding="utf-8"))["groups"]
    return {doc: name for name, docs in groups.items() for doc in docs}


def check_splits(
    records: list[Record], final: bool = False, groups: Mapping[str, str] | None = None
) -> list[str]:
    """Problems with the development/test split.

    Always: no source document of an E or C question, and no group of near-identical documents
    (``groups``: doc id -> group name), in both partitions. With ``final``: the counts per type
    match ``QUOTAS`` exactly.
    """
    groups = groups or {}
    problems = []
    splits_by_unit: dict[str, set[str]] = defaultdict(set)
    for record in records:
        if isinstance(record, ExtractionRecord | CohortRecord):
            unit = groups.get(record.source, record.source)
            splits_by_unit[unit].add(record.split)
    problems += [
        f"{unit} is the source of questions in both dev and test"
        for unit, splits in sorted(splits_by_unit.items())
        if len(splits) > 1
    ]
    if final:
        counts = Counter((r.type, r.split) for r in records)
        for type_, quota in QUOTAS.items():
            for split, expected in quota.items():
                if counts[(type_, split)] != expected:
                    problems.append(
                        f"{type_}/{split}: {counts[(type_, split)]} questions, expected {expected}"
                    )
    return problems


def relevant_chunk_ids(quote: str, chunks: Iterable[tuple[str, str, str]]) -> set[str]:
    """Chunk ids (from ``(chunk_id, doc_id, text)``) that contain the quote: retrieval hits.

    Scoring retrieval this way is strategy-neutral: the ground truth never names chunk ids.
    """
    return {chunk_id for chunk_id, _, text in chunks if contains_quote(text, quote)}


def dataset_id(sums_path: Path = SYNTHEA_SUMS) -> str:
    """Identifier of the synthetic dataset a cohort answer belongs to."""
    return hashlib.sha256(sums_path.read_bytes()).hexdigest()


def file_hash(path: Path) -> str:
    """SHA-256 of a ground-truth file, to freeze the test set (ADR-0003 §4)."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(path: Path = GROUND_TRUTH_PATH, final: bool = False) -> list[str]:
    """All problems in a ground-truth file; an empty list means it is valid."""
    from oncology_assistant.corpus import load_manifest

    records, problems = parse_records(path.read_text(encoding="utf-8").splitlines())
    docs = {d.doc_id: d for d in load_documents()}
    unknown, missing = unverifiable_citations(records, docs, set(load_manifest()))
    problems += [f"unknown document: {item}" for item in unknown]
    for item in missing:
        logger.warning("cannot verify (document not on disk): %s", item)
    problems += check_ids(records) + check_citations(records, docs)
    problems += check_splits(records, final, load_split_groups())
    logger.info("%d records: %s", len(records), dict(Counter(r.type for r in records)))
    return problems


def main(argv: list[str] | None = None) -> int:
    """CLI: ``validate`` the ground truth (``--final`` also checks the quotas)."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("validate", help="check schema, citations and splits")
    check.add_argument("path", nargs="?", type=Path, default=GROUND_TRUTH_PATH)
    check.add_argument("--final", action="store_true", help="also require the exact quotas")
    sub.add_parser("dataset-id", help="print the id of the current Synthea dataset")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if args.command == "dataset-id":
        print(dataset_id())
        return 0
    problems = validate(args.path, final=args.final)
    for problem in problems:
        logger.error(problem)
    logger.info("%s", "valid" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
