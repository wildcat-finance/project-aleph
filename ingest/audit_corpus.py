#!/usr/bin/env python3
"""Produce a deterministic, review-oriented inventory of an Aleph corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys


REVIEW_SIZE = 2_000
PATHOLOGICAL_SIZE = 10_000
WHOLE_DOCUMENT_MAX = 500
ATX = re.compile(r"(?m)^ {0,3}#{1,6}[ \t]+(.+?)[ \t]*#*[ \t]*$")
STRONG = re.compile(
    r"(?m)^ {0,3}(?:\*\*([^*\r\n][^*\r\n]*?)\*\*"
    r"|__([^_\r\n][^_\r\n]*?)__)[ \t]*$")
ORPHAN = re.compile(r"^ {0,3}(?:\*|\*\*|_|__)[ \t]*$")


class AuditError(Exception):
    pass


def _canonical(value) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"))
            + "\n").encode()


def load_chunks(path: Path) -> tuple[list[dict], str]:
    raw = path.read_bytes()
    rows: list[dict] = []
    for number, line in enumerate(raw.splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise AuditError(f"{path}:{number}: invalid JSON: {error}") from error
        if not isinstance(row, dict) or not row.get("id"):
            raise AuditError(f"{path}:{number}: chunk object has no id")
        rows.append(row)
    if not rows:
        raise AuditError(f"{path}: corpus is empty")
    return rows, hashlib.sha256(raw).hexdigest()


def _normalized_hash(row: dict) -> str:
    text = " ".join(str(row.get("model_text") or "").split())
    return hashlib.sha256(text.encode()).hexdigest() if text else ""


def _orphan_at_edge(text: str) -> bool:
    lines = [line for line in text.splitlines() if line.strip()]
    return bool(lines and (ORPHAN.fullmatch(lines[0])
                           or ORPHAN.fullmatch(lines[-1])))


def inventory(rows: list[dict], corpus_sha256: str) -> dict:
    duplicates: dict[str, list[str]] = {}
    for row in rows:
        digest = _normalized_hash(row)
        if digest:
            duplicates.setdefault(digest, []).append(str(row["id"]))

    records: list[dict] = []
    for row in rows:
        display = str(row.get("display_text") or "")
        model = str(row.get("model_text") or "")
        embed = str(row.get("embed_text") or "")
        detail = row.get("detail") or {}
        atx = [m.group(1).strip() for m in ATX.finditer(display)]
        strong = [(m.group(1) or m.group(2)).strip()
                  for m in STRONG.finditer(display)]
        exact_dupes = duplicates.get(_normalized_hash(row), [])
        path = str(row.get("path") or "")
        legal = path.startswith("legal/") or "/legal/" in f"/{path}"
        whole = bool(detail.get("whole_document"))

        warnings: list[str] = []
        blockers: list[str] = []
        if len(model) > REVIEW_SIZE:
            warnings.append("oversized-review")
        if legal:
            warnings.append("legal")
        if bool(row.get("synthesised")):
            warnings.append("synthesised")
        if whole:
            warnings.append("whole-document")
        if len(exact_dupes) > 1:
            warnings.append("duplicate-content")
        if (len(strong) > 1 and detail.get("heading_level", 0) == 0
                and not row.get("synthesised")):
            blockers.append("multiple-strong-sections")
        elif len(strong) > 1:
            warnings.append("nested-strong-sections")
        if (row.get("source_type") == "markdown"
                and not row.get("synthesised")
                and len(model) > PATHOLOGICAL_SIZE):
            blockers.append("pathological-size")
        if whole and len(model) > WHOLE_DOCUMENT_MAX:
            blockers.append("large-whole-document")
        if _orphan_at_edge(model):
            blockers.append("orphan-markup")

        if blockers:
            disposition = "blocked"
        elif warnings:
            disposition = "review-required"
        else:
            disposition = "auto-pass"
        records.append({
            "id": row["id"],
            "path": path,
            "source_type": row.get("source_type"),
            "tier": row.get("tier"),
            "kind": row.get("kind"),
            "synthesised": bool(row.get("synthesised")),
            "sizes": {"display": len(display), "model": len(model),
                      "embed": len(embed)},
            "heading_count": len(atx) + len(strong),
            "topic_boundary_indicators": {
                "markdown_headings": atx,
                "strong_sections": strong,
            },
            "legal": legal,
            "whole_document": whole,
            "duplicate_ids": [cid for cid in exact_dupes
                              if cid != row["id"]],
            "warnings": warnings,
            "blockers": blockers,
            "disposition": disposition,
        })

    counts: dict[str, int] = {}
    findings: dict[str, int] = {}
    for record in records:
        counts[record["disposition"]] = counts.get(record["disposition"], 0) + 1
        for finding in record["blockers"] + record["warnings"]:
            findings[finding] = findings.get(finding, 0) + 1
    payload = {
        "schema_version": 1,
        "corpus_sha256": corpus_sha256,
        "chunk_count": len(records),
        "thresholds": {
            "review_size_chars": REVIEW_SIZE,
            "pathological_markdown_chars": PATHOLOGICAL_SIZE,
            "whole_document_chars": WHOLE_DOCUMENT_MAX,
        },
        "dispositions": dict(sorted(counts.items())),
        "findings": dict(sorted(findings.items())),
        "chunks": sorted(records, key=lambda record: record["id"]),
    }
    payload["audit_id"] = hashlib.sha256(_canonical(payload)).hexdigest()[:16]
    return payload


def markdown_report(audit: dict) -> str:
    records = audit["chunks"]
    flagged = [r for r in records if r["disposition"] != "auto-pass"]
    flagged.sort(key=lambda r: (
        0 if r["disposition"] == "blocked" else 1,
        -r["sizes"]["model"], r["id"]))
    lines = [
        "# Aleph corpus structural audit",
        "",
        f"Audit `{audit['audit_id']}` covers all {audit['chunk_count']:,} chunks ",
        f"in corpus payload `{audit['corpus_sha256']}`.",
        "",
        "## Dispositions",
        "",
    ]
    for name, count in audit["dispositions"].items():
        lines.append(f"- **{name}**: {count:,}")
    lines += [
        "",
        "`auto-pass` means an explicit structural rule covers the chunk. ",
        "`review-required` identifies material that needs a recorded human ",
        "classification. `blocked` is a release-stopping structural defect.",
        "",
        "## Findings",
        "",
    ]
    for name, count in audit["findings"].items():
        lines.append(f"- **{name}**: {count:,}")
    lines += [
        "",
        "## Review queue",
        "",
        "| Disposition | Model chars | Tier | Source | Findings |",
        "| --- | ---: | --- | --- | --- |",
    ]
    for row in flagged:
        findings = ", ".join(row["blockers"] + row["warnings"])
        source = str(row["id"]).replace("|", "\\|")
        lines.append(
            f"| {row['disposition']} | {row['sizes']['model']:,} | "
            f"{row['tier']} | `{source}` | {findings} |")
    lines += [
        "",
        "## Interpretation",
        "",
        "This report inventories structure; it does not certify factual truth. ",
        "Legal, synthesised, oversized, duplicate, and whole-document evidence ",
        "stays visible for review even when it is structurally valid. Exact ",
        "duplicates across different sources are reported rather than silently ",
        "removed because authority and provenance differ.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunks", required=True, type=Path)
    parser.add_argument("--json", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--fail-on-blockers", action="store_true")
    args = parser.parse_args()
    try:
        rows, digest = load_chunks(args.chunks)
        audit = inventory(rows, digest)
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_bytes(json.dumps(audit, indent=2, sort_keys=True).encode()
                              + b"\n")
        args.report.write_text(markdown_report(audit), encoding="utf-8")
    except (AuditError, OSError) as error:
        print(f"audit failed: {error}", file=sys.stderr)
        return 2
    blockers = audit["dispositions"].get("blocked", 0)
    print(f"audit {audit['audit_id']}: {audit['chunk_count']} chunks, "
          f"{blockers} blocked")
    return 1 if args.fail_on_blockers and blockers else 0


if __name__ == "__main__":
    sys.exit(main())
