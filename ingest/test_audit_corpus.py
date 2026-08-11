#!/usr/bin/env python3
"""Focused checks for the deterministic corpus structural audit."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("audit_corpus", HERE / "audit_corpus.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def row(cid: str, text: str, **overrides) -> dict:
    value = {
        "id": cid,
        "path": "docs/test.md",
        "source_type": "markdown",
        "tier": "A",
        "kind": "section",
        "synthesised": False,
        "display_text": text,
        "model_text": text,
        "embed_text": text,
        "detail": {},
    }
    value.update(overrides)
    return value


def main() -> int:
    rows = [
        row("source:clean", "# Clean\n\nOne coherent section with useful prose."),
        row("source:bad", "**One**\n\nFirst topic.\n\n**Two**\n\nSecond topic."),
        row("source:whole", "x" * 600,
            detail={"whole_document": True}),
        row("source:duplicate", "# Clean\n\nOne coherent section with useful prose."),
    ]
    result = audit.inventory(rows, "0" * 64)
    by_id = {item["id"]: item for item in result["chunks"]}
    assert result["chunk_count"] == 4
    assert by_id["source:bad"]["blockers"] == ["multiple-strong-sections"]
    assert "large-whole-document" in by_id["source:whole"]["blockers"]
    assert by_id["source:clean"]["duplicate_ids"] == ["source:duplicate"]
    assert by_id["source:clean"]["disposition"] == "review-required"
    assert "source:bad" in audit.markdown_report(result)

    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "chunks.jsonl"
        source.write_text("\n".join(json.dumps(item) for item in rows) + "\n")
        loaded, digest = audit.load_chunks(source)
        assert loaded == rows
        assert len(digest) == 64
    print("corpus audit checks pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
