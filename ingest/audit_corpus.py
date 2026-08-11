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
REVIEW_DECISIONS = frozenset({
    "coherent", "split-required", "exclude-required", "source-fix-required",
})
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


def load_reviews(path: Path) -> dict:
    try:
        value = json.loads(path.read_bytes())
    except json.JSONDecodeError as error:
        raise AuditError(f"{path}: invalid review JSON: {error}") from error
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise AuditError(f"{path}: review ledger must use schema_version 1")
    records = value.get("reviews", [])
    rules = value.get("rules", [])
    if not isinstance(records, list) or not isinstance(rules, list):
        raise AuditError(f"{path}: review ledger reviews/rules must be lists")
    if not records and not rules:
        raise AuditError(f"{path}: review ledger has no reviews or rules")
    return value


def _ids_digest(ids: list[str]) -> str:
    return hashlib.sha256(_canonical(sorted(ids))).hexdigest()


def apply_reviews(audit: dict, ledger: dict) -> dict:
    """Bind explicit structural judgements to one exact inventory.

    Reviews may clear warnings, never machine blockers. Non-passing decisions
    become blockers so a ledger cannot hide work that still needs a split,
    exclusion, or upstream source fix. Oversized chunks need an explicit size
    exception in addition to a coherent judgement.
    """
    if ledger.get("corpus_sha256") != audit["corpus_sha256"]:
        raise AuditError("review ledger corpus_sha256 does not match the corpus")
    if ledger.get("audit_id") != audit["audit_id"]:
        raise AuditError("review ledger audit_id does not match the base inventory")
    reviewer = ledger.get("reviewer")
    if not isinstance(reviewer, str) or not reviewer.strip():
        raise AuditError("review ledger reviewer is empty")

    by_id = {row["id"]: row for row in audit["chunks"]}
    seen: set[str] = set()

    def apply(review: dict, chunk_id: str) -> None:
        if chunk_id in seen:
            raise AuditError(f"review ledger repeats chunk {chunk_id}")
        seen.add(chunk_id)
        row = by_id[chunk_id]
        if row["disposition"] == "blocked":
            raise AuditError(f"review cannot override blockers on {chunk_id}")
        if row["disposition"] != "review-required":
            raise AuditError(f"review is unnecessary for {chunk_id}")
        decision = review.get("decision")
        if decision not in REVIEW_DECISIONS:
            raise AuditError(f"invalid review decision for {chunk_id}: {decision!r}")
        rationale = review.get("rationale")
        if not isinstance(rationale, str) or not rationale.strip():
            raise AuditError(f"review rationale is empty for {chunk_id}")
        if (decision == "coherent" and "oversized-review" in row["warnings"]
                and review.get("size_exception") is not True):
            raise AuditError(
                f"oversized coherent chunk needs size_exception: {chunk_id}")
        row["review"] = {
            "decision": decision,
            "rationale": rationale.strip(),
            "reviewer": reviewer.strip(),
            "size_exception": (
                "oversized-review" in row["warnings"]
                and review.get("size_exception") is True),
            "rule": review.get("name"),
        }
        if decision == "coherent":
            row["disposition"] = "reviewed-pass"
        else:
            row["disposition"] = "blocked"
            row["blockers"].append(f"review-{decision}")

    for review in ledger.get("reviews", []):
        if not isinstance(review, dict):
            raise AuditError("review ledger entries must be objects")
        chunk_id = review.get("id")
        if not isinstance(chunk_id, str) or chunk_id not in by_id:
            raise AuditError(f"review ledger names unknown chunk {chunk_id!r}")
        apply(review, chunk_id)

    for rule in ledger.get("rules", []):
        if not isinstance(rule, dict) or not isinstance(rule.get("name"), str):
            raise AuditError("review rules need a name")
        warning = rule.get("warning")
        if not isinstance(warning, str) or not warning:
            raise AuditError(f"review rule {rule['name']} has no warning selector")
        matches = [row["id"] for row in audit["chunks"]
                   if row["disposition"] == "review-required"
                   and warning in row["warnings"]]
        expected_count = rule.get("expected_count")
        expected_digest = rule.get("expected_ids_sha256")
        if expected_count != len(matches) or expected_digest != _ids_digest(matches):
            raise AuditError(
                f"review rule {rule['name']} matched {len(matches)} chunks with "
                f"digest {_ids_digest(matches)}, expected {expected_count} / "
                f"{expected_digest}")
        for chunk_id in matches:
            apply(rule, chunk_id)

    counts: dict[str, int] = {}
    findings: dict[str, int] = {}
    for row in audit["chunks"]:
        counts[row["disposition"]] = counts.get(row["disposition"], 0) + 1
        for finding in row["blockers"] + row["warnings"]:
            findings[finding] = findings.get(finding, 0) + 1
    audit["dispositions"] = dict(sorted(counts.items()))
    audit["findings"] = dict(sorted(findings.items()))
    audit["review_ledger"] = {
        "reviewer": reviewer.strip(),
        "review_count": len(seen),
        "ledger_sha256": hashlib.sha256(_canonical(ledger)).hexdigest(),
    }
    audit.pop("audit_id", None)
    audit["audit_id"] = hashlib.sha256(_canonical(audit)).hexdigest()[:16]
    return audit


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
        "`review-required` identifies material that needs a recorded ",
        "classification. `reviewed-pass` is bound to the exact corpus and base ",
        "audit by a disposition ledger. `blocked` is release-stopping.",
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
    parser.add_argument("--reviews", type=Path,
                        help="corpus-bound structural disposition ledger")
    parser.add_argument("--fail-on-blockers", action="store_true")
    parser.add_argument("--fail-on-unreviewed", action="store_true")
    args = parser.parse_args()
    try:
        rows, digest = load_chunks(args.chunks)
        audit = inventory(rows, digest)
        if args.reviews:
            audit = apply_reviews(audit, load_reviews(args.reviews))
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_bytes(json.dumps(audit, indent=2, sort_keys=True).encode()
                              + b"\n")
        args.report.write_text(markdown_report(audit), encoding="utf-8")
    except (AuditError, OSError) as error:
        print(f"audit failed: {error}", file=sys.stderr)
        return 2
    blockers = audit["dispositions"].get("blocked", 0)
    unreviewed = audit["dispositions"].get("review-required", 0)
    print(f"audit {audit['audit_id']}: {audit['chunk_count']} chunks, "
          f"{blockers} blocked, {unreviewed} unreviewed")
    if args.fail_on_blockers and blockers:
        return 1
    return 1 if args.fail_on_unreviewed and unreviewed else 0


if __name__ == "__main__":
    sys.exit(main())
