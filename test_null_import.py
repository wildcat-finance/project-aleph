#!/usr/bin/env python3
"""Adversarial tests for Project Null export import and disposition."""

from __future__ import annotations

import hashlib
import json
import pathlib
import shutil
import sys
import tempfile

import yaml

from eval import null_import


FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if ok else 'FAIL'} {name}"
          + (f" — {detail}" if detail and not ok else ""))
    if not ok:
        FAILURES.append(name)


def canonical(value) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False) + "\n").encode()


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def candidate(identifier: str, question: str,
              kind: str = "regression") -> dict:
    return {
        "candidate_id": f"candidate_{identifier}",
        "created_at": "2026-08-11T00:00:00Z",
        "evidence_targets": [],
        "expected_outcome": "answered",
        "kind": kind,
        "provenance": "synthetic",
        "question": question,
        "question_id": f"question_{identifier}",
        "rationale": "Reviewed fixture rationale.",
        "record_type": "export_candidate",
        "schema_version": 1,
    }


def export_fixture(root: pathlib.Path, *, with_corpus: bool = False):
    regressions = [
        candidate("1" * 20, "A new reviewed question?"),
        candidate("2" * 20, "A semantic duplicate?"),
        candidate("3" * 20, "A deferred capability?"),
    ]
    corpus = ([candidate("4" * 20, "An untrusted factual proposal?",
                         "corpus_proposal")]
              if with_corpus else [])
    regression_bytes = canonical(regressions)
    corpus_bytes = canonical(corpus)
    basis = {
        "schema_version": 1,
        "regression_sha256": sha(regression_bytes),
        "corpus_proposals_sha256": sha(corpus_bytes),
        "candidate_ids": sorted(
            item["candidate_id"] for item in regressions + corpus),
    }
    export_id = sha(canonical(basis))[:20]
    directory = root / export_id
    directory.mkdir()
    manifest = {
        "export_id": export_id,
        **basis,
        "counts": {"regression": 3, "corpus_proposals": len(corpus)},
    }
    (directory / "manifest.json").write_bytes(canonical(manifest))
    (directory / "regressions.json").write_bytes(regression_bytes)
    (directory / "corpus-proposals.json").write_bytes(corpus_bytes)
    return directory, export_id


def review_fixture(root: pathlib.Path, export_id: str):
    golden_path = root / "golden.yaml"
    golden = {"questions": [
        {
            "id": "z01", "question": "A new reviewed question?",
            "expected": "corpus", "null_export_id": export_id,
            "null_candidate_id": "candidate_" + "1" * 20,
        },
        {"id": "z00", "question": "Existing semantic coverage?",
         "expected": "refuse"},
    ]}
    golden_path.write_text(yaml.safe_dump(golden, sort_keys=False))
    dispositions_path = root / "dispositions.yaml"
    dispositions = {
        "meta": {"version": 1, "source_export_id": export_id},
        "dispositions": [
            {
                "candidate_id": "candidate_" + "1" * 20,
                "status": "accepted", "expected": "corpus",
                "golden_id": "z01", "rationale": "New reviewed coverage.",
            },
            {
                "candidate_id": "candidate_" + "2" * 20,
                "status": "duplicate", "expected": "refuse",
                "golden_id": "z00", "rationale": "Same reviewed boundary.",
            },
            {
                "candidate_id": "candidate_" + "3" * 20,
                "status": "deferred", "expected": "live",
                "issue": "https://github.com/wildcat-finance/project-aleph/issues/999",
                "rationale": "Needs a separately tracked capability.",
            },
        ],
    }
    dispositions_path.write_text(
        yaml.safe_dump(dispositions, sort_keys=False))
    return golden_path, dispositions_path


def refusal(callable_) -> str:
    try:
        callable_()
    except null_import.NullImportError as error:
        return str(error)
    return ""


def run(root: pathlib.Path) -> None:
    print("\nN1 — immutable Null artifacts are validated before disposition")
    directory, export_id = export_fixture(root / "valid")
    golden, dispositions = review_fixture(root / "review", export_id)
    report = null_import.disposition_report(
        str(directory), str(dispositions), str(golden))
    check("all candidates receive one explicit disposition",
          report["candidate_count"] == 3
          and report["counts"]["accepted"] == 1
          and report["counts"]["duplicate"] == 1
          and report["counts"]["deferred"] == 1
          and report["ready"] is True)

    damaged_root = root / "damaged"
    damaged = shutil.copytree(directory, damaged_root / export_id)
    (damaged / "regressions.json").write_bytes(
        (damaged / "regressions.json").read_bytes() + b" ")
    message = refusal(lambda: null_import.load_export(str(damaged)))
    check("a modified immutable candidate file is rejected",
          "hash does not match" in message, message)

    print("\nN2 — reviewed mappings are exact and corpus proposals stay separate")
    corpus_directory, _ = export_fixture(root / "corpus", with_corpus=True)
    message = refusal(lambda: null_import.load_export(str(corpus_directory)))
    check("the regression importer cannot admit factual proposals",
          "corpus proposals cannot enter" in message, message)

    missing = yaml.safe_load(dispositions.read_bytes())
    missing["dispositions"].pop()
    missing_path = root / "missing.yaml"
    missing_path.write_text(yaml.safe_dump(missing, sort_keys=False))
    message = refusal(lambda: null_import.disposition_report(
        str(directory), str(missing_path), str(golden)))
    check("an undispositioned candidate fails closed",
          "lack dispositions" in message, message)

    changed_golden = yaml.safe_load(golden.read_bytes())
    changed_golden["questions"][0]["question"] = "Reworded without review?"
    changed_path = root / "changed-golden.yaml"
    changed_path.write_text(yaml.safe_dump(changed_golden, sort_keys=False))
    message = refusal(lambda: null_import.disposition_report(
        str(directory), str(dispositions), str(changed_path)))
    check("accepted question text cannot drift from the Null artifact",
          "changed question text" in message, message)

    wrong_route = yaml.safe_load(dispositions.read_bytes())
    wrong_route["dispositions"][1]["expected"] = "corpus"
    wrong_route_path = root / "wrong-route.yaml"
    wrong_route_path.write_text(yaml.safe_dump(wrong_route, sort_keys=False))
    message = refusal(lambda: null_import.disposition_report(
        str(directory), str(wrong_route_path), str(golden)))
    check("duplicate coverage must name the reviewed Aleph route",
          "route differs" in message, message)


def main() -> int:
    root = pathlib.Path(tempfile.mkdtemp())
    try:
        (root / "valid").mkdir()
        (root / "review").mkdir()
        (root / "corpus").mkdir()
        run(root)
    finally:
        shutil.rmtree(root, ignore_errors=True)
    print(f"\n{len(FAILURES)} failure(s)"
          + (": " + ", ".join(FAILURES) if FAILURES else ""))
    return len(FAILURES)


if __name__ == "__main__":
    sys.exit(main())
