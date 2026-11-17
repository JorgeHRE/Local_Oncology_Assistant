"""Generation evaluation: compare LLMs on the same retrieved passages (ADR-0005 candidates).

Retrieval is run once per R question (same retriever, same rewritten query) and every model gets
exactly the same numbered passages, so only the generation differs. Automatic measures:

- ``json_ok``: the reply was valid JSON of the expected shape.
- ``grounded``: it cited something and every quote is literal in its passage.
- ``answered_grounded``: of the answers that were not a refusal, how many are grounded (a refusal
  has no citations, so it is not an error of this kind; an answer with a made-up quote is).
- ``refused``: it said the passages do not contain the answer.
- ``refused_but_answerable``: it refused although a reference quote was among the passages.
- latency (seconds per answer, excluding a warm-up call that loads the model).

Whether an answer is *correct* is judged by the annotator: the answers and the reference answers
are written to a Markdown file for review (an LLM judge from the same families would be biased).
The test split is frozen (ADR-0003): the CLI defaults to ``--split dev``.
"""

from __future__ import annotations

import argparse
import json
import logging
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from oncology_assistant.db import REPO_ROOT
from oncology_assistant.eval_retrieval import load_r_records
from oncology_assistant.ground_truth import RetrievalRecord
from oncology_assistant.rag import (
    NOT_FOUND,
    REWRITE_SCHEMA,
    Answer,
    Llm,
    build_messages,
    ollama_llm,
    parse_answer,
    quote_in_passage,
    retrieve,
    rewrite_query,
)

logger = logging.getLogger(__name__)

DEFAULT_MODELS = ("qwen3:8b", "gemma3:12b", "medgemma:4b")
REWRITE_MODEL = "qwen3:8b"
REPORT_DIR = REPO_ROOT / "data" / "processed"  # gitignored


@dataclass
class Item:
    """One model's answer to one question, with the automatic measures."""

    question_id: str
    answer: Answer | None
    seconds: float
    json_ok: bool
    answerable: bool
    error: str | None = None

    @property
    def refused(self) -> bool:
        """True if the model said the passages do not contain the answer."""
        return self.answer is not None and self.answer.answer.strip() == NOT_FOUND

    @property
    def grounded(self) -> bool:
        """True if the answer has citations and all of them are literal."""
        return self.answer is not None and self.answer.grounded


@dataclass
class ModelReport:
    """All the items of one model."""

    model: str
    items: list[Item] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        """Rates over the questions, plus the mean latency."""
        n = len(self.items)
        answerable = [i for i in self.items if i.answerable]
        answered = [i for i in self.items if not i.refused]
        return {
            "model": self.model,
            "n": n,
            "json_ok": sum(i.json_ok for i in self.items),
            "grounded": sum(i.grounded for i in self.items),
            "answered": len(answered),
            "answered_grounded": sum(i.grounded for i in answered),
            "refused": sum(i.refused for i in self.items),
            "refused_but_answerable": sum(i.refused for i in answerable),
            "answerable": len(answerable),
            "mean_seconds": round(statistics.mean(i.seconds for i in self.items), 2) if n else 0.0,
        }


def retrieve_once(
    records: list[RetrievalRecord], rewriter: Llm | None, k: int = 6
) -> dict[str, list[dict[str, Any]]]:
    """The passages of every question: same retriever and rewritten query for all models."""
    passages = {}
    for record in records:
        extra = [rewrite_query(record.question, rewriter)] if rewriter else []
        passages[record.id] = retrieve(record.question, k=k, extra_queries=extra)
    return passages


def is_answerable(record: RetrievalRecord, passages: list[dict[str, Any]]) -> bool:
    """True if some reference quote is inside the retrieved passages."""
    return any(
        quote_in_passage(p["text"], cite.quote) for cite in record.relevant for p in passages
    )


def run_model(
    model: str,
    records: list[RetrievalRecord],
    passages: dict[str, list[dict[str, Any]]],
    llm: Llm | None = None,
) -> ModelReport:
    """Ask one model every question with the given passages (one warm-up call first)."""
    llm = llm or ollama_llm(model=model)
    first = records[0]
    try:
        llm(build_messages(first.question, passages[first.id]))  # loads the model; not timed
    except RuntimeError as error:
        logger.warning("warm-up of %s failed: %s", model, error)
    report = ModelReport(model)
    for record in records:
        found = passages[record.id]
        started = time.perf_counter()
        try:
            raw = llm(build_messages(record.question, found))
            error = None
        except RuntimeError as exc:
            raw, error = "", str(exc)
        seconds = time.perf_counter() - started
        try:
            data = json.loads(raw)
            json_ok = isinstance(data.get("answer"), str) and isinstance(
                data.get("citations"), list
            )
        except (ValueError, AttributeError):
            json_ok = False
        answer = parse_answer(raw, record.question, found) if raw else None
        report.items.append(
            Item(record.id, answer, seconds, json_ok, is_answerable(record, found), error)
        )
    return report


def write_review(path: Path, reports: list[ModelReport], records: list[RetrievalRecord]) -> None:
    """A Markdown file for the annotator: each question, its reference answer and every answer."""
    lines = ["# Revisión de respuestas por modelo\n"]
    by_model = {r.model: {i.question_id: i for i in r.items} for r in reports}
    for record in records:
        lines += [f"## {record.id}", f"**Pregunta:** {record.question}", ""]
        lines += [f"**Respuesta de referencia:** {record.reference_answer}", ""]
        for model, items in by_model.items():
            item = items[record.id]
            text = item.answer.answer if item.answer else f"(sin respuesta: {item.error})"
            flags = (
                f"citas verificadas: {'sí' if item.grounded else 'no'}; "
                f"se negó: {'sí' if item.refused else 'no'}; {item.seconds:.1f} s"
            )
            lines += [f"### {model}  ({flags})", text, ""]
            lines += ["**Correcta (sí / parcial / no):** ", ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    """CLI: compare the models on the R questions of one split."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--split", choices=("dev", "test"), default="dev")
    parser.add_argument("--models", nargs="+", default=list(DEFAULT_MODELS))
    parser.add_argument("-k", type=int, default=6)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    records = load_r_records(split=args.split)
    rewriter = ollama_llm(model=REWRITE_MODEL, schema=REWRITE_SCHEMA)
    passages = retrieve_once(records, rewriter, args.k)
    reports = []
    for model in args.models:
        report = run_model(model, records, passages)
        reports.append(report)
        print(json.dumps(report.summary(), ensure_ascii=False))
    out = REPORT_DIR / f"llm_comparison_{args.split}.md"
    write_review(out, reports, records)
    print(f"review file: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
