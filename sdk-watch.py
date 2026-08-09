#!/usr/bin/env python3
"""
sdk-watch.py — Project Aleph

Watches @wildcatfi/wildcat-sdk for updates and, more importantly, for changes to
the *mainnet* deployment address map that the SDK ships in dist/constants.js.

The SDK's Deployments map is the de facto address book for the protocol. Nothing
binds it to a v2-protocol tag or commit, so a change to it is the only signal we
get that the addresses Aleph answers about have moved.

Two things this deliberately does NOT do:

  * It does not order versions by semver. The registry's publish history is
    non-monotonic with respect to semver (3.1.4-beta.4 was published after
    3.1.16-beta), so "highest version" is not "newest". Ordering is by publish
    time, with the dist-tag reported alongside.
  * It does not look at any chain other than mainnet.

Exit codes:
  0  no mainnet address change
  1  MAINNET ADDRESS CHANGED  (or the pinned/candidate version is missing)
  2  newer SDK published, mainnet addresses unchanged
  3  operational failure (network, parse)

Stdlib only, so it drops into CI without a lockfile.
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
import tarfile
import urllib.error
import urllib.request

REGISTRY = "https://registry.npmjs.org/@wildcatfi/wildcat-sdk"
APP_PKG_JSON = (
    "https://raw.githubusercontent.com/"
    "wildcat-finance/wildcat-app-v2/main/package.json"
)
SDK_DEP_NAME = "@wildcatfi/wildcat-sdk"
CHAIN = "Mainnet"
TIMEOUT = 30


# --------------------------------------------------------------------------
# fetch
# --------------------------------------------------------------------------

def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "aleph-sdk-watch/1"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read()


def registry_metadata() -> dict:
    return json.loads(_get(REGISTRY))


def pinned_from_app() -> str:
    """Read the exact SDK version the frontend pins on main."""
    pkg = json.loads(_get(APP_PKG_JSON))
    dep = pkg.get("dependencies", {}).get(SDK_DEP_NAME)
    if not dep:
        raise RuntimeError(f"{SDK_DEP_NAME} not found in app dependencies")
    # The app enforces exact pins via check:exact-versions, but strip a range
    # prefix defensively rather than silently comparing against the wrong thing.
    if dep[0] in "^~>=<":
        raise RuntimeError(
            f"app pins a range ({dep!r}), not an exact version — "
            "exact-version enforcement has regressed"
        )
    return dep


# --------------------------------------------------------------------------
# deployment map extraction
# --------------------------------------------------------------------------

def _brace_block(s: str, start: int) -> str:
    """Return the {...} block beginning at the first brace at/after `start`."""
    i = s.index("{", start)
    depth, j = 0, i
    while j < len(s):
        if s[j] == "{":
            depth += 1
        elif s[j] == "}":
            depth -= 1
            if depth == 0:
                return s[i : j + 1]
        j += 1
    raise ValueError("unbalanced braces in constants.js")


def mainnet_addresses(constants_js: str) -> dict[str, str]:
    """Extract {ContractName: address} for mainnet from the compiled SDK."""
    anchor = constants_js.find("exports.Deployments")
    if anchor == -1:
        raise ValueError("no exports.Deployments in constants.js")

    marker = re.search(
        rf"SupportedChainId\.{CHAIN}\]\s*:", constants_js[anchor:]
    )
    if not marker:
        raise ValueError(f"no {CHAIN} entry in Deployments")

    block = _brace_block(constants_js, anchor + marker.end())
    found = re.findall(r'(\w+)\s*:\s*"(0x[a-fA-F0-9]{40})"', block)
    if not found:
        raise ValueError(f"no addresses parsed from {CHAIN} block")
    # Checksum casing is not consistent across releases; compare case-insensitively
    # but report what the SDK actually ships.
    return {name: addr for name, addr in found}


def fetch_constants(meta: dict, version: str) -> str:
    try:
        url = meta["versions"][version]["dist"]["tarball"]
    except KeyError:
        raise RuntimeError(f"version {version} not present in registry")
    blob = _get(url)
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tf:
        member = tf.extractfile("package/dist/constants.js")
        if member is None:
            raise RuntimeError(f"{version}: no dist/constants.js in tarball")
        return member.read().decode("utf-8", errors="replace")


# --------------------------------------------------------------------------
# version selection
# --------------------------------------------------------------------------

def newest_by_publish_time(meta: dict) -> tuple[str, str]:
    times = {
        v: t for v, t in meta.get("time", {}).items()
        if v not in ("created", "modified") and v in meta.get("versions", {})
    }
    if not times:
        raise RuntimeError("registry returned no publish times")
    version = max(times, key=lambda v: times[v])
    return version, times[version]


def tags_for(meta: dict, version: str) -> list[str]:
    return sorted(t for t, v in meta.get("dist-tags", {}).items() if v == version)


def published_after(meta: dict, pinned: str) -> list[tuple[str, str]]:
    times = meta.get("time", {})
    if pinned not in times:
        return []
    cutoff = times[pinned]
    out = [
        (v, t) for v, t in times.items()
        if v not in ("created", "modified")
        and v in meta.get("versions", {})
        and t > cutoff
    ]
    return sorted(out, key=lambda x: x[1])


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="Watch wildcat-sdk mainnet deployments")
    ap.add_argument("--pinned", help="version to treat as pinned (default: read from app main)")
    ap.add_argument("--candidate", help="version to compare against (default: newest by publish time)")
    ap.add_argument("--dist-tag", help="compare against this dist-tag instead, e.g. latest")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    try:
        meta = registry_metadata()
        pinned = args.pinned or pinned_from_app()

        if args.candidate:
            candidate, cand_time = args.candidate, meta.get("time", {}).get(args.candidate, "?")
        elif args.dist_tag:
            candidate = meta.get("dist-tags", {}).get(args.dist_tag)
            if not candidate:
                raise RuntimeError(f"no such dist-tag: {args.dist_tag}")
            cand_time = meta.get("time", {}).get(candidate, "?")
        else:
            candidate, cand_time = newest_by_publish_time(meta)

        pinned_map = mainnet_addresses(fetch_constants(meta, pinned))
        cand_map = mainnet_addresses(fetch_constants(meta, candidate))
    except (urllib.error.URLError, RuntimeError, ValueError, KeyError) as e:
        print(f"sdk-watch: FAILED: {e}", file=sys.stderr)
        return 3

    names = sorted(set(pinned_map) | set(cand_map))
    changes = []
    for n in names:
        a, b = pinned_map.get(n), cand_map.get(n)
        if (a or "").lower() != (b or "").lower():
            kind = "added" if a is None else "removed" if b is None else "changed"
            changes.append({"contract": n, "kind": kind, "pinned": a, "candidate": b})

    behind = published_after(meta, pinned)
    result = {
        "pinned": {"version": pinned, "dist_tags": tags_for(meta, pinned)},
        "candidate": {
            "version": candidate,
            "published": cand_time,
            "dist_tags": tags_for(meta, candidate),
        },
        "chain": CHAIN,
        "contracts_tracked": len(names),
        "versions_published_since_pin": [v for v, _ in behind],
        "mainnet_changes": changes,
    }

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        pt = ",".join(result["pinned"]["dist_tags"]) or "—"
        ct = ",".join(result["candidate"]["dist_tags"]) or "—"
        print(f"pinned    : {pinned}  [{pt}]")
        print(f"candidate : {candidate}  [{ct}]  published {cand_time}")
        print(f"tracked   : {len(names)} mainnet contracts")
        if behind:
            print(f"newer     : {len(behind)} version(s) published since the pin")
            for v, t in behind[-5:]:
                print(f"            {t[:10]}  {v}")
        if changes:
            print("\n!! MAINNET DEPLOYMENT ADDRESSES DIFFER !!")
            for c in changes:
                print(f"   {c['kind']:8} {c['contract']}")
                print(f"            pinned    {c['pinned']}")
                print(f"            candidate {c['candidate']}")
            print("\nAleph's address book is stale or the protocol has redeployed.")
            print("Do not re-index until this is reconciled by a human.")
        else:
            print("\nmainnet addresses identical")

    if changes:
        return 1
    if behind:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
