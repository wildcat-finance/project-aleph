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

        # pinning the signer: the right key passes, a valid signature from the
        # wrong key is a different claim and is refused
        fpr = subprocess.run(["gpg", "--list-keys", "--with-colons"],
                             capture_output=True, text=True,
                             env=dict(os.environ, **env)).stdout
        fingerprint = next(l.split(":")[9] for l in fpr.splitlines()
                           if l.startswith("fpr"))
        pinned = {**src, "ref": {**src["ref"],
                                 "signer_fingerprint": fingerprint}}
        out = ab.resolve_ref(pinned, repo, allow_unverified=False)
        check("a signature from the pinned key passes",
              out["signature"] == "verified" and out.get("signer_pinned"),
              str(out.get("signature")))
        check("...and the fingerprint is recorded",
              out.get("signed_by") == fingerprint, str(out.get("signed_by")))

        wrong_fpr = {**src, "ref": {**src["ref"],
                                    "signer_fingerprint": "0" * 40}}
        raised = ""
        try:
            ab.resolve_ref(wrong_fpr, repo, allow_unverified=True)
        except ab.BuildError as e:
            raised = str(e)
        check("a valid signature from an unpinned key is refused",
              "manifest pins" in raised and "Not waivable" in raised,
              raised[:140])

        unpinned = ab.resolve_ref(src, repo, allow_unverified=False)
        check("an unpinned signer is flagged rather than assumed good",
              unpinned.get("signer_pinned") is False,
              str(unpinned.get("signer_pinned")))
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

def test_keyring(tmp: pathlib.Path) -> None:
    print("\nB7 — verification uses the shipped keyring, not the machine's")
    home = tmp / "gnupg"
    home.mkdir(mode=0o700)
    env = {"GNUPGHOME": str(home)}

    def genkey(name):
        subprocess.run(["gpg", "--batch", "--passphrase", "",
                        "--quick-generate-key", f"{name} <{name}@example.invalid>",
                        "default", "default", "never"],
                       capture_output=True, text=True,
                       env=dict(os.environ, **env))
        listing = subprocess.run(["gpg", "--list-keys", "--with-colons", name],
                                 capture_output=True, text=True,
                                 env=dict(os.environ, **env)).stdout
        return next(l.split(":")[9] for l in listing.splitlines()
                    if l.startswith("fpr"))

    fpr_release = genkey("release")
    fpr_rogue = genkey("rogue")
    keyfile = tmp / "release.asc"
    keyfile.write_bytes(subprocess.run(
        ["gpg", "--armor", "--export", fpr_release], capture_output=True,
        env=dict(os.environ, **env)).stdout)

    # a tag signed by the rogue key — which is present on this machine
    repo = make_repo(tmp / "kr", {"a.md": f"# A\n\n{LONG}\n"})
    git(repo, "config", "user.signingkey", fpr_rogue)
    git(repo, "tag", "-s", "-m", "signed by the wrong key", "v1.0.0",
        env_extra=env)

    manifest = tmp / "kr.yaml"
    manifest.write_text(
        "version: 1\nsources:\n  - id: alpha\n    tier: B\n    repo: x/alpha\n"
        "    ref:\n      kind: tag\n      tag: v1.0.0\n"
        "      require_signature: true\n"
        f"      signer_fingerprint: '{fpr_release}'\n"
        f"      signer_key_file: '{keyfile}'\n"
        "    include: ['**/*.md']\n", encoding="utf-8")

    # the ambient keyring has the rogue key; the shipped one does not
    os.environ["GNUPGHOME"] = str(home)
    try:
        raised = ""
        try:
            ab.build(str(manifest), str(tmp / "k1"), "solc", str(tmp / "wk"),
                     {"alpha": str(repo)}, False, True, False, None)
        except ab.BuildError as e:
            raised = str(e)
        check("a key trusted by the machine but not shipped does not count",
              "public key" in raised, raised[:140])

        # now sign with the release key and it passes, no ambient help needed
        git(repo, "config", "user.signingkey", fpr_release)
        git(repo, "tag", "-s", "-f", "-m", "signed properly", "v1.0.0",
            env_extra=env)
        rec = ab.build(str(manifest), str(tmp / "k2"), "solc", str(tmp / "wk"),
                       {"alpha": str(repo)}, False, True, False, None)
        check("the shipped key verifies its own signature",
              rec["gates"]["signature_verified"] is True, str(rec["gates"]))
        check("and the signer is pinned, not merely valid",
              rec["gates"]["signer_pinned"] is True, str(rec["gates"]))
        check("no waiver was needed", rec["waivers"] == [], str(rec["waivers"]))
        check("the build records which key file was trusted",
              rec["keyring"]["alpha"]["fingerprints"] == [fpr_release],
              str(rec.get("keyring")))

        # A key that signs with a dedicated signing subkey — the ordinary
        # shape of a GitHub-registered key. GnuPG reports the subkey as the
        # signer and the primary last on the VALIDSIG line; the manifest pins
        # the primary, so the two must not be confused.
        subprocess.run(["gpg", "--batch", "--passphrase", "",
                        "--quick-add-key", fpr_release, "default", "sign",
                        "never"], capture_output=True,
                       env=dict(os.environ, **env))
        listing = subprocess.run(["gpg", "--list-keys", "--with-colons",
                                  fpr_release], capture_output=True, text=True,
                                 env=dict(os.environ, **env)).stdout
        subkeys, insub = [], False
        for line in listing.splitlines():
            if line.startswith("sub:"):
                insub = True
            elif line.startswith("fpr:") and insub:
                subkeys.append(line.split(":")[9])
                insub = False
        check("the release key now has a signing subkey", bool(subkeys),
              str(subkeys))
        if subkeys:
            # The shipped public key must be re-exported after the subkey is
            # added: a key file that predates the signing subkey cannot verify
            # its signatures, and fails as "no public key" — which reads like a
            # missing key rather than a stale one.
            stale = ab.prepare_keyring
            raised = ""
            git(repo, "config", "user.signingkey", subkeys[-1] + "!")
            git(repo, "tag", "-s", "-f", "-m", "signed by subkey", "v1.0.0",
                env_extra=env)
            try:
                ab.build(str(manifest), str(tmp / "k3b"), "solc",
                         str(tmp / "wk2b"), {"alpha": str(repo)}, False, True,
                         False, None)
            except ab.BuildError as e:
                raised = str(e)
            check("a key file predating the signing subkey does not verify",
                  "public key" in raised, raised[:120])
            keyfile.write_bytes(subprocess.run(
                ["gpg", "--armor", "--export", fpr_release],
                capture_output=True, env=dict(os.environ, **env)).stdout)
            raw = git(repo, "verify-tag", "--raw", "v1.0.0",
                      env_extra=env).stderr
            check("the signature is made by the subkey",
                  subkeys[-1] in raw.split("VALIDSIG")[1].split()[0]
                  if "VALIDSIG" in raw else False, raw[:120])
            check("...but the fingerprint pinned on is the primary",
                  ab._validsig_fingerprint(raw) == fpr_release,
                  str(ab._validsig_fingerprint(raw)))
            rec = ab.build(str(manifest), str(tmp / "k4"), "solc",
                           str(tmp / "wk3"), {"alpha": str(repo)}, False, True,
                           False, None)
            check("a subkey-signed tag satisfies the pin on its primary",
                  rec["gates"]["signature_verified"] is True
                  and rec["gates"]["signer_pinned"] is True, str(rec["gates"]))

        # a key file that does not contain the pinned key is caught at import
        other = tmp / "rogue.asc"
        other.write_bytes(subprocess.run(
            ["gpg", "--armor", "--export", fpr_rogue], capture_output=True,
            env=dict(os.environ, **env)).stdout)
        swapped = manifest.read_text().replace(str(keyfile), str(other))
        (tmp / "kr2.yaml").write_text(swapped, encoding="utf-8")
        raised = ""
        try:
            ab.build(str(tmp / "kr2.yaml"), str(tmp / "k3"), "solc",
                     str(tmp / "wk2"), {"alpha": str(repo)}, False, True,
                     False, None)
        except ab.BuildError as e:
            raised = str(e)
        check("a swapped key file is caught before any tag is looked at",
              "does not contain the pinned key" in raised, raised[:140])
    finally:
        os.environ.pop("GNUPGHOME", None)


def test_watched_documents(tmp: pathlib.Path) -> None:
    print("\nB8 — a watched document that changes is noticed, not blocked")
    import hashlib
    body = b"Terms of Use, version one. " + b"x" * 200
    a = make_repo(tmp / "wsrc", {"doc.md": f"# Doc\n\n{LONG}\n",
                                 "legal/tou.txt": body.decode()})
    git(a, "tag", "-a", "-m", "t", "v1.0.0")
    digest = hashlib.sha256((a / "legal" / "tou.txt").read_bytes()).hexdigest()

    manifest = tmp / "w.yaml"
    manifest.write_text(
        "version: 1\nsources:\n  - id: alpha\n    tier: B\n    repo: x/alpha\n"
        "    ref: {kind: tag, tag: v1.0.0}\n    include: ['**/*.md']\n"
        "    watch:\n"
        "      - path: 'legal/tou.txt'\n"
        f"        sha256: '{digest}'\n", encoding="utf-8")

    rec = ab.build(str(manifest), str(tmp / "w1"), "solc", str(tmp / "ww"),
                   {"alpha": str(a)}, True, True, False, None)
    check("an unchanged document reports unchanged",
          rec["watch"]["alpha"][0]["status"] == "unchanged",
          str(rec["watch"]))
    check("...and the gate is true",
          rec["gates"]["watched_documents_unchanged"] is True,
          str(rec["gates"]["watched_documents_unchanged"]))

    # the revision lands
    (a / "legal" / "tou.txt").write_text(
        "Terms of Use, version TWO, substantively revised. " + "y" * 200,
        encoding="utf-8")
    git(a, "add", "-A")
    git(a, "commit", "-qm", "substantive ToU revision")
    git(a, "tag", "-a", "-f", "-m", "t", "v1.0.0")

    rec = ab.build(str(manifest), str(tmp / "w2"), "solc", str(tmp / "ww"),
                   {"alpha": str(a)}, True, True, False, None)
    w = rec["watch"]["alpha"][0]
    check("a revised document is flagged CHANGED", w["status"] == "CHANGED",
          str(w["status"]))
    check("both digests are recorded, so the diff is reviewable",
          w["expected"] == digest and w["actual"] != digest, str(w))
    check("the gate goes false",
          rec["gates"]["watched_documents_unchanged"] is False,
          str(rec["gates"]["watched_documents_unchanged"]))
    check("but the build still succeeds — a revision is not a fault",
          rec["chunks"]["total"] > 0, str(rec["chunks"]["total"]))

    # frontmatter is metadata, not the document: a watch scoped to the body
    # must survive the very PR that adds effective_date and doc_version
    fm = tmp / "fmsrc"
    body = "# Terms\n\nThe operative legal text, unchanged.\n" + "z" * 200
    b = make_repo(fm, {"doc.md": f"# Doc\n\n{LONG}\n",
                       "legal/tou.md": f"---\ndescription: 'v1'\n---\n\n{body}"})
    git(b, "tag", "-a", "-m", "t", "v1.0.0")
    body_digest = hashlib.sha256(body.encode()).hexdigest()
    fman = tmp / "fm.yaml"
    fman.write_text(
        "version: 1\nsources:\n  - id: alpha\n    tier: B\n    repo: x/alpha\n"
        "    ref: {kind: tag, tag: v1.0.0}\n    include: ['**/*.md']\n"
        "    watch:\n      - path: 'legal/tou.md'\n"
        "        strip_frontmatter: true\n"
        f"        sha256: '{body_digest}'\n", encoding="utf-8")
    rec = ab.build(str(fman), str(tmp / "f1"), "solc", str(tmp / "fw"),
                   {"alpha": str(fm)}, True, True, False, None)
    check("a body-scoped watch matches on the body",
          rec["watch"]["alpha"][0]["status"] == "unchanged"
          and rec["watch"]["alpha"][0]["scope"] == "body",
          str(rec["watch"]["alpha"][0]))

    (fm / "legal" / "tou.md").write_text(
        f"---\ndescription: 'v1'\neffective_date: \"2025-01-16\"\n"
        f"doc_version: \"2025-01-16\"\n---\n\n{body}", encoding="utf-8")
    git(fm, "add", "-A"); git(fm, "commit", "-qm", "add metadata")
    git(fm, "tag", "-a", "-f", "-m", "t", "v1.0.0")
    rec = ab.build(str(fman), str(tmp / "f2"), "solc", str(tmp / "fw"),
                   {"alpha": str(fm)}, True, True, False, None)
    check("adding frontmatter does not trip it",
          rec["watch"]["alpha"][0]["status"] == "unchanged",
          str(rec["watch"]["alpha"][0]["status"]))

    (fm / "legal" / "tou.md").write_text(
        f"---\ndescription: 'v1'\n---\n\n{body}\n\nAn added clause.",
        encoding="utf-8")
    git(fm, "add", "-A"); git(fm, "commit", "-qm", "revise the text")
    git(fm, "tag", "-a", "-f", "-m", "t", "v1.0.0")
    rec = ab.build(str(fman), str(tmp / "f3"), "solc", str(tmp / "fw"),
                   {"alpha": str(fm)}, True, True, False, None)
    check("...but changing the text does",
          rec["watch"]["alpha"][0]["status"] == "CHANGED",
          str(rec["watch"]["alpha"][0]["status"]))

    # a watched path that disappears is also worth knowing about
    (a / "legal" / "tou.txt").unlink()
    git(a, "add", "-A")
    git(a, "commit", "-qm", "removed")
    git(a, "tag", "-a", "-f", "-m", "t", "v1.0.0")
    rec = ab.build(str(manifest), str(tmp / "w3"), "solc", str(tmp / "ww"),
                   {"alpha": str(a)}, True, True, False, None)
    check("a watched document that vanishes is reported missing",
          rec["watch"]["alpha"][0]["status"] == "missing",
          str(rec["watch"]["alpha"][0]["status"]))


def test_scoped_metadata(tmp: pathlib.Path) -> None:
    print("\nB9 — metadata_required can be scoped to the documents it fits")
    a = make_repo(tmp / "msrc", {
        "legal/terms.md": f'---\neffective_date: "2025-02-12"\n'
                          f'doc_version: "sha256:abc"\n---\n\n# Terms\n\n{LONG}\n',
        "legal/undated.md": f"# Undated\n\n{LONG}\n",
        "guide.md": f"# Guide\n\n{LONG}\n",
    })
    git(a, "tag", "-a", "-m", "t", "v1.0.0")

    def manifest(spec: str) -> str:
        path = tmp / f"m{abs(hash(spec)) % 9999}.yaml"
        path.write_text(
            "version: 1\nsources:\n  - id: alpha\n    tier: B\n"
            "    repo: x/alpha\n    ref: {kind: tag, tag: v1.0.0}\n"
            "    include: ['**/*.md']\n" + spec, encoding="utf-8")
        return str(path)

    # scoped, and one document in scope is missing both fields
    strict = manifest("    metadata_required:\n      paths: ['legal/**']\n"
                      "      fields: [doc_version, effective_date]\n")
    raised = ""
    try:
        ab.build(strict, str(tmp / "m1"), "solc", str(tmp / "mw"),
                 {"alpha": str(a)}, True, False, False, None)
    except ab.BuildError as e:
        raised = str(e)
    check("an in-scope document missing the fields stops the build",
          "legal/**" in raised and "metadata_required" in raised, raised[:140])
    check("...and the message says how many chunks were in scope",
          "chunks); missing on" in raised, raised[:200])

    # give it what it asks for
    (a / "legal" / "undated.md").write_text(
        f'---\neffective_date: "2025-01-16"\ndoc_version: "2025-01-16"\n'
        f'---\n\n# Undated\n\n{LONG}\n', encoding="utf-8")
    git(a, "add", "-A")
    git(a, "commit", "-qm", "dates")
    git(a, "tag", "-a", "-f", "-m", "t", "v1.0.0")
    rec = ab.build(strict, str(tmp / "m2"), "solc", str(tmp / "mw"),
                   {"alpha": str(a)}, True, False, False, None)
    check("with both in scope satisfied, the gate passes",
          rec["gates"]["metadata_required"] is True, str(rec["gates"]))
    check("and no waiver was needed", rec["waivers"] == [], str(rec["waivers"]))

    rows = [json.loads(l) for l in
            open(pathlib.Path(tmp / "m2" / rec["build_id"] / "chunks.jsonl"))]
    legal = [c for c in rows if c["path"].startswith("legal/")]
    other = [c for c in rows if not c["path"].startswith("legal/")]
    check("in-scope chunks carry the dates as schema fields",
          all(c["effective_date"] and c["doc_version"] for c in legal),
          str([(c["path"], c["effective_date"]) for c in legal][:2]))
    check("out-of-scope chunks are left alone, not backfilled",
          all(not c["effective_date"] for c in other),
          str([(c["path"], c["effective_date"]) for c in other][:2]))

    # the bare-list form still means every document
    everywhere = manifest("    metadata_required: [effective_date]\n")
    raised = ""
    try:
        ab.build(everywhere, str(tmp / "m3"), "solc", str(tmp / "mw"),
                 {"alpha": str(a)}, True, False, False, None)
    except ab.BuildError as e:
        raised = str(e)
    check("an unscoped list still applies to everything",
          "every document" in raised, raised[:140])


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
    check("signer_pinned is null when no signature was verified, not true",
          rec["gates"]["signer_pinned"] is None,
          str(rec["gates"]["signer_pinned"]))
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
    for fn in (test_signatures, test_keyring, test_watched_documents,
               test_scoped_metadata, test_policy,
               test_merge_and_provenance,
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
