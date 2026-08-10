#!/usr/bin/env python3
"""
markdown.py — Project Aleph

Chunks markdown on heading boundaries, emitting the shared schema.

    python3 ingest/chunkers/markdown.py --root wildcat-docs \
        --manifest manifest.yaml --summary SUMMARY.md --out docs.jsonl

`display_text` is a byte-exact slice of the source file, same promise as the
Solidity chunker, so a citation quotes what is actually in the file. Everything
here works on bytes and slices by byte offset.

Structure is resolved in one pass that tracks fences and HTML comments together,
because they interact: a heading inside a fence is not a heading, and a heading
inside an HTML comment is not a heading either. Establishing that with a regex
over already-split chunks — which is what this did originally — lets a comment
that spans a heading boundary deposit its contents into the model's context with
the comment markers stranded in adjacent chunks.
"""

from __future__ import annotations

import argparse
import fnmatch
import html
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

# CommonMark allows up to three leading spaces before an ATX marker, and a
# closing hash sequence only when it is preceded by a space.
ATX = re.compile(rb"^ {0,3}(#{1,6})(?:[ \t]+(.*?))?[ \t]*$")
FENCE = re.compile(rb"^( {0,3})(`{3,}|~{3,})(.*)$")
SETEXT = re.compile(rb"^ {0,3}(=+|-+)[ \t]*$")
CLOSING_HASHES = re.compile(r"[ \t]+#+[ \t]*$")

MAX_HEADING_LEVEL = 4          # H5/H6 stay inside their parent section


# --------------------------------------------------------------------------
# line handling — LF, CRLF and lone CR are all line terminators
# --------------------------------------------------------------------------

LINE_END = re.compile(rb"\r\n|\n|\r")


def iter_lines(blob: bytes, start: int = 0):
    """Yield (offset, line_without_terminator) over any line ending."""
    pos = start
    n = len(blob)
    while pos < n:
        m = LINE_END.search(blob, pos)
        if m is None:
            yield pos, blob[pos:]
            return
        yield pos, blob[pos:m.start()]
        pos = m.end()


def line_number(blob: bytes, offset: int) -> int:
    return len(LINE_END.split(blob[:offset]))


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
    lines = list(iter_lines(blob))
    if not lines or lines[0][1].strip() != b"---":
        return {}, 0
    for offset, line in lines[1:]:
        if line.strip() == b"---":
            body_start = offset + len(line)
            m = LINE_END.match(blob, body_start)
            if m:
                body_start = m.end()
            fields: dict[str, str] = {}
            raw = blob[len(lines[0][1]):offset].decode("utf-8", "replace")
            for fl in raw.split("\n"):
                fl = fl.rstrip("\r")
                if ":" in fl and not fl.startswith((" ", "\t", "-")):
                    k, _, v = fl.partition(":")
                    fields[k.strip()] = v.strip().strip('"').strip("'")
            return fields, body_start
    return {}, 0


# --------------------------------------------------------------------------
# structure scan — fences, HTML comments and headings in a single pass
# --------------------------------------------------------------------------

def scan_structure(blob: bytes, start: int):
    """
    Return (headings, comment_spans).

    headings: [(offset, level, raw_text)] for headings that are genuinely
    headings — outside code fences, outside HTML comments.
    comment_spans: [(start, end)] byte ranges of HTML comments outside fences,
    so they can be removed by span rather than by a regex that cannot see
    whether it is inside a code example.
    """
    headings: list[tuple[int, int, bytes]] = []
    comments: list[tuple[int, int]] = []

    fence_char = b""
    fence_len = 0
    in_comment = False
    comment_start = -1
    prev_text: tuple[int, bytes] | None = None   # for setext

    for offset, line in iter_lines(blob, start):
        stripped = line.strip()

        # --- fences -------------------------------------------------------
        m = FENCE.match(line)
        if m and not in_comment:
            indent, marker, rest = m.group(1), m.group(2), m.group(3)
            if not fence_char:
                # opening fence; info string may not contain a backtick
                if marker[:1] == b"`" and b"`" in rest:
                    pass
                else:
                    fence_char, fence_len = marker[:1], len(marker)
                    prev_text = None
                    continue
            elif (marker[:1] == fence_char and len(marker) >= fence_len
                  and rest.strip() == b""):
                # a closing fence must use the same character, be at least as
                # long as the opener, and carry nothing but whitespace after it
                fence_char, fence_len = b"", 0
                prev_text = None
                continue
        if fence_char:
            prev_text = None
            continue

        # --- HTML comments ------------------------------------------------
        pos = 0
        consumed_line = False
        while True:
            if in_comment:
                end = line.find(b"-->", pos)
                if end == -1:
                    consumed_line = True
                    break
                in_comment = False
                comments.append((comment_start, offset + end + 3))
                pos = end + 3
            else:
                begin = line.find(b"<!--", pos)
                if begin == -1:
                    break
                in_comment = True
                comment_start = offset + begin
                pos = begin + 4
        if consumed_line or in_comment:
            prev_text = None
            continue
        if comments and comments[-1][1] > offset and pos > 0:
            # a comment ended on this line; anything before it was inside
            line = b" " * pos + line[pos:]

        # --- headings -------------------------------------------------------
        atx = ATX.match(line)
        if atx:
            level = len(atx.group(1))
            if level <= MAX_HEADING_LEVEL:
                headings.append((offset, level, atx.group(2) or b""))
            prev_text = None
            continue

        st = SETEXT.match(line)
        if st and prev_text is not None:
            level = 1 if st.group(1)[:1] == b"=" else 2
            headings.append((prev_text[0], level, prev_text[1].strip()))
            prev_text = None
            continue

        prev_text = (offset, line) if stripped else None

    if in_comment:
        # unterminated: everything from the opener onward is comment
        comments.append((comment_start, len(blob)))
    return headings, comments


def strip_comments_by_span(blob: bytes, chunk_start: int, chunk_end: int,
                           comments) -> str:
    """
    Remove HTML comments from a chunk using spans found by the structural scan.

    A regex over the chunk cannot do this: a comment opening before the chunk
    and closing inside it leaves an orphan `-->` and, worse, leaves the comment
    body looking like ordinary prose. Comments inside fenced code are not in
    `comments` at all, so example markup shown to a reader survives intact.
    """
    keep: list[bytes] = []
    cursor = chunk_start
    for c_start, c_end in comments:
        if c_end <= chunk_start or c_start >= chunk_end:
            continue
        s = max(c_start, chunk_start)
        e = min(c_end, chunk_end)
        keep.append(blob[cursor:s])
        cursor = e
    keep.append(blob[cursor:chunk_end])
    return b"".join(keep).decode("utf-8", "replace")


# --------------------------------------------------------------------------
# heading text and anchors
# --------------------------------------------------------------------------

def heading_text(raw: bytes) -> str:
    """
    Rendered heading text: entity-decoded, with a CommonMark closing hash
    sequence removed only when it is actually one.

    `&#x20;` appears in GitBook output and was previously slugged as the literal
    characters `x20`, which produced 33 wrong anchors in the live corpus.
    """
    text = raw.decode("utf-8", "replace").strip()
    text = CLOSING_HASHES.sub("", text)
    if text.endswith("#") and not text.endswith(" #"):
        pass                     # `# Name#` keeps its hash, per CommonMark
    return html.unescape(text).strip()


def slug(text: str) -> str:
    s = re.sub(r"[^\w\s-]", "", text.lower()).strip()
    return re.sub(r"[\s_]+", "-", s)


# --------------------------------------------------------------------------
# SUMMARY.md — cross-document hierarchy
# --------------------------------------------------------------------------

SUMMARY_ENTRY = re.compile(r"^(\s*)\*\s+\[([^\]]*)\]\(([^)]+)\)")
SUMMARY_PART = re.compile(r"^##\s+(.*)$")


def parse_summary(path: pathlib.Path) -> dict[str, list[str]]:
    """
    Map each document path to the titles of its ancestors in the GitBook nav.

    Without this a page knows its own headings and nothing else, so
    `day-to-day-usage/lenders.md` has no idea it sits under "Using Wildcat".
    PIPELINE.md has promised this since the beginning and it was never built.
    """
    hierarchy: dict[str, list[str]] = {}
    stack: list[tuple[int, str]] = []
    part: str | None = None
    for line in path.read_text(encoding="utf-8", errors="replace").split("\n"):
        p = SUMMARY_PART.match(line)
        if p:
            part = p.group(1).strip()
            stack = []
            continue
        m = SUMMARY_ENTRY.match(line)
        if not m:
            continue
        indent, title, target = len(m.group(1)), m.group(2).strip(), m.group(3)
        while stack and stack[-1][0] >= indent:
            stack.pop()
        ancestors = ([part] if part else []) + [t for _, t in stack]
        target = target.split("#")[0].strip()
        if target.endswith(".md"):
            hierarchy[target] = ancestors
        stack.append((indent, title))
    return hierarchy


# --------------------------------------------------------------------------
# chunking
# --------------------------------------------------------------------------

def chunk_file(path: pathlib.Path, root: pathlib.Path,
               min_chars: int = 40,
               hierarchy: dict[str, list[str]] | None = None) -> list[Chunk]:
    blob = path.read_bytes()
    rel = str(path.relative_to(root))
    front, body_start = split_frontmatter(blob)
    headings, comments = scan_structure(blob, body_start)
    ancestors = (hierarchy or {}).get(rel, [])

    spans: list[tuple[int, int, int, str]] = []
    if headings and headings[0][0] > body_start:
        spans.append((body_start, headings[0][0], 0, ""))
    elif not headings:
        spans.append((body_start, len(blob), 0, ""))
    for i, (off, level, raw) in enumerate(headings):
        end = headings[i + 1][0] if i + 1 < len(headings) else len(blob)
        spans.append((off, end, level, heading_text(raw)))

    chunks: list[Chunk] = []
    trail: dict[int, str] = {}
    seen_ids: dict[str, int] = {}
    seen_anchors: dict[str, int] = {}

    for start, end, level, text in spans:
        # The trail is updated BEFORE the size filter. Doing it after meant a
        # heading whose own body was too short never entered the trail, so its
        # descendants inherited their grandparent instead — 309 of 452 live
        # chunks had the wrong ancestry.
        if level:
            trail[level] = text
            for deeper in [k for k in list(trail) if k > level]:
                trail.pop(deeper)

        body = blob[start:end].decode("utf-8", "replace")
        if len(body.strip()) < min_chars:
            continue

        heading_path = [v for _, v in sorted(trail.items())]
        breadcrumb = " › ".join([rel] + ancestors + heading_path)

        base = f"{rel}#{slug(text) if text else 'intro'}"
        n = seen_ids.get(base, 0)
        seen_ids[base] = n + 1
        uid = base if n == 0 else f"{base}-{n + 1}"

        # Anchors are deduplicated the same way, so a citation URL built from
        # the second "Overview" does not navigate to the first.
        anchor = slug(text) if text else None
        if anchor:
            a = seen_anchors.get(anchor, 0)
            seen_anchors[anchor] = a + 1
            if a:
                anchor = f"{anchor}-{a + 1}"

        model = strip_comments_by_span(blob, start, end, comments)

        chunks.append(Chunk(
            id=uid,
            kind="section",
            source_type="markdown",
            path=rel,
            line=line_number(blob, start),
            breadcrumb=breadcrumb,
            display_text=body,
            model_text=model,
            embed_text=f"{breadcrumb}\n\n{model}",
            tier="B",
            detail={
                "heading": text,
                "heading_level": level,
                "heading_path": heading_path,
                "nav_path": ancestors,
                "anchor": anchor,
                "description": front.get("description"),
            },
        ))

    # A document with headings is worth indexing even when no single section
    # clears the size filter — five navigation pages were dropped entirely.
    if chunks or headings or front.get("description"):
        chunks.append(document_index(rel, front, headings, ancestors,
                                     line_number(blob, body_start)))
    return chunks


def document_index(rel, front, headings, ancestors, line) -> Chunk:
    """
    One synthesised chunk per document listing its headings.

    "What does the lender guide cover" is not answerable from any single
    section, in the same way "what can I call on WildcatMarket" is not
    answerable from any single function. Assembled, so it is flagged.
    """
    lines = [f"{'  ' * (lvl - 1)}{heading_text(raw)}" for _, lvl, raw in headings]
    desc = front.get("description") or ""
    nav = " › ".join(ancestors)
    body = (f"{rel} — contents\n\n"
            + (f"{nav}\n\n" if nav else "")
            + (desc + "\n\n" if desc else "")
            + "\n".join(lines))
    breadcrumb = " › ".join([rel] + ancestors + ["contents"])
    return Chunk(
        id=f"{rel}#index",
        kind="index",
        source_type="markdown",
        path=rel,
        line=line,
        breadcrumb=breadcrumb,
        display_text=body,
        model_text=body,
        embed_text=body,
        tier="B",
        synthesised=True,
        detail={"description": front.get("description"),
                "nav_path": ancestors,
                "heading_count": len(headings)},
    )


def chunk_tree(root: str, excludes: list[str],
               summary: str | None = None) -> list[Chunk]:
    base = pathlib.Path(root)
    hierarchy = {}
    if summary:
        sp = pathlib.Path(summary)
        if not sp.is_absolute():
            sp = base / summary
        if sp.exists():
            hierarchy = parse_summary(sp)
            print(f"  {len(hierarchy)} document(s) placed from {sp.name}")
        else:
            print(f"  WARNING: {sp} not found; no cross-document hierarchy",
                  file=sys.stderr)
    out: list[Chunk] = []
    skipped = 0
    for path in sorted(base.rglob("*.md")):
        rel = str(path.relative_to(base))
        if any(fnmatch.fnmatch(rel, g) or rel.startswith(g.rstrip("*"))
               for g in excludes):
            skipped += 1
            continue
        out.extend(chunk_file(path, base, hierarchy=hierarchy))
    print(f"  skipped {skipped} excluded file(s)")
    return out


# --------------------------------------------------------------------------

def excludes_from_manifest(manifest_path: str, source_id: str) -> list[str]:
    """
    Read the exclude list out of manifest.yaml rather than taking it on the
    command line.

    Written after passing the excludes by hand and omitting AGENTS.md, which put
    agent-directed instructions straight into the corpus. The manifest's first
    principle is that exclusion lists rot silently; a list that has to be
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
    ap.add_argument("--summary", default="SUMMARY.md",
                    help="GitBook nav to derive cross-document hierarchy from; "
                         "pass '' to disable")
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

    chunks = chunk_tree(args.root, excludes, args.summary or None)
    problems = _schema.validate(chunks)

    docs = len({c.path for c in chunks})
    sizes = sorted(len(c.model_text) for c in chunks) or [0]
    placed = sum(1 for c in chunks if c.detail.get("nav_path"))
    print(f"{len(chunks)} chunks from {docs} document(s)")
    print(f"  synthesised   : {sum(1 for c in chunks if c.synthesised)}"
          f"  (not quotable as source)")
    print(f"  nav hierarchy : {placed} chunks placed in the SUMMARY tree")
    print(f"  size          : median {sizes[len(sizes)//2]}, "
          f"p99 {sizes[int(0.99*len(sizes))]}, max {sizes[-1]}")
    print(f"  schema        : {len(problems)} problem(s)"
          + ("  <-- FATAL" if problems else ""))
    for p in problems[:5]:
        print(f"      {p}")

    if args.out and not problems:
        with open(args.out, "w") as f:
            for c in chunks:
                f.write(json.dumps(c.to_dict()) + "\n")
        print(f"  written       : {args.out}")
    elif args.out:
        print("  NOT WRITTEN   : refusing to emit a corpus that fails its checks")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
