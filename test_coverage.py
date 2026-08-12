#!/usr/bin/env python3
"""Executable privacy and integrity gates for coverage silhouettes."""

from __future__ import annotations

import hashlib
import json
import pathlib
import shutil
import tempfile

import yaml

from eval import coverage


FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if ok else 'FAIL'} {name}"
          + (f" — {detail}" if detail and not ok else ""))
    if not ok:
        FAILURES.append(name)


def sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixture(root: pathlib.Path) -> dict[str, pathlib.Path]:
    artifacts = root / "artifacts"
    release_id = "11111111111111111111"
    build_id = "2222222222222222"
    evaluation_id = "33333333333333333333"
    manifest = root / "manifest.yaml"
    questions = root / "golden.yaml"
    topics = root / "topics.yaml"
    chunks = artifacts / "corpus" / build_id / "chunks.jsonl"
    evaluation_path = artifacts / "evaluations" / evaluation_id / "evaluation.json"
    release_path = artifacts / "releases" / release_id / "release.json"
    pointer_path = root / "active-release.json"
    for path in (chunks, evaluation_path, release_path):
        path.parent.mkdir(parents=True, exist_ok=True)

    manifest.write_text("version: 1\n")
    question_doc = {"questions": [
        {"id": "a01", "question": "How do withdrawals work?",
         "expected": "corpus", "frequency": "high"},
        {"id": "b01", "question": "What is this market doing now?",
         "expected": "live", "frequency": "medium"},
        {"id": "c01", "question": "Where is this missing procedure?",
         "expected": "corpus", "corpus_gap": "not documented"},
    ]}
    questions.write_text(yaml.safe_dump(question_doc, sort_keys=False))
    topics.write_text(yaml.safe_dump({
        "schema_version": 1,
        "topics": {"a": "withdrawals", "b": "live-markets", "c": "gaps"},
    }, sort_keys=False))
    chunk_records = [
        {"id": "protocol:docs/Withdrawals.md#cycles", "path": "docs/Withdrawals.md",
         "tier": "A", "source_type": "markdown", "corpus_build_id": build_id,
         "protocol_version": "v2.0", "deployment_status": "deployed",
         "display_text": "secret one", "model_text": "secret one",
         "embed_text": "secret one"},
        {"id": "protocol:src/market/WildcatMarket.sol:state",
         "path": "src/market/WildcatMarket.sol", "tier": "A",
         "source_type": "solidity", "corpus_build_id": build_id,
         "protocol_version": "v2.0", "deployment_status": "deployed",
         "display_text": "secret two", "model_text": "secret two",
         "embed_text": "secret two"},
        {"id": "docs:overview/faqs.md#index", "path": "overview/faqs.md",
         "tier": "B", "source_type": "markdown", "corpus_build_id": build_id,
         "display_text": "secret three", "model_text": "secret three",
         "embed_text": "secret three"},
    ]
    chunks.write_text("".join(
        json.dumps(item, sort_keys=True) + "\n" for item in chunk_records))
    evaluation = {
        "evaluation_id": evaluation_id,
        "inputs": {"questions_sha256": sha(questions),
                   "manifest_sha256": sha(manifest)},
        "report": {
            "passed": True, "golden": {"total": 3, "known_gaps": 1},
            "cases": [
                {"id": "a01", "risk": "high", "citation_ids": [
                    "protocol:docs/Withdrawals.md#cycles"], "live": None},
                {"id": "b01", "risk": "medium", "citation_ids": [],
                 "live": {"operation": "market"}},
                {"id": "c01", "risk": "low", "citation_ids": [], "live": None},
            ],
        },
    }
    evaluation_path.write_text(json.dumps(evaluation, sort_keys=True))
    release = {
        "release_id": release_id, "promotable": True,
        "evolution": {"number": 2,
                      "contract": "mixed-candidate-dispositions-v2",
                      "sha256": "a" * 64},
        "manifest": {"sha256": sha(manifest)},
        "corpus": {"build_id": build_id, "path": f"corpus/{build_id}",
                   "chunks_sha256": sha(chunks)},
        "evaluation": {"evaluation_id": evaluation_id,
                       "path": f"evaluations/{evaluation_id}/evaluation.json",
                       "sha256": sha(evaluation_path)},
    }
    release_path.write_text(json.dumps(release, sort_keys=True))
    pointer_path.write_text(json.dumps({
        "schema_version": 2, "release_id": release_id,
        "evolution": 2, "generation": 1,
    }, sort_keys=True))
    return {"artifacts": artifacts, "release": release_path,
            "manifest": manifest, "questions": questions, "topics": topics,
            "pointer": pointer_path}


def build(paths: dict[str, pathlib.Path],
          topics: pathlib.Path | None = None) -> dict:
    return coverage.build(
        paths["release"], paths["manifest"], paths["questions"],
        topics or paths["topics"], paths["pointer"])


def run(tmp: pathlib.Path) -> None:
    paths = fixture(tmp / "fixture")
    print("\nC1 — output is deterministic, reconciled and answer-free")
    first = build(paths)
    second = build(paths)
    serialized = json.dumps(first, sort_keys=True)
    golden = yaml.safe_load(paths["questions"].read_text())
    check("identical bound inputs produce one silhouette identity",
          first["silhouette_id"] == second["silhouette_id"])
    check("evaluated shapes and declared gaps reconcile",
          first["evaluation"]["total"] == 3
          and first["evaluation"]["known_gaps"] == 1)
    check("corpus topology is represented without content",
          first["corpus"]["total_chunks"] == 3
          and len(first["corpus"]["topics"]) == 3
          and "secret one" not in serialized)
    check("no golden question is copied into the silhouette",
          all(item["question"] not in serialized
              for item in golden["questions"]))
    check("the explicit boundary forbids grading and corpus writes",
          first["boundary"]["factual_grading"] == "forbidden"
          and first["boundary"]["autonomous_corpus_writes"] == "forbidden")

    print("\nC2 — publication is immutable and content-addressed")
    published_root = tmp / "published"
    out = coverage.publish(published_root, first)
    original = out.read_bytes()
    repeated = coverage.publish(published_root, second)
    check("an identical publish reuses identical bytes",
          repeated == out and out.read_bytes() == original)
    damaged = json.loads(out.read_text())
    damaged["evaluation"]["total"] = 1
    out.write_text(json.dumps(damaged))
    refused = ""
    try:
        coverage.publish(published_root, first)
    except coverage.CoverageError as error:
        refused = str(error)
    check("a modified immutable artifact is rejected",
          "modified immutable silhouette" in refused, refused)
    out.write_bytes(original)

    print("\nC3 — input binding and leakage checks fail closed")
    original_questions = paths["questions"].read_bytes()
    paths["questions"].write_bytes(original_questions + b"\n")
    refused = ""
    try:
        build(paths)
    except coverage.CoverageError as error:
        refused = str(error)
    check("a changed golden set is rejected before summarisation",
          "not bound" in refused, refused)
    paths["questions"].write_bytes(original_questions)

    leaking = json.loads(json.dumps(first))
    leaking["question"] = "raw material"
    refused = ""
    try:
        coverage.publish(tmp / "leak", leaking)
    except coverage.CoverageError as error:
        refused = str(error)
    check("forbidden content-bearing fields cannot be published",
          "forbidden keys" in refused, refused)

    topics_copy = tmp / "topics.yaml"
    topics_copy.write_text(paths["topics"].read_text().replace(
        "withdrawals", "withdrawal-boundaries"))
    changed = build(paths, topics_copy)
    check("curated topic-shape changes produce a new bound identity",
          changed["silhouette_id"] != first["silhouette_id"]
          and changed["binding"]["topic_map_sha256"]
          != first["binding"]["topic_map_sha256"])


def main() -> int:
    tmp = pathlib.Path(tempfile.mkdtemp())
    try:
        run(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{len(FAILURES)} failure(s)"
          + (": " + ", ".join(FAILURES) if FAILURES else ""))
    return len(FAILURES)


if __name__ == "__main__":
    raise SystemExit(main())
