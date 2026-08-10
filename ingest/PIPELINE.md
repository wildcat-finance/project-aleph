# Ingestion Pipeline

How `manifest.yaml` becomes a queryable corpus. Seven stages, all of them
deterministic, none of them incremental.

```
acquire → filter → parse → enrich → embed → gate → publish
```

The pipeline is a pure function of `manifest.yaml` plus the refs it names. Given
the same manifest it produces a byte-identical corpus, which is what makes "replay
build 47" a real answer to a complaint rather than a figure of speech.

---

## 0. Trigger

Human-initiated, always. Someone cuts a tag, or promotes a docs commit, or edits
`manifest.yaml`. Nothing rebuilds on a schedule and nothing rebuilds on a push.

`sdk-watch.py` runs daily and **does not trigger a build**. An address change means
a person needs to look at something, not that the index should quietly regenerate
around it. Alarm, not automation.

---

## 1. Acquire

For each source, resolve the ref exactly as `manifest.yaml` names it.

For `v2-protocol`, the order matters:

```bash
git fetch --tags
git verify-tag v2.1.0                    # tag object 8aab396 — presently unsigned
git rev-parse v2.1.0^{}                  # only now resolve to commit c7be403
```

Signature verification precedes resolution. Verifying the commit verifies nothing —
an annotated tag is a separate object and the signature lives on it. If
`require_signature` is true and verification fails, the build aborts. It does not
warn and continue.

Three outcomes, and `ingest/build.py` keeps them apart. A signature that is
**present and invalid** is an attack signal and aborts unconditionally. A
signature that is **absent**, or that cannot be checked because the signer's key
is not in the keyring, is a missing control: it aborts too, but
`--allow-unverified-signature` will carry it, and the waiver is written into
`build.json` so a corpus built without attestation can never be mistaken for one
built with it.

A valid signature is not the whole claim. `git verify-tag` succeeds for any key
in the keyring, so `ref.signer_fingerprint` pins *whose* signature is expected;
a valid signature from a different key is refused and is not waivable, because
it is a different assertion rather than a weaker one. When no fingerprint is
pinned the build says so on every run.

`v2-protocol` is pinned at `aleph-v2.1.0`, a signed tag on the same commit as
the unsigned release tag `v2.1.0`. The release tag was annotated but carried no
signature and `v2.0.0` is lightweight, so `require_signature` could not be met
by any build of either — which the first run of this driver discovered. Rather
than move `v2.1.0`, which nobody who had already fetched it would ever pick up,
a second tag carries the signature. Same commit, same corpus, byte for byte.

The signature is a designation rather than an authorship claim: it says Wildcat
pins this commit as the v2.0 corpus source. Signed with the key at
`ingest/keys/release.asc`, whose fingerprint the manifest pins. The tag-object and commit hashes the manifest names are asserted on
every build regardless, and those need no key — the build is pinned to exact
objects whether or not anyone has vouched for them.

`wildcat-docs` has no tags, so the promoted commit SHA is recorded into build
metadata at acquisition time and treated as immutable thereafter.

Submodules are never initialised. `lib/**` is excluded, and `git submodule update`
would pull unpinned third-party code into the corpus by the back door.

---

## 2. Filter

Apply `include`, then `exclude`, then `verification_only` — in that order, since
`verification_only` paths must survive `include` but never reach the chunker.

The filter is fail-loud: if an `include` glob matches nothing, that is an error, not
an empty set. A silently-empty glob is how a renamed directory quietly removes half
the corpus while every build stays green. As of Round 2 the chunkers enforce this
themselves — a pattern matching nothing anywhere, a unit selecting nothing, an
unreadable `SUMMARY.md`, or a zero-chunk corpus all exit 1 and write no output —
so the promise no longer depends on the stage around them.

---

### Watched documents

A source may pin the digest of individual files under `watch`. The ref already
fixes what a build ingests, so this is not a reproducibility control — it is an
alarm for the one moment reproducibility cannot help with: a person deciding
whether to move the pin.

A document Aleph quotes verbatim can be substantively revised between
promotions, and an answer citing superseded terms is indistinguishable from a
correct one. A mismatch is therefore reported loudly and recorded in
`build.json` with both digests, feeding the `corpus_diff_reviewed` gate. It is
deliberately not fatal: a promotion carrying a revision is legitimate, it must
simply not pass unnoticed.

`strip_frontmatter: true` hashes the document body alone, which is what a
Markdown page needs: the watch is on the legal language, not on the GitBook
`description:` above it. Without it, the PR that adds `effective_date` and
`doc_version` would trip every watched page at once, and a check that cries
wolf on its own maintenance is one people learn to ignore.

Currently watched: all four documents under `legal/`. The Terms of Use is
pinned on its plaintext, whose digest is both the agreement hash a lender signs
in their wallet and the version identifier the page states about itself; the
other three on their bodies. A substantive revision of all of them is
expected.

---

## 3. Parse

The stage most likely to be done badly, and the one that determines retrieval
quality more than the embedding model does.

### Solidity — AST, not character windows

Chunking Solidity on a character or line window produces half-functions with no
signature and no owning contract. Instead, compile to AST and emit one chunk per
semantic unit:

```bash
python3 ingest/build.py --manifest manifest.yaml --out corpus/ --solc "$SOLC"

That drives everything below from the manifest: acquire with verification,
filter, both chunkers, provenance stamping, schema validation, and a build
record. The individual chunkers remain runnable on their own for development
and are what the tests exercise, but a corpus assembled by hand is a corpus
nobody can replay — which is what every build before the driver was.

```bash
python3 ingest/chunkers/solidity.py \
  $(for d in deployments/mainnet/*/; do echo --input $d/standard-input.json; done) \
  --include 'src/**' --expect-solc 0.8.25 --out chunks.jsonl
```

Use `--solc ingest/solc-container` in CI: the pinned `ethereum/solc` image with
no network, no capabilities, read-only root and a non-root user. A local
`solc-select` binary is fine for development, but only the pinned digest gives a
byte-identical AST across machines.

**Pass every deployment input, not one.** Inheritance resolves within a single
compilation unit, so a contract deployed separately — the hooks instances, for
instance — is invisible to the market's build. Merging unions the exposures.

Implemented in `ingest/chunkers/solidity.py`. Input is the deployment's
`standard-input.json` — full source set plus the exact compiler settings behind
the verified bytecode, so chunks describe deployed code by construction rather
than by hope. Compilation errors abort the run.

Review brief and invariants: `ingest/ADVERSARIAL.md`. Tests:
`ingest/chunkers/test_solidity.py`, which gates on exit code.

One chunk per: contract, function, modifier, struct, event, error, state variable
group. Each chunk carries:

- its own natspec, attached rather than orphaned;
- the owning contract name and inheritance chain;
- the full signature, even when the body is what matched;
- file path and line span, for citation.

A function chunk that doesn't name its contract is close to useless — half the
protocol has a `deposit`.

Where a contract is too large for one chunk and a function is too small to be
meaningful alone, prefer the function and rely on the contract-name metadata for
grouping. Do not produce overlapping chunks; overlap inflates retrieval scores for
whatever happens to sit in the overlap.

### Markdown — heading boundaries and breadcrumbs

```bash
python3 ingest/chunkers/markdown.py --root wildcat-docs --manifest manifest.yaml \
  --summary SUMMARY.md --out docs.jsonl
```

Pass `--manifest`. The exclude list lives there, and a list retyped at every
invocation is a list that will one day omit `AGENTS.md`.

Split on heading boundaries, not length. Each chunk keeps its heading path in
metadata:

```
Core Behavior › Withdrawals › Expired batches
```

For `wildcat-docs`, `SUMMARY.md` is GitBook's table of contents. It is consumed
as structure and excluded as content: `parse_summary()` resolves each document to
its place in the nav, and that prefix goes in front of the in-document heading
path. Without it `day-to-day-usage/lenders.md` has no idea it sits under "Using
Wildcat", which is most of what a reader means when they ask where something is
documented.

A chunk under a heading it doesn't repeat is a chunk that retrieves badly and cites
worse. The breadcrumb goes in metadata *and* is prepended to the embedded text.

### Two texts per chunk

This corrects §5 of the ingestion manifest, which as written breaks citation.

| Field | Contents | Used for |
|---|---|---|
| `display_text` | verbatim, exactly as on disk | citation, quoting, anything a human sees |
| `model_text` | non-natspec comments stripped | what enters the context window |

The injection defence applies to what the model reads. Stripping comments from the
indexed text as well would mean citations quote something that doesn't exist in the
file — a worse failure than the one being defended against, because it looks
correct.

Natspec is kept in `model_text` (it is real documentation) but fenced as quoted
untrusted material in the prompt, never as instruction.

---

## 4. Enrich

Attach the §4 metadata schema to every chunk: `corpus_build_id`, `tier`,
`source_ref`, `source_path`, `protocol_version`, `deployment_status`,
`effective_date`, `doc_version`, `supersedes`.

`protocol_version` is the load-bearing one. It is what lets retrieval filter to the
version being asked about, and it is what stops the v2.5 pre-release index bleeding
into v2.0 answers the day someone re-snapshots the branch.

Chunks from `v2-protocol-prerelease` additionally carry `audited: false` and
`deployment_status: not_deployed`, and the retrieval layer refuses to return them
unless the query explicitly names v2.5.

---

### Per-document provenance

`corpus_build_id`, `source_ref`, `protocol_version` and `deployment_status`
are properties of the source and are the same for every chunk in it.
`effective_date` and `doc_version` are properties of the *document*, read from
its frontmatter and promoted to schema fields during enrich, so a citation can
say which version of the Terms of Use it is quoting without anyone rummaging
in `detail`.

`metadata_required` may name the paths it applies to:

```yaml
metadata_required:
  paths: [ "legal/**" ]
  fields: [ doc_version, effective_date ]
```

Scoped, because the requirement is not uniform. "Which version is in force" is
a real question about the Terms of Use and a meaningless one about the
delinquency explainer. Demanding a date for all eighty documents would mean
inventing seventy-six of them, and a typo fix would then claim the terms had
changed — ceremony that degrades the thing it decorates. A bare list still
means every document in the source.

---

## 5. Embed and index

Postgres. One database, three tables: `chunks`, `chunk_vectors`, `builds`.

- **Lexical:** `tsvector` + GIN. Solidity identifiers survive tokenisation badly by
  default; use a configuration that keeps `camelCase` and underscore-separated
  identifiers intact, or `getMarketAccountData` becomes unsearchable.
- **Semantic:** pgvector over `model_text`, with the breadcrumb or contract name
  prepended so the embedding carries context the raw body lacks.
- **Hybrid:** reciprocal rank fusion over both. The corpus is small; exotic
  retrieval buys nothing and costs debuggability.

`display_text` is stored verbatim alongside, so a citation quotes the file rather
than a reconstruction.

The embedding model ID is written into `builds` next to the git SHAs. Changing it is
a corpus rebuild with an eval run, not a configuration tweak — it changes every
answer with no source-side diff to explain why.

**Full rebuild, always.** The corpus is a few megabytes and rebuilds in minutes.
Incremental indexing introduces state that can diverge from source without anyone
noticing, which is precisely the failure this design exists to prevent.

---

## 6. Gate

All blocking. A build failing any gate does not swap.

1. **Signature verified** — §1.
2. **Address assertions hold** — every entry under `addresses.assertions` still
   resolves to the pinned value in SDK `3.1.17`. This is the check that catches
   `MarketLens` drift before it becomes a wrong number in a lender's chat.
3. **Corpus diff reviewed** — a human-readable changelog of chunks added, removed
   and changed since the last build. A docstring-only commit that alters Aleph's
   behaviour should be visible on one screen. Unreviewed diff blocks the swap.
4. **Eval not regressed** — citation validity, version correctness, calibrated
   abstention. Blocking once the golden set exists; until then this gate is a
   placeholder and the build is explicitly untested.

---

## 7. Publish

```
corpus artefact (numbered, immutable) → atomic pointer swap
```

The previous build stays on disk. Rollback is a pointer change, not a rebuild.
Nothing mutates in place, ever — an index you can edit is an index you can't
reproduce.

Every answer cites its `corpus_build_id`. Given a build number and a question, the
whole retrieval path is replayable.

---

## Failure modes this is built against

**Silent corpus shrinkage.** A renamed directory quietly drops half the source and
every build stays green. Caught by fail-loud globs (§2) and the diff gate (§6.3).

**Version bleed.** A v2.5 chunk answers a v2.0 question. Caught by
`protocol_version` filtering (§4) and separate indices (§3 of the manifest).

**Citation drift.** The bot quotes text that isn't in the file. Caught by storing
`display_text` verbatim (§3).

**Injection via docstring.** A comment-only commit changes the bot's behaviour.
Caught by signed-tag-only ingestion (§1), comment stripping into `model_text` (§3),
and the diff gate (§6.3).

**Quiet degradation.** The gateway is unhealthy and answers get worse rather than
stopping. Not a pipeline concern — handled at query time by the lag gate — but the
same principle: fail closed, loudly, or don't fail at all.
