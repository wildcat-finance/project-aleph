#!/usr/bin/env python3
"""
markdown.py — Project Aleph

Chunks markdown on heading boundaries, emitting the shared schema.

    python3 ingest/chunkers/markdown.py --root wildcat-docs \\
        --exclude 'SUMMARY.md' --exclude 'miscellaneous/deprecated-documentation/**' \\
        --out docs.jsonl

The promise is the same as the Solidity chunker's: `display_text` is byte-exact
source, so a citation quotes what is actually in the file. That is why this
works on bytes and slices by byte offset rather than reflowing anything.

Two failure modes drive most of the design:

  * Splitting inside a fenced code block. A `# comment` line in a bash example
    is not a heading, and treating it as one produces a chunk whose breadcrumb
    is a lie and whose body starts mid-example.
  * Losing the heading path. A section body rarely repeats its own subject —
    "the timer decrements" means nothing without "Delinquency" above it — so
    the breadcrumb is carried in metadata *and* prepended to the embedded text.
"""

from __future__ import annotations

import argparse
import fnmatch
import importlib.util
import json
import pathlib
import re
import sys

_spec = importlib.util.spec_from_file_location(
    "aleph_schema", pathlib.Path(__file__).resolve().parent.parent / "schema.py")
_schema = importlib.util.module_from_spec(_spec)
sys.modules["aleph_schema"] = _schema
_spec.loader.exec_module(_schema)
Chunk = _schema.Chunk

ATX = re.compile(rb"^(#{1,6})\s+(.*?)\s*#*\s*$")
FENCE = re.compile(rb"^\s*(```|~~~)")
HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)

MAX_HEADING_LEVEL = 4          # H5/H6 stay inside their parent section


# --------------------------------------------------------------------------
# frontmatter
# --------------------------------------------------------------------------

def split_frontmatter(blob: bytes) -> tuple[dict, int]:
    """
    Return (fields, byte offset where the body starts).

    Deliberately not a YAML parser: frontmatter here is a handful of scalar
    fields, and pulling in a parser to read `description:` would mean a
    malformed document could abort a build over metadata nobody retrieves.
    Unparseable frontmatter yields no fields and is skipped, not fatal.
    """
    if not blob.startswith(b"---\n"):
        return {}, 0
    end = blob.find(b"\n---\n", 4)
    if end == -1:
        return {}, 0
    body_start = end + 5
    fields: dict[str, str] = {}
    for line in blob[4:end].decode("utf-8", "replace").split("\n"):
        if ":" in line and not line.startswith((" ", "\t", "-")):
            k, _, v = line.partition(":")
            fields[k.strip()] = v.strip().strip('"').strip("'")
    return fields, body_start


# --------------------------------------------------------------------------
# heading scan
# --------------------------------------------------------------------------

def scan_headings(blob: bytes, start: int) -> list[tuple[int, int, str]]:
    """
    Return [(byte_offset, level, text)] for ATX headings outside code fences.

    Fence state is tracked because a heading inside an example is not a heading.
    Only ``` and ~~~ are recognised; indented code blocks are not, which is a
    known gap — see ADVERSARIAL.md.
    """
    out: list[tuple[int, int, str]] = []
    offset = start
    in_fence = False
    fence_marker = b""
    for line in blob[start:].split(b"\n"):
        m = FENCE.match(line)
        if m:
            if not in_fence:
                in_fence, fence_marker = True, m.group(1)
            elif m.group(1) == fence_marker:
                in_fence = False
        elif not in_fence:
            h = ATX.match(line)
            if h and len(h.group(1)) <= MAX_HEADING_LEVEL:
                out.append((offset, len(h.group(1)),
                            h.group(2).decode("utf-8", "replace")))
        offset += len(line) + 1
    return out


def slug(text: str) -> str:
    s = re.sub(r"[^\w\s-]", "", text.lower()).strip()
    return re.sub(r"[\s_]+", "-", s)


# --------------------------------------------------------------------------
# chunking
# --------------------------------------------------------------------------

def chunk_file(path: pathlib.Path, root: pathlib.Path,
               min_chars: int = 40) -> list[Chunk]:
    blob = path.read_bytes()
    rel = str(path.relative_to(root))
    front, body_start = split_frontmatter(blob)
    headings = scan_headings(blob, body_start)

    chunks: list[Chunk] = []
    trail: dict[int, str] = {}
    seen_ids: dict[str, int] = {}

    # Content before the first heading is real — the opening paragraph of a
    # page usually says what the page is for — so it becomes a chunk rather
    # than being dropped for lacking a heading.
    spans: list[tuple[int, int, int, str]] = []
    if headings and headings[0][0] > body_start:
        spans.append((body_start, headings[0][0], 0, ""))
    elif not headings:
        spans.append((body_start, len(blob), 0, ""))
    for i, (off, level, text) in enumerate(headings):
        end = headings[i + 1][0] if i + 1 < len(headings) else len(blob)
        spans.append((off, end, level, text))

    for start, end, level, text in spans:
        body = blob[start:end].decode("utf-8", "replace")
        if len(body.strip()) < min_chars:
            continue

        if level:
            trail[level] = text
            for deeper in [k for k in list(trail) if k > level]:
                trail.pop(deeper)
        crumb_parts = [rel] + [v for _, v in sorted(trail.items())]
        breadcrumb = " › ".join(crumb_parts)

        # Duplicate headings within one document are common ("Overview" twice)
        # and would collide. Disambiguate rather than silently drop one.
        base = f"{rel}#{slug(text) if text else 'intro'}"
        n = seen_ids.get(base, 0)
        seen_ids[base] = n + 1
        uid = base if n == 0 else f"{base}-{n + 1}"

        model = HTML_COMMENT.sub("", body)

        chunks.append(Chunk(
            id=uid,
            kind="section",
            source_type="markdown",
            path=rel,
            line=blob[:start].count(b"\n") + 1,
            breadcrumb=breadcrumb,
            display_text=body,
            model_text=model,
            embed_text=f"{breadcrumb}\n\n{model}",
            tier="B",
            detail={
                "heading": text,
                "heading_level": level,
                "heading_path": [v for _, v in sorted(trail.items())],
                "anchor": slug(text) if text else None,
                "description": front.get("description"),
            },
        ))

    if chunks:
        chunks.append(document_index(rel, front, headings, chunks[0].line))
    return chunks


def document_index(rel: str, front: dict, headings, line: int) -> Chunk:
    """
    One synthesised chunk per document listing its headings.

    "What does the lender guide cover" is not answerable from any single
    section, in the same way "what can I call on WildcatMarket" is not
    answerable from any single function. Assembled, so it is flagged.
    """
    lines = [f"{'  ' * (lvl - 1)}{text}" for _, lvl, text in headings]
    desc = front.get("description") or ""
    body = f"{rel} — contents\n\n" + (desc + "\n\n" if desc else "") + "\n".join(lines)
    return Chunk(
        id=f"{rel}#index",
        kind="index",
        source_type="markdown",
        path=rel,
        line=line,
        breadcrumb=f"{rel} › contents",
        display_text=body,
        model_text=body,
        embed_text=body,
        tier="B",
        synthesised=True,
        detail={"description": front.get("description"),
                "heading_count": len(headings)},
    )


def chunk_tree(root: str, excludes: list[str]) -> list[Chunk]:
    base = pathlib.Path(root)
    out: list[Chunk] = []
    skipped = 0
    for path in sorted(base.rglob("*.md")):
        rel = str(path.relative_to(base))
        if any(fnmatch.fnmatch(rel, g) or rel.startswith(g.rstrip("*"))
               for g in excludes):
            skipped += 1
            continue
        out.extend(chunk_file(path, base))
    print(f"  skipped {skipped} excluded file(s)")
    return out


# --------------------------------------------------------------------------

def excludes_from_manifest(manifest_path: str, source_id: str) -> list[str]:
    """
    Read the exclude list out of manifest.yaml rather than taking it on the
    command line.

    Written after passing the excludes by hand and omitting AGENTS.md, which
    put agent-directed instructions straight into the corpus. The manifest's
    first principle is that exclusion lists rot silently; a list that has to be
    retyped at every invocation rots faster than most.
    """
    try:
        import yaml
    except ImportError:
        sys.exit("--manifest needs pyyaml (pip install pyyaml)")
    doc = yaml.safe_load(open(manifest_path))
    for src in doc.get("sources", []):
        if src.get("id") == source_id:
            return list(src.get("exclude", []))
    sys.exit(f"no source {source_id!r} in {manifest_path}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, help="markdown tree to chunk")
    ap.add_argument("--manifest", help="read excludes from manifest.yaml")
    ap.add_argument("--source", default="wildcat-docs",
                    help="which manifest source to read excludes from")
    ap.add_argument("--exclude", action="append", default=[],
                    help="additional glob or path prefix; repeatable")
    ap.add_argument("--out", help="JSONL output")
    args = ap.parse_args()

    excludes = list(args.exclude)
    if args.manifest:
        excludes += excludes_from_manifest(args.manifest, args.source)
        print(f"  {len(excludes)} exclusion(s) from {args.manifest}")
    elif not excludes:
        print("  WARNING: no excludes and no --manifest. Everything under "
              "--root will be indexed, including any agent instruction files.",
              file=sys.stderr)

    chunks = chunk_tree(args.root, excludes)
    problems = _schema.validate(chunks)

    docs = len({c.path for c in chunks})
    sizes = sorted(len(c.model_text) for c in chunks)
    print(f"{len(chunks)} chunks from {docs} document(s)")
    print(f"  synthesised   : {sum(1 for c in chunks if c.synthesised)}"
          f"  (not quotable as source)")
    print(f"  size          : median {sizes[len(sizes)//2]}, "
          f"p99 {sizes[int(0.99*len(sizes))]}, max {sizes[-1]}")
    print(f"  schema        : {len(problems)} problem(s)"
          + ("  <-- BUG" if problems else ""))
    for p in problems[:5]:
        print(f"      {p}")

    if args.out:
        with open(args.out, "w") as f:
            for c in chunks:
                f.write(json.dumps(c.to_dict()) + "\n")
        print(f"  written       : {args.out}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
