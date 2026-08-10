#!/usr/bin/env python3
"""
test_embed.py — Project Aleph

Adversarial tests for the embedding boundary and the index. Same contract as
the other suites: exit code is the failure count.

    python3 embed/test_embed.py              # no model, no network
    python3 embed/test_embed.py --model st:sentence-transformers/all-MiniLM-L6-v2

Most of these run on the stub, because what is being tested is not whether a
model is any good — `eval/` answers that — but whether the machinery around it
can tell one model from another. That distinction is the entire safety
property here: a mismatched embedder does not fail, it returns a confident
ranking of the wrong chunks.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from embed import embedder as em          # noqa: E402
from embed import index as ix             # noqa: E402

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if ok else 'FAIL'} {name}"
          + (f"  — {detail}" if detail and not ok else ""))
    if not ok:
        FAILURES.append(name)


def fake_corpus(tmp: pathlib.Path, build_id: str = "abc123",
                n_a: int = 6, n_b: int = 4) -> pathlib.Path:
    d = tmp / "corpus" / build_id
    d.mkdir(parents=True)
    rows = []
    for i in range(n_a):
        rows.append({
            "id": f"v2-protocol:src/M{i}.sol:M{i}.f()", "kind": "Function",
            "source_type": "solidity", "path": f"src/M{i}.sol", "line": 1,
            "breadcrumb": f"src/M{i}.sol › M{i} › f()", "tier": "A",
            "synthesised": False, "display_text": "x", "model_text": "x",
            "embed_text": f"contract M{i} function f returns the balance",
            "corpus_build_id": build_id, "source_ref": "repo@tag/abc1234",
            "protocol_version": "v2.0", "deployment_status": "deployed",
            "effective_date": None, "doc_version": None,
            "content_hash": f"h{i}", "warnings": [], "detail": {},
        })
    for i in range(n_b):
        rows.append({
            "id": f"wildcat-docs:legal/d{i}.md#s", "kind": "section",
            "source_type": "markdown", "path": f"legal/d{i}.md", "line": 1,
            "breadcrumb": f"legal/d{i}.md › Legal › Section", "tier": "B",
            "synthesised": False, "display_text": "y", "model_text": "y",
            "embed_text": f"legal document {i} concerning withdrawals",
            "corpus_build_id": build_id, "source_ref": "docs@tag/def5678",
            "protocol_version": None, "deployment_status": None,
            "effective_date": "2025-01-16", "doc_version": "2025-01-16",
            "content_hash": f"g{i}", "warnings": [], "detail": {},
        })
    with open(d / "chunks.jsonl", "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    (d / "build.json").write_text(json.dumps({
        "build_id": build_id,
        "chunks": {"total": len(rows)},
        "gates": {"schema_valid": True},
        "waivers": ["metadata_required_unmet"],
    }, indent=2))
    return d


# --------------------------------------------------------------------------

def test_identity() -> None:
    print("\nE1 — an identity distinguishes what a bare model name cannot")
    a = em.Identity("ollama", "bge-m3", 1024, True, "790764642607")
    b = em.Identity("sentence-transformers", "BAAI/bge-m3", 1024, True, "")
    c = em.Identity("ollama", "bge-m3", 1024, True, "ffffffffffff")
    check("the same weights via a different backend are not the same thing",
          a.key() != b.key(), f"{a.key()} vs {b.key()}")
    check("a different digest of the same model is not the same thing",
          a.key() != c.key(), f"{a.key()} vs {c.key()}")
    check("an identity round-trips through JSON",
          em.Identity.from_dict(json.loads(json.dumps(a.to_dict()))) == a)

    raised = ""
    try:
        em.require_match(a, b)
    except em.EmbeddingError as e:
        raised = str(e)
    check("a mismatch is refused, naming both sides",
          "ollama" in raised and "sentence-transformers" in raised,
          raised[:120])
    ok = True
    try:
        em.require_match(a, em.Identity("ollama", "bge-m3", 1024, True,
                                        "790764642607"))
    except em.EmbeddingError:
        ok = False
    check("an exact match is allowed", ok)

    prefix_mismatch = ""
    try:
        em.require_match(a, em.Identity(
            "ollama", "bge-m3", 1024, True, "790764642607",
            "Represent this sentence:"))
    except em.EmbeddingError as e:
        prefix_mismatch = str(e)
    check("a query-prefix mismatch is refused",
          "query_prefix" in prefix_mismatch, prefix_mismatch[:160])


def test_stub() -> None:
    print("\nE2 — the stub is deterministic, bounded and obviously a stub")
    import numpy as np
    e = em.make_embedder("stub:test")
    v1 = e.embed(["hello", "world"])
    v2 = e.embed(["hello", "world"])
    check("same input, same vectors", np.array_equal(v1, v2))
    check("different input, different vectors", not np.allclose(v1[0], v1[1]))
    check("unit length", np.allclose(np.linalg.norm(v1, axis=1), 1.0),
          str(np.linalg.norm(v1, axis=1)))
    check("finite — no NaN or infinity from reinterpreted bytes",
          bool(np.isfinite(v1).all()))
    check("its identity says stub, so an index cannot hide it",
          e.identity().backend == "stub", e.identity().key())
    check("dimensions are configurable",
          em.make_embedder("stub:x", dimensions=8).embed(["a"]).shape == (1, 8))


def test_specs() -> None:
    print("\nE3 — the runtime is configuration, not an import")
    check("ollama spec", isinstance(em.make_embedder("ollama:bge-m3"),
                                    em.OllamaEmbedder))
    check("sentence-transformers spec",
          isinstance(em.make_embedder("st:BAAI/bge-m3"),
                     em.SentenceTransformersEmbedder))
    check("url spec", isinstance(em.make_embedder("https://embed.internal"),
                                 em.HttpEmbedder))
    for bad in ("bge-m3", "nonsense:x", "ollama:"):
        raised = False
        try:
            em.make_embedder(bad)
        except em.EmbeddingError:
            raised = True
        check(f"rejected: {bad!r}", raised)


def test_ollama_digest_fallback() -> None:
    print("\nE3b — current Ollama identity remains artifact-pinned")

    class CurrentOllama(em.OllamaEmbedder):
        def _show(self):
            return {"model_info": {"bert.embedding_length": 1024}}

        def _tags(self):
            return {"models": [{
                "name": "bge-m3:latest", "model": "bge-m3:latest",
                "digest": "790764642607" + "0" * 52,
            }]}

    identity = CurrentOllama(
        "bge-m3", expect_digest="790764642607").identity()
    check("a digest omitted by /api/show is resolved from the exact tag",
          identity.digest == "790764642607" and identity.dimensions == 1024,
          str(identity))

    class Ambiguous(CurrentOllama):
        def _tags(self):
            row = {"digest": "790764642607" + "0" * 52}
            return {"models": [
                {**row, "name": "bge-m3", "model": "other"},
                {**row, "name": "other", "model": "bge-m3:latest"},
            ]}

    refused = ""
    try:
        Ambiguous("bge-m3").identity()
    except em.EmbeddingError as error:
        refused = str(error)
    check("multiple exact tag aliases fail rather than choosing one",
          "2 exact model matches" in refused, refused)


def test_index_build(tmp: pathlib.Path) -> None:
    print("\nE4 — an index keeps the tiers apart and records its provenance")
    corpus = fake_corpus(tmp)
    manifest = ix.build_index(str(corpus), str(tmp / "index"), "stub:test")
    out = tmp / "index" / "abc123"

    check("one vector file per tier",
          (out / "tier-A.npy").exists() and (out / "tier-B.npy").exists())
    check("tiers are not blended",
          manifest["tiers"]["A"]["chunks"] == 6
          and manifest["tiers"]["B"]["chunks"] == 4, str(manifest["tiers"]))
    check("the index names the corpus it came from",
          manifest["corpus_build_id"] == "abc123")
    check("...and the embedder that built it",
          manifest["embedder"]["backend"] == "stub", str(manifest["embedder"]))
    check("corpus waivers are carried into the index",
          manifest["corpus_waivers"] == ["metadata_required_unmet"],
          str(manifest.get("corpus_waivers")))

    meta = [json.loads(l) for l in open(out / "tier-B.jsonl")]
    check("metadata travels with the vectors, so search needs no corpus",
          all(m["breadcrumb"] and m["id"] for m in meta))
    check("per-document provenance survives into the index",
          all(m["effective_date"] == "2025-01-16" for m in meta),
          str(meta[0]))
    check("citation text travels with the vectors",
          all(m["display_text"] and m["detail"] is not None for m in meta))

    index_record = out / "index.json"
    original_record = index_record.read_bytes()
    reused = ix.build_index(str(corpus), str(tmp / "index"), "stub:test")
    check("a repeat build reuses the immutable index",
          reused["created"] == manifest["created"]
          and index_record.read_bytes() == original_record)

    vector_path = out / "tier-A.npy"
    vector_path.write_bytes(vector_path.read_bytes() + b"damage")
    raised = ""
    try:
        ix.build_index(str(corpus), str(tmp / "index"), "stub:test")
    except ix.IndexError_ as e:
        raised = str(e)
    check("a modified immutable vector artifact is refused",
          "modified immutable" in raised, raised[:160])

    mismatch = ""
    try:
        ix.build_index(str(corpus), str(tmp / "other-index"), "stub:test",
                       expected_identity=em.Identity(
                           "stub", "other", 64, True, "test-v1", ""))
    except ix.IndexError_ as e:
        mismatch = str(e)
    check("a runtime differing from the manifest identity is refused",
          "does not match manifest" in mismatch, mismatch[:160])


def test_search(tmp: pathlib.Path) -> None:
    print("\nE5 — search ranks, scopes and refuses the wrong embedder")
    corpus = fake_corpus(tmp, build_id="def456")
    ix.build_index(str(corpus), str(tmp / "index"), "stub:test")
    index = ix.Index(str(tmp / "index" / "def456"))
    e = em.make_embedder("stub:test")
    q = e.embed(["withdrawals"], kind="query")[0]

    hits = index.search(q, e.identity(), k=3)
    check("both tiers are searched by default",
          {h["tier"] for h in hits} == {"A", "B"}, str({h["tier"] for h in hits}))
    check("k applies per tier", len(hits) == 6, str(len(hits)))
    b_only = index.search(q, e.identity(), tier="B", k=2)
    check("a tier can be requested alone",
          all(h["tier"] == "B" for h in b_only) and len(b_only) == 2)
    check("results are ordered by score within a tier",
          all(b_only[i]["score"] >= b_only[i + 1]["score"]
              for i in range(len(b_only) - 1)), str([h["score"] for h in b_only]))
    check("a hit carries what a citation needs",
          all(k in b_only[0] for k in
              ("id", "breadcrumb", "source_ref", "score", "doc_version")))

    # the invariant this whole module exists for
    other = em.make_embedder("stub:different-model")
    qv = other.embed(["withdrawals"], kind="query")[0]
    raised = ""
    try:
        index.search(qv, other.identity(), k=1)
    except em.EmbeddingError as e2:
        raised = str(e2)
    check("a query from a different embedder is refused, not ranked",
          "different model" in raised, raised[:120])

    wrong_dims = em.make_embedder("stub:test", dimensions=8)
    raised = ""
    try:
        index.search(wrong_dims.embed(["x"])[0], index.identity, k=1)
    except (em.EmbeddingError, ix.IndexError_) as e3:
        raised = str(e3)
    check("a dimension mismatch is refused even when identity is spoofed",
          "dimensional" in raised or "dimension" in raised, raised[:120])

    raised = ""
    try:
        index.search([0.0] * index.identity.dimensions, index.identity, k=1)
    except ix.IndexError_ as e4:
        raised = str(e4)
    check("an all-zero query vector is refused", "zeros" in raised, raised[:80])


def test_corpus_integrity(tmp: pathlib.Path) -> None:
    print("\nE6 — an edited or incoherent corpus does not become an index")
    corpus = fake_corpus(tmp, build_id="ghi789")
    rows = open(corpus / "chunks.jsonl").readlines()

    with open(corpus / "chunks.jsonl", "w") as f:
        f.writelines(rows[:-1])
    raised = ""
    try:
        ix.build_index(str(corpus), str(tmp / "i1"), "stub:test")
    except ix.IndexError_ as e:
        raised = str(e)
    check("chunks.jsonl disagreeing with build.json is fatal",
          "edited since it was built" in raised, raised[:140])

    mixed = fake_corpus(tmp, build_id="jkl012")
    lines = [json.loads(l) for l in open(mixed / "chunks.jsonl")]
    lines[0]["corpus_build_id"] = "somethingelse"
    with open(mixed / "chunks.jsonl", "w") as f:
        for r in lines:
            f.write(json.dumps(r) + "\n")
    raised = ""
    try:
        ix.build_index(str(mixed), str(tmp / "i2"), "stub:test")
    except ix.IndexError_ as e:
        raised = str(e)
    check("chunks from two different builds are not one corpus",
          "not one corpus" in raised, raised[:140])

    empty = fake_corpus(tmp, build_id="mno345")
    lines = [json.loads(l) for l in open(empty / "chunks.jsonl")]
    lines[0]["embed_text"] = "   "
    with open(empty / "chunks.jsonl", "w") as f:
        for r in lines:
            f.write(json.dumps(r) + "\n")
    raised = ""
    try:
        ix.build_index(str(empty), str(tmp / "i3"), "stub:test")
    except ix.IndexError_ as e:
        raised = str(e)
    check("an empty embed_text is refused rather than embedded",
          "empty embed_text" in raised, raised[:140])

    raised = ""
    try:
        ix.build_index(str(tmp / "nowhere"), str(tmp / "i4"), "stub:test")
    except ix.IndexError_ as e:
        raised = str(e)
    check("a missing corpus is a clear error", "not found" in raised,
          raised[:120])


def test_real_model(spec: str, tmp: pathlib.Path) -> None:
    print(f"\nE7 — a real model through the same interface ({spec})")
    import numpy as np
    e = em.make_embedder(spec)
    ident = e.identity()
    check("it reports a dimension", ident.dimensions > 0, str(ident))
    docs = ["A market is delinquent when its reserve ratio is too low.",
            "The scale factor accrues interest by scaling balances.",
            "Borrowers complete onboarding before creating a market."]
    dv = e.embed(docs, kind="document")
    qv = e.embed(["what does market delinquency mean?"], kind="query")
    check("vectors are unit length",
          np.allclose(np.linalg.norm(dv, axis=1), 1.0, atol=1e-5))
    check("the relevant document ranks first",
          int(np.argmax(dv @ qv[0])) == 0, str((dv @ qv[0]).round(3)))

    corpus = fake_corpus(tmp, build_id="real01")
    ix.build_index(str(corpus), str(tmp / "ri"), spec)
    index = ix.Index(str(tmp / "ri" / "real01"))
    hits = index.search(e.embed(["withdrawals"], kind="query")[0],
                        e.identity(), tier="B", k=1)
    check("an index built with it can be queried with it", len(hits) == 1)
    stub = em.make_embedder("stub:test")
    raised = ""
    try:
        index.search(stub.embed(["withdrawals"])[0], stub.identity(), k=1)
    except em.EmbeddingError as e2:
        raised = str(e2)
    check("...and not with anything else", "different model" in raised,
          raised[:100])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", help="also exercise a real embedder, e.g. "
                                    "ollama:bge-m3 or st:BAAI/bge-m3")
    args = ap.parse_args()

    test_identity()
    test_stub()
    test_specs()
    test_ollama_digest_fallback()
    for fn in (test_index_build, test_search, test_corpus_integrity):
        td = tempfile.mkdtemp()
        try:
            fn(pathlib.Path(td))
        finally:
            shutil.rmtree(td, ignore_errors=True)
    if args.model:
        td = tempfile.mkdtemp()
        try:
            test_real_model(args.model, pathlib.Path(td))
        finally:
            shutil.rmtree(td, ignore_errors=True)

    print(f"\n{len(FAILURES)} failure(s)"
          + (": " + ", ".join(FAILURES) if FAILURES else ""))
    return len(FAILURES)


if __name__ == "__main__":
    sys.exit(main())
