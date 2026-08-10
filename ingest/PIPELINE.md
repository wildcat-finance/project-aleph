# Ingestion and indexing pipeline

This document describes the pipeline implemented in this repository. Corpus
generation and embedding are separate operations:

```text
acquire -> filter/watch -> parse -> enrich/validate -> write corpus
                                                        |
                                                        v
                                                  embed per tier
                                                        |
                                                        v
                                                  searchable index
```

`ingest/build.py` stops after writing a validated corpus. `embed/index.py`
consumes that corpus and writes a tiered vector index. Answer generation,
live-state queries, deployment promotion, and atomic pointer swaps are outside
this repository.

## Prerequisites

Corpus builds require Python, `pyyaml`, Git, and GnuPG. Solidity parsing also
requires solc 0.8.25. The reproducible path is the pinned container wrapper:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install pyyaml numpy

python3 ingest/build.py \
  --manifest manifest.yaml \
  --solc ingest/solc-container \
  --out corpus
```

`ingest/solc-container` uses Docker by default. Set
`CONTAINER_RUNTIME=podman` for Podman, or pass a local solc 0.8.25 executable
for development.

The main build selects sources without `index: separate`. `--prerelease`
instead builds the isolated v2.5 corpus. `--source-path ID=PATH` reuses a local
checkout and records that non-canonical acquisition method in `build.json`.

## 1. Acquire immutable refs

Each source is cloned or fetched, resolved exactly as `manifest.yaml` specifies,
and checked out detached. Moving branches are rejected.

For an annotated tag, the build independently checks:

1. the tag object hash;
2. the commit hash reached by dereferencing the tag;
3. the tag signature when `require_signature` is true; and
4. the primary signer fingerprint when one is pinned.

The main protocol source uses `aleph-v2.1.0`, a signed tag on the same commit as
the unsigned release tag `v2.1.0`. Verification uses an ephemeral GnuPG keyring
containing only keys shipped under `ingest/keys/`, so ambient machine trust
cannot satisfy the gate. A valid signature from the wrong signer is fatal and
cannot be waived.

An absent signature or unavailable public key can be carried only with
`--allow-unverified-signature`; the waiver is recorded in `build.json`. A
present but invalid signature is always fatal.

The published docs source uses the lightweight tag `aleph-v0.3`. Its tag and
commit are pinned, but it is unsigned by design.

Submodules are not initialized. The manifest selects the one external Solidity
library that is relevant from bytes already contained in the deployment
verification inputs.

## 2. Filter and watch

Filtering applies `include`, then `exclude`, then `verification_only`.
`verification_only` paths remain available for validation without becoming
chunks.

The build fails when an include pattern matches nothing, a selected compilation
unit emits nothing, a requested `SUMMARY.md` cannot be read, or the merged corpus
contains zero chunks. This makes source shrinkage visible instead of producing a
smaller green build.

Paths that resolve through symlinks or outside the source root are rejected.
Source-unit paths containing absolute paths, backslashes, empty components,
`.` or `..` are also rejected before compilation and when reading compiler
output.

### Watched documents

The `watch` entries in `manifest.yaml` pin content digests for the four legal
documents Aleph may quote. A watched digest is an alarm for a docs promotion,
not an additional ref pin: the Git ref already determines the bytes.

A mismatch is reported and recorded with the expected and actual digests. It is
not fatal because a legitimate promotion may intentionally revise the document.
The `watched_documents_unchanged` field in `build.json` exposes the result to a
separate promotion controller.

For Markdown watches, `strip_frontmatter: true` hashes the document body rather
than GitBook metadata. This keeps legal-text changes distinct from metadata
maintenance.

## 3. Parse

### Solidity

`ingest/chunkers/solidity.py` compiles every configured deployment
`standard-input.json` through `solc --standard-json`. These inputs contain the
source set and compiler settings used for deployment verification, so the
result describes deployed code rather than a working-tree build.

All configured deployment inputs are required. Inheritance is resolved within a
compilation unit, while hooks implementations are deployed separately from the
market. The merge unions exposure across units and ORs override state.

The chunker emits semantic units for contracts, interfaces, libraries,
functions, modifiers, structs, enums, events, errors, user-defined value types,
and state-variable groups. It also emits assembled callable surfaces for concrete
contracts. Public getters participate in shadowing and surfaces, constructors do
not inherit, and the generated surface is checked against the compiler ABI by
whole signature.

The pinned wrapper runs the official solc image by digest with no network,
read-only root, no capabilities, a non-root user, and resource limits. The image
pin supplies reproducibility; the sandbox is defense in depth.

### Markdown

`ingest/chunkers/markdown.py` splits documents on rendered heading boundaries.
For `wildcat-docs`, `SUMMARY.md` supplies the cross-document GitBook hierarchy
but is not itself indexed.

The structural pass handles ATX and setext headings, fenced code, HTML comments,
CommonMark HTML blocks, inline code spans, lazy list and blockquote continuation,
and CR/CRLF input. It assigns GitBook-style anchors across all headings,
including headings too small to emit as chunks, so duplicate numbering matches
the renderer.

Short sections may be omitted, but an otherwise empty document is emitted as a
single whole-document chunk. Coverage is computed from emitted documents, not
from discovered filenames.

### Three text fields

Every chunk separates evidence from model input:

| Field | Contents | Consumer |
|---|---|---|
| `display_text` | byte-exact source slice | citation and human display |
| `model_text` | visible source with non-documentation comments removed | model context |
| `embed_text` | model text plus breadcrumb, kind, exposure, and aliases | embedder |

Solidity natspec remains in `model_text` only when solc attaches it as
documentation. Downstream prompts must still treat it as quoted, untrusted
material.

Assembled contract headers, callable surfaces, and document indexes carry
`synthesised: true`. They support retrieval but cannot be presented as verbatim
quotes.

## 4. Enrich and validate

The pipeline namespaces source-local IDs and stamps source provenance onto every
chunk:

- `corpus_build_id`;
- `tier`;
- `source_ref`;
- `protocol_version`;
- `deployment_status`;
- document-level `effective_date`, `doc_version`, and `supersedes` where present.

`metadata_required` is scoped to the paths named in the manifest. The main docs
source requires version and effective-date metadata on `legal/**`, not on every
documentation page. Missing required metadata is fatal unless
`--allow-missing-metadata` is supplied, in which case the waiver is recorded.
The pinned `aleph-v0.3` docs satisfy both required fields on every legal page.

`ingest/schema.py` then rejects duplicate IDs, empty required fields, invalid
tiers or source types, inconsistent synthesized flags, and oversize model or
embedding text. Cross-source collisions are checked after namespacing.

## 5. Corpus identity and output

The build ID is derived from manifest bytes, resolved refs, compiler version,
and hashes of the ingestion code. The clock does not affect the ID. Unchanged
inputs therefore resolve to the same build directory and the same sorted
`chunks.jsonl`.

```text
corpus/<build_id>/
  chunks.jsonl   sorted validated chunks
  build.json     refs, tools, counts, gates, watches, waivers, optional diff
```

`build.json` includes a creation timestamp, so the directory is not byte-for-byte
identical across reruns even though its identity and chunks are deterministic.
The command also reuses an existing build directory and rewrites its two files.
Deployment tooling must therefore treat published build directories as immutable;
immutability is not enforced by this CLI.

`--against path/to/chunks.jsonl` records added, removed, and changed chunk IDs.
The driver produces the diff but does not record human approval of it.

## 6. Build record and gates

The current driver enforces some gates and exposes placeholders for downstream
ones:

| Gate or check | Current behavior |
|---|---|
| Signed source and pinned signer | enforced during acquisition; limited waiver for absent/uncheckable signatures |
| Required document metadata | enforced; explicit waiver available |
| Schema validity | enforced |
| Watched legal digests | measured and recorded; mismatch is not fatal |
| Corpus diff review | diff can be generated; approval is not implemented |
| SDK address assertions | recorded as `null`; not implemented in the build |
| Retrieval/answer evaluation | recorded as `null`; not implemented in the build |
| Atomic deployment swap | not implemented in this repository |

The `gates` section of `manifest.yaml` is the promotion policy. A corpus existing
on disk does not by itself mean that every promotion gate passed.

## 7. Embed and search

Build a separate vector index from a corpus directory:

```bash
python3 embed/index.py build \
  --corpus corpus/<build_id> \
  --embedder ollama:bge-m3 \
  --out index
```

The implementation writes one normalized NumPy matrix and one aligned metadata
file per tier, plus `index.json`. It uses exact cosine search. At roughly 1,600
chunks and 1,024 dimensions, approximate nearest-neighbor infrastructure adds
complexity without useful latency savings.

```text
index/<build_id>/
  tier-A.npy
  tier-A.jsonl
  tier-B.npy
  tier-B.jsonl
  index.json
```

Search checks the query embedder's complete identity against the index identity
before comparing vectors. Results remain grouped and ranked per tier; `k` applies
to each tier independently.

The repository does not implement BM25, reciprocal-rank fusion, Postgres,
pgvector, answer synthesis, citation rendering, or live-state joins.

## Failure boundaries

- **Silent corpus shrinkage:** fail-loud selection and emitted-document coverage.
- **Version bleed:** separate prerelease builds plus stamped protocol versions.
- **Citation drift:** byte-exact display text and explicit synthesized chunks.
- **Instruction injection through comments:** signed source refs and comment
  removal from model text; natspec remains untrusted downstream.
- **Embedding substitution:** full embedder identity recorded in the index and
  required at query time.
- **Stale live data:** outside this pipeline; downstream code must use the health
  and block-number requirements in `manifest.yaml` and fail closed.
