#!/usr/bin/env python3
"""
test_build.py — Project Aleph

Adversarial tests for the pipeline driver. Same contract as the chunker suites:
exit code is the failure count, and every case corresponds to something the
driver claims in its docstring or in PIPELINE.md.

    python3 ingest/test_build.py                 # no compiler needed
    python3 ingest/test_build.py --solc solc     # + a real chunking run

The signature cases build their own throwaway GPG key and sign a real tag, so
the *passing* path is exercised rather than assumed. Nothing in this repository
had ever run a successful `git verify-tag` — the pinned corpus cannot, because
its tags are unsigned — which is exactly the kind of check that quietly turns
out to be untested at the moment it matters.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("ab", HERE / "build.py")
ab = importlib.util.module_from_spec(_spec)
sys.modules["ab"] = ab
_spec.loader.exec_module(ab)

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if ok else 'FAIL'} {name}"
          + (f"  — {detail}" if detail and not ok else ""))
    if not ok:
        FAILURES.append(name)


def git(repo: pathlib.Path, *args: str, **kw) -> subprocess.CompletedProcess:
    env = dict(os.environ, **kw.pop("env_extra", {}))
    return subprocess.run(["git", *args], cwd=repo, capture_output=True,
                          text=True, env=env)


def make_repo(root: pathlib.Path, files: dict[str, str]) -> pathlib.Path:
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "-q")
    git(root, "config", "user.email", "t@example.invalid")
    git(root, "config", "user.name", "T")
    for rel, body in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "one")
    return root


LONG = "Body text comfortably past the minimum chunk length filter for markdown."


# --------------------------------------------------------------------------
# B1 — the build id is a function of the inputs
# --------------------------------------------------------------------------

def test_build_id() -> None:
    print("\nB1 — the build id comes from the inputs, never the clock")
    res = {"a": {"commit": "c" * 40}}
    tools = {"solc": "0.8.25", "build.py": "abc"}
    one = ab.compute_build_id(b"manifest", res, tools)
    two = ab.compute_build_id(b"manifest", res, tools)
    check("same inputs give the same id", one == two, f"{one} {two}")
    check("a changed manifest changes it",
          ab.compute_build_id(b"manifest2", res, tools) != one)
    check("a changed commit changes it",
          ab.compute_build_id(b"manifest", {"a": {"commit": "d" * 40}}, tools) != one)
    check("a changed tool changes it",
          ab.compute_build_id(b"manifest", res, {**tools, "solc": "0.8.36"}) != one)


# --------------------------------------------------------------------------
# B2 — signatures: verified, absent, invalid
# --------------------------------------------------------------------------

def test_signatures(tmp: pathlib.Path) -> None:
    print("\nB2 — a missing signature and a bad one are not the same thing")
    gnupg = tmp / "gnupg"
    gnupg.mkdir(mode=0o700)
    env = {"GNUPGHOME": str(gnupg)}
    gen = subprocess.run(
        ["gpg", "--batch", "--passphrase", "", "--quick-generate-key",
         "Aleph Test <test@example.invalid>", "default", "default", "never"],
        capture_output=True, text=True, env=dict(os.environ, **env))
    if gen.returncode != 0:
        check("gpg available for the signed-tag fixture", False, gen.stderr[:120])
        return
    keys = subprocess.run(["gpg", "--list-secret-keys", "--with-colons"],
                          capture_output=True, text=True,
                          env=dict(os.environ, **env)).stdout
    key = next(l.split(":")[4] for l in keys.splitlines() if l.startswith("sec"))

    repo = make_repo(tmp / "signed", {"a.txt": "hi"})
    git(repo, "config", "user.signingkey", key)
    git(repo, "tag", "-s", "-m", "signed", "v1.0.0", env_extra=env)
    commit = git(repo, "rev-parse", "HEAD").stdout.strip()
    tag_obj = git(repo, "rev-parse", "refs/tags/v1.0.0").stdout.strip()

    src = {"id": "s", "repo": "x/y",
           "ref": {"kind": "annotated_tag", "tag": "v1.0.0",
                   "require_signature": True}}
    os.environ["GNUPGHOME"] = str(gnupg)
    try:
        out = ab.resolve_ref(src, repo, allow_unverified=False)
        check("a genuinely signed tag verifies", out["signature"] == "verified",
              str(out.get("signature")))
        check("...and resolves to the tagged commit",
              out["commit"] == commit, out.get("commit", "")[:12])

        # the manifest's hash assertions are checkable with no key at all
        moved = {**src, "ref": {**src["ref"], "tag_object": "0" * 7}}
        raised = ""
        try:
            ab.resolve_ref(moved, repo, allow_unverified=True)
        except ab.BuildError as e:
            raised = str(e)
        check("a tag pointing somewhere else is fatal",
              "has been moved" in raised, raised[:100])

        wrong = {**src, "ref": {**src["ref"], "commit": "abcdef0"}}
        raised = ""
        try:
            ab.resolve_ref(wrong, repo, allow_unverified=True)
        except ab.BuildError as e:
            raised = str(e)
        check("resolving away from the named commit is fatal",
              "manifest names" in raised, raised[:100])
    finally:
        os.environ.pop("GNUPGHOME", None)

    # an annotated but unsigned tag — the state the real corpus is in
    plain = make_repo(tmp / "unsigned", {"a.txt": "hi"})
    git(plain, "tag", "-a", "-m", "annotated", "v1.0.0")
    raised = ""
    try:
        ab.resolve_ref(src, plain, allow_unverified=False)
    except ab.BuildError as e:
        raised = str(e)
    check("an unsigned tag stops a build that requires one",
          "carries no signature" in raised, raised[:120])
    out = ab.resolve_ref(src, plain, allow_unverified=True)
    check("...and is waivable, recorded as unsigned",
          out["signature"] == "unsigned", str(out.get("signature")))

    # a signature that is present and invalid is never waivable
    bad = make_repo(tmp / "badsig", {"a.txt": "hi"})
    git(bad, "tag", "-a", "-m", "annotated", "v1.0.0")
    obj = git(bad, "cat-file", "-p", "refs/tags/v1.0.0").stdout
    forged = obj + "-----BEGIN PGP SIGNATURE-----\nnot a signature\n-----END PGP SIGNATURE-----\n"
    new_obj = subprocess.run(["git", "hash-object", "-t", "tag", "-w", "--stdin"],
                             cwd=bad, input=forged, capture_output=True,
                             text=True).stdout.strip()
    git(bad, "update-ref", "refs/tags/v1.0.0", new_obj)
    raised = ""
    try:
        ab.resolve_ref(src, bad, allow_unverified=True)   # waiver offered anyway
    except ab.BuildError as e:
        raised = str(e)
    check("an invalid signature is fatal even with the waiver",
          "not waivable" in raised, raised[:140])


# --------------------------------------------------------------------------
# B3 — policy the manifest states and nothing enforced
# --------------------------------------------------------------------------

def test_policy(tmp: pathlib.Path) -> None:
    print("\nB3 — stated policy is enforced, not merely stated")
    repo = make_repo(tmp / "pol", {"a.txt": "hi"})
    git(repo, "tag", "-a", "-m", "t", "v1.0.0")

    raised = ""
    try:
        ab.resolve_ref({"id": "s", "ref": {"kind": "branch", "branch": "main"}},
                       repo, allow_unverified=True)
    except ab.BuildError as e:
        raised = str(e)
    check("a branch ref is refused", "moving target" in raised, raised[:100])

    manifest = tmp / "self.yaml"
    manifest.write_text(
        "version: 1\npolicy:\n  self_ingestion: forbidden\n"
        "sources:\n  - id: aleph\n    repo: wildcat-finance/project-aleph\n"
        "    include: ['**/*.md']\n", encoding="utf-8")
    raised = ""
    try:
        ab.build(str(manifest), str(tmp / "o"), "solc", str(tmp / "w"),
                 {"aleph": str(repo)}, True, True, False, None)
    except ab.BuildError as e:
        raised = str(e)
    check("the Aleph repo cannot be its own source",
          "self_ingestion" in raised, raised[:100])

    dirty = make_repo(tmp / "dirty", {"a.txt": "hi"})
    git(dirty, "tag", "-a", "-m", "t", "v1.0.0")
    (dirty / "a.txt").write_text("changed after the tag", encoding="utf-8")
    raised = ""
    try:
        ab.acquire({"id": "d", "repo": "x/y",
                    "ref": {"kind": "tag", "tag": "v1.0.0"}},
                   tmp / "w2", {"d": str(dirty)}, True)
    except ab.BuildError as e:
        raised = str(e)
    check("a dirty working tree is fatal",
          "uncommitted changes" in raised, raised[:100])


# --------------------------------------------------------------------------
# B4 — merge, namespacing, provenance
# --------------------------------------------------------------------------

def test_merge_and_provenance(tmp: pathlib.Path) -> None:
    print("\nB4 — two sources merge without colliding, and everything is stamped")
    a = make_repo(tmp / "srcA", {"README.md": f"# Shared Name\n\n{LONG}\n"})
    git(a, "tag", "-a", "-m", "t", "v1.0.0")
    b = make_repo(tmp / "srcB", {"README.md": f"# Shared Name\n\n{LONG}\n"})
    git(b, "tag", "-a", "-m", "t", "v1.0.0")

    manifest = tmp / "two.yaml"
    manifest.write_text(
        "version: 1\npolicy:\n  branches: never\nsources:\n"
        "  - id: alpha\n    tier: A\n    repo: x/alpha\n"
        "    protocol_version: 'v2.0'\n    deployment_status: deployed\n"
        "    ref: {kind: tag, tag: v1.0.0}\n    include: ['**/*.md']\n"
        "  - id: beta\n    tier: B\n    repo: x/beta\n"
        "    ref: {kind: tag, tag: v1.0.0}\n    include: ['**/*.md']\n",
        encoding="utf-8")

    rec = ab.build(str(manifest), str(tmp / "out"), "solc", str(tmp / "w3"),
                   {"alpha": str(a), "beta": str(b)}, True, True, False, None)
    path = pathlib.Path(tmp / "out" / rec["build_id"] / "chunks.jsonl")
    rows = [json.loads(l) for l in open(path)]

    check("both sources are present",
          {c["id"].split(":")[0] for c in rows} == {"alpha", "beta"},
          str({c["id"].split(":")[0] for c in rows}))
    check("identical filenames do not collide",
          len({c["id"] for c in rows}) == len(rows), str(len(rows)))
    check("every chunk carries the build id",
          all(c["corpus_build_id"] == rec["build_id"] for c in rows))
    check("every chunk names its source ref",
          all(c["source_ref"] for c in rows))
    check("the manifest's tier wins over the chunker's guess",
          {c["id"].split(":")[0]: c["tier"] for c in rows}
          == {"alpha": "A", "beta": "B"},
          str({c["id"].split(":")[0]: c["tier"] for c in rows}))
    alpha = [c for c in rows if c["id"].startswith("alpha:")][0]
    check("provenance comes from the manifest, not from guesswork",
          alpha["protocol_version"] == "v2.0"
          and alpha["deployment_status"] == "deployed",
          str((alpha["protocol_version"], alpha["deployment_status"])))
    check("the build record counts what it wrote",
          rec["chunks"]["total"] == len(rows), str(rec["chunks"]["total"]))

    # a second identical run is the same build, byte for byte
    rec2 = ab.build(str(manifest), str(tmp / "out2"), "solc", str(tmp / "w3"),
                    {"alpha": str(a), "beta": str(b)}, True, True, False, None)
    other = pathlib.Path(tmp / "out2" / rec2["build_id"] / "chunks.jsonl")
    check("a repeat build has the same id",
          rec2["build_id"] == rec["build_id"], rec2["build_id"])
    check("...and byte-identical contents",
          path.read_bytes() == other.read_bytes())


# --------------------------------------------------------------------------
# B5 — gates and waivers
# --------------------------------------------------------------------------

def test_gates(tmp: pathlib.Path) -> None:
    print("\nB5 — an unmet gate stops the build, and a waiver is recorded")
    a = make_repo(tmp / "gsrc", {"doc.md": f"# Doc\n\n{LONG}\n"})
    git(a, "tag", "-a", "-m", "t", "v1.0.0")
    manifest = tmp / "gate.yaml"
    manifest.write_text(
        "version: 1\nsources:\n  - id: alpha\n    tier: B\n    repo: x/alpha\n"
        "    ref: {kind: tag, tag: v1.0.0, require_signature: true}\n"
        "    include: ['**/*.md']\n"
        "    metadata_required: [doc_version, effective_date]\n",
        encoding="utf-8")

    raised = ""
    try:
        ab.build(str(manifest), str(tmp / "g1"), "solc", str(tmp / "w4"),
                 {"alpha": str(a)}, False, False, False, None)
    except ab.BuildError as e:
        raised = str(e)
    check("an unsigned required signature stops it",
          "carries no signature" in raised, raised[:100])

    raised = ""
    try:
        ab.build(str(manifest), str(tmp / "g2"), "solc", str(tmp / "w4"),
                 {"alpha": str(a)}, True, False, False, None)
    except ab.BuildError as e:
        raised = str(e)
    check("unmet metadata_required stops it too",
          "metadata_required is not satisfied" in raised, raised[:100])

    rec = ab.build(str(manifest), str(tmp / "g3"), "solc", str(tmp / "w4"),
                   {"alpha": str(a)}, True, True, False, None)
    check("both waivers are recorded in the build record",
          set(rec["waivers"]) == {"signature_not_attested",
                                  "metadata_required_unmet"},
          str(rec["waivers"]))
    check("the gates say false rather than quietly passing",
          rec["gates"]["signature_verified"] is False
          and rec["gates"]["metadata_required"] is False,
          str(rec["gates"]))
    check("gates that need downstream artefacts are null, not true",
          rec["gates"]["address_assertions_hold"] is None
          and rec["gates"]["eval_not_regressed"] is None,
          str(rec["gates"]))
    written = json.load(open(pathlib.Path(tmp / "g3" / rec["build_id"]
                                          / "build.json")))
    check("the record on disk carries the waivers",
          written["waivers"] == rec["waivers"], str(written.get("waivers")))


# --------------------------------------------------------------------------
# B6 — filter semantics and the diff
# --------------------------------------------------------------------------

def test_filter_and_diff(tmp: pathlib.Path) -> None:
    print("\nB6 — include then exclude then verification_only, and the diff")
    a = make_repo(tmp / "fsrc", {
        "keep.md": f"# Keep\n\n{LONG}\n",
        "drop.md": f"# Drop\n\n{LONG}\n",
        "verify-only.md": f"# VerifyOnly\n\n{LONG}\n",
        "elsewhere/other.md": f"# Other\n\n{LONG}\n",
    })
    git(a, "tag", "-a", "-m", "t", "v1.0.0")
    manifest = tmp / "filt.yaml"
    manifest.write_text(
        "version: 1\nsources:\n  - id: alpha\n    tier: B\n    repo: x/alpha\n"
        "    ref: {kind: tag, tag: v1.0.0}\n"
        "    include: ['*.md']\n"
        "    exclude: ['drop.md']\n"
        "    verification_only: ['verify-only.md']\n",
        encoding="utf-8")
    rec = ab.build(str(manifest), str(tmp / "f1"), "solc", str(tmp / "w5"),
                   {"alpha": str(a)}, True, True, False, None)
    rows = [json.loads(l) for l in
            open(pathlib.Path(tmp / "f1" / rec["build_id"] / "chunks.jsonl"))]
    paths = {c["path"] for c in rows}
    check("included files are chunked", "keep.md" in paths, str(paths))
    check("excluded files are not", "drop.md" not in paths, str(paths))
    check("verification_only survives include but never reaches a chunker",
          "verify-only.md" not in paths, str(paths))
    check("a file outside the include glob is not chunked",
          "elsewhere/other.md" not in paths, str(paths))

    # an include glob matching nothing is a typo, not an empty set
    manifest.write_text(
        "version: 1\nsources:\n  - id: alpha\n    tier: B\n    repo: x/alpha\n"
        "    ref: {kind: tag, tag: v1.0.0}\n    include: ['typo/**/*.md']\n",
        encoding="utf-8")
    raised = ""
    try:
        ab.build(str(manifest), str(tmp / "f2"), "solc", str(tmp / "w5"),
                 {"alpha": str(a)}, True, True, False, None)
    except Exception as e:                          # noqa: BLE001
        raised = str(e)
    check("an include glob matching nothing is fatal",
          "matched no markdown" in raised, raised[:120])

    before = pathlib.Path(tmp / "f1" / rec["build_id"] / "chunks.jsonl")
    diff = ab.corpus_diff(before, [])
    check("the diff reports everything removed",
          diff["counts"]["removed"] == len(rows)
          and diff["counts"]["added"] == 0, str(diff["counts"]))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--solc", help="unused today; accepted for symmetry")
    ap.parse_args()

    test_build_id()
    for fn in (test_signatures, test_policy, test_merge_and_provenance,
               test_gates, test_filter_and_diff):
        td = tempfile.mkdtemp()
        try:
            fn(pathlib.Path(td))
        finally:
            shutil.rmtree(td, ignore_errors=True)

    print(f"\n{len(FAILURES)} failure(s)"
          + (": " + ", ".join(FAILURES) if FAILURES else ""))
    return len(FAILURES)


if __name__ == "__main__":
    sys.exit(main())
