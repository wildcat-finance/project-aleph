#!/usr/bin/env python3
"""
schema.py — Project Aleph

The one chunk shape. Every chunker emits this; the index, the retriever and the
citation layer all read this and nothing else.

Written before the markdown chunker exists, deliberately. Retrofitting a shared
schema after two chunkers have grown their own is how you end up with a
retrieval layer full of `if source_type == ...`.

DESIGN

Three tiers of field, and the split is load-bearing:

  Core        — every chunk has it, and the retriever may rely on it.
  Provenance  — §4 of the ingestion manifest. What makes an answer citable and
                a build replayable. Filled by the pipeline, not the chunker.
  detail      — everything source-specific, in a dict. Solidity's `exposed_by`
                has no markdown analogue and markdown's `anchor` has no
                Solidity analogue; forcing both into the top level produces a
                schema that is mostly nulls.

`display_text` and `model_text` are separate on purpose. The first is what a
human is shown and what a citation quotes — verbatim, always. The second is what
reaches the model's context window, with comments stripped. Collapsing them
means either citing text that isn't in the file, or feeding the model comments
that are attacker-writable free text. Both are worse than carrying two fields.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, asdict
from typing import Any

SOURCE_TYPES = ("solidity", "markdown")
TIERS = ("A", "B")


@dataclass
class Chunk:
    # ---- core: present on every chunk -------------------------------------
    id: str                       # stable, unique, human-readable
    kind: str                     # Function | Struct | surface | section | ...
    source_type: str              # solidity | markdown
    path: str                     # path within the source repo
    line: int                     # 1-based; 0 when not meaningful
    breadcrumb: str               # "file › Contract › signature" or heading path

    display_text: str             # verbatim — what a citation quotes
    model_text: str               # what enters the context window
    embed_text: str               # what gets embedded

    # ---- provenance: filled by the pipeline, not the chunker --------------
    tier: str = "A"               # A canonical, B published docs
    corpus_build_id: str | None = None
    source_ref: str | None = None         # tag + commit, or promoted docs commit
    protocol_version: str | None = None   # "v2.0" | "v2.5" — public names only
    deployment_status: str | None = None  # deployed | not_deployed | n/a
    effective_date: str | None = None     # tier B
    doc_version: str | None = None        # tier B
    supersedes: str | None = None

    # ---- integrity --------------------------------------------------------
    # True when display_text is assembled rather than sliced from source. The
    # citation layer must never present one of these as a verbatim quote: it is
    # a summary that looks exactly like source, which is worse than either.
    synthesised: bool = False
    warnings: list[str] = field(default_factory=list)

    # ---- source-specific --------------------------------------------------
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.model_text.encode()).hexdigest()


# --------------------------------------------------------------------------
# validation — run before anything is indexed
# --------------------------------------------------------------------------

def validate(chunks: list[Chunk], oversize_chars: int = 24_000,
             embed_oversize_chars: int | None = None) -> list[str]:
    """
    Return a list of problems. Empty means the set is safe to index.

    These are the failures that produce a *plausible* wrong answer rather than
    an obvious one, which is why they are checked rather than trusted.
    """
    problems: list[str] = []
    embed_limit = (oversize_chars if embed_oversize_chars is None
                   else embed_oversize_chars)

    seen: dict[str, int] = {}
    for c in chunks:
        seen[c.id] = seen.get(c.id, 0) + 1
    for cid, n in seen.items():
        if n > 1:
            problems.append(f"duplicate id ({n}x): {cid}")

    for c in chunks:
        if c.source_type not in SOURCE_TYPES:
            problems.append(f"{c.id}: unknown source_type {c.source_type!r}")
        if c.tier not in TIERS:
            problems.append(f"{c.id}: unknown tier {c.tier!r}")
        if not c.display_text.strip():
            problems.append(f"{c.id}: empty display_text")
        if not c.embed_text.strip():
            problems.append(f"{c.id}: empty embed_text — will embed as noise")
        if len(c.model_text) > oversize_chars:
            problems.append(
                f"{c.id}: model_text {len(c.model_text)} chars exceeds "
                f"{oversize_chars}; the context window truncates silently")
        # embed_text is a superset of model_text by construction, and it is the
        # string the embedder actually receives. Checking only the shorter one
        # enforces a limit on text nothing consumes.
        if len(c.embed_text) > embed_limit:
            problems.append(
                f"{c.id}: embed_text {len(c.embed_text)} chars exceeds "
                f"{embed_limit}; the embedder truncates silently")
        # A sliced chunk exists to quote its source. One whose visible content
        # is empty — an all-comment section, say — quotes nothing while still
        # occupying an index slot and a citation.
        if not c.synthesised and not c.model_text.strip():
            problems.append(
                f"{c.id}: empty model_text — sliced from source but there is "
                "nothing a reader can see")
        # A chunk claiming to be verbatim must actually be quotable. The
        # chunker knows whether it sliced or assembled; nothing downstream can
        # tell by looking, which is exactly why the flag has to be right.
        if c.synthesised and c.kind not in _ASSEMBLED_KINDS:
            problems.append(
                f"{c.id}: synthesised but kind={c.kind!r} is normally sliced")
        if not c.synthesised and c.kind in _ASSEMBLED_KINDS:
            problems.append(
                f"{c.id}: kind={c.kind!r} is assembled but not flagged "
                "synthesised — it would be quoted as source")

    return problems


_ASSEMBLED_KINDS = {"contract", "interface", "library", "surface", "index"}


def stamp(chunks: list[Chunk], **provenance) -> list[Chunk]:
    """
    Apply build-time provenance uniformly. Chunkers do not know their own
    corpus_build_id or source_ref — the pipeline does — and letting each one
    guess is how two chunks from one build end up claiming different origins.
    """
    for c in chunks:
        for k, v in provenance.items():
            if not hasattr(c, k):
                raise AttributeError(f"no such provenance field: {k}")
            setattr(c, k, v)
    return chunks
