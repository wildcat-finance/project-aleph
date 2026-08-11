#!/usr/bin/env python3
"""Adversarial tests for product evaluation and promotion approval."""

from __future__ import annotations

import hashlib
import json
import pathlib
import shutil
import sys
import tempfile

import agent
from eval import product_eval
import live
import promotion
import release
import test_agent


FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if ok else 'FAIL'} {name}"
          + (f" — {detail}" if detail and not ok else ""))
    if not ok:
        FAILURES.append(name)


def sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(tmp: pathlib.Path) -> None:
    retriever, _, _ = test_agent.components(tmp)
    fixture_path = pathlib.Path("eval/live-fixture-v1.json").resolve()
    fixture = json.loads(fixture_path.read_text())
    client = live.GatewayClient(
        str(retriever.main.manifest_path),
        product_eval.FixtureTransport(fixture), token="fixture")
    # Stub vectors deliberately carry no relevance signal. Product evaluation
    # still exercises routing, support, citations, and live determinism; strict
    # topic isolation is covered with controlled adversarial evidence in
    # test_agent.py and runs by default with the production embedder.
    engine = agent.AnswerEngine(
        retriever, client,
        writer=agent.ExtractiveWriter(require_topic_match=False))
    labels = pathlib.Path("eval/labels.yaml").resolve()
    policy = {
        "route_accuracy": 1.0, "outcome_accuracy": 1.0,
        "citation_validity": 1.0, "claim_support": 1.0,
        "live_determinism": 1.0, "refusal_accuracy": 1.0,
        "minimum_retrieval_label_passes": 1,
        "maximum_known_gap_answers": 0,
    }

    print("\nE1 — all reviewed routes pass through the complete answer path")
    report = product_eval.evaluate(
        engine, retriever, "eval/golden-v1.yaml", str(labels), policy, fixture)
    check("all 143 questions are evaluated, not sampled",
          report["golden"]["total"] == 143)
    check("the eight declared corpus gaps abstain or route elsewhere",
          report["golden"]["known_gaps"] == 8
          and report["known_gap_answers"] == 0)
    check("mode and risk regression groups are both emitted",
          set(report["groups"]["by_mode"]) == {
              "corpus", "live", "corpus+live", "correct", "refuse",
              "refuse+point", "triage", "partial", "clarify", "easter_egg"}
          and set(report["groups"]["by_risk"]) == {"high", "medium", "low"})
    check("citations, exact claim support, live determinism and refusals gate",
          report["passed"], str(report["failures"][:5]))
    check("v2.5 isolation and unsupported-chain refusal are executable checks",
          all(report["version_isolation"].values())
          and report["unsupported_chain_refused"]
          and report["registry_discovery"]
          and report["governance_apr_correction"]
          and report["unsafe_content_refused"]
          and report["history_capability"]
          and report["missing_symbol_abstains"]
          and report["off_topic_refused"])

    print("\nE2 — evaluation records are content-addressed and immutable")
    record = {
        "evaluation_id": "", "created": "2026-08-10T00:00:00+00:00",
        "candidate_release_id": report["candidate_release_id"],
        "prerelease_release_id": report["prerelease_release_id"],
        "inputs": {
            "paths": {
                "manifest": str(retriever.main.manifest_path),
                "release": str(retriever.main.release_path),
                "prerelease": str(retriever.prerelease.release_path),
                "questions": str(pathlib.Path("eval/golden-v1.yaml").resolve()),
                "labels": str(labels), "live_fixture": str(fixture_path),
            },
            "manifest_sha256": sha(retriever.main.manifest_path),
            "release_sha256": sha(retriever.main.release_path),
            "prerelease_sha256": sha(retriever.prerelease.release_path),
            "questions_sha256": sha(pathlib.Path("eval/golden-v1.yaml")),
            "labels_sha256": sha(labels),
            "live_fixture_sha256": sha(fixture_path),
        },
        "tools": product_eval._tool_hashes(), "report": report,
    }
    published = product_eval.publish(str(tmp / "artifacts"), record)
    evaluation_path = (tmp / "artifacts" / "evaluations"
                       / published["evaluation_id"] / "evaluation.json")
    original = evaluation_path.read_bytes()
    repeated = product_eval.publish(str(tmp / "artifacts"), record)
    check("an identical evaluation reuses exactly the same bytes",
          repeated["evaluation_id"] == published["evaluation_id"]
          and evaluation_path.read_bytes() == original)
    damaged = json.loads(evaluation_path.read_text())
    damaged["report"]["passed"] = False
    evaluation_path.write_text(json.dumps(damaged, indent=2))
    refused = ""
    try:
        product_eval.publish(str(tmp / "artifacts"), record)
    except product_eval.ProductEvaluationError as error:
        refused = str(error)
    check("a modified immutable evaluation is never repaired in place",
          "modified artifact" in refused, refused)
    evaluation_path.write_bytes(original)

    print("\nE3 — approval binds the exact passing evaluation and all gates")
    # The retrieval fixture uses a separate artifact root. Publish the
    # evaluation beside that release so approval cannot traverse roots.
    release_root = retriever.main.release_path.parents[2]
    bound = product_eval.publish(str(release_root), record)
    bound_path = (release_root / "evaluations" / bound["evaluation_id"]
                  / "evaluation.json")
    approved = promotion.approve(
        str(retriever.main.release_path), str(bound_path), str(release_root))
    check("approval produces a new immutable, promotable release identity",
          approved["promotable"] is True
          and approved["release_id"] != report["candidate_release_id"]
          and approved["gates"]["eval_not_regressed"] is True
          and approved["evaluation"]["evaluation_id"] == bound["evaluation_id"])

    failed = json.loads(bound_path.read_text())
    failed["report"]["passed"] = False
    failed["evaluation_id"] = product_eval.compute_evaluation_id(failed)
    failed_dir = release_root / "evaluations" / failed["evaluation_id"]
    failed_dir.mkdir()
    failed_path = failed_dir / "evaluation.json"
    failed_path.write_text(json.dumps(failed, indent=2))
    refused = ""
    try:
        promotion.approve(str(retriever.main.release_path), str(failed_path),
                          str(release_root))
    except promotion.PromotionError as error:
        refused = str(error)
    check("a failed evaluation cannot set eval_not_regressed",
          "did not pass" in refused, refused)

    blocked_candidate = json.loads(retriever.main.release_path.read_text())
    blocked_candidate["release_id"] = ""
    blocked_candidate["gates"]["address_assertions_hold"] = None
    blocked_candidate["release_id"] = release.compute_release_id(blocked_candidate)
    blocked_dir = release_root / "releases" / blocked_candidate["release_id"]
    blocked_dir.mkdir()
    blocked_path = blocked_dir / "release.json"
    blocked_path.write_text(json.dumps(blocked_candidate, indent=2))
    blocked_evaluation = json.loads(bound_path.read_text())
    blocked_evaluation["candidate_release_id"] = blocked_candidate["release_id"]
    blocked_evaluation["report"]["candidate_release_id"] = blocked_candidate["release_id"]
    blocked_evaluation["inputs"]["release_sha256"] = sha(blocked_path)
    blocked_evaluation["evaluation_id"] = product_eval.compute_evaluation_id(
        blocked_evaluation)
    blocked_eval_dir = (release_root / "evaluations"
                        / blocked_evaluation["evaluation_id"])
    blocked_eval_dir.mkdir()
    blocked_eval_path = blocked_eval_dir / "evaluation.json"
    blocked_eval_path.write_text(json.dumps(blocked_evaluation, indent=2))
    refused = ""
    try:
        promotion.approve(str(blocked_path), str(blocked_eval_path),
                          str(release_root))
    except promotion.PromotionError as error:
        refused = str(error)
    check("a null address gate blocks approval despite a passing evaluation",
          "address_assertions_hold=None" in refused, refused)


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
    sys.exit(main())
