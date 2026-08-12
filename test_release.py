#!/usr/bin/env python3
"""Adversarial tests for the canonical release builder."""

from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import sys
import tempfile

import release

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if ok else 'FAIL'} {name}"
          + (f" — {detail}" if detail and not ok else ""))
    if not ok:
        FAILURES.append(name)


def git(repo: pathlib.Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, capture_output=True,
                            text=True, check=True)
    return result.stdout.strip()


def make_fixture(tmp: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path]:
    repo = tmp / "source"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "test@example.invalid")
    git(repo, "config", "user.name", "Aleph test")
    (repo / "guide.md").write_text(
        "# Guide\n\nMarkets use a reserve ratio to determine available "
        "liquidity and withdrawal coverage.\n")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "fixture")
    commit = git(repo, "rev-parse", "HEAD")
    manifest = tmp / "manifest.yaml"
    manifest.write_text(
        "version: 1\n"
        "policy:\n  branches: never\n  rebuild: full\n"
        "  self_ingestion: forbidden\n"
        "embedding:\n  backend: stub\n  model: test\n  digest: ''\n"
        "  dimensions: 64\n  normalised: true\n  query_prefix: none\n"
        "gates:\n  - signature_verified\n  - corpus_diff_reviewed\n"
        "  - address_assertions_hold\n  - eval_not_regressed\n"
        "sources:\n  - id: docs\n    tier: B\n    repo: x/docs\n"
        f"    ref: {{kind: commit, commit: {commit}, require_signature: false}}\n"
        "    include: ['**/*.md']\n")
    (tmp / "evolution.yaml").write_text(
        "schema_version: 1\n"
        "evolution: 2\n"
        "contract: mixed-candidate-dispositions-v2\n"
        "reason: Fixture evolution identity.\n")
    return repo, manifest


def run(tmp: pathlib.Path) -> None:
    print("\nR1 — one command publishes a coherent immutable release")
    source, manifest = make_fixture(tmp)
    root = tmp / "artifacts"
    args = dict(manifest_path=str(manifest), artifact_root=str(root),
                workdir=str(tmp / "work"), local={"docs": str(source)})
    first = release.build_release(**args)
    release_path = root / "releases" / first["release_id"] / "release.json"
    check("the release names existing corpus and index artifacts",
          (root / first["corpus"]["path"]).is_dir()
          and (root / first["index"]["path"]).is_dir())
    check("the manifest embedding identity is enforced and recorded",
          first["embedding"]["backend"] == "stub"
          and first["embedding"]["dimensions"] == 64)
    check("the reviewed evolution contract is release identity",
          first["evolution"]["number"] == 2
          and first["evolution"]["contract"]
          == "mixed-candidate-dispositions-v2")
    check("unknown downstream gates keep the release non-promotable",
          first["promotable"] is False
          and first["gates"]["address_assertions_hold"] is None)
    original = release_path.read_bytes()
    second = release.build_release(**args)
    check("a repeat returns the same release without rewriting it",
          second["release_id"] == first["release_id"]
          and release_path.read_bytes() == original)

    mismatch = ""
    try:
        release.build_release(**{**args,
            "artifact_root": str(tmp / "wrong-runtime"),
            "embedder_spec": "stub:other"})
    except release.indexer.IndexError_ as error:
        mismatch = str(error)
    check("a runtime not named by the manifest cannot publish a release",
          "does not match manifest" in mismatch, mismatch[:160])

    print("\nR2 — corpus changes require an explicit, attributable review")
    previous = root / first["corpus"]["path"] / "chunks.jsonl"
    (source / "guide.md").write_text(
        "# Guide\n\nMarkets use a reserve ratio. This revision adds a "
        "specific delinquency explanation for lenders.\n")
    git(source, "add", ".")
    git(source, "commit", "-qm", "revise")
    commit = git(source, "rev-parse", "HEAD")
    text = manifest.read_text()
    old_commit = json.loads(json.dumps(first["sources"]))["docs"]["commit"]
    manifest.write_text(text.replace(old_commit, commit))
    changed_args = {**args, "against": str(previous)}
    pending = release.build_release(**changed_args)
    check("a changed corpus creates a pending, non-promotable release",
          pending["review"]["status"] == "pending"
          and pending["gates"]["corpus_diff_reviewed"] is False)
    approved = release.build_release(
        **changed_args, diff_reviewed_by="test-reviewer")
    check("review creates a distinct attributable release record",
          approved["release_id"] != pending["release_id"]
          and approved["review"]["reviewed_by"] == "test-reviewer"
          and approved["gates"]["corpus_diff_reviewed"] is True)


def main() -> int:
    temp = pathlib.Path(tempfile.mkdtemp())
    try:
        run(temp)
    finally:
        shutil.rmtree(temp, ignore_errors=True)
    print(f"\n{len(FAILURES)} failure(s)"
          + (": " + ", ".join(FAILURES) if FAILURES else ""))
    return len(FAILURES)


if __name__ == "__main__":
    sys.exit(main())
