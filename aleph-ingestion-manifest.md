# Why the manifest says what it says

`manifest.yaml` is the source of truth for what gets indexed. This document is
the reasoning behind it — the arguments, the rejected alternatives, and the
things that are true but not expressible in YAML.

If the two disagree, the YAML wins and this file is a bug. It deliberately
contains no configuration: an earlier version restated the manifest in YAML
blocks and the copies drifted apart within days.

> **Blocked on Dave — subgraph provenance.** The Data Gateway resolves subgraph
> *routing and pinning*: releases are explicit immutable identifiers with no
> `latest`, no default and no cross-release fallback. Better than a deployment
> ID. What it does not resolve: which subgraph commit produced release
> `v2.0.30`, and which release SDK `3.1.17` expects. `subgraph@main` is at
> `2.0.22`, so the repository cannot answer either.

Everything indexed is public material. The controls here exist for
**reproducibility, correctness and injection resistance**, not confidentiality.

---

## 1. Governing principles

1. **Default deny.** A source is ingested only if `manifest.yaml` names it.
   There is no crawl-and-exclude mode. Exclusion lists rot silently; allowlists
   fail loudly.
2. **Pinned, never tracking.** Every source resolves to an immutable ref. No
   branch tracking, including `main`.
3. **Reproducible answers.** Every answer cites the corpus build that produced
   it, so any complaint can be replayed against that exact build.
4. **Live state is not corpus.** Anything that changes without a human deciding
   it changed is read at query time through a tool, never embedded.
5. **Deployed beats merged.** Where they disagree the deployed contract is the
   truth. Merged-and-undeployed is the highest-risk answer class in the system:
   correct citation, real code, wrong protocol.
6. **A citation is a promise.** Text presented as source must be byte-exact
   source. The newest principle, and the one with the most machinery behind it
   — see §5.

---

## 2. Corpus tiers

| Tier | Contents | Pin | Rebuild trigger |
|---|---|---|---|
| A — Canonical | Deployed contract source, natspec, audits, deployment address book | Release tag ↔ verified deployment | Human cuts a tag |
| B — Published docs | docs.wildcat.finance, ToU, guides, long-form | Promoted tag on `wildcat-docs` | Docs promotion |
| L — Live state | Archcontroller registry, market parameters, queue state | None — read at query time | n/a |

A and B are indexed and retrieved separately. A blended index lets a blog
paragraph outrank a contract on a question about contract behaviour, which is
the failure mode that matters most here.

**Ethereum mainnet only.** Other chains and every testnet are out of scope —
not ingested, not queried, not answerable. Wildcat deploys to more than one
chain, and the gateway routes to all of them, so this is a deliberate narrowing
rather than a description of the protocol. An answer drawn from the wrong chain
is indistinguishable from a right one until someone acts on it.

Widening later is a config change plus a re-run of the eval set. Widening by
accident, because a chain qualifier was omitted somewhere, is a wrong answer
about someone's money.

---

## 3. What is in, and why

### Solidity comes from the deployment inputs, not the working tree

Chunks are built from the `standard-input.json` files that `v2-protocol` ships
for Etherscan verification. Those carry the full source set *and* the exact
compiler settings behind the deployed bytecode, so chunks describe deployed code
by construction rather than by hope. Compiling the working tree would describe
whatever happens to be checked out.

Every deployment input is passed, not one. Inheritance resolves within a single
compilation unit, and the hooks instances are deployed separately from the
market — a single input under-reports and produces false "unreachable" findings.

### `src/libraries/` is where a third of the protocol lives

154 functions, against 89 in `src/access` and 70 in `src/market`.
`MarketStateLib`, `FeeMath`, `WithdrawalLib`, `MathUtils` — `liquidityRequired()`,
the scale factor, the delinquency maths. The things the docs cite by name. Not a
utilities drawer.

### Exactly one external library is included

Across all five deployment inputs, only three `lib/` files are compiled in.
Solady's `Ownable` contributes 18 chunks exposed by `WildcatArchController`,
including `owner()` and `transferOwnership` — that is where "who controls the
archcontroller" is answered, and it is not in `src/` at all. `EnumerableSet` is
used via `using for` rather than inherited, so nothing exposes it. `LibBit` is
bit arithmetic.

Note the distinction from excluding `lib/**` generally. That rule is about
ingesting unpinned submodules from a working tree. Library code arriving *inside*
a `standard-input.json` is pinned by construction — it is part of the verified
bytecode.

### `Known Issues.md` is volunteered, not merely retrievable

The protocol repo's `docs/` is genuine prose, not generated material — Core
Behavior, Terminology, Scale Factor, three hooks documents, and Known Issues.
That last one is marked `always_cite` for a reason: any answer touching a
behaviour documented there should cite it unprompted rather than waiting to be
asked. It is where the batch-interest asymmetry lives, and where "if a borrower
fails to repay, lenders will inevitably lose funds" is stated plainly. A bot that
retrieves it only when directly asked is a bot that sounds more reassuring than
the documentation does.

### The pre-release branch is quarantined, not excluded

`release/v2.5` is snapshotted at a commit and indexed separately. It answers only
when the asker names v2.5 explicitly, always with an unaudited-and-undeployed
preamble, and never satisfies a general question. "How do withdrawals work"
answers from v2.0.

### Three things are excluded, for three different reasons

**`wildcat-juris`** is claim-intake for defaulted markets — lender contact
details, country, signed claims. Public code, but defaults and claims are the one
topic where a wrong or merely tonally-off answer is worst.

The exclusion got easier to hold at `aleph-v0.1`: the docs now carry
*Proving You Are An Affected Lender in a Default*, which documents the process —
produce a signed claim at juris.wildcat.finance, send the verification bundle to
the Foundation. Aleph can describe the route from Tier B without ingesting the
tool, which is exactly the shape wanted. It should also carry that page's own
distinction: the protocol-observable default it checks, delinquency beyond grace
plus 90 days, is *not* an Event of Default under an MLA, which may trigger
earlier and on grounds the protocol never observes. It also does borrower→markets enumeration, which is the
capability bounded in §4; Aleph should not learn that pattern from a tool built
for a different purpose under different consent.

**`wildcat.ts`** is the SDK source, and `main` sits at `3.0.54-beta` against a
published `3.1.17`. The repository cannot tell you what is in the deployed SDK,
so address and ABI truth stays with the npm artefact.

**Agent-directed files** — `AGENTS.md`, `CLAUDE.md`, and `skills/` — are prose
written to direct an agent's behaviour, sitting inside a repository Aleph trusts.
In the context window they are indistinguishable from instructions Wildcat
intended Aleph to follow, and unlike a natspec comment they are *designed* to be
obeyed.

The exclusion is enforced by the chunker reading `manifest.yaml` rather than
taking a list on the command line. That was not the original design: the docs
tree was first chunked with excludes typed by hand, the list omitted `AGENTS.md`,
and agent instructions went straight into the corpus. Principle 1 says exclusion
lists rot silently — one retyped at every invocation rots fastest.

**`miscellaneous/deprecated-documentation/`** is 17 of 82 files, describing
superseded V1 internals. The pages self-identify — "this page has not been
updated to reflect Wildcat V2" — but only in prose that a retriever will happily
ignore while indexing the rest as authoritative. A fifth of the docs corpus
answering confidently about behaviour that no longer exists is worse than having
no answer, and it fails in the direction of sounding informed.

### `wildcat-notifications` is a sibling, not a source

The existing event bot pushes deposits, batch creation and status changes into
Telegram with an established vocabulary — "market now Pending Repayment", "new
withdrawal batch of $X". Aleph is pull to its push. Two constraints follow:
Aleph's renderer reuses that phrasing for the same states, because two bots in
one channel describing a market differently is a contradiction someone will
screenshot; and Aleph derives state from the gateway, never by reading the
notification feed, because a second-hand event cannot be cited to a block.

---

## 4. Live state

The archcontroller is a live contract, not a document. Registry queries — which
markets exist, is this borrower registered — are read on chain and cached with a
block number. Anything about a specific market's current numbers is always live,
never cached, never embedded.

**Address book precedence.** Two mainnet address books exist and they disagree.
The SDK is authoritative; the repo's `deployments.json` is stale, carrying a
superseded `MarketLens` and omitting `Wildcat4626WrapperFactory` despite v2.1.0
being named for it.

**Resolve the lens by key, never by name.** Three distinct mainnet addresses have
carried the label "MarketLens", and the production one sits under the
`MarketLensV2` key. All three are live contracts with distinct bytecode, so "does
it have code" is not a validity check. A lookup keyed on the human-readable name
returns the legacy contract and produces plausible, wrong numbers.

**The gateway is the transport.** Explicit immutable release routing, no
`latest`, no fallback; an unavailable release is an error rather than a guess.
`/health` is unauthenticated and returns lag and sync state from a maintained
snapshot, so Aleph checks it before answering any market question and declines
rather than serving stale numbers. Every subgraph answer carries
`_meta { block { number } }`. It is public staging with no SLA, so Aleph fails
*closed* — no fallback provider, no unpinned release, no cached figure presented
as current.

**Borrower-keyed aggregation is permitted; characterisation is not.** This has to
be enforced in the shape of the tool layer, not the prompt, because a prompt
instruction is not a control. The query interface may take a borrower as a key
and range over their markets; results return through the deterministic renderer;
no comparative or evaluative field exists for the model to populate. If the
renderer cannot emit it, the model cannot assert it. Questions of the form "is
this borrower reliable" are refusals, not answers with caveats.

Every fact is public. The compilation is an artefact Wildcat produced on request,
and the line between showing and characterising is where the risk lives.

---

## 5. What a chunk is

Defined by `ingest/schema.py`, which every chunker emits and the retriever,
citation layer and index all read.

**Three texts, not one.** `display_text` is verbatim source — what a citation
quotes. `model_text` has non-natspec comments stripped — what reaches the context
window. `embed_text` carries the breadcrumb and kind, because a function body
alone does not say which contract it belongs to and half the protocol has a
`deposit`.

An earlier version of this document said to strip comments *before chunking*.
That was wrong, and the correction is the point: stripping the indexed text means
citations quote something that is not in the file — a failure that looks correct,
which is worse than one that doesn't. The injection defence applies to what the
model reads, never to what a human is shown.

**Assembled chunks are flagged.** Contract headers and callable surfaces are
constructed rather than sliced — the header from a declaration plus state
variables, the surface from the resolved inheritance chain. They carry
`synthesised: true` and must never be quoted as source. A synthesised chunk
presented as a citation is a fabricated quote that looks verified.

**Inheritance is resolved, not merely recorded.** Every member carries the
concrete contracts that expose it, computed by walking solc's linearisation and
keeping the first definition of each signature — Solidity's own override
semantics. Without it, "does WildcatMarket have `queueWithdrawal`" cannot
retrieve a function defined three contracts up the chain, and `WildcatMarket` is
almost entirely inherited behaviour.

**Source-specific fields live in `detail`.** Solidity's `exposed_by` has no
markdown analogue and markdown's anchors have none in Solidity. Keeping them out
of the top level stops the schema becoming mostly nulls and stops the retriever
branching on source type.

**Provenance is stamped by the pipeline, not guessed by the chunker.** A chunker
that invents its own `corpus_build_id` is how two chunks from one build end up
claiming different origins.

`protocol_version` is the load-bearing field: it filters retrieval to the version
being asked about, and it is what stops v2.5 chunks bleeding into v2.0 answers.

---

## 6. Injection surface

Natspec and comments are free text inside otherwise-trustworthy files, and they
reach the model as context. Given a named actor with prior interest in these
repositories:

- **Signed tags only.** A human cutting a tag is the review gate, and it is one
  that already exists rather than one that has to be built.
- **Comments stripped from `model_text`**, natspec kept but fenced in the prompt
  as quoted untrusted material, never as instruction. The chunker deliberately
  does not sanitise natspec — silently rewriting documentation would break the
  citation promise, and it is the prompt layer's job.
- **Corpus diffed between builds.** A human-readable changelog of what entered
  and left Aleph's knowledge. A docstring-only commit that changes behaviour
  should be visible on one screen.
- **`solc` runs containerised**, pinned by image digest, with no network. The
  reproducibility argument is the strong one — a pinned digest makes the AST
  byte-identical anywhere. The isolation is defence in depth: the real trust
  boundary is the tag signature, since anyone who can put hostile Solidity in
  front of this compiler can already sign a tag.

---

## 7. Build and deploy

```
cut tag → CI ingest → corpus artefact (numbered, immutable) → gates → atomic swap
```

Full rebuild every time; the corpus is a few megabytes and incremental indexing
introduces state that can diverge from source without anyone noticing. The index
is never mutated in place, the previous build stays on disk, and rollback is a
pointer change.

Gates are blocking: signature verified, address assertions hold, corpus diff
reviewed, eval not regressed.

`sdk-watch.py` runs daily and **does not trigger a build**. An address change
means a person needs to look at something, not that the index should quietly
regenerate around it.

---

## 8. Eval

`eval/golden-v1.yaml` — 125 questions clustered from ~2,940 real messages across
five channels. `eval/labels.yaml` gives retrieval ground truth for the 25 where
being wrong costs something.

Three blocking metrics: **citation validity** (does the cited chunk exist in this
build and support the claim), **version correctness** (does a v2.0 question get a
v2.0 answer), and **calibrated abstention** (refusal rate on the
known-unanswerable subset). The last decides whether Aleph saves time or costs
it: a bot that refuses 20% of the time frees you up, and one that confabulates 5%
of the time means every answer needs checking.

Ten questions are marked `corpus_gap` — real, recurring, and unanswerable from
the docs. That is documentation work no retrieval model can substitute for, and
the list lives in the golden set rather than in someone's head.

The gate cannot be built yet: it needs a retrieval and answer layer to grade. The
questions are no longer what is missing.

---

## 9. Escalation and retention

A refusal does not ping anyone. It logs, and offers the asker an explicit
escalate action. Automatic paging on every refusal hands an unbounded interrupt
budget to whoever is asking, and the people it interrupts are the people this was
built to unburden. Escalation is round-robin across a roster held in deployment
config — four Telegram handles in a repository, annotated with escalation
authority, is a targeting list.

Retention is two-tier because identifiers and questions have opposite optimal
lifetimes. Raw records — Telegram ID, username, channel, question as asked — are
destroyed at **30 days**. De-identified question text is kept indefinitely,
because that is the eval set and it has no data subject once the ID is gone.

De-identification is not dropping the ID column. Questions carry identifiers in
their text: "our market", named counterparties, position sizes. The scrub runs
over the text, and anything that cannot be scrubbed confidently is dropped — the
eval set is allowed to be lossy, the retention boundary is not.

Derived artefacts inherit the boundary. A record purged at day 30 that was copied
into an eval fixture on day 3 has not been deleted. This includes backups: a
30-day policy against a 90-day snapshot retention is a 90-day policy.

---

## 10. Open decisions

1. **Subgraph provenance** — which release SDK `3.1.17` expects, and which commit
   produced `v2.0.30`. Blocked on Dave.
2. **Vocabulary alignment with `wildcat-notifications`** — whose phrasing wins
   where the two bots describe the same state differently.
3. **`triage` behaviour** — nine golden-set items are action requests or UI
   faults where the value is collecting the four details a human always asks for.
   A distinct mode from answering and refusing, specified nowhere.
4. **Markdown chunking** — the shared schema exists; the chunker does not.
   `embed_compare.py` has a heading splitter, but that is eval scaffolding.

Settled, and recorded so nobody relitigates them: cross-market aggregation
(permitted, rendering only), the repository list, the deployment tag (`v2.1.0` /
`c7be403`, signed), the address book (the SDK), abstention posture, the docs
branches, the embedding model (`bge-m3`, chosen by measurement), and
containerised solc.

---

## 11. Accepted risks

**Lens provenance.** `MarketLens`, `MarketLensV2` and `CollateralLens` are
deployed with no recorded binding to a tag or commit. They are view-only, so this
is not a funds risk — but the lens contracts are precisely what produce the
numbers Aleph renders. Aleph's most consequential output therefore terminates in
a contract whose source is not traceable to reviewed code.

A market-data answer can be cited to a block and an SDK version, but not to
source. That is a weaker claim than a docs answer makes, and Aleph should not
present the two as equally grounded. If numbers are disputed, the resolution path
is on-chain state, not the lens. Cost to close is one person recording three
commit hashes.

**Dependence on staging infrastructure.** The live-state path runs through the
Data Gateway, which is public staging with no SLA. A deliberate trade: Aleph is
close to the ideal first non-trivial consumer, because its failure mode is a bot
saying "I can't reach live data" rather than a lender unable to withdraw. The
condition is failing closed.

**The chunker has not been independently reviewed.** 47 assertions written by the
same author as the code they check, which is a statement about what that author
thought to verify rather than about what is true. `ingest/REVIEW.md` is the brief.
