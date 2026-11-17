"""Alternative embedding models served by the local Ollama, each with its own index.

The default embedder of ``index.py`` (all-MiniLM-L6-v2) is general-purpose and English-only. To
compare models fairly, every model gets its own ChromaDB directory (``data/processed/chroma_<model>``),
built from the same chunks, so the retrieval evaluation can be run on each (ADR pending).

CLI: ``python -m oncology_assistant.embedders build bge-m3``.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import urllib.error
import urllib.request
from pathlib import Path

from oncology_assistant.chunking import STRATEGIES, load_documents
from oncology_assistant.db import REPO_ROOT
from oncology_assistant.index import Embedder, build_index

logger = logging.getLogger(__name__)

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11500")
BATCH = 16


def index_dir_for(model: str) -> Path:
    """The ChromaDB directory of a model (``:`` is not kept in the folder name)."""
    return REPO_ROOT / "data" / "processed" / f"chroma_{model.replace(':', '-')}"


def ollama_embedder(model: str, url: str = OLLAMA_URL, timeout: int = 300) -> Embedder:
    """An ``Embedder`` that calls Ollama's ``/api/embed`` in batches."""

    def embed(texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), BATCH):
            body = json.dumps({"model": model, "input": texts[start : start + BATCH]}).encode()
            request = urllib.request.Request(
                f"{url}/api/embed", body, {"Content-Type": "application/json"}
            )
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    vectors += json.loads(response.read())["embeddings"]
            except urllib.error.URLError as error:
                raise RuntimeError(
                    f"cannot reach Ollama at {url} ({error.reason}); start it with `make llm-up`"
                ) from error
        return vectors

    return embed


def main(argv: list[str] | None = None) -> int:
    """CLI: build the indexes of one model."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", help="embed the chunks with an Ollama model")
    build.add_argument("model")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    embedder = ollama_embedder(args.model)
    docs = load_documents()
    for strategy in STRATEGIES:
        build_index(strategy, docs=docs, path=index_dir_for(args.model), embedder=embedder)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
