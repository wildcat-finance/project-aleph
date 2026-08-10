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
- **Not a profiling service.** Borrower-keyed aggregation across markets is
  permitted — a lender can ask what markets a borrower has run and see them — but
  the output is deterministic rendering only. Aleph presents the facts; it does
  not characterise them. It will show six markets and their histories; it will not
  say that a borrower "tends to" or "has a pattern of" anything, will not score,
  rank, compare or infer intent, and will not answer whether a borrower is
  trustworthy. Every fact in such an answer is public and on-chain, but the
  compilation is an artefact Wildcat produced on request, and the line between
  showing and characterising is where the risk lives.
- **Not an oracle for unreleased code.** The corpus tracks release tags bound to
  verified mainnet deployments. If a behaviour exists only on `main`, the correct
  answer is that it isn't released.
- **Not a key holder.** The bot process never has signing authority in its address
  space. See *Design commitments*.
- **Not a general chatbot.** Out-of-corpus questions get a refusal and a pointer to
  a human, not a best guess.

## It speaks in Wildcat's voice, and isn't Wildcat speaking

Aleph will read as authoritative — same name, same channel, answering in the first
person about live facilities. It isn't a representation by Wildcat Labs or the
Wildcat Foundation, doesn't create obligations, and doesn't supersede the Terms of
Use or the market's own on-chain state. Where Aleph and the chain disagree, the
chain is correct. Where Aleph and the ToU disagree, the ToU is correct.

The gap between how authoritative it sounds and what it actually is cannot be
closed by a disclaimer nobody reads — which is why the constraints below exist:
cite everything, generate no numbers, decline rather than guess.

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
manifest.yaml                 machine-readable corpus definition — CI reads this
aleph-ingestion-manifest.md   why the manifest says what it says
ingest/PIPELINE.md            how manifest.yaml becomes a queryable corpus
sdk-watch.py                  mainnet SDK deployment-map watcher (CI)
README.md                     this file
eval/golden-v0.yaml           baseline question set — straw man, not validated
```

`manifest.yaml` is the source of truth; the prose document explains it. If the two
disagree, the YAML wins and the prose is a bug.

Implementation to follow. The manifest and the eval set come first deliberately:
the question set determines what the corpus needs to contain, which is cheaper to
learn before ingestion is built than after.

## Status

**This repository is private; the bot it produces is public.** Those are different
boundaries and only one of them is a control. Anything that reaches Aleph's context
window is effectively published — a public bot can be asked what it knows, and will
eventually be asked in a way that works. Repository privacy protects the working
notes, the frank assessments and the roster; it protects nothing that gets loaded
into the model at runtime.

Two consequences. Aleph's own repository is never a source for Aleph — the spec
documents are not in the allowlist and must not drift into it. And the deployed
context should be assumed readable by anyone, so it carries public corpus and
nothing else: no internal status, no names, no gaps we haven't announced.

Pre-implementation. Scope is **mainnets only** — Ethereum and Plasma. Sepolia and
other testnets are ignored entirely: not ingested, not queried, not answerable.

Detailed decisions and accepted risks are at the end of
[`aleph-ingestion-manifest.md`](./aleph-ingestion-manifest.md). The items below are
the ones that need a human rather than a build step.

## To address

**Needs Dave**

- Which subgraph release does SDK `3.1.17` expect? `v2.0.26` and `v2.0.30` are both
  live on mainnet and Aleph must pin one in config, not choose at runtime.
- Which subgraph commit produced release `v2.0.30`? `subgraph@main` is at `2.0.22`,
  so the repo can't say.
- Commit provenance for `MarketLensV2` and `CollateralLens`. Deployed, view-only,
  and untraceable to source — which is the code that produces every number Aleph
  will quote.
- A dedicated gateway bearer for Aleph, separate from the frontend's, so revoking
  one doesn't take down the other.

**Needs a decision**

- Vocabulary alignment with `wildcat-notifications`. Aleph is pull to that bot's
  push; both live in Telegram and must describe the same market state in the same
  words. Whose phrasing wins where they differ?
- `wildcat-juris` is currently excluded from the corpus (claims intake for
  defaulted markets, identified lenders). Confirm or override.
- Duty roster lives in deployment config, not here. Confirm.

**Needs authoring, not deciding**

- The golden question set. `eval/golden-v0.yaml` is a baseline written from public
  sources by someone who has never been asked any of them — react to it rather
  than start from blank. What it can't supply is frequency, real phrasing, and the
  questions people ask when a market is already delinquent.

**Housekeeping**

- Report the `@functi0nZer0` Telegram squat via @NoToScam. Not a Fragment
  collectible, so it is actionable.
- Publish the real team handles on docs.wildcat.finance so refusals can point at
  an authoritative page rather than naming a person in-channel.

---

**A note on the name.** Borges' Aleph is the point in space that contains every
other point, seen simultaneously and without distortion. The last part is the
design constraint, not the first.
