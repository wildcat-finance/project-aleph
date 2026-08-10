#!/usr/bin/env python3
"""Adversarial tests for scoped retrieval and citation resolution."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import pathlib
import shutil
import sys
import tempfile

from embed import index as indexer
from eval import retrieval_eval
import retrieval
import release

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if ok else 'FAIL'} {name}"
          + (f" — {detail}" if detail and not ok else ""))
    if not ok:
        FAILURES.append(name)


def sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def row(source: str, name: str, text: str, *, tier: str = "A",
        version: str | None = "v2.0", path: str = "src/Market.sol",
        kind: str = "Function", line: int = 10, synthesised: bool = False,
        anchor: str | None = None) -> dict:
    detail = {"anchor": anchor} if anchor else {}
    return {
        "id": f"{source}:{path}:{name}", "kind": kind,
        "source_type": "markdown" if path.endswith(".md") else "solidity",
        "path": path, "line": line,
        "breadcrumb": f"{path} › {name}", "tier": tier,
        "synthesised": synthesised, "display_text": text,
        "model_text": text, "embed_text": f"{name} {text}",
        "corpus_build_id": "", "source_ref": "",
        "protocol_version": version,
        "deployment_status": "not_deployed" if version == "v2.5" else "deployed",
        "effective_date": "2025-01-16" if tier == "B" else None,
        "doc_version": "2025-01-16" if tier == "B" else None,
        "content_hash": hashlib.sha256(text.encode()).hexdigest(),
        "warnings": [], "detail": detail,
    }


def write_release(root: pathlib.Path, manifest: pathlib.Path,
                  build_id: str, rows: list[dict], kind: str) -> pathlib.Path:
    corpus = root / "corpus" / build_id
    corpus.mkdir(parents=True)
    for item in rows:
        item["corpus_build_id"] = build_id
        item["source_ref"] = f"fixture@{item['id'].split(':', 1)[0]}/{'a' * 40}"
    with open(corpus / "chunks.jsonl", "w") as handle:
        for item in rows:
            handle.write(json.dumps(item) + "\n")
    source_ids = {item["id"].split(":", 1)[0] for item in rows}
    build_record = {
        "build_id": build_id, "chunks": {"total": len(rows)},
        "gates": {"schema_valid": True}, "waivers": [],
        "sources": {source: {"commit": "a" * 40} for source in source_ids},
    }
    (corpus / "build.json").write_text(json.dumps(build_record, indent=2))
    index_root = root / "index" / kind
    index_record = indexer.build_index(
        str(corpus), str(index_root), "stub:test")
    index_dir = index_root / build_id
    release_record = {
        "release_id": "", "kind": kind,
        "manifest": {"path": str(manifest), "sha256": sha(manifest)},
        "corpus": {"build_id": build_id,
                   "path": str(corpus.relative_to(root)),
                   "chunks_sha256": sha(corpus / "chunks.jsonl"),
                   "record_sha256": sha(corpus / "build.json")},
        "index": {"namespace": kind,
                  "path": str(index_dir.relative_to(root)),
                  "record_sha256": sha(index_dir / "index.json"),
                  "artifacts": index_record["artifacts"]},
        "embedding": index_record["embedder"],
        "sources": build_record["sources"],
        "review": {"status": "not_applicable", "reviewed": True},
        "gates": {"corpus_diff_reviewed": True},
        "tools": {"release.py": "fixture-release-tool"},
    }
    release_record["release_id"] = release.compute_release_id(release_record)
    release_id = release_record["release_id"]
    release_dir = root / "releases" / release_id
    release_dir.mkdir(parents=True)
    path = release_dir / "release.json"
    path.write_text(json.dumps(release_record, indent=2))
    return path


def fixture(tmp: pathlib.Path):
    manifest = tmp / "manifest.yaml"
    manifest.write_text(
        "version: 1\npolicy:\n  scope:\n    chains: [1]\n"
        "embedding:\n  backend: stub\n  model: test\n  dimensions: 64\n"
        "  normalised: true\nsources:\n"
        "  - id: v2-protocol\n    tier: A\n    repo: wildcat/v2-protocol\n"
        "    protocol_version: v2.0\n    always_cite: [docs/Known Issues.md]\n"
        "  - id: wildcat-docs\n    tier: B\n    repo: wildcat/wildcat-docs\n"
        "  - id: v2-protocol-prerelease\n    tier: A\n"
        "    repo: wildcat/v2-protocol\n    index: separate\n"
        "    protocol_version: v2.5\n    deployment_status: not_deployed\n"
        "    audited: false\n    retrieval:\n"
        "      requires_explicit_version: true\n      preamble: mandatory\n")
    main_rows = [
        row("v2-protocol", "Market", "assembled market overview",
            kind="contract", synthesised=True),
        row("v2-protocol", "liquidityRequired()",
            "function liquidityRequired() returns the required liquidity"),
        row("v2-protocol", "exactIdentifier(uint256)",
            "function exactIdentifier(uint256 value) updates the value"),
        row("v2-protocol", "controller()",
            "The controller is 0x1111111111111111111111111111111111111111."),
        row("v2-protocol", "Known delinquency issue",
            "# Delinquency\n\nLenders can lose funds in a delinquent market.",
            path="docs/Known Issues.md", kind="section", anchor="delinquency"),
        row("wildcat-docs", "Withdrawal guide",
            "# Withdrawals\n\nWithdrawal batches become claimable after expiry.",
            tier="B", version=None, path="using-wildcat/withdrawals.md",
            kind="section", line=1, anchor="withdrawals"),
    ]
    prerelease_rows = [
        row("v2-protocol-prerelease", "newV25Feature()",
            "function newV25Feature() exists only in the prerelease",
            version="v2.5"),
    ]
    main = write_release(tmp / "artifacts", manifest,
                         "main-build", main_rows, "main")
    prerelease = write_release(tmp / "artifacts", manifest,
                               "v25-build", prerelease_rows, "prerelease")
    return manifest, main, prerelease


def run(tmp: pathlib.Path) -> None:
    manifest, main, prerelease = fixture(tmp)
    retriever = retrieval.Retriever(
        str(manifest), str(main), "stub:test", str(prerelease))

    print("\nT1 — scope is explicit and prerelease evidence cannot bleed")
    refused = ""
    try:
        retriever.search(retrieval.RetrievalRequest("markets", 8453))
    except retrieval.ScopeError as error:
        refused = str(error)
    check("a non-mainnet chain is refused before retrieval",
          "outside" in refused, refused)
    refused = ""
    try:
        retriever.search(retrieval.RetrievalRequest(
            "new feature", 1, protocol_version="v2.5"))
    except retrieval.ScopeError as error:
        refused = str(error)
    check("v2.5 requires an explicit user version request",
          "explicit" in refused, refused)
    general = retriever.search(retrieval.RetrievalRequest(
        "newV25Feature()", 1, tiers=("A",), limit_per_tier=20))
    check("a general request contains no prerelease chunks",
          all(item.protocol_version == "v2.0"
              for item in general.by_tier["A"]))
    v25 = retriever.search(retrieval.RetrievalRequest(
        "newV25Feature()", 1, protocol_version="v2.5",
        version_explicit=True, tiers=("A",)))
    check("an explicit v2.5 request loads only the isolated release",
          v25.release_id == prerelease.parent.name
          and v25.by_tier["A"][0].protocol_version == "v2.5")
    check("prerelease status is deterministic and mandatory",
          "unaudited" in (v25.preamble or "")
          and v25.deployment_status == "not_deployed")

    print("\nT2 — lexical and semantic results fuse without blending tiers")
    exact = retriever.search(retrieval.RetrievalRequest(
        "What does exactIdentifier(uint256) do?", 1,
        tiers=("A", "B"), limit_per_tier=3))
    check("an exact function signature ranks first in its tier",
          exact.by_tier["A"][0].id.endswith("exactIdentifier(uint256)"),
          str([item.id for item in exact.by_tier["A"]]))
    address = retriever.search(retrieval.RetrievalRequest(
        "0x1111111111111111111111111111111111111111", 1,
        tiers=("A",), limit_per_tier=1))
    check("an exact address is findable even when semantic ranking disagrees",
          address.by_tier["A"][0].id.endswith("controller()"),
          address.by_tier["A"][0].id)
    check("Tier A and Tier B remain separate typed result lists",
          all(item.tier == "A" for item in exact.by_tier["A"])
          and all(item.tier == "B" for item in exact.by_tier["B"]))
    check("per-tier limits are enforced independently",
          len(exact.by_tier["A"]) <= 3 and len(exact.by_tier["B"]) <= 3)
    check("always_cite policy cannot disappear from a response",
          exact.mandatory_source_paths == ("docs/Known Issues.md",)
          and exact.always_cite_candidates[0].path == "docs/Known Issues.md")

    questions = tmp / "questions.yaml"
    labels = tmp / "labels.yaml"
    questions.write_text(
        "questions:\n  - id: exact\n"
        "    question: What does exactIdentifier(uint256) do?\n")
    labels.write_text("exact: ['updates the value']\n")
    report = retrieval_eval.evaluate(
        retriever, str(questions), str(labels), k=3)
    check("retrieval labels run through the real release retriever",
          report["passed"] == 1 and report["release_id"] == main.parent.name)

    print("\nT3 — citations prove quote bytes and resolve immutable locations")
    withdrawals = retriever.search(retrieval.RetrievalRequest(
        "withdrawal batches claimable expiry", 1, tiers=("B",)))
    evidence = withdrawals.by_tier["B"][0]
    citation = retriever.citation_resolver().resolve(evidence)
    check("a Markdown citation includes the pinned commit and rendered anchor",
          "/blob/" + "a" * 40 in citation.source_url
          and citation.source_url.endswith("#withdrawals"), citation.source_url)
    check("the quote is byte-identical to the corpus chunk",
          citation.quote == evidence.display_text)
    synthesized = next(item for item in general.by_tier["A"]
                       if item.synthesised)
    refused = ""
    try:
        retriever.citation_resolver().resolve(synthesized)
    except retrieval.CitationError as error:
        refused = str(error)
    check("a synthesised retrieval aid can never be quoted",
          "cannot be quoted" in refused, refused)
    forged = dataclasses.replace(evidence, display_text="forged quote")
    refused = ""
    try:
        retriever.citation_resolver().resolve(forged)
    except retrieval.CitationError as error:
        refused = str(error)
    check("a search result that differs from corpus bytes is refused",
          "differs from corpus" in refused, refused)

    original_release = main.read_text()
    changed_release = json.loads(original_release)
    changed_release["gates"]["corpus_diff_reviewed"] = False
    main.write_text(json.dumps(changed_release, indent=2))
    refused = ""
    try:
        retrieval.Retriever(str(manifest), str(main), "stub:test")
    except retrieval.RetrievalError as error:
        refused = str(error)
    check("security-relevant release metadata is bound to the release id",
          "does not match its release_id" in refused, refused)
    main.write_text(original_release)

    index_path = tmp / "artifacts/index/main/main-build/tier-A.npy"
    index_path.write_bytes(index_path.read_bytes() + b"damage")
    refused = ""
    try:
        retrieval.Retriever(str(manifest), str(main), "stub:test")
    except retrieval.RetrievalError as error:
        refused = str(error)
    check("a modified index payload cannot be loaded as evidence",
          "modified index artifact" in refused, refused)


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
