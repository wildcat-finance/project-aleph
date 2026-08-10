#!/usr/bin/env python3
"""
solidity.py — Project Aleph

Turns Solidity into retrieval chunks via the compiler's AST, one chunk per
semantic unit, with natspec attached and citations that point at real bytes.

Input is a solc standard-json input file — the same `standard-input.json` that
`v2-protocol` ships under `deployments/mainnet/<Contract>-<address>/` for
Etherscan verification. That file carries the full source set *and* the exact
compiler settings used for the deployed bytecode, so chunks are guaranteed to
describe the code that is actually on chain rather than whatever the working
tree happens to contain.

    python3 solidity.py \\
        --input .../WildcatMarket-0xac.../standard-input.json \\
        --solc solc --include 'src/**' --out chunks.jsonl

Read ADVERSARIAL.md before trusting the output. The dangerous failure here is
not a crash — it is a chunk that cites the wrong source, because that looks
verified.
"""

from __future__ import annotations

import argparse
import fnmatch
import importlib.util
import json
import pathlib
import subprocess
import sys

_spec = importlib.util.spec_from_file_location(
    "aleph_schema", pathlib.Path(__file__).resolve().parent.parent / "schema.py")
_schema = importlib.util.module_from_spec(_spec)
sys.modules["aleph_schema"] = _schema
_spec.loader.exec_module(_schema)
Chunk = _schema.Chunk

# Nodes that become their own chunk.
CHUNKABLE = {
    "FunctionDefinition",
    "ModifierDefinition",
    "EventDefinition",
    "ErrorDefinition",
    "StructDefinition",
    "EnumDefinition",
    "UserDefinedValueTypeDefinition",
}
CONTAINERS = {"ContractDefinition"}

# bge-m3 has an 8192-token context. Solidity tokenises at roughly three
# characters per token, so this is the point at which truncation starts — and
# truncation is silent, which is why it is checked rather than assumed.
# Measured against v2.1.0: median chunk 175 chars, p99 2,292, max 5,062. The
# limit is nowhere near being approached; the check exists to notice if that
# changes.
OVERSIZE_CHARS = 24_000


class ChunkError(Exception):
    """Raised for conditions that must stop a build rather than warn."""


# --------------------------------------------------------------------------
# source handling — byte offsets, not character offsets
# --------------------------------------------------------------------------

class SourceMap:
    """
    solc `src` fields are "start:length:fileIndex" in **bytes**. Slicing a
    Python str with those numbers silently corrupts any file containing a
    non-ASCII byte — and Solidity source legitimately contains them, in string
    literals, natspec and identifiers. Everything here works on bytes and
    decodes only at the end.
    """

    def __init__(self, sources: dict[str, dict], ast_ids: dict[str, int]):
        self.by_index: dict[int, tuple[str, bytes]] = {}
        for path, entry in sources.items():
            idx = ast_ids.get(path)
            if idx is None:
                continue
            self.by_index[idx] = (path, entry["content"].encode("utf-8"))

    def slice(self, src: str) -> tuple[str, str]:
        """`src` -> (path, text). Raises rather than guessing."""
        start_s, len_s, file_s = src.split(":")
        start, length, file_idx = int(start_s), int(len_s), int(file_s)
        if file_idx not in self.by_index:
            raise KeyError(f"src {src!r} references unknown file index {file_idx}")
        path, blob = self.by_index[file_idx]
        end = start + length
        if start < 0 or end > len(blob):
            raise ValueError(f"src {src!r} out of range for {path} ({len(blob)} bytes)")
        return path, blob[start:end].decode("utf-8")

    def line_of(self, src: str) -> int:
        """
        1-based line number. Counts LF, CRLF and lone CR, because solc accepts
        all three and a citation that says line 1 for every node in a CR-only
        file is worse than no line number at all.
        """
        start_s, _, file_s = src.split(":")
        _, blob = self.by_index[int(file_s)]
        head = blob[: int(start_s)]
        return len(head.replace(b"\r\n", b"\n").replace(b"\r", b"\n").split(b"\n"))

    def span(self, src: str) -> tuple[int, int, int]:
        """(start, length, file_index) as integers."""
        a, b, c = src.split(":")
        return int(a), int(b), int(c)

    def slice_range(self, file_idx: int, start: int, end: int) -> tuple[str, str]:
        path, blob = self.by_index[file_idx]
        if start < 0 or end > len(blob) or start >= end:
            raise ValueError(f"range {start}:{end} out of bounds for {path}")
        return path, blob[start:end].decode("utf-8")


# --------------------------------------------------------------------------
# comment stripping — for model_text only, never for display_text
# --------------------------------------------------------------------------

def strip_comments(code: str, keep_natspec: bool = True) -> str:
    """
    Remove comments while preserving string and hex literals.

    A regex cannot do this correctly: `"http://x"` contains `//`, and
    `unicode"/* "` contains a comment opener inside a literal. This is a small
    hand-rolled scanner instead, and it is deliberately conservative — when in
    doubt it keeps the character.

    Natspec (`///` and `/** */`) is kept by default because it is real
    documentation. It is still untrusted text and must be fenced as quoted
    material in the prompt, never treated as instruction.
    """
    out: list[str] = []
    i, n = 0, len(code)
    while i < n:
        c = code[i]

        # string literals — including the unicode"" and hex"" prefixed forms
        if c in ('"', "'"):
            quote = c
            out.append(c)
            i += 1
            while i < n:
                if code[i] == "\\" and i + 1 < n:      # escape: copy both
                    out.append(code[i:i + 2])
                    i += 2
                    continue
                out.append(code[i])
                if code[i] == quote:
                    i += 1
                    break
                i += 1
            continue

        if code.startswith("//", i):
            is_natspec = code.startswith("///", i)
            # solc accepts LF, CRLF and lone CR. Stopping only at LF eats the
            # rest of a CR-only file from the first line comment onward.
            nl, cr = code.find("\n", i), code.find("\r", i)
            cands = [x for x in (nl, cr) if x != -1]
            j = min(cands) if cands else n
            if is_natspec and keep_natspec:
                out.append(code[i:j])
            else:
                out.append(" ")     # never weld the comment's neighbours together
            i = j
            continue

        if code.startswith("/*", i):
            is_natspec = code.startswith("/**", i)
            j = code.find("*/", i + 2)
            j = n if j == -1 else j + 2
            if is_natspec and keep_natspec:
                out.append(code[i:j])
            else:
                # A block comment can sit between two tokens with no other
                # separator — `uint256/* x */value` is valid Solidity — so it
                # must leave whitespace behind, not nothing. Newlines are
                # preserved so line numbers stay usable.
                removed = code[i:j]
                nl = removed.count("\n")
                out.append("\n" * nl if nl else " ")
            i = j
            continue

        out.append(c)
        i += 1

    return "".join(out)


# --------------------------------------------------------------------------
# signatures — overloads must not collide
# --------------------------------------------------------------------------

# Leading keywords solc puts in front of user-defined types, and the data
# location suffixes it puts after them.
_TYPE_PREFIXES = ("struct ", "enum ", "contract ", "interface ", "library ",
                  "type ", "function ")
_TYPE_SUFFIXES = (" memory", " storage", " calldata", " pointer", " ptr",
                  " ref", " slot", " super")


def canonical_type(type_string: str) -> str:
    """
    Reduce a solc `typeString` to something short, stable and *distinguishing*.

        "struct MarketState memory"  -> "MarketState"
        "contract IHooks"            -> "IHooks"
        "uint256[] calldata"         -> "uint256[]"
        "enum AuthRole"              -> "AuthRole"

    Taking the first whitespace-delimited token instead — as this did
    originally — collapses every struct parameter to the literal word "struct",
    so two functions differing only by struct type produce identical
    signatures and therefore identical chunk IDs. Nothing in the current corpus
    collides, but that is luck rather than design, and a silent ID collision
    means one chunk overwrites another.
    """
    t = (type_string or "?").strip()
    for prefix in _TYPE_PREFIXES:
        if t.startswith(prefix):
            t = t[len(prefix):]
            break
    changed = True
    while changed:                      # "storage pointer" needs two passes
        changed = False
        for suffix in _TYPE_SUFFIXES:
            if t.endswith(suffix):
                t = t[: -len(suffix)]
                changed = True
    # struct types are reported fully qualified when imported: "Foo.Bar"
    return " ".join(t.split()).strip()


def param_types(node: dict) -> list[str]:
    params = (node.get("parameters") or {}).get("parameters") or []
    return [canonical_type((p.get("typeDescriptions") or {}).get("typeString"))
            for p in params]


# Solidity permits overloading on all of these, so a bare name is not a unique
# identifier for any of them. Only functions and modifiers can be *overridden*;
# the rest are merely inherited, which matters in resolve_inheritance().
PARAMETERISED = {"FunctionDefinition", "EventDefinition",
                 "ErrorDefinition", "ModifierDefinition"}
OVERRIDABLE = {"FunctionDefinition", "ModifierDefinition"}


def signature(node: dict) -> str:
    kind = node.get("kind")
    name = node.get("name") or ""
    if node["nodeType"] == "FunctionDefinition":
        if kind == "constructor":
            name = "constructor"
        elif kind in ("fallback", "receive"):
            name = kind
    if node["nodeType"] in PARAMETERISED:
        return f"{name}({','.join(param_types(node))})"
    return name


# --------------------------------------------------------------------------
# chunks
# --------------------------------------------------------------------------

def natspec_of(node: dict, smap: SourceMap) -> str:
    doc = node.get("documentation")
    if not doc:
        return ""
    if isinstance(doc, str):
        return doc
    if doc.get("src"):
        try:
            return smap.slice(doc["src"])[1]
        except (KeyError, ValueError):
            pass
    return doc.get("text", "")


def documented_span(node: dict, smap: SourceMap):
    """
    Return (path, text, line) covering documentation *and* declaration as one
    contiguous slice, or None if they cannot be joined contiguously.

    Concatenating the two separately-sliced ranges — which is what this used to
    do — silently drops whatever whitespace sat between them, so the result is
    not a substring of the file it cites. It still looked verbatim, which is the
    failure this whole design exists to avoid. If a single span cannot be taken,
    the caller keeps the declaration alone and leaves the natspec in `detail`.
    """
    doc = node.get("documentation")
    if not isinstance(doc, dict) or not doc.get("src"):
        return None
    try:
        d_start, d_len, d_file = smap.span(doc["src"])
        n_start, n_len, n_file = smap.span(node["src"])
    except (ValueError, KeyError):
        return None
    if d_file != n_file or d_start + d_len > n_start:
        return None
    try:
        path, text = smap.slice_range(d_file, d_start, n_start + n_len)
    except (KeyError, ValueError):
        return None
    return path, text, smap.line_of(doc["src"])


def make_chunk(node, contract, smap, inherits) -> Chunk | None:
    try:
        path, text = smap.slice(node["src"])
    except (KeyError, ValueError) as e:
        print(f"  !! skipping node: {e}", file=sys.stderr)
        return None

    kind = node["nodeType"].replace("Definition", "")
    sig = signature(node)
    cname = contract["name"] if contract else None
    ckind = contract.get("contractKind") if contract else None
    doc = natspec_of(node, smap)

    # Take documentation and declaration as one contiguous slice where possible,
    # so display_text remains byte-exact source. Where it is not possible, the
    # declaration alone is quoted and the natspec stays in `detail` — a smaller
    # chunk is better than an unquotable one.
    line = smap.line_of(node["src"])
    joined = documented_span(node, smap)
    if joined:
        _, display, line = joined
    else:
        display = text
    model = strip_comments(display, keep_natspec=True)

    breadcrumb = " › ".join(x for x in (path, cname, sig) if x)

    warnings = []
    if len(model) > OVERSIZE_CHARS:
        warnings.append("chunk exceeds the embedding context; truncation is silent")

    uid = f"{path}:{cname or '<file>'}.{sig}"
    return Chunk(
        id=uid,
        kind=kind,
        source_type="solidity",
        path=path,
        line=line,
        breadcrumb=breadcrumb,
        display_text=display,
        model_text=model,
        # the embedding needs the context the body lacks: which contract, what
        # it is called, what kind of thing it is
        embed_text=f"{breadcrumb}\n{kind}\n\n{model}",
        warnings=warnings,
        detail={
            "contract": cname,
            "name": node.get("name") or sig,
            "signature": sig,
            "visibility": node.get("visibility"),
            "natspec": doc,
            "inherits": inherits,
            "declared_in_kind": ckind,
            "exposed_by": [],
            "overridden": False,
        },
    )


def contract_header(contract: dict, smap: SourceMap, inherits) -> Chunk | None:
    """
    A chunk for the contract itself: its natspec, declaration line, inheritance
    and state variables — but not the bodies of its functions, which are their
    own chunks. Without this, "what is WildcatMarket" has nothing to retrieve.
    """
    try:
        path, _ = smap.slice(contract["src"])
    except (KeyError, ValueError):
        return None
    doc = natspec_of(contract, smap)
    state = []
    for n in contract.get("nodes", []):
        if n["nodeType"] == "VariableDeclaration":
            try:
                state.append(smap.slice(n["src"])[1])
            except (KeyError, ValueError):
                continue
    decl = f"{contract.get('contractKind','contract')} {contract['name']}"
    if inherits:
        decl += " is " + ", ".join(inherits)
    body = decl + " {\n" + "\n".join("  " + s + ";" for s in state) + "\n}"
    display = (doc + "\n" + body) if doc else body
    model = strip_comments(display, keep_natspec=True)
    breadcrumb = f"{path} › {contract['name']}"
    return Chunk(
        id=f"{path}:{contract['name']}",
        kind=contract.get("contractKind", "contract"),
        source_type="solidity",
        path=path,
        line=smap.line_of(contract["src"]),
        breadcrumb=breadcrumb,
        display_text=display,
        model_text=model,
        embed_text=f"{breadcrumb}\ncontract declaration and state\n\n{model}",
        synthesised=True,
        detail={
            "contract": contract["name"],
            "name": contract["name"],
            "signature": contract["name"],
            "visibility": None,
            "natspec": doc,
            "inherits": inherits,
            "declared_in_kind": contract.get("contractKind"),
            "exposed_by": [],
            "overridden": False,
        },
    )


# --------------------------------------------------------------------------
# driver
# --------------------------------------------------------------------------

def compile_ast(input_path: str, solc: str) -> dict:
    doc = json.load(open(input_path))
    doc.setdefault("settings", {})["outputSelection"] = {"*": {"": ["ast"]}}
    doc["settings"].pop("libraries", None)
    r = subprocess.run([solc, "--standard-json"], input=json.dumps(doc),
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise ChunkError(f"solc failed: {r.stderr[:400]}")
    out = json.loads(r.stdout)
    errors = [e for e in out.get("errors", []) if e.get("severity") == "error"]
    if errors:
        detail = "\n".join(e.get("formattedMessage", "")[:300] for e in errors[:5])
        raise ChunkError(
            f"{len(errors)} compilation error(s) — refusing to chunk\n{detail}")
    return doc, out


def chunk(input_path: str, solc: str, includes: list[str]) -> list[Chunk]:
    doc, out = compile_ast(input_path, solc)
    ast_ids = {p: s["id"] for p, s in out["sources"].items()}
    smap = SourceMap(doc["sources"], ast_ids)

    chunks: list[Chunk] = []
    for path, entry in out["sources"].items():
        if includes and not any(fnmatch.fnmatch(path, g) for g in includes):
            continue
        ast = entry.get("ast")
        if not ast:
            continue
        for node in ast.get("nodes", []):
            if node["nodeType"] in CONTAINERS:
                inherits = [b["baseName"].get("name", "?")
                            for b in node.get("baseContracts", [])]
                header = contract_header(node, smap, inherits)
                if header:
                    chunks.append(header)
                for member in node.get("nodes", []):
                    if member["nodeType"] in CHUNKABLE:
                        c = make_chunk(member, node, smap, inherits)
                        if c:
                            chunks.append(c)
            elif node["nodeType"] in CHUNKABLE:
                # free functions, file-level structs/errors/enums
                c = make_chunk(node, None, smap, [])
                if c:
                    chunks.append(c)

    chunks = resolve_inheritance(out, chunks)
    chunks += surface_chunks(out, includes, smap)

    # Within one compilation unit an ID must be unique. Checking after the
    # cross-unit merge is too late: the merge is dict-keyed, so a duplicate is
    # silently absorbed and the collision count reports zero.
    seen: dict[str, Chunk] = {}
    for c in chunks:
        prior = seen.get(c.id)
        if prior is not None:
            raise ChunkError(
                f"duplicate id within one compilation unit: {c.id}\n"
                f"  {prior.breadcrumb} (line {prior.line})\n"
                f"  {c.breadcrumb} (line {c.line})\n"
                "  signature generation is not distinguishing these")
        seen[c.id] = c
    return chunks


def resolve_inheritance(out: dict, chunks: list[Chunk]) -> list[Chunk]:
    """
    Annotate each member chunk with the concrete contracts that expose it.

    solc gives `linearizedBaseContracts` — the C3 resolution order, most derived
    first. Walking it and keeping the first definition of each signature is
    exactly Solidity's own override semantics, so an overridden base function is
    correctly *not* attributed to the derived contract.

    Bases are collected from every source in the compilation, including paths
    excluded from chunking: a contract in `src/` can inherit from `lib/`, and
    resolving against only the included subset would silently under-report.
    """
    by_id: dict[int, dict] = {}
    node_path: dict[int, str] = {}
    for path, entry in out["sources"].items():
        ast = entry.get("ast")
        if not ast:
            continue
        for node in ast.get("nodes", []):
            if node["nodeType"] == "ContractDefinition":
                by_id[node["id"]] = node
                node_path[node["id"]] = path

    # signature -> defining contract, per concrete contract
    exposure: dict[tuple[str, str], list[str]] = {}
    overridden: set[tuple[str, str]] = set()

    for cid, contract in by_id.items():
        if contract.get("contractKind") != "contract" or contract.get("abstract"):
            continue                      # only concrete contracts have a surface
        seen: set[tuple[str, str]] = set()
        for base_id in contract.get("linearizedBaseContracts", []):
            base = by_id.get(base_id)
            if base is None:
                continue
            for member in base.get("nodes", []):
                if member["nodeType"] not in CHUNKABLE:
                    continue
                sig = signature(member)
                key = (node_path[base_id], f"{base['name']}.{sig}")
                # Only functions and modifiers can be overridden. Two events
                # with the same signature in a hierarchy are a redeclaration,
                # not a shadowing, and marking one "overridden" hides it from
                # the unreachable report for the wrong reason.
                shadow_key = (member["nodeType"], sig)
                if shadow_key in seen:
                    if member["nodeType"] in OVERRIDABLE:
                        overridden.add(key)
                    continue
                seen.add(shadow_key)
                exposure.setdefault(key, []).append(contract["name"])

    for c in chunks:
        if c.synthesised or c.detail.get("contract") is None:
            continue
        key = (c.path, f'{c.detail["contract"]}.{c.detail["signature"]}')
        c.detail["exposed_by"] = sorted(set(exposure.get(key, [])))
        c.detail["overridden"] = key in overridden
    return chunks


def rebuild_embed_text(chunks: list[Chunk]) -> None:
    """
    Derive embed_text from final state, once, after all merging is done.

    Appending "exposed by:" during per-unit resolution and then guarding the
    append with a substring check made the embedded text depend on which
    compilation unit was processed first: a member exposed by two contracts
    would carry whichever one its first unit knew about, and never both. The
    metadata was right and the thing actually being embedded was wrong, which is
    the worst arrangement of the two.
    """
    for c in chunks:
        base = c.embed_text.split("\n\nexposed by: ")[0]
        exposed = c.detail.get("exposed_by") or []
        c.embed_text = base + ("\n\nexposed by: " + ", ".join(exposed)
                               if exposed else "")


def getter_params(var: dict) -> list[str]:
    """
    Parameter list of the compiler-generated getter for a public state variable.
    Mappings take a key per level; arrays take a uint256 index. Anything else
    takes none.
    """
    params: list[str] = []
    t = var.get("typeName") or {}
    while True:
        kind = t.get("nodeType")
        if kind == "Mapping":
            params.append(canonical_type(
                ((t.get("keyType") or {}).get("typeDescriptions") or {}).get("typeString")))
            t = t.get("valueType") or {}
        elif kind == "ArrayTypeName":
            params.append("uint256")
            t = t.get("baseType") or {}
        else:
            return params


def surface_chunks(out: dict, includes: list[str], smap: SourceMap) -> list[Chunk]:
    """
    One chunk per concrete contract listing its full callable surface — every
    external and public function, with the contract that actually defines it.

    This is what answers "what can I call on WildcatMarket", which no
    per-function chunk can, because the answer is spread across eight contracts.
    Synthesised, and marked as such.
    """
    by_id, node_path = {}, {}
    for path, entry in out["sources"].items():
        ast = entry.get("ast")
        if not ast:
            continue
        for node in ast.get("nodes", []):
            if node["nodeType"] == "ContractDefinition":
                by_id[node["id"]] = node
                node_path[node["id"]] = path

    chunks = []
    for cid, contract in by_id.items():
        path = node_path[cid]
        if includes and not any(fnmatch.fnmatch(path, g) for g in includes):
            continue
        if contract.get("contractKind") != "contract" or contract.get("abstract"):
            continue
        seen: set[str] = set()
        lines: list[str] = []
        for base_id in contract.get("linearizedBaseContracts", []):
            base = by_id.get(base_id)
            if base is None:
                continue
            for m in base.get("nodes", []):
                origin = "" if base_id == cid else f"   (from {base['name']})"

                # Public state variables get a compiler-generated getter and are
                # part of the callable surface; omitting them understates it.
                if m["nodeType"] == "VariableDeclaration":
                    if m.get("visibility") != "public" or m.get("constant"):
                        continue
                    sig = f"{m.get('name')}({','.join(getter_params(m))})"
                    if sig in seen:
                        continue
                    seen.add(sig)
                    lines.append(f"  public {sig}   [getter]{origin}")
                    continue

                if m["nodeType"] != "FunctionDefinition":
                    continue
                # A constructor is not callable on a deployed contract, and a
                # base contract's constructor is not callable at all. Listing
                # them answers "what can I call" incorrectly in one direction
                # while the missing getters answer it incorrectly in the other.
                if m.get("kind") == "constructor":
                    continue
                if m.get("visibility") not in ("external", "public"):
                    continue
                sig = signature(m)
                if sig in seen:
                    continue
                seen.add(sig)
                lines.append(f"  {m.get('visibility')} {sig}{origin}")
        if not lines:
            continue
        body = f"{contract['name']} callable surface\n\n" + "\n".join(sorted(lines))
        breadcrumb = f"{path} › {contract['name']} › callable surface"
        chunks.append(Chunk(
            id=f"{path}:{contract['name']}#surface",
            kind="surface",
            source_type="solidity",
            path=path,
            line=smap.line_of(contract["src"]) if contract.get("src") else 0,
            breadcrumb=breadcrumb,
            display_text=body,
            model_text=body,
            embed_text=f"{breadcrumb}\n\n{body}",
            synthesised=True,
            detail={
                "contract": contract["name"],
                "name": contract["name"],
                "signature": "#surface",
                "visibility": None,
                "natspec": "",
                "inherits": [b["baseName"].get("name", "?")
                             for b in contract.get("baseContracts", [])],
                "declared_in_kind": "contract",
                "exposed_by": [],
                "overridden": False,
            },
        ))
    return chunks


def dedupe(chunks: list[Chunk]) -> tuple[list[Chunk], int]:
    """
    Identical bodies appear across files — the same interface vendored twice,
    the same trivial getter. Duplicates inflate retrieval scores for whatever
    happens to be duplicated, so keep the first and record the rest.
    """
    # Sorted, so which duplicate survives does not depend on the order inputs
    # happened to be passed on the command line.
    seen: dict[str, Chunk] = {}
    kept, dropped = [], 0
    for c in sorted(chunks, key=lambda x: x.id):
        h = c.content_hash
        prior = seen.get(h)
        if prior is not None:
            dropped += 1
            # Keep the discarded identity rather than losing it: the body is the
            # same, but the ID and its contract context are not, and a query
            # naming the dropped contract should still find something.
            prior.detail.setdefault("aliases", []).append(c.id)
            prior.detail["exposed_by"] = sorted(
                set(prior.detail.get("exposed_by") or [])
                | set(c.detail.get("exposed_by") or []))
            continue
        seen[h] = c
        kept.append(c)
    return kept, dropped


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, action="append",
                    help="solc standard-json input file; repeat to merge "
                         "compilation units (inheritance resolves per unit)")
    ap.add_argument("--solc", default="solc")
    ap.add_argument("--include", action="append", default=[],
                    help="glob of source paths to chunk, e.g. 'src/**'")
    ap.add_argument("--out", help="JSONL output; stdout summary if omitted")
    ap.add_argument("--no-dedupe", action="store_true")
    args = ap.parse_args()

    merged: dict[str, Chunk] = {}
    try:
        # Sorted, so the merge does not depend on the order inputs were listed.
        for path in sorted(args.input):
            for c in chunk(path, args.solc, args.include):
                prior = merged.get(c.id)
                if prior is None:
                    merged[c.id] = c
                    continue
                # Same member in another compilation unit. Inheritance resolves
                # per unit, so a function can look unreachable in one build and
                # be exposed by a concrete contract in another — the truth is
                # the union. Anything else differing is a disagreement about
                # source, which is fatal.
                if prior.display_text != c.display_text:
                    raise ChunkError(
                        f"conflicting source for {c.id} across compilation units\n"
                        f"  {prior.path}:{prior.line} and {c.path}:{c.line}\n"
                        "  two builds disagree about the same source. Keeping\n"
                        "  either body would attach a plausible citation to\n"
                        "  arbitrary code.")
                prior.detail["exposed_by"] = sorted(
                    set(prior.detail.get("exposed_by") or [])
                    | set(c.detail.get("exposed_by") or []))
                # OR, not AND: a member absent from one unit is not evidence
                # that it is un-overridden there.
                prior.detail["overridden"] = (
                    prior.detail.get("overridden") or c.detail.get("overridden"))
    except ChunkError as e:
        print(f"\nFATAL: {e}", file=sys.stderr)
        return 1

    chunks = list(merged.values())
    dropped = 0
    if not args.no_dedupe:
        chunks, dropped = dedupe(chunks)
    chunks.sort(key=lambda c: c.id)

    # embed_text is derived last, from final state, so it cannot disagree with
    # the metadata beside it.
    rebuild_embed_text(chunks)

    # Oversize is a property of length, not of "has any warning attached".
    oversize = [c for c in chunks if len(c.model_text) > OVERSIZE_CHARS]
    sizes = sorted(len(c.model_text) for c in chunks)
    p99 = sizes[int(0.99 * len(sizes))] if sizes else 0
    synth = sum(1 for c in chunks if c.synthesised)
    exposed = sum(1 for c in chunks if c.detail.get("exposed_by"))
    aliased = sum(len(c.detail.get("aliases") or []) for c in chunks)

    problems = _schema.validate(chunks, oversize_chars=OVERSIZE_CHARS)

    orphan = [c for c in chunks
              if c.detail.get("contract") and not c.synthesised
              and not c.detail.get("exposed_by")
              and c.kind == "Function"
              and c.detail.get("visibility") in ("external", "public")
              and c.detail.get("declared_in_kind") == "contract"
              and not c.detail.get("overridden")]

    print(f"{len(chunks)} chunks from {len(args.input)} compilation unit(s)  "
          f"({dropped} duplicate bodies folded, {aliased} alias id(s) kept)")
    print(f"  schema        : {len(problems)} problem(s)"
          + ("  <-- FATAL" if problems else ""))
    for pr in problems[:5]:
        print(f"      {pr}")
    print(f"  oversize      : {len(oversize)}  "
          f"(p99 {p99} chars, max {sizes[-1] if sizes else 0}, "
          f"limit {OVERSIZE_CHARS})")
    print(f"  synthesised   : {synth}  (not quotable as source)")
    print(f"  inheritance   : {exposed} chunks attributed to a concrete contract")
    print(f"  unreachable   : {len(orphan)} public/external fns on contracts "
          f"exposed by nothing" + ("  <-- check" if orphan else ""))
    for c in orphan[:5]:
        print(f"      {c.breadcrumb}")
    kinds: dict[str, int] = {}
    for c in chunks:
        kinds[c.kind] = kinds.get(c.kind, 0) + 1
    print("  by kind       : " + ", ".join(f"{k}={v}" for k, v in sorted(kinds.items())))

    if args.out and not problems and not oversize:
        with open(args.out, "w") as f:
            for c in chunks:
                f.write(json.dumps(c.to_dict()) + "\n")
        print(f"  written       : {args.out}")
    elif args.out:
        print("  NOT WRITTEN   : refusing to emit a corpus that fails its own checks")

    return 1 if (problems or oversize) else 0


if __name__ == "__main__":
    sys.exit(main())
