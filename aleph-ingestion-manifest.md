# Corpus policy and rationale

`manifest.yaml` is the executable source of truth for what Aleph indexes and for
the runtime boundaries expected of downstream components. This document explains
the current policy without duplicating its configuration values. If the two
disagree, the manifest wins.

Everything in the corpus is public. The controls below provide reproducibility,
correctness, citation integrity, and injection resistance—not confidentiality.

## 1. Governing principles

1. **Default deny.** A source enters the corpus only when the manifest names it.
   Include and exclude patterns fail loudly rather than silently shrinking the
   corpus.
2. **Immutable source identity.** Every source resolves to a tag object and/or
   commit named by the manifest. Moving branches are forbidden.
3. **Deployed beats merged.** General protocol answers describe verified
   mainnet deployment inputs, not the current state of a repository branch.
4. **Live state is not corpus.** Values that change without a corpus promotion
   are read at query time and accompanied by a block number.
5. **A citation is a promise.** Quoted source is byte-exact. Assembled retrieval
   aids are explicitly non-quotable.
6. **Failures are visible.** Missing sources, invalid signatures, empty
   selections, schema errors, and embedder substitutions stop the relevant
   operation.

## 2. Evidence tiers

| Tier | Evidence | Identity | Current implementation |
|---|---|---|---|
| A | Deployed protocol source, natspec, audits, deployment material | signed release designation plus verified deployment inputs | ingested and indexed separately |
| B | Published docs, legal text, guides | promoted docs tag and commit | ingested and indexed separately |
| L | Registry and market state | gateway release, health state, block number | typed client and deterministic renderers in `live.py` |

Tier A and Tier B never share one ranked vector list. Readable prose can outrank
the code it describes on wording alone; preserving both result sets leaves that
choice visible to the downstream retriever.

The configured chain scope is Ethereum mainnet. Other chains and all testnets are
excluded from corpus and runtime answers. A cross-chain answer can look correct
until someone acts on it, so widening scope requires an explicit manifest change
and a new evaluation run.

## 3. Protocol source

### Deployment inputs define deployed code

Solidity chunks come from every mainnet `standard-input.json` shipped for
deployment verification. Those files carry the exact source set and compiler
settings behind the deployed bytecode. Compiling a working tree would instead
describe whatever happened to be checked out.

All deployment inputs are processed because inheritance resolves inside one
compilation unit and hooks implementations are deployed separately from the
market. Merging the units unions exposure without treating absence from one unit
as evidence against exposure in another.

### Internal libraries are protocol behavior

`src/libraries/` contains market state, fee, withdrawal, scaling, and delinquency
logic. It is part of the canonical source set, not a utilities drawer.

Of the external library files present in deployment inputs, only Solady
`Ownable.sol` is selected. It contributes ownership behavior exposed by
`WildcatArchController`. `EnumerableSet` and `LibBit` do not add separately
answerable inherited behavior.

This does not contradict the general `lib/**` exclusion. Uninitialized Git
submodules are excluded as independent inputs; selected library bytes already
inside a pinned deployment input are part of the verified compilation unit.

### Known issues are volunteered

`docs/Known Issues.md` is marked `always_cite`. A downstream answer touching a
documented limitation should cite it without relying on the user to ask the
exact retrieval query. This prevents the system from sounding more reassuring
than the protocol documentation.

### Prerelease code is isolated

The v2.5 snapshot has its own corpus because it is neither deployed nor audited.
It is eligible only when a question explicitly names v2.5, and the answer must
state its deployment and audit status. It cannot satisfy a general v2.0 query.

## 4. Published documentation

The docs source is pinned at `wildcat-docs@aleph-v0.3`. `SUMMARY.md` supplies the
GitBook navigation hierarchy and is excluded as content.

The corpus excludes:

- `AGENTS.md`, `CLAUDE.md`, skills, and packaged `.skill` files because they are
  written to direct an agent's behavior;
- deprecated V1 documentation because topical retrieval can ignore its warning
  while treating obsolete internals as authoritative; and
- `wildcat-notifications` implementation material because that bot is a sibling
  product, not evidence about protocol behavior.

The claims-intake application `wildcat-juris` is also excluded. Published docs
can describe the default-claim route without loading a system containing lender
contact, country, and signed-claim workflows into the retrieval context.

The SDK repository is not a corpus source. Published package artifacts, rather
than an unrelated branch state, define the ABI and address book used by runtime
policy.

### Legal document controls

`metadata_required` applies `doc_version` and `effective_date` to `legal/**`.
Applying those fields to every page would create meaningless versions for
ordinary explainers and falsely imply substantive changes on typo fixes.

The pinned `aleph-v0.3` legal pages contain both fields. The Terms of Use uses
its agreement hash as `doc_version`; the other pages use their effective date.

Four legal documents are also watched by content digest. The source ref already
pins their bytes; the digest exists to make substantive changes conspicuous at
the point a new docs ref is promoted. A mismatch is recorded for human review
and is not automatically rejected.

## 5. Chunk and citation model

`ingest/schema.py` defines one shape for both source types.

**Three text fields serve three consumers.**

- `display_text` is the exact source slice a reader may see.
- `model_text` removes non-documentation comments while preserving visible code
  and compiler-attached natspec.
- `embed_text` adds breadcrumbs, kind, exposure, and deduplicated aliases for
  retrieval.

Removing comments before preserving the display slice would create citations to
text that does not exist. The injection defense therefore changes model input,
not quoted evidence.

**Assembled chunks are not quotes.** Contract headers, callable surfaces, and
document indexes are constructed from multiple source regions. They carry
`synthesised: true` and may support retrieval, but a citation renderer must not
present them as verbatim source.

**Inheritance is resolved.** Member chunks list the concrete contracts that
expose them. Public getters participate in shadowing, derived overrides replace
base entries by signature, and callable surfaces are checked against the compiler
ABI. This makes inherited protocol behavior retrievable under the deployed
contract that exposes it.

**Provenance is stamped centrally.** Chunkers do not invent build identity.
`ingest/build.py` applies the resolved source ref, corpus build ID, tier, protocol
version, deployment status, and document metadata after parsing.

## 6. Trust boundary

Source code comments and natspec are writable free text. The corpus limits that
surface with several independent controls:

- the canonical protocol tag is signed and verified against a shipped public
  key plus a pinned primary fingerprint;
- non-documentation comments are removed from model text;
- compiler-attached natspec remains quoted, untrusted context downstream;
- source and tool changes alter the deterministic corpus build ID;
- optional corpus diffs expose added, removed, and changed chunk text; and
- solc runs through a pinned, networkless container for reproducibility and
  defense in depth.

Tag signing is a release designation: it attests that Wildcat chose the commit
as corpus input. It is not a claim that the signer authored every source line.

## 7. Live-state policy

Live-state configuration in `manifest.yaml` is a contract for downstream code,
not an implemented adapter in this repository.

The SDK package is the address-book authority. Resolution is by map key, not by
human-readable contract name, because multiple live addresses have carried the
`MarketLens` label. The configured production lens is under `MarketLensV2`;
legacy addresses can still contain code and return plausible data.

Gateway requests must name an immutable release, check health before answering,
and carry the observed block in every response. An unavailable or lagging release
causes a refusal. There is no automatic fallback to an unpinned provider or a
cached figure presented as current.

Borrower-keyed enumeration may report public facts across markets, but the tool
shape must not expose scoring, ranking, comparison, or characterisation fields.
Questions about whether a borrower is trustworthy are refusals rather than
evaluative answers with caveats.

`live.py` implements this boundary. It verifies the SDK tarball against the
manifest-pinned npm SRI digest and registry `gitHead`, enforces every address
assertion, and resolves only asserted map keys. Before every query it requires
the pinned mainnet gateway deployment and every routable replica to be ready,
integrity-verified, circuit-closed, and zero-lag. The query is fixed to that
checked block and the response `_meta` block must agree exactly. Typed integer
facts then pass through deterministic renderers; no model formats or
characterizes them.

## 8. Embedding and retrieval

`bge-m3` through Ollama is the selected embedding artifact. On the recorded
Markdown evaluation it achieved 20/25 recall@1, compared with 18/25 for
`qwen3-embedding:0.6b` and 17/25 for `qwen3-embedding:8b`. It also spread first
place across more distinct chunks.

The decisive operational reason is reproducibility: bge-m3 performs without a
query instruction prefix, while the Qwen packaging tested here performed better
only when its documented prefix was removed. The larger Qwen model also used far
more resident memory without improving retrieval.

The model digest, dimensions, normalization behavior, and query prefix are part
of index identity. `embed/index.py` refuses a query produced by a different
identity. `release.py` derives the required identity from `manifest.yaml` and
refuses to publish an index when the runtime backend, model, digest, dimensions,
normalization, or query prefix differs.

Exact cosine search is intentional at the current corpus size. Tier matrices are
only a few megabytes; an approximate index would introduce a new recall boundary
without measurable benefit.

`retrieval.py` applies the runtime policy around those matrices. Every request
names its chain, version, tiers, and limits. Lexical and semantic ranks are fused
within a tier but never across tiers. Deployed v2.0 is the default; the isolated
v2.5 release is loaded only for an explicit v2.5 request and carries a mandatory
unaudited, undeployed preamble. Citation resolution compares the indexed quote
with the named corpus bytes and refuses synthesized retrieval aids as quotes.

## 9. Evaluation

`eval/golden-v1.yaml` contains 125 questions clustered from support traffic.
`eval/labels.yaml` supplies retrieval labels for 25 consequential corpus
questions. Ten entries identify genuine corpus gaps rather than pretending a
retrieval model can answer from absent documentation.

The model-selection harness is narrower than the production target: it uses a
simple Markdown splitter over protocol docs. It does not exercise the built
corpus, tier policy, answer generation, citation rendering, abstention,
live-state joins, or Telegram behavior.

`ingest/build.py` therefore records `eval_not_regressed: null`. A downstream
promotion controller must run and enforce the complete retrieval-and-answer
evaluation before deployment.

## 10. Current limitations

- The answer, live-state, deterministic-renderer, and Telegram layers are not
  present in this repository. Citation resolution is implemented, but answer
  assembly does not yet consume it.
- SDK address assertions are enforced by `live.AddressBook` and can be bound
  into a release with `release.py --fetch-sdk`. A release built without that
  artifact check keeps `address_assertions_hold: null`.
- Corpus diffs carry pending, unchanged, or named-reviewer approval state in an
  immutable release record. Activation of an approved release is not yet
  implemented.
- Lens addresses are pinned through the SDK artifact, while the deployed
  `MarketLens`, `MarketLensV2`, and `CollateralLens` source is not bound here to
  reviewed commits. A disputed numeric answer must be resolved against on-chain
  state rather than treated as source-cited in the same sense as a docs answer.
- The gateway release is pinned for routing, but this repository does not record
  the commit that produced that deployed subgraph release.
- GitBook anchor behavior has no public specification. The chunker is fitted to
  the rendered site and must be rechecked with
  `ingest/chunkers/verify_anchors.py` after renderer or docs changes.
- Corpus, index, and release directories are atomically published and immutable.
  A rerun verifies and reuses the existing bytes; corruption or identity drift
  is fatal rather than repaired in place.

These are current boundaries, not prompts for the build to guess. A downstream
component either supplies the missing control explicitly or fails closed.
