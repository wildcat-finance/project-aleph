# Project Aleph — Ingestion Manifest v0.1

> **DAVE WORKING ON THIS — subgraph provenance.** The Data Gateway (public staging)
> resolves subgraph *routing and pinning*: releases are explicit immutable
> identifiers with no `latest`, no default and no cross-release fallback, reachable
> at `graph.wildcat.finance/{network}/{release}`. That is a better pin than a
> deployment ID. What it does not resolve: which subgraph *commit* produced release
> `v2.0.30`, and which release SDK `3.1.17` expects. `wildcat-finance/subgraph` on
> `main` is at `2.0.22`, so the repo cannot answer either. Both still open.

Scope: what goes into the index, at what version, and what is deliberately excluded.
Everything here is public material. The controls below exist for **reproducibility,
correctness and injection resistance**, not confidentiality.

Status: draft. Sections marked **[OPEN]** need a decision from LD before build.

---

## 1. Governing principles

1. **Default deny.** A source is ingested only if it appears in §3. There is no
   "crawl and exclude" mode. Exclusion lists rot silently; allowlists fail loudly.
2. **Pinned, never tracking.** Every source resolves to an immutable ref (git tag,
   commit SHA, docs build hash). No branch tracking, including `main`.
3. **Reproducible answers.** Every answer cites the corpus build that produced it.
   Any complaint can be replayed against that exact build.
4. **Live state is not corpus.** Anything that changes without a human deciding it
   changed is read at query time through a tool, never embedded.
5. **Deployed beats merged.** Where the two disagree, the deployed contract is the
   truth. Merged-and-undeployed is the highest-risk answer class in the system.

---

## 2. Corpus tiers

| Tier | Contents | Pin | Rebuild trigger |
|---|---|---|---|
| A — Canonical | Deployed contract source, natspec, audit reports, deployment address book | Release tag ↔ verified deployment | Human cuts a tag |
| B — Published docs | docs.wildcat.finance, ToU, lender/borrower guides, long-form (*The Promise Machine*) | Docs build hash / doc version + effective date | Docs deploy, manually promoted |
| L — Live state | Archcontroller registry, market parameters, queue state | None — read at query time | n/a |

Tiers A and B are indexed separately and retrieved separately. A single blended
index lets a blog paragraph outrank a contract on a question about contract
behaviour, which is the failure mode that matters most here.

---

## 3. Sources

### 3.1 `v2-protocol` — Tier A

```yaml
repo: wildcat-finance/v2-protocol
ref_policy: signed_tags_only
refs:
  - tag: v2.1.0
    sha: c7be403
    released: 2026-04-01
    label: "v2.1 — 4626 Vault Wrapper"
    signature: gpg_verified          # 0xMcsweeja, GitHub vigilant mode
    status: current
  - tag: v2.0.0
    sha: a70f297
    released: 2026-03-17
    label: "v2.0 Protocol Release"
    status: superseded               # retained for historical questions
  - tag: <v2.5 tag, when cut>
    status: pending
include:
  - "src/**/*.sol"
  - "docs/**/*.md"                   # real prose, not natspec — see below
  - "EIP-4626_audit_scope.md"
  - "README.md"
  - "TESTS.md"
exclude:
  - "test/**"          # asserts behaviour that may never have shipped
  - "script/**"        # deploy scripts read as instructions
  - "scripts/**"
  - "lib/**"           # git submodules (.gitmodules present); never ingest
  - ".github/**"
  - "**/*.t.sol"
verification_only:                   # fetched, never chunked or embedded
  - "deployments/mainnet/**/standard-input.json"
```

`docs/` at the tag is genuine documentation rather than generated material — ten
files including `Core Behavior.md`, `Known Issues.md`, `Terminology.md`,
`Scale Factor.md` and three hooks documents. **`Known Issues.md` should be
volunteered, not merely retrievable**: any answer touching a behaviour documented
there cites it unprompted.

`deployments/mainnet/<Contract>-<address>/standard-input.json` is solc standard
JSON verification input. It makes the tag ↔ bytecode check buildable from material
already published, without scraping a block explorer. It is a build-time input to
that check and must never enter the index.

**Pre-release: `release/v2.5`.** The to-audit branch, near-frozen, not audited and
not deployed. Useful to have retrievable; dangerous to have retrievable *silently*.

```yaml
prerelease:
  branch: release/v2.5
  snapshot_sha: dec36d2          # pinned, not tracked — re-snapshot deliberately
  index: separate                # never merged into the Tier A index
  status: not_audited, not_deployed
  answerable: only when the asker names v2.5 explicitly
  preamble: mandatory            # every answer states unaudited + undeployed
```

It is a *snapshot*, not a branch subscription — same reasoning as everywhere else,
plus this is the branch most likely to move under an auditor's feedback. Retrieval
from it never satisfies a general question: "how do withdrawals work" answers from
v2.1.0, and mentions v2.5 only if the delta is material and the user asked.

Note for the verification tooling: `v2.1.0` is an **annotated** tag. The tag object
is `8aab396` and the commit is `c7be403`; the GPG signature is on the tag object.
Verify the tag, then resolve to the commit — checking the commit alone verifies
nothing.


**No `main`.** If a question can only be answered from unreleased code, the correct
answer is "that isn't released yet," not a citation to a merge.

**Tag ↔ deployment binding.** Each tag in the manifest carries the mainnet addresses
it corresponds to, and the build fails if an address in the book is not
Etherscan-verified against that tag's bytecode. This is the check that stops Aleph
describing code no lender's money is in. **[OPEN]** where does the canonical
address book live today — repo, docs, or somewhere else?

### 3.2 Live state — Tier L

The archcontroller is a live contract, not a document. Two distinct uses:

- **Registry queries** ("which markets exist", "is this borrower registered",
  "which hooks templates are approved") — read on chain, cached with a block
  number, refreshed on a schedule. Every answer states the block.
- **Anything about a specific market's current numbers** — always live, never
  cached, never embedded.

The ABI and the deployed address go in Tier A via the repo pin. The *values* never
enter the index.

**Borrower-keyed aggregation — resolved, and structural.** Aggregating a borrower's
markets is permitted; characterising them is not. This has to be enforced in the
shape of the tool layer, not in the prompt, because a prompt instruction is not a
control:

- The query interface may take a borrower as a key and range over their markets.
- Results return through the deterministic renderer, same as any market answer —
  facts, addresses, amounts, timestamps, block number.
- No comparative or evaluative field exists for the model to populate. No score,
  no rank, no aggregate ratio computed across markets, no derived "history"
  object. If the renderer cannot emit it, the model cannot assert it.
- Questions of the form "is this borrower reliable / would you lend to them /
  how do they compare to X" are refusals, not answers with caveats.

The facts are public. The compilation is an artefact Wildcat produced on request,
and the line between showing and characterising is where the risk lives.

**Lens resolution — resolve by key, never by name.** Three distinct mainnet
addresses have carried the label "MarketLens" across sources, and the production
one is not the one keyed `MarketLens`:

| Source / key | Address | Status |
|---|---|---|
| SDK `MarketLensV2` | `0xfDA5C5B96bb198D2fca1A01d759620B64Ae5afE7` | **production** |
| SDK `MarketLens` | `0xf1D516954f96c1363f8b0aE48D79c8ddE6237847` | legacy |
| repo `deployments.json` `MarketLens` | `0xC672760757da93B5f3275dc97203D145806dae33` | stale |

All three are live contracts with distinct bytecode, so "does it have code" is not
a validity check. Aleph resolves the lens through the `MarketLensV2` key and pins
the expected address explicitly; a lookup keyed on the human-readable name
"MarketLens" returns the legacy contract and produces plausible, wrong numbers.
The SDK's own typing anticipates this — `MarketLensV2Like = MarketLensV2 |
MarketLensV21` — so the version axis will move again.

Build-time assertion: the address behind `MarketLensV2` matches the pinned value,
or the build fails. "SDK is authoritative" is not sufficient on its own when the
authoritative source carries a decoy under a more obvious name.


disagree. `@wildcatfi/wildcat-sdk` (`dist/constants.js`, `Deployments`) is
authoritative and reflects the current state of production. The repo's
`deployments/mainnet/deployments.json` is **stale** — it carries a superseded
`MarketLens` address and omits `Wildcat4626WrapperFactory` entirely, despite that
being the contract v2.1.0 is named for. Aleph reads addresses from the SDK only.
The repo book stays in `verification_only`, never as an answer source.

Confirmed with D. Coleman, 2026-08-09: one 4626 wrapper factory on mainnet
(`0xEA6DE11f…`); SDK 3.1.17 and subgraphs 2.0.30 are current for production.

Mainnet contracts the SDK carries that the repo book does not — `MarketLensV2`,
`CollateralLens`, `Wildcat4626WrapperFactory`, `WildcatCollateralFactory`,
`WildcatMarketControllerFactory`, `OpenAccessRoleProvider` — are live-state
sources with no corresponding tag binding. See §10.

Conversely the repo book carries `_initCodeStorage` addresses for `WildcatMarket`,
`OpenTermHooks` and `FixedTermHooks` that the SDK omits. That is where market and
hook behaviour actually lives, so "what code is my market running" is answerable
from the repo book and not from the SDK. Neither book is complete.

### 3.3 Live-state transport: the Data Gateway — Tier L

All chain and subgraph reads go through the Wildcat Data Gateway rather than
directly to a provider. One stable Wildcat-owned address, ordered failover behind
it, and — the part that matters here — exact release routing.

```yaml
rpc:    https://rpc.wildcat.finance/{chainId}        # 1, 9745, 9746 — mainnets only
graph:  https://graph.wildcat.finance/{network}/{release}
health: https://graph.wildcat.finance/health         # unauthenticated
auth:   Authorization: Bearer $ALEPH_GATEWAY_TOKEN   # dedicated, not shared
pinned_release:
  mainnet: v2.0.30            # v2.0.26 also live — [OPEN] which does SDK 3.1.17 speak?
  plasma-mainnet: v2.0.30
```

**Release pinning is solved by the gateway, and solved the right way.** There is no
`latest` route, no default release, no "closest compatible" fallback. If the
requested release is unavailable the gateway says so rather than guessing. Aleph
pins one release per network and states it in citations; a schema it does not
understand is an error, not a degraded answer.

**Testnets are out of scope.** Sepolia routes, releases and deployments are
ignored entirely: not ingested, not queried, not answerable. A testnet answer that
looks like a mainnet answer is a wrong answer about someone's money.

**Two mainnet releases are live simultaneously** (`v2.0.26` and `v2.0.30`). Aleph
must not choose dynamically. The pin is config, changed deliberately.

**Lag gate — the mitigation for indexer drift.** `/health` is unauthenticated and
returns release readiness, sync state, freshness/lag and circuit-breaker state from
a maintained snapshot, so polling it costs no upstream provider traffic. Aleph
checks it before answering any market question. If the pinned release is lagging or
its providers are unhealthy, Aleph says so and declines rather than serving stale
numbers as current.

**Every subgraph answer carries `_meta { block { number } }`.** The "state the
indexed block, not chain head" requirement is one field in the query, so there is
no excuse for an answer that omits it.

**Token hygiene.** Aleph gets its own bearer, not the frontend's. It is a read
credential — worst case is provider spend and abuse, not fund loss — but a shared
token means revoking Aleph's access takes the app down with it. Server-side only;
Aleph has no browser surface, so the `NEXT_PUBLIC_*` failure mode does not apply.

**Status: public staging, no production SLA.** Aleph should be configured to
degrade to "I can't reach live data right now" rather than to a fallback provider,
because a silent fallback path is how an unpinned release gets queried. See §10.

### 3.4 `docs.wildcat.finance` — Tier B

```yaml
source: docs.wildcat.finance
ingest: build_output          # prefer the docs repo over scraping rendered HTML
ref_policy: promoted_build
include:
  - "content/**/*.md(x)"
exclude:
  - blog posts superseded by a later post on the same subject   # [OPEN] curate list
metadata_required:
  - doc_version
  - effective_date
  - supersedes            # nullable
```

ToU chunks carry the version in force and Aleph names it when quoting. A ToU answer
without a version is a wrong answer even when the text is right.

**`AGENTS.md` and `CLAUDE.md` are excluded.** They are prose written to direct an
agent's behaviour, sitting inside an otherwise-trustworthy documentation repo. In
the context window they are indistinguishable from instructions Wildcat intended
Aleph to follow, and unlike a natspec comment they are *designed* to be obeyed.
Useful to the pipeline as structure hints; never as retrievable content.

**`wildcat-notifications` is a sibling, not a source.** The existing event bot
pushes deposits, withdrawal-batch creation and status changes into Telegram with an
established vocabulary — "market now Pending Repayment", "new withdrawal batch of
$X (batch expires ...)". Aleph is pull to its push and must not duplicate the feed.
Two constraints follow:

- **Vocabulary alignment.** Aleph's deterministic renderer reuses the notification
  bot's phrasing for the same states. Two bots in the same channel describing one
  market differently is a contradiction someone will screenshot.
- **No bot chaining.** Aleph derives state from the gateway, never by reading the
  notification feed. A second-hand event is an unciteable one.

### 3.5 Other repositories — inputs

All five are inputs to the system; only two are answer sources.

| Repo | What it is | Role |
|---|---|---|
| `v2-protocol` | Solidity, docs, deployment records | **Tier A** — §3.1 |
| `wildcat-docs` | GitBook source for docs.wildcat.finance, branch `master` | **Tier B** — §3.4 |
| `subgraph` | `@wildcatfi/wildcat-subgraph`, `main` at 2.0.22 | Live-state schema. Not an answer source. |
| `wildcat.ts` | Source of `@wildcatfi/wildcat-sdk`, `main` at 3.0.54-beta | ABI/address provenance only. **Not an answer source** — see below. |
| `wildcat-app-v2` | Next.js frontend, `main` at 2.17.0 | Reference for the SDK pin. Not indexed. |
| `wildcat-juris` | Lender claim-intake for defaulted markets, branch `master` | **Excluded.** See below. |
| `wildcat-gateway` | Data Gateway deployment — provider order, chain inventory, release identities | Live-state transport config (§3.3). Not indexed. |

**`wildcat.ts` is behind npm.** Repo `main` is `3.0.54-beta`; published production is
`3.1.17`. The repo cannot tell you what is in the deployed SDK, so address and ABI
truth stays with the npm artefact (§3.2) and the repo is provenance only. Third
instance of the same pattern in this document.

**`wildcat-juris` is excluded from the corpus.** It is a claim-intake tool for
*defaulted* markets: it collects lender contact details, country, and signed claim
forms. The code is public; the subject matter is defaults, claims and identified
lenders. Two reasons to keep Aleph away from it:

1. Ingesting it invites default-and-claims questions, which is the one topic where
   a confidently wrong or merely *tonally* wrong answer is worst. Those route to a
   human, always.
2. It enumerates a borrower's markets on-chain — the same capability bounded in
   §3.2. Aleph should not learn that pattern from a tool built for a different
   purpose under different consent.

If a lender asks Aleph about a claim, the correct behaviour is a pointer to the
claims process, not an answer about it.

**Subgraph `networks.json` is a third address book.** It carries mainnet
`WildcatArchController`, `WildcatSanctionsSentinel`, `HooksFactory` and
`CollateralFactory` with `startBlock` values, and agrees with the SDK on all four.
Useful as a cross-check and as the source of indexing start blocks; not authoritative.

## 4. Chunk metadata schema

Every chunk, every tier:

```
corpus_build_id      # monotonic, e.g. 47
tier                 # A | B
source_ref           # git tag + SHA, or docs build hash
source_path
protocol_version     # "v2" | "v2.5" | null
deployment_status    # deployed | pending | n/a
effective_date       # tier B
doc_version          # tier B
supersedes           # nullable
```

`protocol_version` is the important one: it is what lets a retrieved chunk be
filtered against the version the user is actually asking about, and what stops v2.5
answers leaking into v2 questions the day the tag is cut.

---

## 5. Injection surface

Natspec and comments are free text inside otherwise-trustworthy files, and they
reach the model as context. Given a named actor with prior interest in these repos:

- Ingest from **signed tags only** — a human cutting a tag is the review gate.
- Strip non-natspec comment bodies before chunking. Natspec is kept (it is real
  documentation) but is fenced in the prompt as untrusted quoted material, not
  instruction.
- **Diff the corpus between builds.** Emit a human-readable changelog of what
  entered and left the bot's knowledge. A docstring-only commit that changes
  Aleph's behaviour should be visible in one screen.
- No source ingests markdown or comments that arrive by PR from outside the org.

---

## 6. Build and deploy

```
cut tag  →  CI ingest  →  corpus artefact (immutable, numbered)  →  eval gate  →  atomic swap
```

- The index is never mutated in place.
- The previous build stays on disk; rollback is a pointer change.
- The eval gate (§7) is blocking: a build that regresses abstention or citation
  accuracy does not ship, regardless of what changed in the corpus.

---

## 7. Eval gate — placeholder

Golden set of ~100 real questions with known-correct answers. Blocking metrics:

- **Citation validity** — does the cited chunk exist in this build and support the
  claim.
- **Version correctness** — does a v2 question get a v2 answer.
- **Calibrated abstention** — refusal rate on the known-unanswerable subset. This is
  the metric that decides whether Aleph saves time or costs it.

Needs the question set before it can be written. See separate workstream.

---

## 8. Escalation and retention

### 8.1 Refusal handling

A refusal does not ping anyone. It logs, and it offers the asker an explicit
escalate action. Automatic paging on every refusal hands an unbounded interrupt
budget to whoever is asking, and the people it interrupts are the people this was
built to unburden.

```yaml
on_refusal:
  log: always
  notify: never
  offer_escalation: true
on_escalation:            # only when the asker explicitly chooses it
  route: round_robin
  roster: $ALEPH_DUTY_ROSTER    # NOT checked in — see below
  rate_limit_per_user: 1 / 24h
  global_cap_per_day: 10
digest:
  non_escalated_refusals: weekly, batched, no interrupt
```

**The roster does not live in this repo.** Four named Telegram handles in a public
repository, annotated with role and escalation authority, is a targeting list — it
tells an attacker precisely who to impersonate and who to approach. Handles go in
deployment config; the repo refers to roles.

### 8.2 Retention

Two tiers, because the identifiers and the questions have opposite optimal
lifetimes.

| | Contents | Retention |
|---|---|---|
| Raw | Telegram ID, username, channel, timestamp, question as asked | **30 days**, then hard delete |
| De-identified | Question text only | Indefinite — this is the eval set |

At 30 days the raw record is destroyed, not archived. What survives is the question
with no data subject attached.

**De-identification is not dropping the ID column.** Questions carry identifiers in
their text: "our market", named counterparties, position sizes, a market address
that is public on chain but identifying in combination with the asker. The 30-day
job runs a scrub pass over the text, and anything that cannot be scrubbed
confidently is dropped rather than retained — the eval set is allowed to be lossy,
the retention boundary is not.

**Derived artefacts inherit the boundary.** Eval fixtures, retrieval indexes and
digests built from raw logs are raw logs. They are built from the de-identified
store only. A record purged at day 30 that was copied into a fixture on day 3 has
not been deleted. This includes backups: a 30-day policy against a 90-day snapshot
retention is a 90-day policy.

---

## 9. Open decisions

1. ~~Cross-market aggregation by borrower.~~ **Resolved:** permitted, deterministic
   rendering only, no characterisation. Enforced in the tool layer (§3.2).
2. ~~Repo list beyond `v2-protocol`.~~ **Resolved:** five named, roles assigned
   (§3.5). `wildcat-juris` excluded.
3. ~~Which tag corresponds to the current mainnet deployment, and who cuts tags.~~
   **Resolved:** `v2.1.0` / `c7be403`, GPG-signed, cut by 0xMcsweeja.
4. ~~Where the canonical address book lives.~~ **Resolved:** the SDK (§3.2).
5. ~~Abstention posture.~~ **Resolved:** silent log, asker-initiated escalation,
   round-robin roster, weekly digest (§8.1).
6. ~~Subgraph version → deployment ID pinning.~~ **Resolved by the gateway** (§3.3).
   Two residual questions, both **blocked on Dave**: which release SDK `3.1.17`
   expects, and which subgraph commit produced release `v2.0.30`.
7. ~~`wildcat-docs` branches.~~ **Resolved:** `llm-rewrite-clean` added agent
   navigation files (`AGENTS.md`, `CLAUDE.md`), not agent-written prose — Tier B
   provenance is intact. `docs-tg-bot` documents `wildcat-notifications`, a
   separate event-polling bot. Both now excluded from the corpus for different
   reasons (§3.4).

---

## 10. Accepted risks

**Dependence on staging infrastructure.** Aleph's live-state path runs through the
Data Gateway, which is public staging with no production SLA. This is a deliberate
trade: Aleph is close to the ideal first non-trivial consumer, because its failure
mode is a bot saying "I can't reach live data" rather than a lender unable to
withdraw. It exercises RPC, WebSocket-free GraphQL and health polling under real
query patterns at genuinely low stakes.

The condition is that Aleph fails *closed*. No fallback to a direct provider, no
unpinned release, no cached number presented as current. A degraded gateway must
produce a refusal, not a quieter answer.

**Lens provenance.** `MarketLens`, `MarketLensV2` and `CollateralLens` are deployed
on mainnet with no recorded binding to a tag or commit; establishing one would
require a manual lookup that has been deprioritised. They are view-only, so this is
not a funds risk — but the lens contracts are precisely what produce the numbers
Aleph renders. Aleph's most consequential output therefore terminates in a contract
whose source is not traceable to reviewed code.

Practical consequence: a market-data answer can be cited to a block and to the SDK
version, but not to source. That is a weaker claim than the docs answers make, and
Aleph should not present the two as equally grounded. If the numbers are ever
disputed, the resolution path is on-chain state, not the lens.

Cost to close is one person recording three commit hashes. Worth doing before v2.5
tagging rather than during it — accepted for now, not resolved.
