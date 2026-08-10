#!/usr/bin/env python3
"""
build.py — Project Aleph

`manifest.yaml` in, a stamped and validated corpus out. The driver owns source
acquisition, manifest filtering, both chunkers, provenance stamping, schema
validation, and the corpus build record so a build does not depend on a person
retyping manifest policy as command-line options.

    python3 ingest/build.py --manifest manifest.yaml --out corpus/

Stages, in order, all fatal on failure:

    acquire   resolve every ref exactly as the manifest names it, verifying
              the signature where one is required and the object hashes always
    filter    include, then exclude, then verification_only — fail-loud
    parse     both chunkers, over what the filter selected
    enrich    stamp provenance onto every chunk from the resolved refs
    validate  schema.validate() over the merged set
    publish   corpus/<build_id>/{chunks.jsonl,build.json}

Embedding, the address assertions and the eval gate live downstream; this
produces the artefact they consume.

The build id is derived from the inputs — manifest bytes, resolved commits,
chunker and compiler versions — and never from the clock, because "the same
manifest produces the same corpus" is only a real claim if the identity of a
build is a function of what went into it. Two runs a week apart from an
unchanged manifest produce the same id, and `--against` will say so.

Where a gate cannot be satisfied the build stops. Every waiver is an explicit
flag and every waiver used is recorded in build.json, so a corpus produced
without signature verification can never be mistaken for one produced with it.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import os
import shutil
import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

HERE = pathlib.Path(__file__).resolve().parent


def _load(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_schema = _load("aleph_schema", HERE / "schema.py")
_sol = _load("aleph_solidity", HERE / "chunkers" / "solidity.py")
_md = _load("aleph_markdown", HERE / "chunkers" / "markdown.py")


class BuildError(Exception):
    """A condition that must stop a build rather than warn."""


def _run(args: list[str], cwd: pathlib.Path | None = None,
         env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                          env=(dict(os.environ, **env) if env else None))


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --------------------------------------------------------------------------
# 1. acquire
# --------------------------------------------------------------------------

def prepare_keyring(sources: list[dict], manifest_dir: pathlib.Path,
                    workdir: pathlib.Path) -> tuple[dict, dict]:
    """
    An ephemeral keyring holding exactly the keys the manifest declares.

    Verification runs against this and nothing else, so a build cannot be made
    to pass by importing a key on the machine that runs it — which is what
    would otherwise happen, since `git verify-tag` consults whatever keyring
    the invoking user happens to have. Two independent conditions have to hold
    for a signature to count: the key was shipped with the corpus definition,
    and its fingerprint is the one the manifest names.

    The declared fingerprint is checked against the key file at import time, so
    a swapped key is caught before any tag is looked at. The manifest is the
    authority; the file is only how the bytes travel.
    """
    declared = [(s, (s.get("ref") or {}).get("signer_key_file"))
                for s in sources]
    declared = [(s, k) for s, k in declared if k]
    if not declared:
        return {}, {}

    if shutil.which("gpg") is None:
        raise BuildError("a signer_key_file is declared but gpg is not "
                         "installed; signatures cannot be verified")

    # GnuPG creates agent sockets beneath GNUPGHOME. Unix socket paths are
    # short (typically 104–108 bytes), so an arbitrarily deep checkout can
    # make verification fail before a key is imported. This keyring is truly
    # ephemeral; keep its private home beneath the short system path instead.
    home = pathlib.Path(tempfile.mkdtemp(prefix="aleph-gpg-", dir="/tmp"))
    home.chmod(0o700)
    env = {"GNUPGHOME": str(home)}
    report: dict = {}

    for source, rel in declared:
        path = pathlib.Path(rel)
        if not path.is_absolute():
            path = manifest_dir / rel
        if not path.exists():
            cleanup_keyring(env)
            raise BuildError(
                f"{source['id']}: signer_key_file {path} does not exist. "
                "The corpus definition ships the key it trusts; without it "
                "there is nothing to verify against.")
        r = _run(["gpg", "--batch", "--quiet", "--import", str(path)], env=env)
        if r.returncode != 0:
            cleanup_keyring(env)
            raise BuildError(f"{source['id']}: importing {path} failed: "
                             f"{r.stderr[:200]}")
        listing = _run(["gpg", "--list-keys", "--with-colons"], env=env).stdout
        # Only primary keys. `--with-colons` emits an `fpr` record for every
        # subkey too, and a modern `--quick-generate-key` produces an
        # encryption subkey as a matter of course — recording those alongside
        # the primary would list fingerprints that never sign anything as
        # though they were signing identities.
        fingerprints, primary = [], False
        for line in listing.splitlines():
            if line.startswith("pub:"):
                primary = True
            elif line.startswith(("sub:", "uid:")):
                primary = False
            elif line.startswith("fpr:") and primary:
                fingerprints.append(line.split(":")[9])
                primary = False
        expected = ((source.get("ref") or {}).get("signer_fingerprint")
                    or "").replace(" ", "").upper()
        if expected and expected not in fingerprints:
            cleanup_keyring(env)
            raise BuildError(
                f"{source['id']}: {path} does not contain the pinned key\n"
                f"  manifest pins  {expected}\n"
                f"  file provides  {fingerprints}\n"
                "  The key file has been changed, or the manifest has.")
        report[source["id"]] = {"key_file": str(rel),
                                "fingerprints": fingerprints}
        print(f"  [{source['id']}] keyring: imported {path.name} "
              f"({len(fingerprints)} key(s))")
    return env, report


def cleanup_keyring(env: dict) -> None:
    """Stop the private GPG agent and remove its ephemeral home."""
    home = env.get("GNUPGHOME")
    if not home:
        return
    _run(["gpgconf", "--kill", "all"], env=env)
    shutil.rmtree(home, ignore_errors=True)


def _validsig_fingerprint(raw: str) -> str | None:
    """
    The primary key fingerprint from `git verify-tag --raw` output.

    GnuPG's VALIDSIG status line ends with the *primary* fingerprint, which is
    what a manifest should pin: GOODSIG carries only a short key id, and
    KEY_CONSIDERED appears for keys that were merely looked at.
    """
    for line in raw.splitlines():
        if "VALIDSIG" in line:
            parts = line.split()
            if len(parts) >= 3:
                return parts[-1].upper()
    return None


def resolve_ref(source: dict, repo: pathlib.Path, allow_unverified: bool,
                gpg_env: dict | None = None) -> dict:
    """
    Resolve one source to an immutable object, and say how much that resolution
    is worth.

    Three separate questions, deliberately not collapsed into one boolean:

      does the tag object have the hash the manifest names?   — always checkable
      does the commit have the hash the manifest names?       — always checkable
      is the tag signed by someone we trust?                  — needs their key

    The first two pin the build to exact objects with no key material at all.
    Only the third is a trust statement, and only the third can be waived. A
    build that skipped it is marked as such for as long as the corpus exists.
    """
    ref = source.get("ref") or {}
    kind = ref.get("kind")
    if kind == "branch" or ref.get("branch"):
        raise BuildError(
            f"{source['id']}: ref kind {kind!r} tracks a moving target; "
            "policy.branches is 'never'")

    out: dict = {"kind": kind, "signature": "not_required"}
    tag = ref.get("tag")

    if tag:
        out["tag"] = tag
        r = _run(["git", "rev-parse", f"refs/tags/{tag}"], repo)
        if r.returncode != 0:
            raise BuildError(f"{source['id']}: tag {tag!r} not found in {repo}")
        tag_sha = r.stdout.strip()
        obj_type = _run(["git", "cat-file", "-t", tag_sha], repo).stdout.strip()
        out["tag_object"] = tag_sha
        out["tag_object_type"] = obj_type

        declared_obj = ref.get("tag_object")
        if declared_obj and not tag_sha.startswith(declared_obj):
            raise BuildError(
                f"{source['id']}: tag {tag!r} points at object {tag_sha[:12]}, "
                f"manifest names {declared_obj}. The tag has been moved.")

        if ref.get("lightweight") and obj_type == "tag":
            raise BuildError(
                f"{source['id']}: manifest says {tag!r} is lightweight but it "
                "is an annotated tag object — the manifest is out of date")

        if ref.get("require_signature"):
            # Three outcomes, and they are not the same thing. A signature
            # that fails is an attack signal. A signature that is absent, or
            # that cannot be checked for want of a key, is a missing control —
            # bad, but bad in a way a human can knowingly accept for a build.
            # Collapsing them would either block every build forever or wave
            # through the one case that must never be waved through.
            v = _run(["git", "verify-tag", "--raw", tag], repo, env=gpg_env)
            err = (v.stderr or "") + (v.stdout or "")
            if v.returncode == 0:
                out["signature"] = "verified"
                out["signed_by"] = _validsig_fingerprint(err)
                # A valid signature by *someone* is not the claim the manifest
                # is making. `git verify-tag` succeeds for any key that happens
                # to be in the keyring, so without a pinned fingerprint this
                # gate proves far less than it looks like it proves.
                expected = (ref.get("signer_fingerprint") or "").replace(" ", "").upper()
                if expected:
                    if out["signed_by"] != expected:
                        out["signature"] = "wrong_signer"
                        raise BuildError(
                            f"{source['id']}: {tag!r} is validly signed, but by "
                            f"{out['signed_by']}\n"
                            f"  manifest pins {expected}\n"
                            "  A signature from an unexpected key is not a "
                            "weaker signature, it is a different claim. Not "
                            "waivable.")
                    out["signer_pinned"] = True
                else:
                    out["signer_pinned"] = False
                    print(f"  [{source['id']}] WARNING: signature is valid but "
                          "no signer_fingerprint is pinned — any key in the "
                          "keyring would satisfy this")
            elif "no signature found" in err.lower():
                out["signature"] = "unsigned"
                if not allow_unverified:
                    raise BuildError(
                        f"{source['id']}: {tag!r} carries no signature at all.\n"
                        f"  Tag object {out['tag_object'][:12]} is annotated but "
                        "unsigned, so require_signature: true cannot be met by "
                        "any build of this ref.\n"
                        "  The tag object and commit hashes do match the manifest, "
                        "so the build is pinned to exact objects — it is simply "
                        "not attested to a signer.\n"
                        "  Sign the tag, or change the manifest deliberately. "
                        "--allow-unverified-signature records the gap and "
                        "continues.")
            elif "NO_PUBKEY" in err or "No public key" in err:
                out["signature"] = "no_public_key"
                if not allow_unverified:
                    raise BuildError(
                        f"{source['id']}: cannot verify the signature on {tag!r} "
                        "— the signer's public key is not in this keyring.\n"
                        "  The tag object and commit hashes still match the "
                        "manifest, so the build is pinned; it is not attested.\n"
                        "  Import the key, or pass --allow-unverified-signature "
                        "to record the gap in build.json and continue.")
            else:
                out["signature"] = "bad"
                raise BuildError(
                    f"{source['id']}: signature verification FAILED for {tag!r}\n"
                    f"  {err.strip()[:300]}\n"
                    "  A present-but-invalid signature is not waivable.")
        commit = _run(["git", "rev-parse", f"{tag}^{{}}"], repo).stdout.strip()
    else:
        commit = _run(["git", "rev-parse", ref.get("commit", "HEAD")],
                      repo).stdout.strip()

    if not commit:
        raise BuildError(f"{source['id']}: could not resolve a commit")
    declared = ref.get("commit")
    if declared and not commit.startswith(declared):
        raise BuildError(
            f"{source['id']}: resolves to {commit[:12]}, manifest names "
            f"{declared}. Signature verification precedes resolution, and "
            "resolution must land where the manifest says.")
    out["commit"] = commit
    return out


def acquire(source: dict, workdir: pathlib.Path, local: dict[str, str],
            allow_unverified: bool,
            gpg_env: dict | None = None) -> tuple[pathlib.Path, dict]:
    sid = source["id"]
    if sid in local:
        repo = pathlib.Path(local[sid]).resolve()
        if not (repo / ".git").exists():
            raise BuildError(f"{sid}: --source-path {repo} is not a git checkout")
        origin = "local checkout (not acquired by this build)"
    else:
        repo = workdir / sid
        url = f"https://github.com/{source['repo']}.git"
        if not (repo / ".git").exists():
            repo.parent.mkdir(parents=True, exist_ok=True)
            r = _run(["git", "clone", "--quiet", url, str(repo)])
            if r.returncode != 0:
                raise BuildError(f"{sid}: clone failed: {r.stderr[:200]}")
        r = _run(["git", "fetch", "--quiet", "--tags", "origin"], repo)
        if r.returncode != 0:
            raise BuildError(f"{sid}: fetch failed: {r.stderr[:200]}")
        origin = url

    resolution = resolve_ref(source, repo, allow_unverified, gpg_env)
    resolution["origin"] = origin
    r = _run(["git", "checkout", "--quiet", "--detach", resolution["commit"]], repo)
    if r.returncode != 0:
        raise BuildError(f"{sid}: checkout {resolution['commit'][:12]} failed: "
                         f"{r.stderr[:200]}")
    # A dirty tree means the bytes chunked are not the bytes the ref names.
    dirty = _run(["git", "status", "--porcelain"], repo).stdout.strip()
    if dirty:
        raise BuildError(
            f"{sid}: working tree at {repo} has uncommitted changes; the corpus "
            f"would not match {resolution['commit'][:12]}\n  {dirty.splitlines()[0]}")
    return repo, resolution


# --------------------------------------------------------------------------
# 2. filter
# --------------------------------------------------------------------------

def check_watched(source: dict, repo: pathlib.Path) -> list[dict]:
    """
    Compare the digest of every watched document against the manifest.

    The ref already pins what gets ingested, so this is not a reproducibility
    control — it is an alarm for the one moment reproducibility cannot help
    with: somebody deciding whether to move the pin. A document Aleph quotes
    verbatim can be substantively revised between promotions, and an answer
    citing superseded terms is indistinguishable from a correct one.

    `strip_frontmatter` hashes the document body alone. What is being watched
    is the legal text, not the GitBook metadata above it, and pinning the whole
    file would make every `description:` edit look like a revision — including
    the one that adds `effective_date` and `doc_version`. A watch that cries
    wolf on its own maintenance is a watch people learn to ignore.

    Not fatal. A promotion carrying a revision is legitimate; it must simply
    not pass unnoticed, so the result lands in build.json where the
    corpus_diff_reviewed gate can see it.
    """
    results = []
    for entry in source.get("watch") or []:
        path = repo / entry["path"]
        expected = (entry.get("sha256") or "").lower()
        if not path.exists():
            results.append({"path": entry["path"], "status": "missing",
                            "expected": expected, "actual": None})
            continue
        raw = path.read_bytes()
        if entry.get("strip_frontmatter"):
            if raw.startswith(b"---"):
                parts = raw.split(b"---", 2)
                if len(parts) > 2:
                    raw = parts[2].lstrip(b"\r\n")
        actual = _sha256(raw)
        results.append({
            "path": entry["path"],
            "status": "unchanged" if actual == expected else "CHANGED",
            "expected": expected,
            "actual": actual,
            "scope": "body" if entry.get("strip_frontmatter") else "file",
        })
    return results


def markdown_globs(source: dict) -> list[str]:
    """
    The markdown half of a source's include list. A source can name Solidity
    and Markdown in one `include`; the Solidity side is chunked from deployment
    inputs rather than from the tree, so only the `.md` globs are the markdown
    chunker's business.
    """
    return [g for g in (source.get("include") or []) if g.endswith(".md")]


def filter_report(source: dict) -> dict:
    return {
        "include": source.get("include") or [],
        "markdown_include": markdown_globs(source),
        "exclude": source.get("exclude") or [],
        "verification_only": source.get("verification_only") or [],
    }


# --------------------------------------------------------------------------
# 3 + 4. parse and enrich
# --------------------------------------------------------------------------

def chunk_source(source: dict, repo: pathlib.Path, solc: str,
                 report: dict) -> list:
    sid = source["id"]
    chunks: list = []

    sol_cfg = source.get("solidity_chunking")
    if sol_cfg:
        pattern = sol_cfg.get("inputs", "")
        inputs = sorted(str(p) for p in repo.glob(pattern))
        if not inputs:
            raise BuildError(
                f"{sid}: solidity_chunking.inputs {pattern!r} matched nothing "
                f"under {repo}")
        print(f"  [{sid}] solidity: {len(inputs)} compilation unit(s)")
        got, dropped = _sol.build(inputs, solc, list(sol_cfg.get("include") or []),
                                  expect_solc=str(sol_cfg.get("solc") or "") or None)
        report["solidity"] = {"inputs": len(inputs), "chunks": len(got),
                              "duplicates_folded": dropped,
                              "include": list(sol_cfg.get("include") or [])}
        chunks += got

    md_inc = markdown_globs(source)
    if md_inc:
        excludes = list(source.get("exclude") or [])
        # verification_only survives include but must never reach a chunker
        excludes += list(source.get("verification_only") or [])
        summary = "SUMMARY.md" if (repo / "SUMMARY.md").exists() else None
        print(f"  [{sid}] markdown: {len(md_inc)} include glob(s)"
              + (", SUMMARY hierarchy" if summary else ", no hierarchy"))
        got = _md.chunk_tree(str(repo), excludes, summary, includes=md_inc)
        report["markdown"] = {"chunks": len(got), "include": md_inc,
                              "hierarchy": bool(summary)}
        chunks += got

    if not chunks:
        raise BuildError(f"{sid}: produced no chunks")
    return chunks


def namespace_ids(chunks: list, source_id: str) -> None:
    """
    Prefix every chunk id with its source.

    A chunker's ids are unique within the tree it was given, which is all it can
    know. Two sources both having a `README.md` is not exotic — v2-protocol and
    wildcat-docs both do — and their chunks collided the first time anything
    merged more than one markdown source, which is to say the first time this
    driver ran. Ids reach citations, so they are namespaced visibly rather than
    hashed: `wildcat-docs:overview/faqs.md#withdrawals` says where it came from.

    `detail.aliases` holds ids too, and travels with them.
    """
    for c in chunks:
        c.id = f"{source_id}:{c.id}"
        aliases = c.detail.get("aliases")
        if aliases:
            c.detail["aliases"] = [f"{source_id}:{a}" for a in aliases]


def enrich(chunks: list, source: dict, resolution: dict, build_id: str) -> None:
    """
    Stamp provenance from the resolved refs. `schema.stamp()` has existed since
    before either chunker and nothing had ever called it, so every chunk in
    every corpus built so far claimed no origin at all.
    """
    ref = source.get("ref") or {}
    label = ref.get("tag") or ref.get("commit") or "?"
    _schema.stamp(
        chunks,
        corpus_build_id=build_id,
        source_ref=f"{source['repo']}@{label}/{resolution['commit'][:7]}",
        protocol_version=source.get("protocol_version"),
        deployment_status=source.get("deployment_status"),
    )
    # Per-document provenance, which unlike the fields above varies within a
    # source: a chunk of the Terms of Use is dated by the Terms of Use, not by
    # the corpus. The chunkers put it in `detail`; it is promoted to a schema
    # field here so a citation can carry it without anyone rummaging.
    for c in chunks:
        for field in ("effective_date", "doc_version"):
            value = c.detail.get(field)
            if value:
                setattr(c, field, str(value))
    tier = source.get("tier")
    for c in chunks:
        if tier and c.tier != tier:
            # the chunker guesses a tier from its own source type; the manifest
            # is the authority, and a disagreement is worth knowing about
            c.tier = tier


def metadata_coverage(chunks: list, source: dict) -> dict:
    """
    Check `metadata_required`, which may be a bare list of fields or a mapping
    with `paths` scoping it.

    Scoping matters because the requirement is not uniform. "Which version of
    this is in force" is a real question about the Terms of Use and a
    meaningless one about the delinquency explainer, and demanding a date for
    all eighty documents would mean inventing seventy-six of them — at which
    point a typo fix silently claims the terms changed. Ceremony that degrades
    the thing it decorates.
    """
    spec = source.get("metadata_required")
    if not spec:
        return {"required": [], "satisfied": True}
    if isinstance(spec, dict):
        required = list(spec.get("fields") or [])
        paths = list(spec.get("paths") or [])
    else:
        required, paths = list(spec), []
    if not required:
        return {"required": [], "satisfied": True}

    if paths:
        scoped = [c for c in chunks
                  if any(_md.glob_match(c.path, g) for g in paths)]
    else:
        scoped = list(chunks)

    missing: dict[str, int] = {}
    for field in required:
        n = sum(1 for c in scoped if not getattr(c, field, None))
        if n:
            missing[field] = n
    return {"required": required, "paths": paths or None,
            "missing": missing, "satisfied": not missing,
            "chunks": len(scoped), "of": len(chunks)}


# --------------------------------------------------------------------------
# build id
# --------------------------------------------------------------------------

def compute_build_id(manifest_bytes: bytes, resolutions: dict,
                     tool_versions: dict) -> str:
    payload = json.dumps({
        "manifest": _sha256(manifest_bytes),
        "sources": {k: v["commit"] for k, v in sorted(resolutions.items())},
        "tools": dict(sorted(tool_versions.items())),
    }, sort_keys=True).encode()
    return _sha256(payload)[:16]


def tool_versions(solc: str) -> dict:
    v = {"python": sys.version.split()[0]}
    for name in ("schema.py", "chunkers/solidity.py", "chunkers/markdown.py",
                 "build.py"):
        v[name] = _sha256((HERE / name).read_bytes())[:12]
    try:
        v["solc"] = _sol.solc_version(solc)
    except Exception as e:                      # noqa: BLE001 - reported, not raised
        v["solc"] = f"unavailable: {e}"
    return v


# --------------------------------------------------------------------------
# corpus diff — the corpus_diff_reviewed gate's raw material
# --------------------------------------------------------------------------

def corpus_diff(previous: pathlib.Path, chunks: list) -> dict:
    old = {}
    with open(previous) as f:
        for line in f:
            c = json.loads(line)
            old[c["id"]] = c
    new = {c.id: c.to_dict() for c in chunks}
    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    changed = sorted(i for i in set(old) & set(new)
                     if old[i]["display_text"] != new[i]["display_text"])
    return {"added": added, "removed": removed, "changed_text": changed,
            "counts": {"added": len(added), "removed": len(removed),
                       "changed_text": len(changed),
                       "before": len(old), "after": len(new)}}


def _without_created(record: dict) -> dict:
    """The creation clock is provenance, never part of artifact identity."""
    return {k: v for k, v in record.items() if k != "created"}


def _reuse_corpus(out_dir: pathlib.Path, chunks_bytes: bytes,
                  record: dict) -> dict:
    """Validate and return an already-published immutable corpus."""
    chunks_path = out_dir / "chunks.jsonl"
    build_path = out_dir / "build.json"
    if not chunks_path.is_file() or not build_path.is_file():
        raise BuildError(
            f"{out_dir}: an artifact directory already exists but is "
            "incomplete; refusing to repair or overwrite an immutable build")
    if chunks_path.read_bytes() != chunks_bytes:
        raise BuildError(
            f"{out_dir}: chunks.jsonl does not match a replay of build "
            f"{record['build_id']}; refusing to overwrite it")
    try:
        existing = json.loads(build_path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        raise BuildError(f"{build_path}: invalid immutable build record: {e}")
    if _without_created(existing) != _without_created(record):
        raise BuildError(
            f"{build_path}: metadata does not match a replay of build "
            f"{record['build_id']}; use a clean artifact root and investigate")
    print(f"\nreused    {out_dir} (immutable artifact already verified)")
    return existing


def _publish_corpus(out_root: pathlib.Path, chunks: list, record: dict) -> dict:
    """Atomically publish once; subsequent runs can only verify and reuse."""
    out_root.mkdir(parents=True, exist_ok=True)
    out_dir = out_root / record["build_id"]
    chunks_bytes = "".join(
        json.dumps(c.to_dict()) + "\n"
        for c in sorted(chunks, key=lambda x: x.id)).encode()
    if out_dir.exists():
        return _reuse_corpus(out_dir, chunks_bytes, record)

    temp_dir = pathlib.Path(tempfile.mkdtemp(
        prefix=f".{record['build_id']}.", dir=out_root))
    try:
        (temp_dir / "chunks.jsonl").write_bytes(chunks_bytes)
        (temp_dir / "build.json").write_text(
            json.dumps(record, indent=2) + "\n")
        try:
            os.replace(temp_dir, out_dir)
        except OSError:
            # Another identical builder may have won the publish race.
            if out_dir.exists():
                return _reuse_corpus(out_dir, chunks_bytes, record)
            raise
    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
    return record


# --------------------------------------------------------------------------

def build(manifest_path: str, out_root: str, solc: str, workdir: str,
          local: dict[str, str], allow_unverified: bool,
          allow_missing_metadata: bool, prerelease: bool,
          against: str | None) -> dict:
    try:
        import yaml
    except ImportError:
        raise BuildError("build.py needs pyyaml (pip install pyyaml)")

    manifest_bytes = pathlib.Path(manifest_path).read_bytes()
    manifest = yaml.safe_load(manifest_bytes)
    policy = manifest.get("policy") or {}

    sources = []
    for s in manifest.get("sources") or []:
        separate = s.get("index") == "separate"
        if separate != prerelease:
            continue
        sources.append(s)
    if not sources:
        raise BuildError("no sources selected — "
                         + ("nothing marked index: separate" if prerelease
                            else "check the manifest"))

    if policy.get("self_ingestion") == "forbidden":
        for s in sources:
            if "project-aleph" in (s.get("repo") or ""):
                raise BuildError(
                    f"{s['id']}: policy.self_ingestion is forbidden and this "
                    "source is the Aleph repository itself")

    workdir_p = pathlib.Path(workdir).resolve()
    workdir_p.mkdir(parents=True, exist_ok=True)

    print("acquire")
    gpg_env, keyring = prepare_keyring(
        sources, pathlib.Path(manifest_path).resolve().parent, workdir_p)
    repos, resolutions = {}, {}
    try:
        for s in sources:
            repo, res = acquire(s, workdir_p, local, allow_unverified, gpg_env)
            repos[s["id"]], resolutions[s["id"]] = repo, res
            sig = res["signature"]
            mark = {"verified": ("signature verified, signer pinned"
                                 if res.get("signer_pinned")
                                 else "signature valid, SIGNER NOT PINNED"),
                    "unsigned": "NOT ATTESTED (tag carries no signature) — waived",
                    "no_public_key": "NOT ATTESTED (no public key) — waived",
                    "not_required": "unsigned by design"}.get(sig, sig)
            print(f"  [{s['id']}] {res.get('tag') or res['commit'][:7]} "
                  f"-> {res['commit'][:7]}   {mark}")
    finally:
        cleanup_keyring(gpg_env)

    tools = tool_versions(solc)
    build_id = compute_build_id(manifest_bytes, resolutions, tools)
    print(f"\nbuild id {build_id}  (derived from inputs, not from the clock)")

    print("\nfilter + parse")
    all_chunks: list = []
    per_source: dict = {}
    watched: dict = {}
    for s in sources:
        found = check_watched(s, repos[s["id"]])
        if found:
            watched[s["id"]] = found
            for w in found:
                if w["status"] == "unchanged":
                    print(f"  [{s['id']}] watch: {w['path']} unchanged")
                else:
                    print(f"  [{s['id']}] WATCH {w['status']}: {w['path']}")
                    print(f"      pinned {w['expected'][:16]}… "
                          f"actual {(w['actual'] or 'absent')[:16]}…")
                    print("      a watched document has been revised — read "
                          "the diff before promoting this pin")
        report = filter_report(s)
        got = chunk_source(s, repos[s["id"]], solc, report)
        namespace_ids(got, s["id"])
        enrich(got, s, resolutions[s["id"]], build_id)
        report["metadata"] = metadata_coverage(got, s)
        report["chunks"] = len(got)
        per_source[s["id"]] = report
        all_chunks += got

    print("\nenrich + validate")
    ids = {}
    for c in all_chunks:
        ids.setdefault(c.id, []).append(c)
    collisions = {k: len(v) for k, v in ids.items() if len(v) > 1}
    if collisions:
        raise BuildError(
            f"{len(collisions)} chunk id(s) collide across sources: "
            f"{sorted(collisions)[:3]}")

    problems = _schema.validate(all_chunks,
                                oversize_chars=_sol.OVERSIZE_CHARS,
                                embed_oversize_chars=_sol.EMBED_OVERSIZE_CHARS)
    if problems:
        raise BuildError(f"{len(problems)} schema problem(s):\n  "
                         + "\n  ".join(problems[:5]))
    print(f"  {len(all_chunks)} chunks, 0 schema problems")

    unmet = {sid: r["metadata"] for sid, r in per_source.items()
             if not r["metadata"]["satisfied"]}
    if unmet and not allow_missing_metadata:
        detail = "\n".join(
            f"  {sid}: {m['required']} required on "
            + (", ".join(m["paths"]) if m.get("paths") else "every document")
            + f" ({m['chunks']} chunks); missing on "
            + ", ".join(f"{k} ({n} chunks)" for k, n in m["missing"].items())
            for sid, m in unmet.items())
        raise BuildError(
            "metadata_required is not satisfied\n" + detail +
            "\n  Either the source gains the fields, or the manifest stops "
            "requiring them. --allow-missing-metadata records the gap and "
            "continues.")

    waivers = []
    if allow_unverified and any(r["signature"] in ("unsigned", "no_public_key")
                                for r in resolutions.values()):
        waivers.append("signature_not_attested")
    if unmet and allow_missing_metadata:
        waivers.append("metadata_required_unmet")

    _verified = [r for r in resolutions.values()
                 if r["signature"] == "verified"]
    record = {
        "build_id": build_id,
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "manifest_sha256": _sha256(manifest_bytes),
        "manifest_path": str(manifest_path),
        "keyring": keyring or None,
        "index": "prerelease" if prerelease else "main",
        "tools": tools,
        "sources": {sid: {**resolutions[sid], **per_source[sid]}
                    for sid in per_source},
        "chunks": {
            "total": len(all_chunks),
            "by_tier": _count(all_chunks, lambda c: c.tier),
            "by_source_type": _count(all_chunks, lambda c: c.source_type),
            "by_kind": _count(all_chunks, lambda c: c.kind),
        },
        "gates": {
            "signature_verified": all(
                r["signature"] in ("verified", "not_required")
                for r in resolutions.values()),
            # None, not True, when nothing was verified. `all()` over an
            # empty sequence is True, which would have reported a pinned
            # signer next to signature_verified=False — a gate passing
            # vacuously reads exactly like a gate passing.
            "signer_pinned": (
                all(r.get("signer_pinned") for r in _verified)
                if _verified else None),
            "metadata_required": not unmet,
            "schema_valid": True,
            "watched_documents_unchanged": (
                all(w["status"] == "unchanged"
                    for ws in watched.values() for w in ws)
                if watched else None),
            "address_assertions_hold": None,   # needs the SDK artefact
            "eval_not_regressed": None,        # needs an index
        },
        "waivers": waivers,
        "watch": watched or None,
    }

    if against:
        record["diff_against"] = {"corpus": str(against),
                                  **corpus_diff(pathlib.Path(against), all_chunks)}
        c = record["diff_against"]["counts"]
        print(f"\ncorpus diff vs {against}")
        print(f"  {c['before']} -> {c['after']} chunks: +{c['added']} "
              f"-{c['removed']} ~{c['changed_text']} changed text")

    out_dir = pathlib.Path(out_root) / build_id
    record = _publish_corpus(pathlib.Path(out_root), all_chunks, record)

    print(f"\npublished {out_dir}")
    print(f"  chunks.jsonl   {len(all_chunks)} chunks")
    print(f"  build.json     gates "
          + ", ".join(f"{k}={v}" for k, v in record["gates"].items()))
    if waivers:
        print(f"  WAIVED         {', '.join(waivers)} — recorded in build.json")
    return record


def _count(chunks, key) -> dict:
    out: dict = {}
    for c in chunks:
        k = key(c)
        out[k] = out.get(k, 0) + 1
    return dict(sorted(out.items()))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default="manifest.yaml")
    ap.add_argument("--out", default="corpus", help="corpus root; a build id "
                                                    "directory is created under it")
    ap.add_argument("--solc", default="solc")
    ap.add_argument("--workdir", default=".aleph-work",
                    help="where sources are cloned and fetched")
    ap.add_argument("--source-path", action="append", default=[],
                    metavar="ID=PATH",
                    help="use an existing checkout for a source instead of "
                         "cloning; recorded in build.json as non-canonical")
    ap.add_argument("--allow-unverified-signature", action="store_true",
                    help="continue when a required signature cannot be checked "
                         "for want of the signer's key; recorded as a waiver")
    ap.add_argument("--allow-missing-metadata", action="store_true",
                    help="continue when metadata_required is unmet; recorded")
    ap.add_argument("--prerelease", action="store_true",
                    help="build the sources marked index: separate, into their "
                         "own corpus, instead of the main one")
    ap.add_argument("--against", metavar="CHUNKS_JSONL",
                    help="emit a chunk-level diff against a previous corpus")
    args = ap.parse_args()

    local = {}
    for spec in args.source_path:
        if "=" not in spec:
            print(f"FATAL: --source-path wants ID=PATH, got {spec!r}",
                  file=sys.stderr)
            return 1
        k, _, v = spec.partition("=")
        local[k] = v

    try:
        build(args.manifest, args.out, args.solc, args.workdir, local,
              args.allow_unverified_signature, args.allow_missing_metadata,
              args.prerelease, args.against)
    except (BuildError, _sol.ChunkError, _md.ChunkError) as e:
        print(f"\nFATAL: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
