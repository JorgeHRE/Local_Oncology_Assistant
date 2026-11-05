"""Split the RAG corpus into chunks (ADR-0006).

Two strategies over the same documents, so retrieval can be compared on the ground truth:

* ``structural`` (B): one chunk per eligibility criterion for ClinicalTrials.gov records (nested
  bullets stay with their parent, and each chunk records whether it is an inclusion or an
  exclusion criterion), and one chunk per labelled section for PubMed abstracts.
* ``whole`` (C, baseline): one chunk per document.

Chunking never calls a model: it is deterministic, free and testable. Embedding happens in
``oncology_assistant.index``.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from oncology_assistant.corpus import load_manifest
from oncology_assistant.db import REPO_ROOT

logger = logging.getLogger(__name__)

STRATEGIES = ("structural", "whole")

# A section header is a short line that is not a bullet and starts with "Inclusion" or "Exclusion"
# ("Inclusion Criteria:", "Key Exclusion Criteria", "Exclusion criteria related to ...").
_HEADER = re.compile(r"^(?:key\s+)?(inclusion|exclusion)\b.{0,70}$", re.IGNORECASE)
# Top-level bullet: "* ", "- ", "• ", "12. ", "12) " or the full-width "12）".
_BULLET = re.compile(r"^(?:[*\-•]|\d+[.)）])\s*")
# ClinicalTrials.gov text is Markdown: punctuation can be escaped ("1\.", "18\~75", "\>").
_ESCAPED = re.compile(r"\\([.)(~>*_#\[\]-])")
# A labelled PubMed section: "METHODS: ...", "PATIENTS AND METHODS: ...".
_LABEL = re.compile(r"^([A-Z][A-Z /&-]{2,40}):\s*(.*)$")

MetadataValue = str | int | float | bool


@dataclass(frozen=True)
class Document:
    """A corpus document ready to be chunked."""

    doc_id: str
    source: str  # "clinicaltrials.gov" | "pubmed"
    identifier: str  # NCT id or PMID
    title: str
    role: str  # pivotal | candidate | distractor | reference
    record: dict[str, Any] = field(repr=False)


@dataclass(frozen=True)
class Chunk:
    """A retrievable piece of text and where it came from."""

    chunk_id: str
    doc_id: str
    text: str
    context: str  # short header (title, section) that is embedded together with the text
    metadata: dict[str, MetadataValue]

    @property
    def embedding_text(self) -> str:
        """Text sent to the embedding model: context plus the chunk itself."""
        return f"{self.context}\n{self.text}"


def _clean(lines: Iterable[str]) -> str:
    """Join stripped, non-empty lines with newlines."""
    return "\n".join(line.strip() for line in lines if line.strip())


MAX_CRITERION_CHARS = 1500
MAX_LEAD_CHARS = 300
_INLINE_ENUM = re.compile(r"\s(?=\d{1,2}\)\s)")


def _split_oversized(lines: list[tuple[int, str]]) -> list[str]:
    """Split a very long criterion at its sub-bullets, or at inline "1) ... 2) ..." numbering.

    Each part keeps the lead-in (first line) so it still reads on its own. Returns the criterion
    unchanged when there is nothing to split on.
    """
    lead, rest = lines[0][1], lines[1:]
    parts: list[list[str]] = []
    if (
        len(lead) <= MAX_LEAD_CHARS
    ):  # a short lead-in ("must meet the following:") is worth repeating
        for indent, line in rest:
            if indent > 0 and _BULLET.match(line):
                parts.append([_BULLET.sub("", line, count=1)])
            elif parts:
                parts[-1].append(line)
    if len(parts) >= 2:
        return [_clean([lead, *part]) for part in parts]
    whole = _clean(line for _, line in lines)
    inline = [piece.strip() for piece in _INLINE_ENUM.split(whole) if piece.strip()]
    return inline if len(inline) >= 3 else [whole]


def split_criteria(text: str) -> list[tuple[str, str]]:
    """Split an eligibility-criteria text into ``(section, criterion)`` pairs.

    ``section`` is ``inclusion``, ``exclusion`` or ``other`` (text before any header). A criterion
    starts at a top-level bullet (no indentation) and includes its indented sub-bullets and
    continuation lines, so "A, or B" alternatives stay together. Text under a header without
    bullets becomes a single criterion. A criterion longer than ``MAX_CRITERION_CHARS`` is split
    at its sub-bullets (see ``_split_oversized``).
    """
    text = _ESCAPED.sub(r"\1", text)
    items: list[tuple[str, list[tuple[int, str]]]] = []
    section = "other"
    current: list[tuple[int, str]] | None = None
    for raw in text.splitlines():
        if not raw.strip():
            continue
        indent = len(raw) - len(raw.lstrip())
        line = raw.strip()
        header = None if _BULLET.match(line) else _HEADER.match(line)
        if header and indent == 0:
            section = header.group(1).lower()
            current = None
        elif indent == 0 and _BULLET.match(line):
            current = [(0, _BULLET.sub("", line, count=1))]
            items.append((section, current))
        elif current is not None:
            current.append((indent, line))
        else:  # prose right after a header, before any bullet
            current = [(0, line)]
            items.append((section, current))
    out: list[tuple[str, str]] = []
    for sec, lines in items:
        whole = _clean(line for _, line in lines)
        pieces = _split_oversized(lines) if len(whole) > MAX_CRITERION_CHARS else [whole]
        out.extend((sec, piece) for piece in pieces if piece)
    return out


def split_abstract(text: str) -> list[tuple[str, str]]:
    """Split a PubMed abstract into ``(label, text)`` sections.

    Lines without a label continue the previous section; an abstract with no labels at all is a
    single ``abstract`` section.
    """
    sections: list[tuple[str, list[str]]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        match = _LABEL.match(line.strip())
        if match:
            sections.append((match.group(1).lower(), [match.group(2)]))
        elif sections:
            sections[-1][1].append(line)
        else:
            sections.append(("abstract", [line]))
    return [(label, _clean(lines)) for label, lines in sections if _clean(lines)]


def _base_metadata(doc: Document, strategy: str, section: str, position: int) -> dict[str, Any]:
    return {
        "doc_id": doc.doc_id,
        "source": doc.source,
        "identifier": doc.identifier,
        "title": doc.title,
        "role": doc.role,
        "strategy": strategy,
        "section": section,
        "position": position,
    }


def _criteria_text(doc: Document) -> str:
    return doc.record["protocolSection"]["eligibilityModule"].get("eligibilityCriteria", "")


def chunk_structural(doc: Document) -> list[Chunk]:
    """Strategy B: one chunk per criterion (ClinicalTrials.gov) or per abstract section (PubMed)."""
    if doc.source == "clinicaltrials.gov":
        pieces = split_criteria(_criteria_text(doc))
        context = "{title} ({id}) - {section} criterion"
    else:
        pieces = split_abstract(doc.record.get("abstract", ""))
        year = doc.record.get("year", "")
        context = "{title} (PMID {id}, " + str(year) + ") - {section}"
    chunks = []
    for position, (section, text) in enumerate(pieces):
        chunks.append(
            Chunk(
                chunk_id=f"{doc.doc_id}#{position:03d}",
                doc_id=doc.doc_id,
                text=text,
                context=context.format(title=doc.title, id=doc.identifier, section=section),
                metadata=_base_metadata(doc, "structural", section, position),
            )
        )
    return chunks


def chunk_whole(doc: Document) -> list[Chunk]:
    """Strategy C (baseline): the whole criteria text or abstract as a single chunk."""
    if doc.source == "clinicaltrials.gov":
        text, section = _criteria_text(doc).strip(), "criteria"
    else:
        text, section = doc.record.get("abstract", "").strip(), "abstract"
    if not text:
        return []
    return [
        Chunk(
            chunk_id=f"{doc.doc_id}#000",
            doc_id=doc.doc_id,
            text=text,
            context=f"{doc.title} ({doc.identifier})",
            metadata=_base_metadata(doc, "whole", section, 0),
        )
    ]


def chunk_document(doc: Document, strategy: str) -> list[Chunk]:
    """Chunk one document with the named strategy."""
    if strategy == "structural":
        return chunk_structural(doc)
    if strategy == "whole":
        return chunk_whole(doc)
    raise ValueError(f"unknown strategy {strategy!r}; use one of {STRATEGIES}")


def load_documents(manifest_path: Path | None = None) -> list[Document]:
    """Read every document listed in the corpus manifest that is present on disk.

    PubMed abstracts and guidelines live only in ``data/raw/corpus`` (copyright), so a clean clone
    has just the ClinicalTrials.gov records; missing files are skipped with a warning.
    """
    manifest = load_manifest(manifest_path) if manifest_path else load_manifest()
    docs: list[Document] = []
    for entry in manifest.values():
        if entry["source"] not in ("clinicaltrials.gov", "pubmed"):
            continue  # guidelines are not chunked yet
        path = REPO_ROOT / entry["local_path"]
        if not path.exists():
            logger.warning("missing %s (%s): skipped", entry["doc_id"], entry["local_path"])
            continue
        docs.append(
            Document(
                doc_id=entry["doc_id"],
                source=entry["source"],
                identifier=entry["identifier"],
                title=entry.get("title", ""),
                role=entry.get("role", ""),
                record=json.loads(path.read_text(encoding="utf-8")),
            )
        )
    return docs


def build_chunks(docs: Iterable[Document], strategy: str) -> list[Chunk]:
    """Chunk all documents; chunk ids are unique across the corpus."""
    chunks = [c for doc in docs for c in chunk_document(doc, strategy)]
    ids = [c.chunk_id for c in chunks]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate chunk ids")
    return chunks


def summarize(chunks: list[Chunk]) -> dict[str, Any]:
    """Counts and length statistics, to sanity-check a strategy without any model."""
    lengths = sorted(len(c.text) for c in chunks)
    return {
        "chunks": len(chunks),
        "documents": len({c.doc_id for c in chunks}),
        "by_source_section": dict(
            Counter(f"{c.metadata['source']}/{c.metadata['section']}" for c in chunks)
        ),
        "chars_min_median_p95_max": (
            (lengths[0], lengths[len(lengths) // 2], lengths[int(len(lengths) * 0.95)], lengths[-1])
            if lengths
            else None
        ),
    }


def main(argv: list[str] | None = None) -> int:
    """CLI: ``python -m oncology_assistant.chunking`` prints a summary of both strategies."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--strategy", choices=(*STRATEGIES, "both"), default="both")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    docs = load_documents()
    for strategy in STRATEGIES if args.strategy == "both" else (args.strategy,):
        logger.info("%s: %s", strategy, json.dumps(summarize(build_chunks(docs, strategy))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
