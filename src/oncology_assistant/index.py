"""Build and query the local ChromaDB index of the RAG corpus (ADR-0006).

One collection per chunking strategy (``gastric_structural``, ``gastric_whole``), so the same
questions can be asked to both and compared with recall@k (ADR-0002).

The embedding model is injected: pass any callable that maps ``list[str]`` to a list of vectors.
When none is given, ChromaDB's default ONNX model (all-MiniLM-L6-v2) is used; it is downloaded
once on first use and then runs locally. The model choice is a separate decision (ADR pending).
Chunk text is embedded together with its context header (title and section), but the plain text
is what is stored and returned.
"""

from __future__ import annotations

import argparse
import logging
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import chromadb

from oncology_assistant.chunking import STRATEGIES, Chunk, Document, build_chunks, load_documents
from oncology_assistant.db import REPO_ROOT

logger = logging.getLogger(__name__)

INDEX_DIR = REPO_ROOT / "data" / "processed" / "chroma"  # gitignored
BATCH_SIZE = 128

Embedder = Callable[[list[str]], Sequence[Sequence[float]]]


def collection_name(strategy: str) -> str:
    """Name of the collection that holds a strategy's chunks."""
    if strategy not in STRATEGIES:
        raise ValueError(f"unknown strategy {strategy!r}; use one of {STRATEGIES}")
    return f"gastric_{strategy}"


def default_embedder() -> Embedder:
    """ChromaDB's default local ONNX embedder (downloads the model once)."""
    from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

    logger.info("using the default embedder (all-MiniLM-L6-v2, ONNX); first use downloads it")
    return DefaultEmbeddingFunction()


def _embed(embedder: Embedder, texts: list[str]) -> list[list[float]]:
    return [[float(x) for x in vector] for vector in embedder(texts)]


def build_index(
    strategy: str,
    docs: Sequence[Document] | None = None,
    path: Path = INDEX_DIR,
    embedder: Embedder | None = None,
) -> int:
    """Rebuild the collection of ``strategy`` from scratch and return the number of chunks.

    Rebuilding (rather than updating) keeps the index a pure function of the corpus and the
    chunking code, which is what makes retrieval results reproducible.
    """
    embedder = embedder or default_embedder()
    chunks = build_chunks(docs if docs is not None else load_documents(), strategy)
    client = chromadb.PersistentClient(path=str(path))
    name = collection_name(strategy)
    if name in {c.name for c in client.list_collections()}:
        client.delete_collection(name)
    collection = client.create_collection(
        name, embedding_function=None, metadata={"hnsw:space": "cosine", "strategy": strategy}
    )
    for start in range(0, len(chunks), BATCH_SIZE):
        batch: list[Chunk] = chunks[start : start + BATCH_SIZE]
        collection.add(
            ids=[c.chunk_id for c in batch],
            documents=[c.text for c in batch],
            metadatas=[c.metadata for c in batch],
            embeddings=_embed(embedder, [c.embedding_text for c in batch]),
        )
    logger.info("%s: %d chunks indexed in %s", name, len(chunks), path)
    return len(chunks)


def query(
    strategy: str,
    text: str,
    k: int = 5,
    where: dict[str, Any] | None = None,
    path: Path = INDEX_DIR,
    embedder: Embedder | None = None,
) -> list[dict[str, Any]]:
    """Return the ``k`` nearest chunks as dicts (id, text, metadata, distance), best first.

    ``where`` filters on metadata, e.g. ``{"section": "exclusion"}`` or
    ``{"role": {"$ne": "distractor"}}``.
    """
    embedder = embedder or default_embedder()
    client = chromadb.PersistentClient(path=str(path))
    collection = client.get_collection(collection_name(strategy), embedding_function=None)
    result = collection.query(query_embeddings=_embed(embedder, [text]), n_results=k, where=where)
    return [
        {"id": id_, "text": doc, "metadata": meta, "distance": dist}
        for id_, doc, meta, dist in zip(
            result["ids"][0],
            result["documents"][0],
            result["metadatas"][0],
            result["distances"][0],
            strict=True,
        )
    ]


def main(argv: list[str] | None = None) -> int:
    """CLI: ``build`` the indexes or ``query`` one of them."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", help="rebuild one or both collections")
    build.add_argument("--strategy", choices=(*STRATEGIES, "both"), default="both")
    ask = sub.add_parser("query", help="show the nearest chunks for a question")
    ask.add_argument("text")
    ask.add_argument("--strategy", choices=STRATEGIES, default="structural")
    ask.add_argument("-k", type=int, default=5)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if args.command == "build":
        embedder = default_embedder()
        docs = load_documents()
        for strategy in STRATEGIES if args.strategy == "both" else (args.strategy,):
            build_index(strategy, docs=docs, embedder=embedder)
        return 0
    for hit in query(args.strategy, args.text, k=args.k):
        meta = hit["metadata"]
        print(f"{hit['distance']:.3f} {hit['id']} [{meta['section']}/{meta['role']}]")
        print(f"      {hit['text'][:160]!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
