"""Extraction evaluation (ADR-0002, layer 2): atomic criteria extracted by an LLM vs. the E records.

For each E question the model receives the eligibility section of the trial (all the chunks of that
trial and section, in order: this is what the pipeline would fetch with a metadata filter) and must
return the atomic criteria in the format of the annotation guide. The result is scored against the
annotator's criteria, with no LLM judge:

- ``quote_recall``: share of the reference quotes (distinct source sentences) that some extracted
  criterion cites (the quotes overlap).
- ``grounded``: share of extracted criteria whose quote is literal in the section.
- ``count_ratio``: extracted criteria / reference criteria (below 1: merged or skipped conditions;
  above 1: invented or over-split ones).
- ``operator``, ``value``, ``evaluable``: agreement with the reference, over the reference
  criteria that some extracted criterion covers (best-matching one). Values are compared after
  lower-casing and dropping everything but letters and digits, and count as equal if one contains
  the other. The free-text ``concept`` is not scored; it is written to the review file.

The test split is frozen (ADR-0003): the CLI defaults to ``--split dev``.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, get_args

import chromadb

from oncology_assistant.db import REPO_ROOT
from oncology_assistant.embedders import index_dir_for
from oncology_assistant.eval_generation import DEFAULT_MODELS
from oncology_assistant.ground_truth import (
    GROUND_TRUTH_PATH,
    Criterion,
    ExtractionRecord,
    Operator,
    parse_records,
)
from oncology_assistant.index import collection_name
from oncology_assistant.rag import EMBEDDER, Llm, ollama_llm, quote_in_passage

logger = logging.getLogger(__name__)

REPORT_DIR = REPO_ROOT / "data" / "processed"  # gitignored
OPERATORS = list(get_args(Operator))

EXTRACT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "criteria": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "concept": {"type": "string"},
                    "operator": {"type": "string", "enum": [*OPERATORS, ""]},
                    "value": {"type": "string"},
                    "unit": {"type": "string"},
                    "time_window": {"type": "string"},
                    "evaluable": {"type": "boolean"},
                    "quote": {"type": "string"},
                },
                "required": [
                    "concept",
                    "operator",
                    "value",
                    "unit",
                    "time_window",
                    "evaluable",
                    "quote",
                ],
            },
        }
    },
    "required": ["criteria"],
}

EXTRACT_PROMPT = (
    "You turn the {kind} criteria of a clinical trial into atomic conditions, as JSON. Rules: "
    "(1) One record per single condition: 'HER2-negative and CLDN18.2-positive' are two records; "
    "alternatives of the same concept ('ECOG 0 or 1') are one. "
    "(2) concept: what is tested (HER2, ECOG, prior therapy, age...). operator is one of "
    f"{OPERATORS} or '' (use 'present' / 'absent' for something required / forbidden). "
    "(3) value, unit and time_window are copied literally from the text (do not convert units); "
    "use '' when there is none. "
    "(4) evaluable is true only if the condition can be checked in an OMOP database with: gastric "
    "cancer diagnosis, stage group, HER2, CLDN18.2, PD-L1 CPS, MSI, ECOG, age, sex, death, and "
    "drugs with dates; it is false for lab values, comorbidities, pregnancy, consent, tumor "
    "measurability, histology subtype, EBV, FGFR2b and radiotherapy or surgery. "
    "(5) quote: a short exact copy of the part of the text that holds the condition (same "
    "characters, inside a single criterion). Cover every criterion of the text."
)


@dataclass
class DocResult:
    """The extraction of one section by one model, with its scores."""

    record_id: str
    extracted: list[dict[str, Any]]
    json_ok: bool
    seconds: float
    quote_recall: float = 0.0
    grounded: float = 0.0
    count_ratio: float = 0.0
    matched: int = 0
    agree: dict[str, int] = field(default_factory=dict)


def section_text(source: str, kind: str, index_path: Path | None = None) -> str:
    """The chunks of one trial's section, in their original order, joined by newlines."""
    path = index_path or index_dir_for(EMBEDDER)
    collection = chromadb.PersistentClient(path=str(path)).get_collection(
        collection_name("structural"), embedding_function=None
    )
    stored = collection.get(
        where={"$and": [{"doc_id": source}, {"section": kind}]}, include=["documents", "metadatas"]
    )
    ordered = sorted(
        zip(stored["metadatas"], stored["documents"], strict=True), key=lambda p: p[0]["position"]
    )
    return "\n".join(text for _, text in ordered)


def build_messages(kind: str, text: str) -> list[dict[str, str]]:
    """The extraction request for one section."""
    return [
        {"role": "system", "content": EXTRACT_PROMPT.format(kind=kind)},
        {"role": "user", "content": f"{kind.capitalize()} criteria:\n\n{text}"},
    ]


def _squash(text: str) -> str:
    return "".join(re.findall(r"[a-z0-9]", text.lower()))


def overlaps(a: str, b: str) -> bool:
    """True if one quote contains the other (ignoring case, spacing and punctuation)."""
    x, y = _squash(a), _squash(b)
    return len(x) >= 8 and len(y) >= 8 and (x in y or y in x)


def same_value(a: str | None, b: str | None) -> bool:
    """Lenient equality of two values: both empty, or one contains the other."""
    x, y = _squash(a or ""), _squash(b or "")
    return x == y or (bool(x) and bool(y) and (x in y or y in x))


def field_matches(ref: Criterion, got: dict[str, Any]) -> dict[str, bool]:
    """Which fields of an extracted criterion agree with the reference one."""
    return {
        "operator": (ref.operator or "") == (got.get("operator") or ""),
        "value": same_value(ref.value, got.get("value")),
        "evaluable": ref.evaluable == bool(got.get("evaluable")),
    }


def score(record: ExtractionRecord, extracted: list[dict[str, Any]], section: str) -> DocResult:
    """Score the extracted criteria of one section against the reference criteria."""
    refs = record.criteria
    distinct = {_squash(c.citation.quote): c.citation.quote for c in refs}
    covered = sum(
        any(overlaps(q, g.get("quote", "")) for g in extracted) for q in distinct.values()
    )
    result = DocResult(record.id, extracted, True, 0.0)
    result.quote_recall = covered / len(distinct) if distinct else 0.0
    literal = sum(quote_in_passage(section, g.get("quote", "")) for g in extracted)
    result.grounded = literal / len(extracted) if extracted else 0.0
    result.count_ratio = len(extracted) / len(refs)
    result.agree = {"operator": 0, "value": 0, "evaluable": 0}
    for ref in refs:
        candidates = [g for g in extracted if overlaps(ref.citation.quote, g.get("quote", ""))]
        if not candidates:
            continue
        result.matched += 1
        best = max(candidates, key=lambda g: sum(field_matches(ref, g).values()))
        for name, ok in field_matches(ref, best).items():
            result.agree[name] += ok
    return result


def load_e_records(
    path: Path = GROUND_TRUTH_PATH, split: str | None = "dev"
) -> list[ExtractionRecord]:
    """The valid E records of the ground truth, optionally of one split."""
    records, problems = parse_records(path.read_text(encoding="utf-8").splitlines())
    if problems:
        raise ValueError(f"the ground truth has {len(problems)} problem(s); run make gt-validate")
    return [r for r in records if isinstance(r, ExtractionRecord) and split in (None, r.split)]


def run_model(
    model: str,
    records: list[ExtractionRecord],
    sections: dict[str, str],
    llm: Llm | None = None,
) -> list[DocResult]:
    """Extract the criteria of every record with one model (a warm-up call first) and score them."""
    import time

    llm = llm or ollama_llm(model=model, schema=EXTRACT_SCHEMA, timeout=600)
    first = records[0]
    try:
        llm(build_messages(first.criteria[0].kind, sections[first.id]))
    except RuntimeError as error:
        logger.warning("warm-up of %s failed: %s", model, error)
    results = []
    for record in records:
        kind = record.criteria[0].kind
        started = time.perf_counter()
        try:
            raw = llm(build_messages(kind, sections[record.id]))
            data = json.loads(raw)
            extracted = [dict(c) for c in data["criteria"]]
            ok = True
        except (RuntimeError, ValueError, KeyError, TypeError):
            extracted, ok = [], False
        seconds = time.perf_counter() - started
        scored = score(record, extracted, sections[record.id])
        scored.json_ok, scored.seconds = ok, seconds
        results.append(scored)
    return results


def summarize(
    model: str, results: list[DocResult], records: list[ExtractionRecord]
) -> dict[str, Any]:
    """Model-level numbers: means over sections and agreement over matched reference criteria."""
    n = len(results)
    matched = sum(r.matched for r in results)
    total_refs = sum(len(rec.criteria) for rec in records)

    def rate(name: str) -> float:
        return round(sum(r.agree.get(name, 0) for r in results) / matched, 2) if matched else 0.0

    return {
        "model": model,
        "sections": n,
        "json_ok": sum(r.json_ok for r in results),
        "quote_recall": round(sum(r.quote_recall for r in results) / n, 2),
        "grounded": round(sum(r.grounded for r in results) / n, 2),
        "count_ratio": round(sum(len(r.extracted) for r in results) / total_refs, 2),
        "operator": rate("operator"),
        "value": rate("value"),
        "evaluable": rate("evaluable"),
        "matched_criteria": f"{matched}/{total_refs}",
        "mean_seconds": round(sum(r.seconds for r in results) / n, 1),
    }


def write_review(
    path: Path, by_model: dict[str, list[DocResult]], records: list[ExtractionRecord]
) -> None:
    """A Markdown file to compare, per section, the reference criteria with each model's."""
    lines = ["# Revisión de la extracción de criterios\n"]
    for i, record in enumerate(records):
        lines += [
            f"## {record.id}  ({record.source}, {record.criteria[0].kind})",
            "",
            "### Referencia",
        ]
        for c in record.criteria:
            lines.append(
                f"- {c.concept} | {c.operator} | {c.value} | {c.unit} | evaluable={c.evaluable}"
            )
        for model, results in by_model.items():
            lines += ["", f"### {model}"]
            for g in results[i].extracted:
                lines.append(
                    f"- {g.get('concept')} | {g.get('operator')} | {g.get('value')} | {g.get('unit')}"
                    f" | evaluable={g.get('evaluable')}"
                )
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    """CLI: compare the models on the E questions of one split."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--split", choices=("dev", "test"), default="dev")
    parser.add_argument("--models", nargs="+", default=list(DEFAULT_MODELS))
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    records = load_e_records(split=args.split)
    sections = {r.id: section_text(r.source, r.criteria[0].kind) for r in records}
    by_model = {}
    for model in args.models:
        by_model[model] = run_model(model, records, sections)
        print(json.dumps(summarize(model, by_model[model], records), ensure_ascii=False))
    out = REPORT_DIR / f"extraction_comparison_{args.split}.md"
    write_review(out, by_model, records)
    print(f"review file: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
