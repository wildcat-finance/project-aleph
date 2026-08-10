#!/usr/bin/env python3
"""
index.py — Project Aleph

Turns a corpus into something searchable, and searches it.

    python3 embed/index.py build --corpus corpus/<build_id> \
        --embedder ollama:bge-m3 --out index/
    python3 embed/index.py search --index index/<build_id> \
        --embedder ollama:bge-m3 --query "what happens if a borrower is late"

One index per tier, never blended. Tier A is deployed protocol source, Tier B
is published documentation, and a single ranked list across both lets a
paragraph of prose outrank the function it describes — the prose usually wins
on wording because it was written to be readable. Callers ask each tier and
decide, rather than being handed a merged list that has already decided for
them.

Brute-force cosine, deliberately. The corpus is ~1,600 chunks; at 1024
dimensions that is a 6.6 MB matrix and a single matmul, well under a
millisecond. An approximate index would add a dependency, a build step and a
recall cliff in exchange for nothing measurable at this size. Revisit at
perhaps a hundred thousand chunks, which is two orders of magnitude away.

The vectors are stored beside the metadata needed to render a citation, so
searching does not require the corpus. What it does require is the same
embedder that built the index, which is checked before any comparison — see
`embedder.require_match`.
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

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from embed.embedder import (  # noqa: E402
    EmbeddingError, Identity, make_embedder, require_match)

# Metadata carried alongside each vector: enough to rank, attribute and quote
# without reopening the corpus.
CARRIED = ("id", "kind", "source_type", "path", "line", "breadcrumb", "tier",
           "synthesised", "corpus_build_id", "source_ref", "protocol_version",
           "deployment_status", "effective_date", "doc_version",
           "content_hash", "display_text", "model_text", "embed_text",
           "detail", "warnings")


class IndexError_(Exception):
    """Raised for conditions that must stop an index build or a search."""


def _np():
    try:
        import numpy as np
    except ImportError:
        raise IndexError_("embed/index.py needs numpy (pip install numpy)")
    return np


def _sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tool_hashes() -> dict[str, str]:
    return {name: _sha256(HERE / name)
            for name in ("embedder.py", "index.py")}


def _validate_existing(out_dir: pathlib.Path, build_id: str,
                       identity: Identity, tools: dict,
                       rows: list[dict], record: dict,
                       corpus_sha256: str) -> dict:
    """An index directory is immutable: verify it fully or reject it."""
    manifest_path = out_dir / "index.json"
    if not manifest_path.is_file():
        raise IndexError_(f"{out_dir}: incomplete immutable index (index.json "
                          "is missing); refusing to repair or overwrite it")
    try:
        manifest = json.loads(manifest_path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        raise IndexError_(f"{manifest_path}: invalid immutable index: {e}")
    expected = {
        "corpus_build_id": build_id,
        "corpus_sha256": corpus_sha256,
        "embedder": identity.to_dict(),
        "tools": tools,
        "total_chunks": len(rows),
        "corpus_gates": record.get("gates"),
        "corpus_waivers": record.get("waivers"),
    }
    mismatched = [k for k, value in expected.items()
                  if manifest.get(k) != value]
    if mismatched:
        raise IndexError_(
            f"{manifest_path}: immutable index metadata differs in "
            f"{', '.join(mismatched)}; use a clean output path and investigate")
    artifacts = manifest.get("artifacts") or {}
    required = {f"tier-{tier}{suffix}"
                for tier in manifest.get("tiers", {})
                for suffix in (".npy", ".jsonl")}
    if set(artifacts) != required:
        raise IndexError_(f"{manifest_path}: artifact inventory is incomplete")
    for name, declared_hash in artifacts.items():
        path = out_dir / name
        if not path.is_file() or _sha256(path) != declared_hash:
            raise IndexError_(
                f"{path}: missing or modified immutable index artifact; "
                "refusing to repair or overwrite it")
    print(f"reused    {out_dir} (immutable index already verified)")
    return manifest


# --------------------------------------------------------------------------
# build
# --------------------------------------------------------------------------

def load_corpus(corpus_dir: pathlib.Path) -> tuple[list[dict], dict]:
    chunks_path = corpus_dir / "chunks.jsonl"
    build_path = corpus_dir / "build.json"
    if not chunks_path.exists():
        raise IndexError_(f"{chunks_path} not found — point --corpus at a "
                          "directory produced by ingest/build.py")
    rows = [json.loads(line) for line in open(chunks_path)]
    record = json.loads(build_path.read_text()) if build_path.exists() else {}

    declared = (record.get("chunks") or {}).get("total")
    if declared is not None and declared != len(rows):
        raise IndexError_(
            f"{corpus_dir}: build.json declares {declared} chunks, "
            f"chunks.jsonl holds {len(rows)} — the corpus has been edited "
            "since it was built, and an index over it would not be replayable")

    stamped = {r.get("corpus_build_id") for r in rows}
    if len(stamped) > 1:
        raise IndexError_(f"{corpus_dir}: chunks carry {len(stamped)} "
                          "different corpus_build_ids; this is not one corpus")
    return rows, record


def build_index(corpus_dir: str, out_root: str, embedder_spec: str,
                batch: int = 16,
                expected_identity: Identity | None = None) -> dict:
    np = _np()
    corpus = pathlib.Path(corpus_dir)
    rows, record = load_corpus(corpus)
    corpus_sha256 = _sha256(corpus / "chunks.jsonl")
    build_id = (record.get("build_id")
                or (rows[0].get("corpus_build_id") if rows else None))
    if not build_id:
        raise IndexError_(f"{corpus}: no corpus build id — refusing to build "
                          "an index that cannot name the corpus it came from")

    embedder = make_embedder(embedder_spec)
    identity = embedder.identity()
    if expected_identity is not None and identity != expected_identity:
        raise IndexError_(
            "the embedding runtime does not match manifest.yaml\n"
            f"  manifest: {expected_identity.to_dict()}\n"
            f"  runtime : {identity.to_dict()}")
    print(f"embedder  {identity.key()}")
    if identity.backend == "stub":
        print("  WARNING: stub backend — this index is a test artefact and "
              "will retrieve nonsense")

    by_tier: dict[str, list[dict]] = {}
    for r in rows:
        by_tier.setdefault(r.get("tier") or "?", []).append(r)

    out_root_path = pathlib.Path(out_root)
    out_root_path.mkdir(parents=True, exist_ok=True)
    out_dir = out_root_path / build_id
    tools = _tool_hashes()
    if out_dir.exists():
        return _validate_existing(out_dir, build_id, identity, tools,
                                  rows, record, corpus_sha256)

    temp_dir = pathlib.Path(tempfile.mkdtemp(
        prefix=f".{build_id}.", dir=out_root_path))

    tiers: dict[str, dict] = {}
    try:
        for tier in sorted(by_tier):
            members = by_tier[tier]
            texts = [m["embed_text"] for m in members]
            empty = sum(1 for t in texts if not t.strip())
            if empty:
                raise IndexError_(f"tier {tier}: {empty} chunk(s) have empty "
                                  "embed_text; the corpus should not have shipped")
            print(f"  tier {tier}: embedding {len(texts)} chunks…")
            vectors = embedder.embed(texts, kind="document", batch=batch)
            if vectors.shape[0] != len(members):
                raise IndexError_(
                    f"tier {tier}: embedded {vectors.shape[0]} of {len(members)}")

            np.save(temp_dir / f"tier-{tier}.npy",
                    np.ascontiguousarray(vectors, dtype="float32"))
            with open(temp_dir / f"tier-{tier}.jsonl", "w") as f:
                for m in members:
                    f.write(json.dumps({k: m.get(k) for k in CARRIED}) + "\n")
            tiers[tier] = {"chunks": len(members),
                           "dimensions": int(vectors.shape[1])}
            print(f"    {len(members)} vectors, {vectors.shape[1]} dimensions")

        artifacts = {path.name: _sha256(path) for path in sorted(temp_dir.iterdir())}
        manifest = {
            "corpus_build_id": build_id,
            "corpus_sha256": corpus_sha256,
            "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "embedder": identity.to_dict(),
            "embedder_key": identity.key(),
            "tools": tools,
            "tiers": tiers,
            "total_chunks": len(rows),
            "artifacts": artifacts,
            "corpus_gates": record.get("gates"),
            "corpus_waivers": record.get("waivers"),
        }
        (temp_dir / "index.json").write_text(
            json.dumps(manifest, indent=2) + "\n")
        try:
            os.replace(temp_dir, out_dir)
        except OSError:
            if out_dir.exists():
                return _validate_existing(out_dir, build_id, identity, tools,
                                          rows, record, corpus_sha256)
            raise
    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
    print(f"written   {out_dir}")
    if record.get("waivers"):
        print(f"  note: the corpus was built with waivers "
              f"{record['waivers']} — carried into index.json so a retrieval "
              "answer can be traced to them")
    return manifest


# --------------------------------------------------------------------------
# search
# --------------------------------------------------------------------------

class Index:
    """A built index, loaded for querying."""

    def __init__(self, index_dir: str):
        np = _np()
        self.dir = pathlib.Path(index_dir)
        manifest_path = self.dir / "index.json"
        if not manifest_path.exists():
            raise IndexError_(f"{manifest_path} not found")
        self.manifest = json.loads(manifest_path.read_text())
        self.identity = Identity.from_dict(self.manifest["embedder"])
        self.vectors: dict[str, "np.ndarray"] = {}
        self.meta: dict[str, list[dict]] = {}
        for tier in self.manifest["tiers"]:
            self.vectors[tier] = np.load(self.dir / f"tier-{tier}.npy")
            self.meta[tier] = [json.loads(l) for l in
                               open(self.dir / f"tier-{tier}.jsonl")]
            if len(self.meta[tier]) != self.vectors[tier].shape[0]:
                raise IndexError_(
                    f"tier {tier}: {self.vectors[tier].shape[0]} vectors but "
                    f"{len(self.meta[tier])} metadata rows")

    @property
    def corpus_build_id(self) -> str:
        return self.manifest["corpus_build_id"]

    def search(self, query_vector, query_identity: Identity,
               tier: str | None = None, k: int = 5) -> list[dict]:
        """
        Nearest chunks by cosine similarity, per tier.

        `query_identity` is not decoration. An index and a query built by
        different embedders produce a perfectly well-formed ranking of the
        wrong things, and no downstream check can tell. This is where that is
        caught.
        """
        np = _np()
        require_match(self.identity, query_identity)
        q = np.asarray(query_vector, dtype="float32").reshape(-1)
        norm = float(np.linalg.norm(q))
        if norm == 0:
            raise IndexError_("query vector is all zeros")
        q = q / norm

        results = []
        for name in ([tier] if tier else sorted(self.vectors)):
            if name not in self.vectors:
                raise IndexError_(f"no tier {name!r} in this index; "
                                  f"have {sorted(self.vectors)}")
            mat = self.vectors[name]
            if mat.shape[1] != q.shape[0]:
                raise IndexError_(
                    f"tier {name} holds {mat.shape[1]}-dimensional vectors, "
                    f"the query is {q.shape[0]}")
            scores = mat @ q
            top = np.argsort(-scores)[:k]
            for rank, i in enumerate(top, 1):
                results.append({"tier": name, "rank": rank,
                                "score": float(scores[i]),
                                **self.meta[name][int(i)]})
        return results


def search_cli(index_dir: str, embedder_spec: str, query: str,
               tier: str | None, k: int) -> int:
    embedder = make_embedder(embedder_spec)
    index = Index(index_dir)
    vector = embedder.embed([query], kind="query")[0]
    hits = index.search(vector, embedder.identity(), tier=tier, k=k)
    print(f"corpus {index.corpus_build_id}  embedder {index.identity.key()}\n")
    for h in hits:
        print(f"  [{h['tier']}] {h['score']:.4f}  {h['id']}")
        print(f"        {h['breadcrumb']}")
        if h.get("effective_date"):
            print(f"        effective {h['effective_date']}  "
                  f"version {h.get('doc_version')}")
    return 0


# --------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[2])
    sub = ap.add_subparsers(dest="command", required=True)

    b = sub.add_parser("build", help="embed a corpus into a searchable index")
    b.add_argument("--corpus", required=True,
                   help="a corpus/<build_id> directory from ingest/build.py")
    b.add_argument("--out", default="index", help="index root")
    b.add_argument("--embedder", required=True,
                   help="ollama:bge-m3 | st:BAAI/bge-m3 | http://… | stub:x")
    b.add_argument("--batch", type=int, default=16)

    s = sub.add_parser("search", help="query a built index")
    s.add_argument("--index", required=True)
    s.add_argument("--embedder", required=True)
    s.add_argument("--query", required=True)
    s.add_argument("--tier", help="restrict to one tier; default is all")
    s.add_argument("-k", type=int, default=5)

    args = ap.parse_args()
    try:
        if args.command == "build":
            build_index(args.corpus, args.out, args.embedder, args.batch)
            return 0
        return search_cli(args.index, args.embedder, args.query,
                          args.tier, args.k)
    except (IndexError_, EmbeddingError) as e:
        print(f"\nFATAL: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
