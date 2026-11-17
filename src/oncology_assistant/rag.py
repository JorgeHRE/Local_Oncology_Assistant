"""Beta RAG: retrieve chunks from the local index, answer with a local LLM, check the citations.

Pipeline (all local, nothing leaves the machine):

1. ``retrieve``: the nearest chunks from ChromaDB (``index.query``). If the question names trials
   ("NCT01234567"), the search is restricted to those documents.
2. ``ask``: the chunks go to the LLM as numbered passages. The model answers in JSON with the
   numbers of the passages it used and a literal quote from each.
3. Every quote is checked against the text of the passage it points to: same characters, ignoring
   only whitespace (models often drop the stray space the source has before a period). Case,
   numbers and symbols must match, as in the ground truth. A quote that is not there is flagged as
   unverified: the answer is shown, but its citation is not trusted.

The LLM and the embedder are injected, so the pipeline is tested without a model. The default LLM
is Ollama's OpenAI-compatible endpoint (ADR-0004); the model is a placeholder until ADR-0005.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from oncology_assistant.chunking import STRATEGIES
from oncology_assistant.embedders import OLLAMA_URL, index_dir_for, ollama_embedder
from oncology_assistant.ground_truth import normalize
from oncology_assistant.hybrid import hybrid_query
from oncology_assistant.index import INDEX_DIR, Embedder, query

logger = logging.getLogger(__name__)

MODEL = os.environ.get("RAG_MODEL", "qwen3:8b")
# Embedding model of the retriever (Ollama). "default" = the ONNX MiniLM of index.py.
EMBEDDER = os.environ.get("RAG_EMBEDDER", "bge-m3")
SEED = 7
NOT_FOUND = "The retrieved passages do not contain the answer."

_TRIAL = re.compile(r"\bNCT\d{8}\b", re.IGNORECASE)

SYSTEM_PROMPT = (
    "You answer questions about gastric cancer clinical trials and articles using ONLY the "
    "numbered passages you are given. Rules: (1) Do not use outside knowledge. (2) Answer in 1-3 "
    "sentences with the exact values (thresholds, units, time windows) as written in the passages. "
    f"(3) If the passages do not contain the answer, set the answer to exactly: {NOT_FOUND!r} and "
    "cite nothing. (4) For each fact you state, cite the passage number and copy a short quote "
    "from that passage EXACTLY as written (same characters; do not paraphrase or translate). "
    "(5) If the question compares trials, say what each trial states; if the passages of one trial "
    "do not mention the topic, say so for that trial instead of refusing, and cite the trial that "
    "does mention it."
)

ANSWER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "citations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"passage": {"type": "integer"}, "quote": {"type": "string"}},
                "required": ["passage", "quote"],
            },
        },
    },
    "required": ["answer", "citations"],
}

Message = dict[str, str]
Llm = Callable[[list[Message]], str]


@dataclass
class Citation:
    """A quote the model says it took from a passage, and whether it is really there."""

    passage: int
    doc_id: str | None
    quote: str
    verified: bool


@dataclass
class Answer:
    """The model's answer, its citations and the passages it was given."""

    question: str
    answer: str
    citations: list[Citation] = field(default_factory=list)
    passages: list[dict[str, Any]] = field(default_factory=list)

    @property
    def grounded(self) -> bool:
        """True if there is at least one citation and all of them are literal."""
        return bool(self.citations) and all(c.verified for c in self.citations)


def trial_filter(question: str) -> dict[str, Any] | None:
    """Metadata filter for the trials named in the question (``ct:NCT…``), or None."""
    ids = sorted({f"ct:{m.upper()}" for m in _TRIAL.findall(question)})
    if not ids:
        return None
    return {"doc_id": ids[0]} if len(ids) == 1 else {"doc_id": {"$in": ids}}


def retrieve(
    question: str,
    k: int = 6,
    strategy: str = "structural",
    embedder: Embedder | None = None,
    path: Path | None = None,
    hybrid: bool = True,
    model: str = EMBEDDER,
) -> list[dict[str, Any]]:
    """The chunks closest to the question, restricted to the trials it names (if any).

    When the question names several trials, each one gets its own ``k`` nearest chunks, so a
    comparison always has evidence from every trial (a single search would let one trial crowd the
    others out). Results are ordered best first.
    """
    if strategy not in STRATEGIES:
        raise ValueError(f"unknown strategy {strategy!r}; use one of {STRATEGIES}")
    if embedder is None and path is None and model != "default":
        embedder, path = ollama_embedder(model), index_dir_for(model)
    path = path or INDEX_DIR
    search = hybrid_query if hybrid else query
    where = trial_filter(question)
    trials = where["doc_id"].get("$in") if where and isinstance(where["doc_id"], dict) else None
    if not trials:
        return search(strategy, question, k=k, where=where, path=path, embedder=embedder)
    hits: list[dict[str, Any]] = []
    for trial in trials:
        hits += search(
            strategy, question, k=k, where={"doc_id": trial}, path=path, embedder=embedder
        )
    return sorted(hits, key=lambda hit: hit["distance"])


def build_messages(question: str, passages: Sequence[dict[str, Any]]) -> list[Message]:
    """The chat messages: rules, numbered passages (with their source) and the question."""
    blocks = []
    for number, hit in enumerate(passages, start=1):
        meta = hit["metadata"]
        header = (
            f"[{number}] {meta['doc_id']} | {meta.get('section', '')} | {meta.get('title', '')}"
        )
        blocks.append(f"{header}\n{hit['text']}")
    context = "\n\n".join(blocks)
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Passages:\n\n{context}\n\nQuestion: {question}"},
    ]


def ollama_llm(model: str = MODEL, url: str = OLLAMA_URL, timeout: int = 300) -> Llm:
    """An ``Llm`` that calls Ollama's OpenAI-compatible endpoint with a JSON schema (ADR-0004)."""

    def call(messages: list[Message]) -> str:
        body = {
            "model": model,
            "messages": messages,
            "temperature": 0,
            "seed": SEED,
            "reasoning_effort": "none",
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "answer", "strict": True, "schema": ANSWER_SCHEMA},
            },
        }
        request = urllib.request.Request(
            f"{url}/v1/chat/completions",
            json.dumps(body).encode(),
            {"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read())["choices"][0]["message"]["content"]
        except urllib.error.URLError as error:
            raise RuntimeError(
                f"cannot reach the LLM at {url} ({error.reason}); start it with `make llm-up`"
            ) from error

    return call


def quote_in_passage(passage: str, quote: str) -> bool:
    """True if ``quote`` is in ``passage`` after removing Markdown escapes and all whitespace."""

    def squash(text: str) -> str:
        return "".join(normalize(text).split())

    needle = squash(quote)
    return len(needle) >= 10 and needle in squash(passage)


def parse_answer(raw: str, question: str, passages: Sequence[dict[str, Any]]) -> Answer:
    """Turn the model's JSON into an ``Answer``, verifying each quote against its passage."""
    try:
        data = json.loads(raw)
        answer = str(data["answer"]).strip()
        raw_citations = list(data.get("citations", []))
    except (ValueError, KeyError, TypeError):
        return Answer(question, raw.strip() or NOT_FOUND, [], list(passages))
    citations = []
    for item in raw_citations:
        try:
            number, quote = int(item["passage"]), str(item["quote"])
        except (KeyError, TypeError, ValueError):
            continue
        hit = passages[number - 1] if 1 <= number <= len(passages) else None
        doc_id = hit["metadata"]["doc_id"] if hit else None
        verified = bool(hit) and quote_in_passage(hit["text"], quote)
        citations.append(Citation(number, doc_id, quote, verified))
    return Answer(question, answer, citations, list(passages))


def ask(
    question: str,
    k: int = 6,
    strategy: str = "structural",
    llm: Llm | None = None,
    embedder: Embedder | None = None,
    path: Path | None = None,
    model: str = EMBEDDER,
) -> Answer:
    """Retrieve, generate and verify. The whole pipeline for one question."""
    passages = retrieve(question, k=k, strategy=strategy, embedder=embedder, path=path, model=model)
    if not passages:
        return Answer(question, NOT_FOUND)
    raw = (llm or ollama_llm())(build_messages(question, passages))
    return parse_answer(raw, question, passages)


def format_answer(result: Answer, show_passages: bool = False) -> str:
    """Plain-text rendering of an answer for the terminal."""
    lines = [result.answer, ""]
    if result.citations:
        lines.append("Sources:")
        for c in result.citations:
            mark = "ok " if c.verified else "NOT FOUND "
            lines.append(f'  [{c.passage}] {c.doc_id} ({mark}in the passage) "{c.quote}"')
        if not result.grounded:
            lines.append("  Warning: at least one quote is not literal; do not trust this answer.")
    elif result.answer != NOT_FOUND:
        lines.append("Warning: the answer has no citations; do not trust it.")
    if show_passages:
        lines += ["", "Retrieved passages:"]
        for n, hit in enumerate(result.passages, start=1):
            meta = hit["metadata"]
            lines.append(f"  [{n}] {hit['distance']:.3f} {hit['id']} [{meta.get('section')}]")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """CLI: ``python -m oncology_assistant.rag "question"``."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("question")
    parser.add_argument("-k", type=int, default=6, help="passages given to the model")
    parser.add_argument("--strategy", choices=STRATEGIES, default="structural")
    parser.add_argument("--passages", action="store_true", help="also list the retrieved passages")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    print(format_answer(ask(args.question, args.k, args.strategy), args.passages))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
