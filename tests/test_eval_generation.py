"""Tests for the generation comparison with a fake LLM and fake passages (no model needed)."""

from __future__ import annotations

import json

from oncology_assistant import eval_generation as eg
from oncology_assistant.eval_retrieval import load_r_records
from oncology_assistant.rag import NOT_FOUND


def fixture():
    records = load_r_records(split="dev")[:2]
    passages = {}
    for record in records:
        quote = record.relevant[0].quote
        passages[record.id] = [
            {"id": "x#0", "text": quote, "metadata": {"doc_id": record.relevant[0].doc_id}}
        ]
    return records, passages


def test_a_grounded_answer_is_counted_as_json_ok_and_grounded():
    records, passages = fixture()

    def llm(messages):
        quote = messages[-1]["content"].split("Passages:\n\n[1] ")[1].split("\n", 1)[1][:40]
        return json.dumps({"answer": "a", "citations": [{"passage": 1, "quote": quote}]})

    report = eg.run_model("fake", records, passages, llm=llm)
    summary = report.summary()
    assert summary["n"] == 2 and summary["json_ok"] == 2
    assert summary["grounded"] == 2 and summary["refused"] == 0
    assert summary["answerable"] == 2 and summary["answered_grounded"] == 2


def test_a_refusal_with_the_evidence_present_is_counted_as_refused_but_answerable():
    records, passages = fixture()
    llm = lambda _m: json.dumps({"answer": NOT_FOUND, "citations": []})
    summary = eg.run_model("fake", records, passages, llm=llm).summary()
    assert summary["refused"] == 2 and summary["refused_but_answerable"] == 2
    assert summary["answered"] == 0 and summary["grounded"] == 0


def test_a_made_up_quote_is_answered_but_not_grounded():
    records, passages = fixture()
    llm = lambda _m: json.dumps(
        {"answer": "a", "citations": [{"passage": 1, "quote": "this text is invented"}]}
    )
    summary = eg.run_model("fake", records, passages, llm=llm).summary()
    assert summary["answered"] == 2 and summary["answered_grounded"] == 0


def test_invalid_json_and_server_errors_do_not_stop_the_comparison():
    records, passages = fixture()
    assert (
        eg.run_model("fake", records, passages, llm=lambda _m: "not json").summary()["json_ok"] == 0
    )

    def down(_messages):
        raise RuntimeError("no server")

    report = eg.run_model("fake", records, passages, llm=down)
    assert report.summary()["n"] == 2 and report.items[0].error == "no server"


def test_the_review_file_lists_every_question_and_model(tmp_path):
    records, passages = fixture()
    llm = lambda _m: json.dumps({"answer": "an answer", "citations": []})
    reports = [eg.run_model("model-a", records, passages, llm=llm)]
    out = tmp_path / "review.md"
    eg.write_review(out, reports, records)
    text = out.read_text(encoding="utf-8")
    assert all(r.id in text for r in records) and "model-a" in text
    assert "Respuesta de referencia" in text and "Correcta (sí / parcial / no)" in text
