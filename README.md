# Project Aleph

Project Aleph is intended to answer questions about the Wildcat Protocol over
Telegram using pinned, citable protocol knowledge and block-numbered live state.

This repository contains the evidence foundation: corpus policy, reproducible
ingestion, Solidity and Markdown chunkers, provenance, embedding backends, a
tiered vector index, an immutable release builder, evaluation inputs, and an
SDK address watcher. It does not yet contain a user-facing agent.

The shortest honest status is:

> **Aleph can publish a coherent evidence release. It must next implement the
> retrieval policy that turns a scoped request into validated evidence.**

The remaining work is ordered below by dependency. Later stages should not begin
by inventing around a missing earlier boundary.

## Current foundation

The checked-in code already provides:

- immutable source acquisition driven by `manifest.yaml`;
- verification of the signed `v2-protocol@aleph-v2.1.0` corpus tag against a
  shipped key and pinned signer fingerprint;
- published documentation pinned at `wildcat-docs@aleph-v0.3`, including the
  required legal document versions and effective dates;
- fail-loud filtering, watched legal-document digests, and corpus diffs;
- Solidity AST chunking from mainnet deployment verification inputs;
- Markdown chunking with GitBook hierarchy and renderer-compatible anchors;
- byte-exact citation text separated from model and embedding text;
- source, version, deployment, build, and per-document provenance;
- deterministic, immutable corpus and tier-separated vector artifacts;
- a canonical release record that enforces the manifest embedding identity,
  records corpus-diff review state, and exposes every promotion gate;
- exact cosine search with strict full index/query embedder identity checks;
- a 125-question golden set, retrieval labels, and the recorded `bge-m3` model
  comparison; and
- `sdk-watch.py`, which detects mainnet SDK deployment-map changes without
  changing the corpus.

This is the substrate for the product, not the product itself. In particular,
`address_assertions_hold` and `eval_not_regressed` remain `null` in current build
records, and nothing performs a reviewed atomic promotion.

## Required build order

```text
1. canonical corpus + index
             |
2. scoped retrieval + citations
             |
3. live-state tools + deterministic renderers
             |
4. question router + answer engine
             |
5. end-to-end evaluation + promotion gates
             |
6. Telegram adapter
             |
7. production deployment + operations
```

Testing belongs inside every stage. The numbering describes dependency order,
not a plan to defer verification until stage 5.

### 1. Canonical corpus and index artifact — implemented

`release.py` is the stage-one boundary. It builds one named corpus/index pair,
derives the required embedding identity from `manifest.yaml`, and writes an
immutable release record under `artifacts/releases/<release_id>/release.json`.

The implementation provides:

- one release command that produces a named corpus/index pair from
  `manifest.yaml`;
- automatic enforcement of the manifest's embedding model digest, dimensions,
  normalization, and query-prefix policy when building the index;
- atomic, immutable publication: a repeat verifies and reuses the artifact,
  while missing or modified files are fatal;
- a reviewable corpus diff with pending, unchanged, or attributable approved
  state; and
- one machine-readable release record carrying corpus gates, waivers, index
  identity, hashes, source refs, and tier counts.

Downstream gates remain visible rather than being guessed: the current release
is not promotable while `address_assertions_hold` and `eval_not_regressed` are
`null`.

### 2. Build scoped retrieval and citation resolution

`embed/index.py` returns nearest chunks, but it does not implement the retrieval
policy required by the manifest.

Build next:

- a retrieval API whose request explicitly carries chain, public protocol
  version, requested tiers, and result limits;
- Tier A and Tier B searches that remain separate through ranking;
- lexical matching for contract names, function signatures, addresses, and
  exact protocol vocabulary, combined with semantic results within each tier;
- v2.0 as the default deployed corpus and an isolated v2.5 path that activates
  only when the user explicitly names v2.5;
- enforcement of `always_cite`, prerelease preambles, deployment status, and
  source-version filters;
- a citation resolver that turns a hit into a stable source path and Markdown
  anchor or Solidity location; and
- a hard prohibition on quoting chunks marked `synthesised: true`.

Retrieval should return typed evidence objects, not answer prose. Each object
must carry enough provenance for a later citation validator to prove that the
quoted bytes came from the named corpus build.

**Complete when:** retrieval labels run against the actual built corpus rather
than the evaluation harness's simplified Markdown splitter; exact identifiers
are findable; v2.5 cannot bleed into a general question; and every returned quote
resolves to byte-exact source.

### 3. Build live-state tools and deterministic renderers

Anything that changes without a corpus promotion belongs here, not in the vector
index and not in model-authored prose.

Build next:

- SDK artifact loading and enforcement of every address under
  `addresses.assertions` in `manifest.yaml`;
- contract resolution by SDK key, especially `MarketLensV2`, never by a reused
  human-readable name;
- a Wildcat Data Gateway client that names the pinned mainnet release explicitly;
- a health and lag gate checked before every live answer;
- block-number propagation from the query through the rendered response;
- narrow typed operations for registry, market, account, withdrawal queue, and
  borrower-to-markets facts; and
- deterministic renderers for every numeric or market-state response.

The model may eventually choose a typed operation. It must not generate, round,
compare, or characterize the returned figures. Borrower aggregation may show
public facts, but the tool schema must not contain scoring, ranking, reliability,
or inferred-intent fields.

**Complete when:** every live output is reproducible from a typed fixture, names
its observed block and gateway release, declines while the gateway is unhealthy,
and makes no model-authored financial claim.

### 4. Build the question router and answer engine

Only after corpus evidence and live operations have stable contracts should a
model decide how to answer a natural-language question.

Build next:

- a router for the modes already represented in `eval/golden-v1.yaml`:
  `corpus`, `live`, `corpus+live`, premise correction, refusal, refusal with a
  destination, and triage-and-handoff;
- entity and version extraction before retrieval or live queries;
- answer assembly that keeps corpus explanation separate from deterministic live
  values;
- citation validation against the loaded corpus build before an answer leaves
  the process;
- calibrated abstention when evidence is absent, contradictory, out of scope, or
  stale;
- mandatory Known Issues citations when the selected behavior is covered there;
  and
- a triage payload that collects only the details a human actually needs.

The answer engine is not a general chatbot. Advice, borrower trust assessments,
intent inference, unsupported chains, and unreleased behavior are refusals. A
refusal should offer an explicit escalation action rather than paging someone
automatically.

**Complete when:** every factual sentence is backed by validated corpus evidence
or a deterministic live result; unsupported questions decline consistently; and
the same typed inputs produce the same non-model portions of the answer.

### 5. Build end-to-end evaluation and promotion gates

The existing embedding comparison chose a model. It does not test the product
described above.

Build next:

- an evaluator that runs the 125 golden questions through the real router,
  retriever, answer engine, citation resolver, and fixture-backed live tools;
- blocking checks for citation existence and claim support;
- version and deployment correctness, including prerelease isolation;
- calibrated abstention on known-unanswerable and out-of-scope questions;
- deterministic live-value and block-number checks;
- regression reports grouped by answer mode and risk, not only one aggregate
  score;
- explicit human approval of corpus diffs; and
- enforcement of `address_assertions_hold`, `corpus_diff_reviewed`, and
  `eval_not_regressed` before promotion.

Corpus gaps remain documentation work. The evaluator should report them without
rewarding the system for inventing an answer.

**Complete when:** no artifact can become active with a failed or `null` blocking
gate, and a reviewer can reproduce every changed answer from its corpus build,
live fixture, and evaluation record.

### 6. Add the Telegram adapter

Telegram is an interface over the tested answer engine, not the place where
retrieval or policy should live.

Build next:

- long-polling with `getUpdates`, avoiding a public webhook and inbound TLS
  surface;
- group privacy mode so Aleph receives commands and mentions rather than every
  room message;
- message parsing, reply threading, length-aware formatting, and stable citation
  links;
- explicit escalation and triage handoff controls;
- rate limits and bounded concurrency; and
- user-facing failure messages for unavailable live data, unsupported questions,
  and internal errors.

**Complete when:** Telegram integration tests prove that the adapter passes typed
requests and renders typed responses without changing their evidence, figures,
refusal state, or citations.

### 7. Add production deployment and operations

The final stage turns a tested artifact into a service without weakening its
replay and rollback guarantees.

Build next:

- atomic activation of a fully built corpus/index pair;
- rollback by pointer change while retaining the previous artifact;
- separate processes and credentials for ingestion, embedding, query serving,
  and any future signing authority;
- scheduled `sdk-watch.py` execution as an alarm, never an automatic rebuild;
- gateway, model-runtime, Telegram, and evaluation monitoring;
- structured audit records carrying corpus build ID, model identity, route,
  citations, live block, and refusal reason;
- the retention and text-scrubbing boundary for user questions; and
- operational runbooks for stale data, model mismatch, address drift, failed
  promotion, and rollback.

**Complete when:** a bad candidate cannot replace the active artifact, every
served answer identifies the evidence/runtime state behind it, and rollback does
not require rebuilding.

## Explicitly outside the v1 sequence

Hydra integration and on-chain execution are not prerequisites for the retrieval
agent. If added later, the bot process must emit only a signed intent. A separate
executor on a separate host must validate an allowlist of permissionless,
idempotent calls and hold transaction-signing authority. The Telegram or answer
process must never hold that key.

## Rules every stage inherits

**Default deny on sources.** Only manifest-allowed files enter the corpus.
Agent-directed files and deprecated docs stay excluded.

**Deployed beats merged.** General answers describe verified deployed source,
not a repository's current branch.

**A citation is a promise.** Human-visible quotes are byte-exact
`display_text`. Assembled chunks are retrieval aids, never quotations.

**Embedding identity is part of corpus identity.** Backend, model, digest,
dimensions, normalization, and query behavior must match at build and query time.

**Tiers stay visible.** Canonical source and published prose are not silently
collapsed into one authority ranking.

**The model never supplies live numbers.** Typed code queries and renders them,
with a block number.

**Fail closed.** Wrong version, stale gateway, missing citation, model mismatch,
or failed gate produces no answer or promotion.

## Build a canonical evidence release

Python 3.10 or later is required. Corpus builds need `pyyaml` and GnuPG;
indexing needs `numpy`. `ingest/solc-container` uses Docker by default and accepts
Podman through `CONTAINER_RUNTIME`.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install pyyaml numpy

python3 release.py \
  --manifest manifest.yaml \
  --solc ingest/solc-container \
  --artifacts artifacts
```

The command checks the Ollama backend, model, digest, dimensions,
normalization, and query-prefix policy against the manifest before publishing
an index. Use `--against artifacts/corpus/<previous-id>/chunks.jsonl` for a
candidate diff. If it contains changes, a separate reviewed release record can
be created with `--diff-reviewed-by <reviewer>`.

Run the existing checks with:

```bash
python3 ingest/chunkers/test_markdown.py
python3 ingest/chunkers/test_solidity.py --solc ingest/solc-container
python3 ingest/test_build.py
python3 embed/test_embed.py
python3 test_release.py

# Optional real-model smoke test
python3 embed/test_embed.py --model ollama:bge-m3
```

## Repository map

```text
manifest.yaml                 executable corpus and runtime policy
aleph-ingestion-manifest.md   rationale and current limitations
release.py                    manifest -> immutable corpus/index release
test_release.py               release coherence and immutability checks

ingest/
  build.py                    manifest -> validated corpus build
  schema.py                   shared chunk schema and validation
  PIPELINE.md                 implemented ingestion/index workflow
  ADVERSARIAL.md              security invariants and resolved findings
  REVIEW.md                   corpus verification guide
  solc-container              pinned, networkless solc wrapper
  keys/                       trusted public signing keys
  chunkers/
    solidity.py               deployment inputs -> semantic Solidity chunks
    markdown.py               docs tree -> navigable Markdown chunks
    verify_anchors.py         pinned-source vs live-renderer anchor check

embed/
  embedder.py                 embedding backends and identity checks
  index.py                    tiered index build and cosine search
  test_embed.py               index and backend behavior checks

eval/
  golden-v1.yaml              125 questions and expected handling modes
  labels.yaml                 retrieval labels for consequential questions
  embed_compare.py            Markdown-only model comparison harness
  RUNBOOK.md                  recorded model decision and rerun procedure

sdk-watch.py                  mainnet SDK deployment-map change detector
```

`manifest.yaml` is the configuration source of truth. If this README disagrees
with it, the manifest wins and this file needs correction.

---

**A note on the name.** Borges' Aleph is the point in space that contains every
other point, seen simultaneously and without distortion. The last part is the
design constraint, not the first.
