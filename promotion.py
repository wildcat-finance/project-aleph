#!/usr/bin/env python3
"""Bind a passing immutable evaluation to a release after every gate passes."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
from datetime import datetime, timezone

import release
from eval.product_eval import _policy, _tool_hashes, compute_evaluation_id
from retrieval import ReleaseArtifact, RetrievalError


class PromotionError(Exception):
    """A candidate cannot be approved for later activation."""


def _sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: pathlib.Path, kind: str) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise PromotionError(f"cannot load {kind} {path}: {error}")


def approve(release_path: str, evaluation_path: str,
            artifact_root: str | None = None) -> dict:
    candidate_path = pathlib.Path(release_path).resolve()
    evaluated_path = pathlib.Path(evaluation_path).resolve()
    candidate_root = candidate_path.parents[2]
    root = (pathlib.Path(artifact_root).resolve() if artifact_root else
            candidate_root)
    if root != candidate_root:
        raise PromotionError("output artifact root differs from candidate root")
    candidate = _load(candidate_path, "release")
    evaluation = _load(evaluated_path, "evaluation")

    if candidate_path.parent.name != candidate.get("release_id"):
        raise PromotionError("candidate directory does not match release_id")
    try:
        candidate_id = release.compute_release_id(candidate)
    except (KeyError, TypeError, ValueError) as error:
        raise PromotionError(f"candidate identity fields are invalid: {error}")
    if candidate_id != candidate.get("release_id"):
        raise PromotionError("candidate record does not match its release_id")
    if evaluated_path.parent.name != evaluation.get("evaluation_id"):
        raise PromotionError("evaluation directory does not match evaluation_id")
    if compute_evaluation_id(evaluation) != evaluation.get("evaluation_id"):
        raise PromotionError("evaluation record does not match its evaluation_id")
    if evaluation.get("candidate_release_id") != candidate_id:
        raise PromotionError("evaluation names a different candidate release")
    if evaluation.get("inputs", {}).get("release_sha256") != _sha256(candidate_path):
        raise PromotionError("evaluated candidate bytes differ from release input")
    if evaluation.get("inputs", {}).get("manifest_sha256") != candidate.get(
            "manifest", {}).get("sha256"):
        raise PromotionError("evaluation and candidate name different manifests")
    if evaluation.get("tools") != _tool_hashes():
        raise PromotionError(
            "evaluation tool hashes differ from the current promotion runtime")
    manifest_path = pathlib.Path(candidate.get("manifest", {}).get("path", ""))
    if not manifest_path.is_file() or _sha256(manifest_path) != candidate.get(
            "manifest", {}).get("sha256"):
        raise PromotionError("candidate manifest is absent or differs from its hash")
    try:
        ReleaseArtifact(str(candidate_path), str(manifest_path))
    except RetrievalError as error:
        raise PromotionError(f"candidate artifacts no longer verify: {error}")
    try:
        import yaml
        manifest = yaml.safe_load(manifest_path.read_bytes())
    except (ImportError, OSError, ValueError) as error:
        raise PromotionError(f"cannot load candidate manifest policy: {error}")
    manifest_gates = manifest.get("gates") or []
    expected_required = (list(manifest_gates) if isinstance(manifest_gates, list)
                         else list(manifest_gates.keys()))
    if candidate.get("required_gates") != expected_required:
        raise PromotionError("candidate required gates differ from manifest policy")
    report = evaluation.get("report") or {}
    if report.get("candidate_release_id") != candidate_id:
        raise PromotionError("evaluation report names a different candidate")
    if report.get("passed") is not True or not report.get("gates") \
            or not all(value is True for value in report["gates"].values()):
        raise PromotionError("product evaluation did not pass every blocking gate")
    if report.get("policy") != _policy(manifest_path):
        raise PromotionError("evaluation thresholds differ from manifest policy")
    canonical_inputs = {
        "questions_sha256": _sha256(pathlib.Path(__file__).parent
                                    / "eval/golden-v1.yaml"),
        "labels_sha256": _sha256(pathlib.Path(__file__).parent
                                 / "eval/labels.yaml"),
        "live_fixture_sha256": _sha256(pathlib.Path(__file__).parent
                                       / "eval/live-fixture-v1.json"),
    }
    for name, expected in canonical_inputs.items():
        if evaluation.get("inputs", {}).get(name) != expected:
            raise PromotionError(f"evaluation {name} is not the canonical input")
    input_paths = evaluation.get("inputs", {}).get("paths") or {}
    prerelease_path = pathlib.Path(input_paths.get("prerelease", "")).resolve()
    try:
        prerelease_path.relative_to(root)
    except ValueError:
        raise PromotionError("evaluated prerelease is outside the artifact root")
    if (not prerelease_path.is_file()
            or _sha256(prerelease_path) != evaluation["inputs"].get(
                "prerelease_sha256")):
        raise PromotionError("evaluated prerelease artifact is absent or changed")
    prerelease = _load(prerelease_path, "prerelease")
    if (prerelease.get("release_id") != evaluation.get("prerelease_release_id")
            or prerelease.get("release_id") != report.get(
                "prerelease_release_id")):
        raise PromotionError("evaluation names a different prerelease artifact")

    required = expected_required
    gates = dict(candidate.get("gates") or {})
    gates["eval_not_regressed"] = True
    failed = {name: gates.get(name) for name in required
              if gates.get(name) is not True}
    if failed:
        detail = ", ".join(f"{name}={value}" for name, value in failed.items())
        raise PromotionError(f"blocking release gates are not true: {detail}")

    try:
        evaluation_relative = evaluated_path.relative_to(root)
    except ValueError:
        raise PromotionError("evaluation is outside the release artifact root")
    record = {
        **candidate,
        "release_id": "",
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "parent_release_id": candidate_id,
        "gates": gates,
        "promotable": True,
        "evaluation": {
            "evaluation_id": evaluation["evaluation_id"],
            "path": str(evaluation_relative),
            "sha256": _sha256(evaluated_path),
            "passed": True,
        },
        "tools": {**candidate.get("tools", {}),
                  "promotion.py": _sha256(pathlib.Path(__file__))},
    }
    record["release_id"] = release.compute_release_id(record)
    return release._publish_release(root, record)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--release", required=True)
    parser.add_argument("--evaluation", required=True)
    parser.add_argument("--artifacts")
    args = parser.parse_args()
    try:
        record = approve(args.release, args.evaluation, args.artifacts)
    except (PromotionError, release.ReleaseError) as error:
        print(f"FATAL: {error}", file=sys.stderr)
        return 1
    print(f"approved   {record['release_id']}  promotable={record['promotable']}")
    print("activation remains a separate production operation")
    return 0


if __name__ == "__main__":
    sys.exit(main())
