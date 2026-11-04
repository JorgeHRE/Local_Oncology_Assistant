"""Build and verify the document corpus for the RAG (see docs/corpus.md).

ClinicalTrials.gov records are stored as a trimmed snapshot in ``corpus/clinicaltrials/`` and
committed: the eligibility criteria must not change under the ground truth. PubMed abstracts and
guidelines may be copyrighted, so they stay in ``data/raw/corpus/`` (ignored by git). Always
versioned: ``corpus/selection.json`` (what to fetch) and ``corpus/manifest.json`` (what was
fetched: source, version, download date and SHA-256 of every document), so a reader can tell
whether a local copy is the one the ground truth was annotated on.

Usage::

    python -m oncology_assistant.corpus fetch               # download what is missing
    python -m oncology_assistant.corpus ingest-guidelines   # register guideline files you added
    python -m oncology_assistant.corpus verify              # compare local files with the manifest
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from oncology_assistant.db import REPO_ROOT

logger = logging.getLogger(__name__)

CORPUS_DIR = REPO_ROOT / "data" / "raw" / "corpus"  # local only: PubMed, guidelines
# Whether the trimmed ClinicalTrials.gov snapshots are committed to git (corpus/clinicaltrials) or
# kept local with the rest (data/raw/corpus/clinicaltrials). Terms of use reviewed 2026-11-04
# (docs/corpus.md): redistribution is allowed with attribution. Set to False to stop versioning them,
# then `git rm -r corpus/clinicaltrials` and run `make corpus`.
COMMIT_CT_SNAPSHOTS = True
CT_DIR = (
    REPO_ROOT / "corpus" / "clinicaltrials"
    if COMMIT_CT_SNAPSHOTS
    else CORPUS_DIR / "clinicaltrials"
)
SELECTION_PATH = REPO_ROOT / "corpus" / "selection.json"
MANIFEST_PATH = REPO_ROOT / "corpus" / "manifest.json"

CT_URL = "https://clinicaltrials.gov/api/v2/studies/{nct}"
PUBMED_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
CT_DELAY_S = 1.0  # the ClinicalTrials.gov API allows roughly 50 requests/minute per IP
USER_AGENT = "oncology-assistant-corpus/0.1 (+https://github.com/JorgeHRE/Local_Oncology_Assistant)"
PUBMED_BATCH = 20
PUBMED_DELAY_S = 0.4  # NCBI allows 3 requests/second without an API key
GUIDELINE_SUFFIXES = {".pdf", ".txt", ".md", ".html"}
ROLES = {"pivotal", "candidate", "distractor"}

# Fields of a ClinicalTrials.gov record that are kept: what the ground truth needs (which trial,
# when it was last updated, condition, and the eligibility criteria) and nothing else. Free-text
# descriptions, arms and interventions, results, contacts, sites and the sponsor/investigator are
# dropped: they are most of the size, the most likely to carry the sponsor's authorship, and the
# parts that name people.
CT_KEPT_FIELDS: dict[str, tuple[str, ...]] = {
    "identificationModule": ("nctId", "briefTitle"),
    "statusModule": ("overallStatus", "startDateStruct", "lastUpdatePostDateStruct"),
    "conditionsModule": ("conditions",),
    "eligibilityModule": (
        "eligibilityCriteria",
        "healthyVolunteers",
        "sex",
        "minimumAge",
        "maximumAge",
        "stdAges",
    ),
}

LICENSE_NOTES = {
    "clinicaltrials.gov": (
        "Trimmed snapshot of a ClinicalTrials.gov record (title, status, condition and eligibility "
        "criteria only), committed so the annotated criteria do not change. Submitted by the "
        "sponsor: redistribution allowed with attribution, retrieval date and a statement of the "
        "modifications (docs/corpus.md)."
    ),
    "pubmed": "Abstract metadata from PubMed; the abstract may be copyrighted by the publisher: local use only.",
    "guideline": "Copyright of the publisher: local use only, never committed.",
}


def sha256_bytes(data: bytes) -> str:
    """Hex SHA-256 of ``data``."""
    return hashlib.sha256(data).hexdigest()


def now_utc() -> str:
    """Current UTC time in ISO format, to the second."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def pubmed_params(ids: list[str]) -> dict[str, str]:
    """E-utilities query; ``email`` is sent only if NCBI_EMAIL is set (never hard-coded)."""
    params = {
        "db": "pubmed",
        "id": ",".join(ids),
        "retmode": "xml",
        "tool": "oncology-assistant-corpus",
    }
    if email := os.environ.get("NCBI_EMAIL"):
        params["email"] = email
    return params


def http_get(url: str, params: dict[str, str] | None = None, retries: int = 3) -> bytes:
    """GET with a User-Agent and a few retries; raises after the last failure."""
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read()
        except OSError as exc:  # URLError and timeouts are OSError subclasses
            logger.warning("GET %s failed (attempt %d/%d): %s", url, attempt, retries, exc)
            if attempt == retries:
                raise
            time.sleep(2 * attempt)
    raise AssertionError("unreachable")


def normalized_json(obj: Any) -> bytes:
    """Deterministic JSON bytes, so the same content always has the same hash."""
    return (json.dumps(obj, indent=1, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def snapshot_clinicaltrials(record: dict[str, Any]) -> dict[str, Any]:
    """Trimmed record to store: only the fields in ``CT_KEPT_FIELDS``."""
    protocol = record["protocolSection"]
    kept: dict[str, Any] = {}
    for module, fields in CT_KEPT_FIELDS.items():
        source = protocol.get(module, {})
        picked = {f: source[f] for f in fields if f in source}
        if picked:
            kept[module] = picked
    return {"protocolSection": kept}


def parse_clinicaltrials(record: dict[str, Any]) -> dict[str, str]:
    """Title, last update date and eligibility text of a ClinicalTrials.gov API v2 record."""
    protocol = record["protocolSection"]
    ident = protocol["identificationModule"]
    status = protocol.get("statusModule", {})
    return {
        "title": ident.get("briefTitle", ""),
        "source_version": status.get("lastUpdatePostDateStruct", {}).get("date", ""),
        "eligibility": protocol.get("eligibilityModule", {}).get("eligibilityCriteria", ""),
    }


def _plain(node: ET.Element | None) -> str:
    """All the text under an XML node (inline markup included), stripped."""
    return "".join(node.itertext()).strip() if node is not None else ""


def _parse_article(node: ET.Element) -> dict[str, Any]:
    """One normalized dict from a ``PubmedArticle`` node."""
    abstract_parts = []
    for part in node.iter("AbstractText"):
        label = part.get("Label")
        body = _plain(part)
        abstract_parts.append(f"{label}: {body}" if label else body)
    doi = next((_plain(i) for i in node.iter("ArticleId") if i.get("IdType") == "doi"), "")
    revised = node.find("MedlineCitation/DateRevised")
    date_revised = (
        "-".join(revised.findtext(key, "") for key in ("Year", "Month", "Day"))
        if revised is not None
        else ""
    )
    return {
        "pmid": _plain(node.find("MedlineCitation/PMID")),
        "title": _plain(node.find("MedlineCitation/Article/ArticleTitle")),
        "abstract": "\n".join(abstract_parts),
        "journal": _plain(node.find("MedlineCitation/Article/Journal/Title")),
        "year": _plain(node.find("MedlineCitation/Article/Journal/JournalIssue/PubDate/Year")),
        "doi": doi,
        "date_revised": date_revised,
        "publication_types": sorted(_plain(p) for p in node.iter("PublicationType")),
    }


def parse_pubmed(xml_bytes: bytes) -> list[dict[str, Any]]:
    """Parse a PubMed efetch XML into one normalized dict per article."""
    return [_parse_article(node) for node in ET.fromstring(xml_bytes).iter("PubmedArticle")]


def load_selection(path: Path = SELECTION_PATH) -> dict[str, Any]:
    """Read and check the selection file."""
    selection = json.loads(path.read_text(encoding="utf-8"))
    for trial in selection["clinicaltrials"]:
        if trial["role"] not in ROLES:
            raise ValueError(f"unknown role {trial['role']!r} for {trial['id']}")
    return selection


def load_manifest(path: Path = MANIFEST_PATH) -> dict[str, dict[str, Any]]:
    """Manifest entries by ``doc_id`` (empty if there is no manifest yet)."""
    if not path.exists():
        return {}
    documents = json.loads(path.read_text(encoding="utf-8"))["documents"]
    for entry in documents:
        entry.setdefault(
            "committed", COMMIT_CT_SNAPSHOTS and entry["source"] == "clinicaltrials.gov"
        )
    return {entry["doc_id"]: entry for entry in documents}


def save_manifest(entries: dict[str, dict[str, Any]], path: Path = MANIFEST_PATH) -> None:
    """Write the manifest sorted by ``doc_id`` so diffs stay small."""
    body = {
        "description": "Documents of the RAG corpus: source, version, download date and SHA-256. "
        "Sources: ClinicalTrials.gov and PubMed, courtesy of the U.S. National Library of Medicine "
        "(NLM does not endorse this project). Copies are frozen at the retrieval date and may not "
        "reflect the current records. ClinicalTrials.gov snapshots are committed in "
        "corpus/clinicaltrials; PubMed and guidelines live in data/raw/corpus (not committed). "
        "See docs/corpus.md.",
        "documents": [entries[key] for key in sorted(entries)],
    }
    path.write_text(json.dumps(body, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def _entry(doc_id: str, source: str, identifier: str, path: Path, **fields: Any) -> dict[str, Any]:
    data = path.read_bytes()
    return {
        "doc_id": doc_id,
        "source": source,
        "identifier": identifier,
        "local_path": path.relative_to(REPO_ROOT).as_posix(),
        "sha256": sha256_bytes(data),
        "bytes": len(data),
        "license_note": LICENSE_NOTES[source],
        "committed": COMMIT_CT_SNAPSHOTS and source == "clinicaltrials.gov",
        **fields,
    }


def fetch_clinicaltrials(
    selection: dict[str, Any], manifest: dict[str, dict[str, Any]], refresh: bool = False
) -> None:
    """Download every selected ClinicalTrials.gov record that is not on disk yet."""
    folder = CT_DIR
    folder.mkdir(parents=True, exist_ok=True)
    for trial in selection["clinicaltrials"]:
        nct = trial["id"]
        path = folder / f"{nct}.json"
        doc_id = f"ct:{nct}"
        if path.exists() and doc_id in manifest and not refresh:
            continue
        logger.info("downloading %s", nct)
        record = json.loads(http_get(CT_URL.format(nct=nct)))
        snapshot = snapshot_clinicaltrials(record)
        path.write_bytes(normalized_json(snapshot))
        parsed = parse_clinicaltrials(snapshot)
        manifest[doc_id] = _entry(
            doc_id,
            "clinicaltrials.gov",
            nct,
            path,
            title=parsed["title"],
            url=f"https://clinicaltrials.gov/study/{nct}",
            role=trial["role"],
            note=trial.get("note", ""),
            source_version=parsed["source_version"],
            retrieved_at=now_utc(),
        )
        time.sleep(CT_DELAY_S)


def fetch_pubmed(
    selection: dict[str, Any], manifest: dict[str, dict[str, Any]], refresh: bool = False
) -> None:
    """Download the selected PubMed records in batches."""
    folder = CORPUS_DIR / "pubmed"
    folder.mkdir(parents=True, exist_ok=True)
    topics = {item["pmid"]: item["topic"] for item in selection["pubmed"]}
    todo = [
        pmid
        for pmid in topics
        if refresh or f"pm:{pmid}" not in manifest or not (folder / f"{pmid}.json").exists()
    ]
    for start in range(0, len(todo), PUBMED_BATCH):
        batch = todo[start : start + PUBMED_BATCH]
        logger.info("downloading %d PubMed records", len(batch))
        xml_bytes = http_get(PUBMED_URL, pubmed_params(batch))
        retrieved = now_utc()
        found = set()
        for article in parse_pubmed(xml_bytes):
            pmid = article["pmid"]
            found.add(pmid)
            path = folder / f"{pmid}.json"
            path.write_bytes(normalized_json(article))
            manifest[f"pm:{pmid}"] = _entry(
                f"pm:{pmid}",
                "pubmed",
                pmid,
                path,
                title=article["title"],
                url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                role="distractor" if topics[pmid] == "distractor" else "reference",
                note=topics[pmid],
                source_version=article["date_revised"],
                retrieved_at=retrieved,
            )
        missing = set(batch) - found
        if missing:
            logger.warning("PubMed returned no record for: %s", ", ".join(sorted(missing)))
        time.sleep(PUBMED_DELAY_S)


def prune(selection: dict[str, Any], manifest: dict[str, dict[str, Any]]) -> list[str]:
    """Drop manifest entries (and local files) of fetched documents no longer in the selection."""
    wanted = {f"ct:{t['id']}" for t in selection["clinicaltrials"]}
    wanted |= {f"pm:{p['pmid']}" for p in selection["pubmed"]}
    removed = []
    for doc_id in sorted(manifest):
        if doc_id.startswith(("ct:", "pm:")) and doc_id not in wanted:
            (REPO_ROOT / manifest[doc_id]["local_path"]).unlink(missing_ok=True)
            del manifest[doc_id]
            removed.append(doc_id)
            logger.info("removed %s (no longer in the selection)", doc_id)
    return removed


def ingest_guidelines(manifest: dict[str, dict[str, Any]]) -> list[str]:
    """Register guideline files placed by hand in data/raw/corpus/guidelines/.

    Each file needs a sidecar ``<name>.meta.json`` with ``title``, ``publisher``, ``version``,
    ``url`` and ``downloaded_on`` (the data rules require source, version and download date).
    Returns the names of files skipped for lacking a valid sidecar.
    """
    folder = CORPUS_DIR / "guidelines"
    folder.mkdir(parents=True, exist_ok=True)
    skipped = []
    needed = {"title", "publisher", "version", "url", "downloaded_on"}
    for path in sorted(folder.iterdir()):
        if path.suffix.lower() not in GUIDELINE_SUFFIXES:
            continue
        sidecar = path.with_name(path.name + ".meta.json")
        meta = json.loads(sidecar.read_text(encoding="utf-8")) if sidecar.exists() else {}
        if not needed <= meta.keys():
            logger.warning("%s: missing %s (need %s)", path.name, sidecar.name, sorted(needed))
            skipped.append(path.name)
            continue
        doc_id = f"gl:{path.name}"
        manifest[doc_id] = _entry(
            doc_id,
            "guideline",
            path.name,
            path,
            title=meta["title"],
            url=meta["url"],
            role="reference",
            note=meta["publisher"],
            source_version=meta["version"],
            retrieved_at=meta["downloaded_on"],
        )
    return skipped


def verify(manifest: dict[str, dict[str, Any]], only_committed: bool = False) -> list[str]:
    """Problems found comparing local files with the manifest (empty list = all good).

    With ``only_committed`` only the documents versioned in the repo are checked, which is what
    CI can do (the rest lives in ``data/raw/corpus`` on the author's machine).
    """
    problems = []
    for doc_id, entry in manifest.items():
        if only_committed and not entry.get("committed"):
            continue
        path = REPO_ROOT / entry["local_path"]
        if not path.exists():
            problems.append(f"{doc_id}: missing file {entry['local_path']}")
        elif sha256_bytes(path.read_bytes()) != entry["sha256"]:
            problems.append(f"{doc_id}: content differs from the manifest (record updated?)")
    return problems


def main(argv: list[str] | None = None) -> int:
    """Command line entry point."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("command", choices=["fetch", "ingest-guidelines", "verify", "summary"])
    parser.add_argument("--refresh", action="store_true", help="download again even if present")
    parser.add_argument(
        "--committed-only", action="store_true", help="verify: only the documents versioned in git"
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    manifest = load_manifest()
    if args.command == "fetch":
        selection = load_selection()
        prune(selection, manifest)
        fetch_clinicaltrials(selection, manifest, args.refresh)
        fetch_pubmed(selection, manifest, args.refresh)
        save_manifest(manifest)
    elif args.command == "ingest-guidelines":
        skipped = ingest_guidelines(manifest)
        save_manifest(manifest)
        if skipped:
            return 1
    elif args.command == "verify":
        problems = verify(manifest, only_committed=args.committed_only)
        for problem in problems:
            logger.error(problem)
        logger.info("%d documents checked, %d problem(s)", len(manifest), len(problems))
        return 1 if problems else 0
    counts: dict[str, int] = {}
    for entry in manifest.values():
        key = f"{entry['source']}/{entry['role']}"
        counts[key] = counts.get(key, 0) + 1
    logger.info("manifest: %d documents %s", len(manifest), dict(sorted(counts.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
