"""Tests for oncology_assistant.corpus. No network: parsers use small synthetic records."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from oncology_assistant import corpus

PUBMED_XML = b"""<?xml version="1.0"?>
<PubmedArticleSet><PubmedArticle>
  <MedlineCitation>
    <PMID Version="1">111</PMID>
    <DateRevised><Year>2025</Year><Month>01</Month><Day>02</Day></DateRevised>
    <Article>
      <Journal><JournalIssue><PubDate><Year>2024</Year></PubDate></JournalIssue><Title>J Test</Title></Journal>
      <ArticleTitle>A <i>synthetic</i> title</ArticleTitle>
      <Abstract>
        <AbstractText Label="BACKGROUND">Background text.</AbstractText>
        <AbstractText Label="METHODS">Methods with <sup>markup</sup>.</AbstractText>
      </Abstract>
      <PublicationTypeList><PublicationType>Journal Article</PublicationType></PublicationTypeList>
    </Article>
  </MedlineCitation>
  <PubmedData><ArticleIdList><ArticleId IdType="doi">10.1000/test</ArticleId></ArticleIdList></PubmedData>
</PubmedArticle>
<PubmedArticle>
  <MedlineCitation><PMID>222</PMID><Article><ArticleTitle>No abstract</ArticleTitle></Article></MedlineCitation>
</PubmedArticle></PubmedArticleSet>"""


@pytest.fixture
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the module at an empty temporary repo."""
    monkeypatch.setattr(corpus, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(corpus, "CORPUS_DIR", tmp_path / "data" / "raw" / "corpus")
    return tmp_path


def test_parse_pubmed_extracts_fields_and_flattens_markup() -> None:
    first, second = corpus.parse_pubmed(PUBMED_XML)
    assert first["pmid"] == "111"
    assert first["title"] == "A synthetic title"
    assert first["abstract"] == "BACKGROUND: Background text.\nMETHODS: Methods with markup."
    assert (first["journal"], first["year"], first["doi"]) == ("J Test", "2024", "10.1000/test")
    assert first["date_revised"] == "2025-01-02"
    assert first["publication_types"] == ["Journal Article"]
    assert second["pmid"] == "222" and second["abstract"] == ""


def test_parse_clinicaltrials_reads_title_version_and_eligibility() -> None:
    record = {
        "protocolSection": {
            "identificationModule": {"nctId": "NCT0", "briefTitle": "Title"},
            "statusModule": {"lastUpdatePostDateStruct": {"date": "2025-03-04"}},
            "eligibilityModule": {"eligibilityCriteria": "Inclusion: ECOG 0-1"},
        }
    }
    assert corpus.parse_clinicaltrials(record) == {
        "title": "Title",
        "source_version": "2025-03-04",
        "eligibility": "Inclusion: ECOG 0-1",
    }


def test_normalized_json_is_deterministic() -> None:
    assert corpus.normalized_json({"b": 1, "a": [2]}) == corpus.normalized_json({"a": [2], "b": 1})


def test_snapshot_keeps_only_the_fields_the_ground_truth_needs() -> None:
    record = {
        "protocolSection": {
            "identificationModule": {
                "nctId": "NCT0",
                "briefTitle": "T",
                "organization": {"fullName": "Org"},
            },
            "statusModule": {
                "overallStatus": "RECRUITING",
                "lastUpdatePostDateStruct": {"date": "2025-01-01"},
            },
            "descriptionModule": {"briefSummary": "Free prose written by the sponsor."},
            "conditionsModule": {"conditions": ["Gastric Cancer"], "keywords": ["k"]},
            "armsInterventionsModule": {"interventions": [{"name": "Drug"}]},
            "eligibilityModule": {"eligibilityCriteria": "x", "sex": "ALL"},
            "contactsLocationsModule": {"centralContacts": [{"name": "Someone"}]},
            "sponsorCollaboratorsModule": {"responsibleParty": {"investigatorFullName": "A B"}},
        },
        "resultsSection": {"big": "data"},
    }
    assert corpus.snapshot_clinicaltrials(record) == {
        "protocolSection": {
            "identificationModule": {"nctId": "NCT0", "briefTitle": "T"},
            "statusModule": {
                "overallStatus": "RECRUITING",
                "lastUpdatePostDateStruct": {"date": "2025-01-01"},
            },
            "conditionsModule": {"conditions": ["Gastric Cancer"]},
            "eligibilityModule": {"eligibilityCriteria": "x", "sex": "ALL"},
        }
    }


def test_verify_only_committed_skips_local_documents(sandbox: Path) -> None:
    missing = {"sha256": "0" * 64}
    manifest = {
        "pm:9": {**missing, "local_path": "data/raw/corpus/pubmed/9.json", "committed": False},
        "ct:NCT9": {**missing, "local_path": "corpus/clinicaltrials/NCT9.json", "committed": True},
    }
    assert len(corpus.verify(manifest)) == 2
    assert [p.split(":")[0] for p in corpus.verify(manifest, only_committed=True)] == ["ct"]


def test_verify_detects_missing_and_changed_files(sandbox: Path) -> None:
    folder = sandbox / "data" / "raw" / "corpus" / "pubmed"
    folder.mkdir(parents=True)
    ok, changed = folder / "1.json", folder / "2.json"
    ok.write_text("a")
    changed.write_text("b")
    manifest = {
        "pm:1": corpus._entry("pm:1", "pubmed", "1", ok),
        "pm:2": corpus._entry("pm:2", "pubmed", "2", changed),
        "pm:3": {"local_path": "data/raw/corpus/pubmed/3.json", "sha256": "0" * 64},
    }
    changed.write_text("b, but the record was updated")
    problems = corpus.verify(manifest)
    assert len(problems) == 2
    assert any("pm:2" in p and "differs" in p for p in problems)
    assert any("pm:3" in p and "missing" in p for p in problems)


def test_ingest_guidelines_requires_source_version_and_date(sandbox: Path) -> None:
    folder = sandbox / "data" / "raw" / "corpus" / "guidelines"
    folder.mkdir(parents=True)
    (folder / "with_meta.pdf").write_bytes(b"pdf")
    meta = {
        "title": "T",
        "publisher": "P",
        "version": "2022",
        "url": "u",
        "downloaded_on": "2026-10-14",
    }
    (folder / "with_meta.pdf.meta.json").write_text(json.dumps(meta))
    (folder / "no_meta.pdf").write_bytes(b"pdf")
    (folder / "incomplete.pdf").write_bytes(b"pdf")
    (folder / "incomplete.pdf.meta.json").write_text(json.dumps({"title": "T"}))
    manifest: dict = {}
    skipped = corpus.ingest_guidelines(manifest)
    assert skipped == ["incomplete.pdf", "no_meta.pdf"]
    entry = manifest["gl:with_meta.pdf"]
    assert (entry["source_version"], entry["retrieved_at"]) == ("2022", "2026-10-14")
    assert entry["sha256"] == corpus.sha256_bytes(b"pdf")


def test_prune_removes_documents_no_longer_selected(sandbox: Path) -> None:
    folder = sandbox / "data" / "raw" / "corpus" / "clinicaltrials"
    folder.mkdir(parents=True)
    keep, drop = folder / "NCT1.json", folder / "NCT2.json"
    keep.write_text("1")
    drop.write_text("2")
    manifest = {
        "ct:NCT1": corpus._entry("ct:NCT1", "clinicaltrials.gov", "NCT1", keep),
        "ct:NCT2": corpus._entry("ct:NCT2", "clinicaltrials.gov", "NCT2", drop),
    }
    selection = {"clinicaltrials": [{"id": "NCT1", "role": "candidate"}], "pubmed": []}
    assert corpus.prune(selection, manifest) == ["ct:NCT2"]
    assert set(manifest) == {"ct:NCT1"} and not drop.exists() and keep.exists()


# --- The committed selection and manifest -------------------------------------------------------


def test_selection_is_valid() -> None:
    selection = corpus.load_selection()
    ids = [t["id"] for t in selection["clinicaltrials"]]
    pmids = [p["pmid"] for p in selection["pubmed"]]
    assert len(ids) == len(set(ids)) and len(pmids) == len(set(pmids))
    roles = {t["role"] for t in selection["clinicaltrials"]}
    assert roles == {"pivotal", "candidate", "distractor"}
    pivotal = {t["id"] for t in selection["clinicaltrials"] if t["role"] == "pivotal"}
    assert pivotal == {"NCT03504397", "NCT03653507", "NCT02872116", "NCT01041404"}


def test_committed_manifest_covers_the_selection_with_full_provenance() -> None:
    selection = corpus.load_selection()
    manifest = corpus.load_manifest()
    wanted = {f"ct:{t['id']}" for t in selection["clinicaltrials"]}
    wanted |= {f"pm:{p['pmid']}" for p in selection["pubmed"]}
    assert wanted <= set(manifest), "run `make corpus` and commit corpus/manifest.json"
    for doc_id in wanted:
        entry = manifest[doc_id]
        # The data rules: every source declares source, version and download date.
        assert entry["source"] and entry["source_version"] and entry["retrieved_at"], doc_id
        assert len(entry["sha256"]) == 64, doc_id
        assert not entry["local_path"].startswith("/"), doc_id


def test_committed_clinicaltrials_snapshots_match_the_manifest() -> None:
    """CI can check these (the rest of the corpus is local): a hand edit or drift is caught."""
    manifest = corpus.load_manifest()
    assert corpus.verify(manifest, only_committed=True) == []
    committed = [e for e in manifest.values() if e["committed"]]
    assert bool(committed) == corpus.COMMIT_CT_SNAPSHOTS
    assert all(e["source"] == "clinicaltrials.gov" for e in committed)
    assert not any(e["local_path"].startswith("data/") for e in committed)
