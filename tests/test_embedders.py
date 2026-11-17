"""Tests for the Ollama embedder (the HTTP call is faked; no server needed)."""

from __future__ import annotations

import io
import json
import urllib.error

import pytest

from oncology_assistant import embedders


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_index_dir_has_one_folder_per_model():
    assert embedders.index_dir_for("bge-m3").name == "chroma_bge-m3"
    assert embedders.index_dir_for("qwen3-embedding:0.6b").name == "chroma_qwen3-embedding-0.6b"


def test_embedder_sends_texts_in_batches_and_keeps_the_order(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout):
        body = json.loads(request.data)
        calls.append(body["input"])
        return FakeResponse(
            json.dumps({"embeddings": [[float(len(t))] for t in body["input"]]}).encode()
        )

    monkeypatch.setattr(embedders.urllib.request, "urlopen", fake_urlopen)
    texts = ["a" * n for n in range(1, embedders.BATCH + 4)]
    vectors = embedders.ollama_embedder("bge-m3")(texts)
    assert [len(c) for c in calls] == [embedders.BATCH, 3]
    assert vectors == [[float(len(t))] for t in texts]


def test_unreachable_server_gives_a_clear_error(monkeypatch):
    def refuse(request, timeout):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(embedders.urllib.request, "urlopen", refuse)
    with pytest.raises(RuntimeError, match="make llm-up"):
        embedders.ollama_embedder("bge-m3")(["x"])
