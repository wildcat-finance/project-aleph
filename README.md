# Project Aleph

A retrieval agent that answers questions about the Wildcat Protocol — its
documentation, its deployed contracts, and its live market state — over Telegram.

> *"The Aleph's diameter was probably little more than an inch, but all space was
> there, actual and undiminished."*

---

## Why this exists

The same questions arrive repeatedly, across Discord, Telegram and DMs: how does a
withdrawal batch work, what does this parameter mean, what's the state of this
market, where is this behaviour specified. They are answerable — usually from
material that is already public — but they are answerable *by a small number of
people*, one at a time, forever.

Aleph exists to absorb the repetitive fraction of that load so those people can do
something else. It is explicitly **not** an attempt to replace human answers. The
measure of success is not how many questions it answers; it is how many it answers
*correctly* while reliably declining the rest.

## What it is

- A **pinned corpus** built from public Wildcat sources — protocol source at
  release tags, natspec, audits, and the published documentation.
- A **live-state tool layer** that reads the chain at query time for anything that
  changes: the archcontroller registry, market parameters, queue state.
- A **Telegram bot** exposing both, with citations.

Later, and separately: a path to triggering permissionless, idempotent on-chain
actions (queue processing) via the Hydra executor. That capability is out of scope
for v1 and is architecturally fenced — see *Non-goals* below.

## What it is not

- **Not a source of advice.** Aleph reports; it does not recommend, reassure or
  interpret. Market answers are deterministic renderings with a block number
  attached.
- **Not an oracle for unreleased code.** The corpus tracks release tags bound to
  verified mainnet deployments. If a behaviour exists only on `main`, the correct
  answer is that it isn't released.
- **Not a key holder.** The bot process never has signing authority in its address
  space. See *Design commitments*.
- **Not a general chatbot.** Out-of-corpus questions get a refusal and a pointer to
  a human, not a best guess.

## Design commitments

These are load-bearing and shouldn't be relaxed without a deliberate decision.

**Default deny on sources.** Sources are allowlisted, never crawled-and-filtered.
An allowlist fails visibly; an exclusion list fails silently the moment someone adds
a directory.

**Pinned, reproducible, citable.** Nothing tracks a moving branch. Every answer
names the corpus build that produced it, so any disputed answer can be replayed
against the exact index that generated it.

**Deployed beats merged.** Where repository state and deployed contract disagree,
the deployed contract wins. Merged-but-undeployed is the highest-risk answer class
in the system: correct citation, real code, wrong protocol.

**The model never generates numbers.** Live-state answers route through a
deterministic renderer. The model chooses the query; code formats the reply. A
model-authored figure about someone's capital is a statement Wildcat owns.

**Free text in code is untrusted input.** Comments and natspec reach the model as
context. Ingestion is from signed tags only, so that cutting a tag — a review gate
that already exists — stands between a merged docstring and the bot's behaviour.
These repositories have been targeted through the supply chain before; the
threat model assumes it happens again.

**Signing authority is out of process.** If and when Hydra integration lands, Aleph
emits a signed *intent* to a queue. A separate executor, on a separate host,
validates it against a whitelist of idempotent calls and signs. The worst outcome of
a successful prompt injection is a rejected intent.

## Architecture

```
  sources (pinned)                    live state
  ────────────────                    ──────────
  v2-protocol @ tag                   archcontroller  ─┐
  docs build                          market contracts ┤
        │                                              │
        ▼                                              ▼
   CI ingest ──► corpus artefact ──► eval gate ──► atomic swap
                        │                                │
                        └──────────► retrieval ◄─────────┘
                                          │
                                          ▼
                              answer + citation + block no.
                                          │
                                          ▼
                                Telegram (long-poll)
```

Postgres with pgvector for the index, chat log and audit trail. Hybrid BM25 +
embeddings — the corpus is small, and exotic retrieval buys nothing here. Bot
process is stateless; long-polls `getUpdates` rather than exposing a webhook, so
there is no inbound port and no public TLS surface. Privacy mode is on in groups:
Aleph sees commands and mentions, not every message in rooms where counterparties
talk to each other.

## Repository contents

```
ingestion-manifest.md    what is indexed, at what ref, and what is excluded
README.md                this file
eval/                    golden question set and gate    [not yet started]
```

Implementation to follow. The manifest and the eval set come first deliberately:
the question set determines what the corpus needs to contain, which is cheaper to
learn before ingestion is built than after.

## Status

Pre-implementation. Open decisions are listed at the end of
[`ingestion-manifest.md`](./ingestion-manifest.md); the two that block a build are
the tag ↔ mainnet deployment binding, and whether cross-market aggregation by
borrower is a supported query or a declined one.

---

**A note on the name.** Borges' Aleph is the point in space that contains every
other point, seen simultaneously and without distortion. The last part is the
design constraint, not the first.
