"""Retrieval evaluation (ADR-0002, layer 1): recall@k of the R questions of the ground truth.

For each R question, the retriever is run exactly as the RAG runs it (``rag.retrieve``) and each
reference quote in ``relevant`` counts as found if some retrieved chunk contains it. Recall@k is
the fraction of reference quotes found, averaged over the questions.

The test split is frozen (ADR-0003 §4): it is evaluated once per candidate, not used to iterate.
The CLI therefore defaults to ``--split dev`` and asks for ``--split test`` explicitly.
"""

from __future__ import annotations

import argparse
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from oncology_assistant.chunking import STRATEGIES
from oncology_assistant.ground_truth import GROUND_TRUTH_PATH, RetrievalRecord, parse_records
from oncology_assistant.index import INDEX_DIR, Embedder
from oncology_assistant.rag import (
    REWRITE_SCHEMA,
    ollama_llm,
    quote_in_passage,
    retrieve,
    rewrite_query,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class QuestionResult:
    """Retrieval outcome for one R question."""

    question_id: str
    found: int
    total: int

    @property
    def recall(self) -> float:
        """Fraction of the reference quotes found among the retrieved chunks."""
        return self.found / self.total if self.total else 0.0


def load_r_records(path: Path = GROUND_TRUTH_PATH, split: str | None = None):
    """The valid R records of the ground truth, optionally of one split."""
    records, problems = parse_records(path.read_text(encoding="utf-8").splitlines())
    if problems:
        raise ValueError(f"the ground truth has {len(problems)} problem(s); run make gt-validate")
    return [r for r in records if isinstance(r, RetrievalRecord) and split in (None, r.split)]


def evaluate(
    records: Sequence[RetrievalRecord],
    strategy: str,
    k: int,
    embedder: Embedder | None = None,
    index_path: Path = INDEX_DIR,
    hybrid: bool = True,
    rewrites: Mapping[str, str] | None = None,
) -> list[QuestionResult]:
    """Recall of every question for one strategy and cut-off ``k``."""
    results = []
    for record in records:
        extra = [rewrites[record.id]] if rewrites and record.id in rewrites else []
        hits = retrieve(
            record.question,
            k=k,
            strategy=strategy,
            embedder=embedder,
            path=index_path,
            hybrid=hybrid,
            extra_queries=extra,
        )
        found = sum(
            any(quote_in_passage(hit["text"], cite.quote) for hit in hits)
            for cite in record.relevant
        )
        results.append(QuestionResult(record.id, found, len(record.relevant)))
    return results


def mean_recall(results: Sequence[QuestionResult]) -> float:
    """Mean recall over questions (0 if there are none)."""
    return sum(r.recall for r in results) / len(results) if results else 0.0


def main(argv: list[str] | None = None) -> int:
    """CLI: recall@k per strategy over the R questions of one split."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--split", choices=("dev", "test"), default="dev")
    parser.add_argument("-k", type=int, nargs="+", default=[1, 3, 5, 10])
    parser.add_argument("--rewrite", action="store_true", help="rewrite each question with the LLM")
    parser.add_argument(
        "--model",
        help="Ollama embedding model with its own index (see embedders.py); omit or 'default' for the ONNX MiniLM",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    records = load_r_records(split=args.split)
    embedder, index_path = None, INDEX_DIR
    if args.model and args.model != "default":
        from oncology_assistant.embedders import index_dir_for, ollama_embedder

        embedder, index_path = ollama_embedder(args.model), index_dir_for(args.model)
    rewrites = None
    if args.rewrite:
        rewriter = ollama_llm(schema=REWRITE_SCHEMA)
        rewrites = {r.id: rewrite_query(r.question, rewriter) for r in records}
        for qid, text in rewrites.items():
            print(f"  {qid} -> {text}")
    print(
        f"R questions in {args.split}: {len(records)}; embedder: {args.model or 'default'}; rewrite: {args.rewrite}"
    )
    for strategy in STRATEGIES:
        for hybrid in (False, True):
            label = f"{strategy}/{'hybrid' if hybrid else 'vector'}"
            for k in args.k:
                results = evaluate(
                    records,
                    strategy,
                    k,
                    embedder=embedder,
                    index_path=index_path,
                    hybrid=hybrid,
                    rewrites=rewrites,
                )
                missed = [r.question_id for r in results if r.found < r.total]
                print(
                    f"{label:18s} recall@{k:<3d} {mean_recall(results):.2f}  incomplete: {missed}"
                )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
