#!/usr/bin/env python3
"""Validate and disposition a Project Null regression export."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import sys
from collections import Counter


class NullImportError(RuntimeError):
    """The Null export or its reviewed dispositions are not coherent."""


_MANIFEST_KEYS = {
    "candidate_ids", "corpus_proposals_sha256", "counts", "export_id",
    "regression_sha256", "schema_version",
}
_CANDIDATE_KEYS = {
    "candidate_id", "created_at", "evidence_targets", "expected_outcome",
    "kind", "provenance", "question", "question_id", "rationale",
    "record_type", "schema_version",
}
_NULL_OUTCOMES = {"answered", "pointed", "refused", "abstained", "failed"}
_ALEPH_ROUTES = {
    "clarify", "corpus", "corpus+live", "correct", "easter_egg", "live",
    "partial", "refuse", "refuse+point", "triage",
}
_STATUSES = {"accepted", "deferred", "duplicate", "needs_review", "rejected"}
_IDENTIFIER = re.compile(r"[a-z]+_[0-9a-f]{20}")
_EXPORT_ID = re.compile(r"[0-9a-f]{20}")


def _canonical(value) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False) + "\n").encode()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json(path: pathlib.Path):
    try:
        return json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as error:
        raise NullImportError(f"cannot read {path.name}: {error}") from error


def _yaml(path: pathlib.Path):
    try:
        import yaml
    except ImportError as error:
        raise NullImportError("null_import.py needs pyyaml") from error
    try:
        return yaml.safe_load(path.read_bytes())
    except (OSError, ValueError) as error:
        raise NullImportError(f"cannot read {path}: {error}") from error


def _expect_keys(value: dict, expected: set[str], label: str) -> None:
    if not isinstance(value, dict) or set(value) != expected:
        actual = sorted(value) if isinstance(value, dict) else type(value).__name__
        raise NullImportError(
            f"{label} fields differ: expected {sorted(expected)}, got {actual}")


def _validate_candidate(item: dict, kind: str) -> None:
    _expect_keys(item, _CANDIDATE_KEYS, "candidate")
    if item["schema_version"] != 1 or item["record_type"] != "export_candidate":
        raise NullImportError("candidate schema or record type is unsupported")
    if item["kind"] != kind:
        raise NullImportError(
            f"candidate {item.get('candidate_id')} is in the wrong queue")
    if not _IDENTIFIER.fullmatch(item["candidate_id"] or ""):
        raise NullImportError("candidate_id is malformed")
    if not _IDENTIFIER.fullmatch(item["question_id"] or ""):
        raise NullImportError("question_id is malformed")
    if item["expected_outcome"] not in _NULL_OUTCOMES:
        raise NullImportError("candidate expected_outcome is unsupported")
    if not isinstance(item["question"], str) or not item["question"].strip():
        raise NullImportError("candidate question is empty")
    if not isinstance(item["rationale"], str) or not item["rationale"].strip():
        raise NullImportError("candidate rationale is empty")
    if not isinstance(item["evidence_targets"], list):
        raise NullImportError("candidate evidence_targets must be a list")


def load_export(export_dir: str) -> tuple[dict, list[dict]]:
    root = pathlib.Path(export_dir).resolve()
    manifest_path = root / "manifest.json"
    regression_path = root / "regressions.json"
    corpus_path = root / "corpus-proposals.json"
    manifest = _json(manifest_path)
    try:
        regression_bytes = regression_path.read_bytes()
        corpus_bytes = corpus_path.read_bytes()
    except OSError as error:
        raise NullImportError(f"cannot read Null export: {error}") from error
    regression = _json(regression_path)
    corpus = _json(corpus_path)

    _expect_keys(manifest, _MANIFEST_KEYS, "manifest")
    if manifest["schema_version"] != 1:
        raise NullImportError("Null export schema_version must be 1")
    if not _EXPORT_ID.fullmatch(manifest["export_id"] or ""):
        raise NullImportError("manifest export_id is malformed")
    if root.name != manifest["export_id"]:
        raise NullImportError("export directory name does not match export_id")
    if _sha256(regression_bytes) != manifest["regression_sha256"]:
        raise NullImportError("regressions.json hash does not match manifest")
    if _sha256(corpus_bytes) != manifest["corpus_proposals_sha256"]:
        raise NullImportError("corpus-proposals.json hash does not match manifest")
    if regression_bytes != _canonical(regression):
        raise NullImportError("regressions.json is not canonical Null JSON")
    if corpus_bytes != _canonical(corpus):
        raise NullImportError("corpus-proposals.json is not canonical Null JSON")
    if not isinstance(regression, list) or not isinstance(corpus, list):
        raise NullImportError("Null candidate files must contain lists")
    if corpus:
        raise NullImportError(
            "corpus proposals cannot enter through the regression importer")
    if manifest["counts"] != {
            "regression": len(regression), "corpus_proposals": len(corpus)}:
        raise NullImportError("manifest candidate counts do not match files")

    for item in regression:
        _validate_candidate(item, "regression")
    candidate_ids = [item["candidate_id"] for item in regression]
    if candidate_ids != sorted(candidate_ids) or len(set(candidate_ids)) != len(candidate_ids):
        raise NullImportError("regression candidates are not uniquely sorted")
    if manifest["candidate_ids"] != candidate_ids:
        raise NullImportError("manifest candidate_ids do not match regression file")
    basis = {
        "schema_version": 1,
        "regression_sha256": manifest["regression_sha256"],
        "corpus_proposals_sha256": manifest["corpus_proposals_sha256"],
        "candidate_ids": candidate_ids,
    }
    computed_export_id = _sha256(_canonical(basis))[:20]
    if computed_export_id != manifest["export_id"]:
        raise NullImportError("export_id is not derived from the manifest inputs")
    return manifest, regression


def _golden_questions(path: str) -> dict[str, dict]:
    document = _yaml(pathlib.Path(path).resolve())
    questions = document.get("questions") if isinstance(document, dict) else None
    if not isinstance(questions, list):
        raise NullImportError("golden file has no question list")
    indexed = {}
    for item in questions:
        identifier = item.get("id") if isinstance(item, dict) else None
        if not identifier or identifier in indexed:
            raise NullImportError("golden question IDs are missing or duplicated")
        indexed[identifier] = item
    return indexed


def disposition_report(export_dir: str, dispositions_path: str,
                       golden_path: str) -> dict:
    manifest, candidates = load_export(export_dir)
    document = _yaml(pathlib.Path(dispositions_path).resolve())
    if not isinstance(document, dict) or set(document) != {"meta", "dispositions"}:
        raise NullImportError("disposition file must contain meta and dispositions")
    meta = document["meta"]
    if not isinstance(meta, dict):
        raise NullImportError("disposition meta must be a mapping")
    version = meta.get("version")
    if version == 1:
        _expect_keys(meta, {"source_export_id", "version"},
                     "disposition meta")
        predecessor_export_ids = []
    elif version == 2:
        _expect_keys(
            meta,
            {"predecessor_export_ids", "source_export_id", "version"},
            "disposition meta")
        predecessor_export_ids = meta["predecessor_export_ids"]
        if (not isinstance(predecessor_export_ids, list)
                or any(not isinstance(value, str)
                       or not _EXPORT_ID.fullmatch(value)
                       for value in predecessor_export_ids)
                or len(set(predecessor_export_ids))
                != len(predecessor_export_ids)
                or meta["source_export_id"] in predecessor_export_ids):
            raise NullImportError(
                "predecessor export IDs must be unique prior export IDs")
    else:
        raise NullImportError("disposition meta version is unsupported")
    if meta["source_export_id"] != manifest["export_id"]:
        raise NullImportError("disposition file targets a different export")
    accepted_provenance = {
        manifest["export_id"], *predecessor_export_ids}
    dispositions = document["dispositions"]
    if not isinstance(dispositions, list):
        raise NullImportError("dispositions must be a list")
    indexed_candidates = {item["candidate_id"]: item for item in candidates}
    indexed_golden = _golden_questions(golden_path)
    seen = set()
    cases = []
    for item in dispositions:
        if not isinstance(item, dict):
            raise NullImportError("each disposition must be a mapping")
        required = {"candidate_id", "expected", "rationale", "status"}
        optional = {"golden_id", "issue"}
        if not required <= set(item) or set(item) - required - optional:
            raise NullImportError("disposition fields are incomplete or unknown")
        candidate_id = item["candidate_id"]
        if not isinstance(candidate_id, str):
            raise NullImportError("disposition candidate_id must be a string")
        if candidate_id in seen:
            raise NullImportError(f"duplicate disposition for {candidate_id}")
        seen.add(candidate_id)
        candidate = indexed_candidates.get(candidate_id)
        if candidate is None:
            raise NullImportError(f"disposition names unknown candidate {candidate_id}")
        if not isinstance(item["status"], str) or item["status"] not in _STATUSES:
            raise NullImportError(f"unknown disposition status {item['status']}")
        if (not isinstance(item["expected"], str)
                or item["expected"] not in _ALEPH_ROUTES):
            raise NullImportError(f"unknown Aleph route {item['expected']}")
        if not isinstance(item["rationale"], str) or not item["rationale"].strip():
            raise NullImportError("every disposition needs a rationale")

        golden_id = item.get("golden_id")
        if item["status"] in {"accepted", "duplicate"}:
            golden = indexed_golden.get(golden_id)
            if golden is None:
                raise NullImportError(
                    f"{candidate_id} names unknown golden case {golden_id}")
            if golden.get("expected") != item["expected"]:
                raise NullImportError(
                    f"{candidate_id} route differs from golden case {golden_id}")
            if item["status"] == "accepted":
                if golden.get("question") != candidate["question"]:
                    raise NullImportError(
                        f"accepted candidate {candidate_id} changed question text")
                if (golden.get("null_export_id") not in accepted_provenance
                        or golden.get("null_candidate_id") != candidate_id):
                    raise NullImportError(
                        f"accepted candidate {candidate_id} lacks Null provenance")
        elif golden_id is not None:
            raise NullImportError(
                f"{item['status']} disposition cannot name a golden case")
        if item["status"] == "deferred" and not item.get("issue"):
            raise NullImportError("deferred dispositions require a tracking issue")
        cases.append({
            "candidate_id": candidate_id,
            "status": item["status"],
            "expected": item["expected"],
            "golden_id": golden_id,
            "question": candidate["question"],
            "issue": item.get("issue"),
        })
    missing = sorted(set(indexed_candidates) - seen)
    if missing:
        raise NullImportError(f"candidates lack dispositions: {missing}")
    counts = Counter(item["status"] for item in cases)
    return {
        "export_id": manifest["export_id"],
        "candidate_count": len(candidates),
        "counts": {status: counts.get(status, 0) for status in sorted(_STATUSES)},
        "ready": counts.get("needs_review", 0) == 0,
        "cases": cases,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--export", required=True,
                        help="immutable Project Null export directory")
    parser.add_argument("--dispositions", required=True)
    parser.add_argument("--golden", default="eval/golden-v1.yaml")
    parser.add_argument("--json", dest="json_path")
    args = parser.parse_args()
    try:
        report = disposition_report(
            args.export, args.dispositions, args.golden)
    except (NullImportError, OSError) as error:
        print(f"FATAL: {error}", file=sys.stderr)
        return 1
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.json_path:
        pathlib.Path(args.json_path).write_text(rendered)
    print(rendered, end="")
    return 0 if report["ready"] else 2


if __name__ == "__main__":
    sys.exit(main())
