#!/usr/bin/env python3
"""Build one coherent, immutable Project Aleph corpus-and-index release.

This is the canonical stage-one entry point. It derives the required embedding
identity from manifest.yaml, builds or verifies the corpus and index, and emits
one release record that names every artifact and every promotion gate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import shutil
import sys
import tempfile
from datetime import datetime, timezone

from embed import index as indexer
from embed.embedder import EmbeddingError, Identity
from ingest import build as ingestion

HERE = pathlib.Path(__file__).resolve().parent


class ReleaseError(Exception):
    """Raised when a coherent release cannot be produced."""


def _canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _identity_from_manifest(manifest: dict) -> Identity:
    config = manifest.get("embedding") or {}
    required = ("backend", "model", "dimensions", "normalised")
    missing = [key for key in required if key not in config]
    if missing:
        raise ReleaseError("manifest embedding identity is incomplete: "
                           + ", ".join(missing))
    prefix = config.get("query_prefix", "")
    if prefix is None or str(prefix).lower() == "none":
        prefix = ""
    return Identity(
        backend=str(config["backend"]), model=str(config["model"]),
        dimensions=int(config["dimensions"]),
        normalised=bool(config["normalised"]),
        digest=str(config.get("digest") or ""), query_prefix=str(prefix))


def _embedder_spec(identity: Identity) -> str:
    backend = "st" if identity.backend == "sentence-transformers" \
        else identity.backend
    return f"{backend}:{identity.model}"


def _without_created(record: dict) -> dict:
    return {key: value for key, value in record.items() if key != "created"}


def _publish_release(root: pathlib.Path, record: dict) -> dict:
    releases = root / "releases"
    releases.mkdir(parents=True, exist_ok=True)
    out_dir = releases / record["release_id"]
    out_path = out_dir / "release.json"
    if out_dir.exists():
        if not out_path.is_file():
            raise ReleaseError(f"{out_dir}: incomplete immutable release")
        try:
            existing = json.loads(out_path.read_text())
        except (OSError, json.JSONDecodeError) as e:
            raise ReleaseError(f"{out_path}: invalid immutable release: {e}")
        if _without_created(existing) != _without_created(record):
            raise ReleaseError(
                f"{out_path}: release id collision or modified artifact; "
                "refusing to overwrite it")
        print(f"reused    {out_dir} (immutable release already verified)")
        return existing

    temp_dir = pathlib.Path(tempfile.mkdtemp(
        prefix=f".{record['release_id']}.", dir=releases))
    try:
        (temp_dir / "release.json").write_text(
            json.dumps(record, indent=2) + "\n")
        try:
            os.replace(temp_dir, out_dir)
        except OSError:
            if out_dir.exists():
                return _publish_release(root, record)
            raise
    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
    print(f"written   {out_path}")
    return record


def build_release(manifest_path: str = "manifest.yaml",
                  artifact_root: str = "artifacts", solc: str = "solc",
                  workdir: str = ".aleph-work",
                  local: dict[str, str] | None = None,
                  allow_unverified: bool = False,
                  allow_missing_metadata: bool = False,
                  prerelease: bool = False, against: str | None = None,
                  diff_reviewed_by: str | None = None,
                  embedder_spec: str | None = None,
                  batch: int = 16) -> dict:
    try:
        import yaml
    except ImportError:
        raise ReleaseError("release.py needs pyyaml (pip install pyyaml)")

    manifest_path_obj = pathlib.Path(manifest_path).resolve()
    manifest = yaml.safe_load(manifest_path_obj.read_bytes())
    expected_identity = _identity_from_manifest(manifest)
    runtime_spec = embedder_spec or _embedder_spec(expected_identity)
    root = pathlib.Path(artifact_root).resolve()

    corpus_record = ingestion.build(
        str(manifest_path_obj), str(root / "corpus"), solc, workdir,
        local or {}, allow_unverified, allow_missing_metadata, prerelease,
        against)
    corpus_dir = root / "corpus" / corpus_record["build_id"]

    index_tools = indexer._tool_hashes()
    index_namespace = hashlib.sha256(_canonical({
        "identity": expected_identity.to_dict(), "tools": index_tools,
    })).hexdigest()[:16]
    index_root = root / "index" / index_namespace
    index_record = indexer.build_index(
        str(corpus_dir), str(index_root), runtime_spec, batch,
        expected_identity=expected_identity)
    index_dir = index_root / corpus_record["build_id"]

    diff = corpus_record.get("diff_against")
    if diff is None:
        review = {"status": "not_applicable", "reviewed": True,
                  "reviewed_by": None, "counts": None}
    else:
        counts = diff["counts"]
        changed = any(counts[key] for key in
                      ("added", "removed", "changed_text"))
        if not changed:
            review = {"status": "unchanged", "reviewed": True,
                      "reviewed_by": None, "counts": counts}
        else:
            review = {"status": "approved" if diff_reviewed_by else "pending",
                      "reviewed": bool(diff_reviewed_by),
                      "reviewed_by": diff_reviewed_by, "counts": counts}

    gates = dict(corpus_record.get("gates") or {})
    gates["corpus_diff_reviewed"] = review["reviewed"]
    gates["embedding_identity_matches"] = True
    gates["index_integrity"] = True
    gate_policy = manifest.get("gates") or []
    required_gates = (list(gate_policy) if isinstance(gate_policy, list)
                      else list(gate_policy.keys()))
    promotable = all(gates.get(gate) is True for gate in required_gates)

    release_tool = _sha256(HERE / "release.py")
    identity_basis = {
        "corpus_build_id": corpus_record["build_id"],
        "index_namespace": index_namespace,
        "index_artifacts": index_record["artifacts"],
        "embedding": expected_identity.to_dict(),
        "review": review,
        "gates": gates,
        "prerelease": prerelease,
        "release_tool": release_tool,
    }
    release_id = hashlib.sha256(_canonical(identity_basis)).hexdigest()[:20]
    relative = lambda path: str(path.relative_to(root))
    record = {
        "release_id": release_id,
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "kind": "prerelease" if prerelease else "main",
        "manifest": {"path": str(manifest_path_obj),
                     "sha256": _sha256(manifest_path_obj)},
        "corpus": {
            "build_id": corpus_record["build_id"],
            "path": relative(corpus_dir),
            "chunks_sha256": _sha256(corpus_dir / "chunks.jsonl"),
            "record_sha256": _sha256(corpus_dir / "build.json"),
        },
        "index": {
            "namespace": index_namespace, "path": relative(index_dir),
            "record_sha256": _sha256(index_dir / "index.json"),
            "artifacts": index_record["artifacts"],
        },
        "embedding": expected_identity.to_dict(),
        "sources": corpus_record.get("sources"),
        "review": review,
        "gates": gates,
        "required_gates": required_gates,
        "promotable": promotable,
        "waivers": corpus_record.get("waivers") or [],
        "tools": {"release.py": release_tool, **index_tools},
    }
    return _publish_release(root, record)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--manifest", default="manifest.yaml")
    parser.add_argument("--artifacts", default="artifacts")
    parser.add_argument("--solc", default="solc")
    parser.add_argument("--workdir", default=".aleph-work")
    parser.add_argument("--source-path", action="append", default=[],
                        metavar="ID=PATH")
    parser.add_argument("--allow-unverified-signature", action="store_true")
    parser.add_argument("--allow-missing-metadata", action="store_true")
    parser.add_argument("--prerelease", action="store_true")
    parser.add_argument("--against", metavar="CHUNKS_JSONL")
    parser.add_argument("--diff-reviewed-by")
    parser.add_argument("--embedder",
                        help="runtime override; identity must match manifest")
    parser.add_argument("--batch", type=int, default=16)
    args = parser.parse_args()
    local = {}
    for spec in args.source_path:
        key, separator, value = spec.partition("=")
        if not separator or not key or not value:
            print(f"FATAL: --source-path wants ID=PATH, got {spec!r}",
                  file=sys.stderr)
            return 1
        local[key] = value
    try:
        record = build_release(
            args.manifest, args.artifacts, args.solc, args.workdir, local,
            args.allow_unverified_signature, args.allow_missing_metadata,
            args.prerelease, args.against, args.diff_reviewed_by,
            args.embedder, args.batch)
    except (ReleaseError, ingestion.BuildError, indexer.IndexError_,
            EmbeddingError) as error:
        print(f"\nFATAL: {error}", file=sys.stderr)
        return 1
    print(f"release   {record['release_id']}  promotable={record['promotable']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
