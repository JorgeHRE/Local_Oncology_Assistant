"""The assistant: one entry point that sends each question to the right tool.

- A question about the **patients** of the database for a named trial ("Which patients meet the
  criteria of NCT...?") is answered from that trial's OMOP cohort (``cohorts.py``): exact counts
  from SQL views, no LLM involved in the numbers.
- Any other question is answered from the trial and article texts (``rag.py``), with verified
  citations.

The routing is deterministic (keywords and the trial id), so the same question always takes the
same path. See docs/adr for the design of each side.
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass

import psycopg

from oncology_assistant import cohorts, rag
from oncology_assistant.rag import trial_filter


@dataclass
class Response:
    """What the assistant returns: which tool answered and the text to show."""

    route: str  # "cohort", "cohort-missing", "cohort-unavailable" or "rag"
    text: str
    cohort: cohorts.CohortResult | None = None
    answer: rag.Answer | None = None


def trials_named(question: str) -> list[str]:
    """The NCT ids named in the question, in upper case."""
    flt = trial_filter(question)
    if not flt:
        return []
    value = flt["doc_id"]
    ids = value["$in"] if isinstance(value, dict) else [value]
    return [i.removeprefix("ct:") for i in ids]


def ask(question: str, **rag_options) -> Response:
    """Route the question: cohort tool if it asks for patients of a trial, RAG otherwise."""
    named = trials_named(question)
    if named and cohorts.is_cohort_question(question):
        try:
            conn = cohorts.connect()
        except psycopg.OperationalError:
            return Response(
                "cohort-unavailable",
                "The OMOP database is not reachable; start it with `make db` and try again.",
            )
        with conn:
            available = cohorts.available_cohorts(conn)
            missing = [t for t in named if t not in available]
            if missing:
                return Response("cohort-missing", cohorts.describe_missing(missing[0], available))
            result = cohorts.get_cohort(named[0], conn)
        return Response("cohort", cohorts.format_cohort(result), cohort=result)
    answer = rag.ask(question, **rag_options)
    return Response("rag", rag.format_answer(answer), answer=answer)


def main(argv: list[str] | None = None) -> int:
    """CLI: ``python -m oncology_assistant.assistant "question"``."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("question")
    parser.add_argument("-k", type=int, default=6)
    parser.add_argument("--no-rewrite", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    print(ask(args.question, k=args.k, rewrite=not args.no_rewrite).text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
