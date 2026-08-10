# Project Aleph

Project Aleph is intended to answer questions about the Wildcat Protocol over
Telegram using pinned, citable protocol knowledge and block-numbered live state.

This repository contains the evidence and answer path: reproducible ingestion,
tiered retrieval, typed live-state reads, policy-first routing, citable answer
assembly, blocking product evaluation, a long-polling Telegram adapter, and
verified production activation, rollback, audit, and monitoring controls.

The shortest honest status is:

> **Aleph's repository build sequence is implemented end to end. Deployment now
> requires operator-owned infrastructure, service credentials, and a named
> human-handoff destination.**

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
- typed mainnet/version/tier-scoped hybrid retrieval, isolated v2.5 handling,
  manifest-visible mandatory sources, and byte-verified citation resolution;
- pinned SDK address verification, health-gated gateway reads at one observed
  block, five narrow live operations, and deterministic numeric renderers;
- policy-first routing over every golden handling mode, entity extraction,
  evidence-supported claim assembly, refusals, and bounded triage payloads;
- a blocking 125-question product evaluator with deterministic live replay,
  version isolation, exact claim-support checks, and immutable reports;
- approval that binds the exact evaluation to a new release identity only when
  every manifest gate is `true`;
- a privacy-mode, long-polling Telegram adapter with durable offsets, bounded
  admission, threaded replies, exact answer splitting, and confirmed handoffs;
- compare-and-swap activation, immutable switch history, pointer-only rollback,
  scrubbed audit records, runtime composition, and dependency monitoring;
- a 125-question golden set, retrieval labels, and the recorded `bge-m3` model
  comparison; and
- `sdk-watch.py`, which detects mainnet SDK deployment-map changes without
  changing the corpus.

Raw corpus build records retain `null` placeholders for checks that require the
SDK and completed index. `release.py --fetch-sdk`, `eval/product_eval.py`, and
`promotion.py` resolve those gates at their proper boundaries. Production
activation remains a separate, attributable operator action.

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

Downstream gates remain visible rather than being guessed: a candidate is not
promotable while `address_assertions_hold` or `eval_not_regressed` is `null`.

### 2. Scoped retrieval and citation resolution — implemented

`retrieval.py` loads an immutable release and exposes typed `RetrievalRequest`,
`RetrievalResponse`, `Evidence`, and `Citation` objects. It refuses an artifact
whose manifest, corpus, index record, payload hash, embedding identity, or chunk
count does not match the release.

The implementation provides:

- a retrieval API whose request carries chain, public protocol
  version, requested tiers, and result limits;
- Tier A and Tier B searches that remain separate through ranking;
- BM25-style lexical matching and exact identifier/address bonuses fused with
  semantic results independently within each tier;
- v2.0 as the default deployed corpus and an isolated v2.5 path that activates
  only when the user explicitly names v2.5;
- enforcement of `always_cite`, prerelease preambles, deployment status, and
  source-version filters;
- a citation resolver that turns a hit into a stable source path and Markdown
  anchor or Solidity location; and
- a hard prohibition on quoting chunks marked `synthesised: true`, plus a
  corpus-byte comparison before every quote.

`eval/retrieval_eval.py` runs `eval/labels.yaml` through this actual retriever,
not through the model-comparison splitter. Retrieval returns evidence only; it
does not generate answer prose.

### 3. Live-state tools and deterministic renderers — implemented

`live.py` keeps changeable state outside the corpus and outside model-authored
prose. It loads the exact SDK package pinned by version, npm SRI digest, and
registry `gitHead`, then checks every asserted mainnet deployment key.

The implementation provides:

- SDK artifact loading and enforcement of every address under
  `addresses.assertions` in `manifest.yaml`;
- key-only contract resolution—`MarketLens` is refused while `MarketLensV2` is
  asserted and available;
- a Wildcat Data Gateway client that names `mainnet/v2.0.30` explicitly and has
  no provider fallback;
- a health, integrity, circuit, redundancy, and zero-lag check immediately
  before every GraphQL request;
- queries pinned to the checked indexed block, with exact `_meta` block
  agreement required in the response;
- typed registry, market, account, withdrawal-queue, and borrower-to-markets
  operations; and
- deterministic renderers for every numeric or market-state response.

Token amounts and basis points are formatted with integer arithmetic. Every
renderer appends the Ethereum block and gateway release. Borrower aggregation
contains public market facts only—no score, rank, reliability, risk, or inferred
intent. `release.py --fetch-sdk` binds a successful address check into
`address_assertions_hold`; without it, that gate remains `null`.

### 4. Question router and answer engine — implemented

`agent.py` routes before calling retrieval, live state, or a language writer. It
extracts chain, public version, market, lender, and borrower addresses first,
then selects one reviewed handling mode.

The implementation provides:

- a router for the modes already represented in `eval/golden-v1.yaml`:
  `corpus`, `live`, `corpus+live`, premise correction, refusal, refusal with a
  destination, triage-and-handoff, and the set's one partial-answer case;
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

The dependency-free `ExtractiveWriter` emits only exact corpus substrings. A
future language writer plugs into the same typed contract: every claim must name
an evidence ID and an exact supporting quote supplied to it. The engine verifies
both against the loaded corpus before adding a commit-pinned citation. It then
appends the deterministic live block without exposing it to the writer.

Advice, borrower assessment, inferred intent, unsupported chains, private
lender lists, and prompt/private-context extraction are refused. Handoffs are
prepared but never sent without a separate explicit confirmation. The router's
handling mode matches all 125 reviewed golden questions; answer quality and
claim support are enforced by the blocking stage-5 gate.

### 5. End-to-end evaluation and promotion gates — implemented

The existing embedding comparison chose a model. It does not test the product
described above.

`eval/product_eval.py` runs every reviewed question through the real router,
retriever, citation resolver, answer engine, and typed fixture-backed live
client. It publishes a content-addressed record under
`artifacts/evaluations/<evaluation_id>/evaluation.json`.

The implementation provides:

- execution of all 125 golden questions through the real router, retriever,
  answer engine, citation resolver, and fixture-backed live tools;
- blocking checks for citation existence and claim support;
- version and deployment correctness, including prerelease isolation;
- calibrated abstention on known-unanswerable and out-of-scope questions;
- deterministic live-value and block-number checks;
- reporting by reviewed mode and conservative risk class, with every failed ID;
- nine declared corpus gaps that must abstain or route elsewhere rather than
  receiving credit for a plausible-looking answer; and
- `promotion.py`, which verifies the immutable evaluation and current evaluator
  hashes, refuses failed or altered reports, and creates a distinct evaluated
  release only when every required gate is exactly `true`.

The current claim gate is deliberately strict: claims must be exact extracted
evidence. A future paraphrasing writer remains blocked until a separately pinned
semantic verifier exists.

Approval does not activate a release. It produces the only artifact stage 7 may
later activate, retaining the candidate, live fixture hash, tool hashes, per-case
results, and evaluation identity needed for reproduction.

### 6. Telegram adapter — implemented

Telegram is an interface over the tested answer engine, not the place where
retrieval or policy should live.

`telegram.py` implements the interface without moving retrieval or policy into
the transport. `TELEGRAM.md` states its runtime and privacy boundaries.

The implementation provides:

- startup checks that require long polling, an absent webhook, and enabled group
  privacy mode;
- message-only `getUpdates` polling with an atomically persisted offset;
- private questions plus group commands, mentions, and replies, while ambient
  room text and commands for other bots are ignored;
- message parsing, reply threading, length-aware formatting, and stable citation
  links;
- an allowlisted handoff draft and preview followed by a separate explicit
  `/confirm_handoff`, with the default destination disabled;
- rate limits and bounded concurrency; and
- user-facing failure messages for unavailable live data, unsupported questions,
  and internal errors.

`test_telegram.py` passes real fixture-backed answer-engine output through the
adapter. It checks unchanged citation text, topic/reply identity, exact
reconstruction of split answers, send-failure checkpoint behavior, bounded
admission, fixed internal-error text, and the no-confirmation/no-handoff rule.

### 7. Production deployment and operations — implemented

The final stage turns a tested artifact into a service without weakening its
replay and rollback guarantees.

`activation.py`, `serve.py`, `audit.py`, and `monitor.py` implement the runtime
boundary. `ops/OPERATIONS.md` is the operator runbook and `ops/systemd/` contains
hardened service and timer templates.

The implementation provides:

- compare-and-swap activation after re-verifying the release, corpus, index,
  evaluation, manifest policy, and every required gate;
- immutable activation records and atomic pointer replacement;
- rollback as a new pointer generation while retaining every artifact;
- separate processes and credentials for ingestion, embedding, query serving,
  and any future signing authority;
- a daily `sdk-watch.py` alarm that never rebuilds or edits the manifest;
- one-shot active-release, model-runtime, gateway, Telegram, and evaluation
  monitoring suitable for a five-minute supervisor timer;
- a credential-free gateway preflight report backed by one authenticated,
  health-checked, block-pinned registry query;
- structured audit records carrying corpus build ID, model identity, route,
  citations, live block, and refusal reason;
- HMAC-only question fingerprints, no raw question/answer/address retention,
  owner-only daily audit files, and bounded retention; and
- operational runbooks for stale data, model mismatch, address drift, failed
  promotion, and rollback.

The checked tests prove that a raw, failed, null-gated, changed, or incoherent
candidate cannot become active; every served answer audit identifies its
evidence/runtime state; and rollback does not rebuild or delete anything.
Actually starting the service remains an operator action because the repository
does not own its host, gateway token, Telegram bot, or human support destination.

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
  --fetch-sdk \
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
python3 test_retrieval.py
python3 test_live.py
python3 test_agent.py
python3 test_evaluation.py
python3 test_telegram.py
python3 test_operations.py

# After building both main and prerelease evidence releases:
python3 eval/product_eval.py \
  --manifest manifest.yaml \
  --release artifacts/releases/<main_release_id>/release.json \
  --prerelease artifacts/releases/<v25_release_id>/release.json \
  --embedder ollama:bge-m3

python3 promotion.py \
  --release artifacts/releases/<main_release_id>/release.json \
  --evaluation artifacts/evaluations/<evaluation_id>/evaluation.json

# Optional real-model smoke test
python3 embed/test_embed.py --model ollama:bge-m3

# Authenticated Data Gateway preflight (source credentials into the environment)
python3 gateway_smoke.py
```

## Repository map

```text
manifest.yaml                 executable corpus and runtime policy
aleph-ingestion-manifest.md   rationale and current limitations
release.py                    manifest -> immutable corpus/index release
test_release.py               release coherence and immutability checks
retrieval.py                  scoped hybrid retrieval + citation resolver
test_retrieval.py             scope, isolation, ranking and quote checks
live.py                       SDK address gate, gateway reads and renderers
gateway_smoke.py              authenticated block-pinned gateway preflight
test_live.py                  lag, block, address and numeric fixtures
agent.py                      routing, refusals and answer assembly
ANSWERING.md                  answer-path contracts and failure boundaries
test_agent.py                 golden routing and assembly adversarial checks
promotion.py                  all-gates-true evaluated release approval
test_evaluation.py            product gate and approval adversarial checks
telegram.py                   privacy-mode long-polling interface adapter
TELEGRAM.md                   Telegram delivery and handoff boundaries
test_telegram.py              parsing, delivery, offset and handoff integration
activation.py                 verified atomic activation and rollback history
audit.py                      scrubbed append-only answer provenance
serve.py                      production query/Telegram composition
monitor.py                    active/model/gateway/Telegram one-shot checks
test_operations.py            activation, audit, composition and monitor checks

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
  retrieval_eval.py           labels against an immutable release retriever
  product_eval.py             blocking 125-question product evaluation
  live-fixture-v1.json        deterministic typed promotion fixture
  RUNBOOK.md                  recorded model decision and rerun procedure

sdk-watch.py                  mainnet SDK deployment-map change detector
ops/                          production runbook and hardened systemd templates
```

`manifest.yaml` is the configuration source of truth. If this README disagrees
with it, the manifest wins and this file needs correction.

---

**A note on the name.** Borges' Aleph is the point in space that contains every
other point, seen simultaneously and without distortion. The last part is the
design constraint, not the first.
