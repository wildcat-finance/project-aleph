# Adversarial review: the chunkers

**Rounds 1 and 2 complete, both chunkers.** Sol 5.6 reviewed both at `47634bc`
and found six issues in each; a second review at `7b901bd` found five more in
the Solidity chunker and five in the markdown chunker, plus two findings about
the tests themselves. All are fixed; the invariants and tests below reflect the
repaired state. What each round found is recorded at the bottom, because a list
of what a review caught is a better guide to where the next one should look
than a list of what passed.

Read this before the code. It states what the chunkers promise, what breaks
those promises, and what has and hasn't been checked.

Two chunkers, one schema. Invariants I1–I3 and I11 apply to both; I4–I10 are
Solidity-specific; M1–M6 are markdown-specific. Where an invariant is shared,
breaking it in one chunker probably breaks it in the other.

**The dangerous failure mode is not a crash.** A chunker that falls over is
harmless — the build stops. The failure that costs something is a chunk that
carries a correct-looking citation to the wrong source, because Aleph will
present it with a file path and a line number and it will look verified.

---

## Invariants

Each of these should hold for every chunk. Each is something to attack.

**I1 — `display_text` is byte-exact source.** For any chunk where
`synthesised == false`, `display_text` minus its natspec prefix appears verbatim
in the corresponding source file. Nothing is normalised, reflowed or reordered.
*Verified: 486/486 non-container chunks against the WildcatMarket deployment.*

**I2 — synthesised chunks are labelled.** Contract/interface/library header
chunks are *assembled* from the declaration and state variables, not sliced.
They carry `synthesised: true` and must never be quoted as source.
*Verified: 28/28 container chunks flagged; nothing else is.*

**I3 — IDs are unique.** `path:Contract.signature(paramTypes)`. Overloads differ
by parameter types, so `getHooksTemplates(uint,uint)` and
`getHooksTemplates(address,uint,uint)` do not collide. The tool exits non-zero
if any collision appears.
*Verified: 0 collisions across 514 chunks, 7 genuinely overloaded names.*

**I4 — offsets are byte offsets.** solc `src` is `start:length:fileIndex` in
bytes. All slicing happens on `bytes` and decodes afterwards. Slicing a `str`
by those numbers corrupts any file containing a multi-byte character, and
Solidity source legitimately contains them.
*Verified against a fixture with `unicode""` literals and non-ASCII natspec.
Byte-slicing returns the function verbatim; character-slicing returns text
offset by ten characters — corrupted, and plausible enough to ship:*

```
byte : 'function get() external view returns (string memory) { return greeting; }'
char : 'et() external view returns (string memory) { return greeting; }\n}\n'
```

*The test keeps that comparison as a regression canary: if char and byte
slicing ever agree on that fixture, the fixture has stopped exercising the bug.*

**I5 — comment stripping never damages code.** `model_text` has non-natspec
comments removed, and nothing else. String literals containing `//` or `/*`,
`unicode""` and `hex""` forms, and escaped quotes all survive intact.
*Verified: 12/12 adversarial cases, including `"http://x"`, `unicode"héllo // ok"`,
`"/* not a comment */"`, unterminated blocks, and division mistaken for a comment.*

**I6 — natspec is preserved but never trusted.** Natspec is real documentation
and stays in `model_text`. It is also attacker-writable free text inside an
otherwise trustworthy file. The prompt layer must fence it as quoted material.
*The chunker deliberately does NOT sanitise it — that is the prompt's job, and
silently rewriting documentation would break I1.*

**I11 — one schema, and the flags in it are right.** Every chunker emits
`schema.Chunk`; source-specific fields live in `detail` so the retriever never
branches on source type. `validate()` refuses a set with duplicate ids, empty
text, oversize chunks, or a `synthesised` flag that disagrees with the chunk
kind — the last being the one that would let an assembled chunk be quoted as
source. Provenance is stamped by the pipeline, not guessed by the chunker.
*Verified: 962 real chunks validate clean; flipping one `synthesised` flag is
caught; `stamp()` rejects unknown fields.*

**I10 — signature types distinguish.** Parameter types are canonicalised rather
than truncated, so two functions differing only by struct or contract type
produce different signatures and therefore different chunk IDs.
*Verified: 8 type-reduction cases plus the distinctness property.*

**I8 — inheritance is resolved, not merely recorded.** Every member chunk
carries `exposed_by`: the concrete contracts that expose it, computed by walking
solc's `linearizedBaseContracts` and keeping the first definition of each
signature — which is Solidity's own override semantics. A base function shadowed
by a derived override is correctly *not* attributed to the deriving contract.
Each concrete contract also gets a synthesised `surface` chunk listing its full
external/public API with the contract that defines each entry.
*Verified: `queueWithdrawal(uint256)`, defined in `WildcatMarketWithdrawals`,
resolves to `exposed_by=[WildcatMarket, WildcatMarketWithdrawals]`.*

**I9 — merging compilation units unions, never intersects.** Inheritance
resolves within one `standard-input.json`. `IHooks` is abstract and its concrete
implementations are deployed separately, so it looks unreachable in the market
build and is overridden by `OpenTermHooks` in another. Passing every deployment
input merges them: `exposed_by` unions, `overridden` ORs.
*This found a real bug. The merge originally ANDed `overridden`, so a member
overridden in one unit and simply absent from another came out un-overridden and
produced thirteen false "unreachable" reports. Absence is not evidence. With OR,
the count is zero.*

**I7 — the corpus describes deployed code.** Input is the
`standard-input.json` used for Etherscan verification, so sources and compiler
settings match the deployed bytecode by construction. Compilation errors abort
the run rather than producing partial output.
*Verified: 0 errors, 35 sources, solc 0.8.25 matching `foundry.toml`.*

---

## Attacks worth attempting

**Against citation integrity (I1, I2)**

1. Craft a source file where a natspec block contains text identical to a real
   function body. Does anything downstream conflate the two?
2. Add a contract whose state variable declarations contain `}` inside a string.
   Does the synthesised header chunk still parse as plausible Solidity, and does
   anyone downstream try to compile it?
3. Feed a `standard-input.json` whose `sources` map contains a path not present
   in the AST output. Currently skipped silently in `SourceMap.__init__` — is
   that right, or should it abort?

**Against the comment stripper (I5)**

4. Nested block comments: `/* outer /* inner */ still outer? */`. Solidity does
   not support nesting, so the scanner ends at the first `*/`. Confirm that
   matches solc's lexer rather than merely being defensible.
5. A comment inside a string inside a comment.
6. `///` appearing mid-line after code: `uint x = 1; /// @notice tricky`. Kept as
   natspec — should it be, given solc only treats leading natspec as
   documentation?
7. Line separator characters (U+2028/U+2029) inside a `//` comment. Python's
   `str.find("\n")` will not stop there; does anything downstream treat them as
   newlines and desynchronise?

**Against IDs and dedupe (I3)**

8. Two contracts with the same name in different files — IDs stay distinct via
   path, but does the *breadcrumb* become ambiguous to a reader?
9. ~~Struct parameters collapsing to `struct` in signatures.~~ **Fixed.**
   `canonical_type()` strips solc's leading keyword and trailing data location,
   so `struct MarketState memory` becomes `MarketState` and
   `contract WildcatMarket` becomes `WildcatMarket`. IDs are now
   self-describing — `fill(MarketData,WildcatMarket)` rather than
   `fill(struct,contract)` — which also improves what the embedding sees. No
   live collision existed beforehand; the risk was latent. Remaining question
   for review: fully qualified struct names (`Foo.Bar`) survive, but do they
   stay stable across compilation units that import differently?
10. Dedupe hashes `model_text`. Two genuinely different functions with identical
    bodies but different natspec are deduped — is dropping the second right?

**Against resource use**

11. A single function larger than the embedding context (~24,000 chars). Flagged
    as a warning, not an error, and the chunk is still emitted. bge-m3 will
    truncate it silently at 8K tokens. Should oversize be fatal?
12. Deeply nested AST from generated code — recursion is currently only two
    levels (source → contract → member), so this is bounded. Confirm no
    contract-in-contract construct exists that would need more.

**Against the trust boundary**

13. `standard-input.json` is read from a repo path and passed to `solc`. It is
    an untrusted-shaped input executed by a compiler. Is running solc on it
    inside CI acceptable, or does it want a container?
14. The `--include` globs use `fnmatch`, where `src/**` does not behave like a
    shell globstar. Confirm the include set is what you think it is; an
    over-broad glob silently pulls `lib/` into the corpus.

---

## Known gaps

- **`--include` uses `fnmatch`, not shell globbing.** `src/**` matches by
  substring semantics rather than path segments. Verify the include set is what
  you intend; an over-broad pattern quietly pulls library code into the corpus.
  Attack 14.
- **Assembly blocks are chunked as part of their enclosing function** and carry
  no special treatment. Some are long and dominated by opcodes, which may
  embed poorly.
- **Only `src/**` is chunked.** Library code from `lib/` is present in the
  compilation input but excluded from output. Behaviour inherited from those
  libraries is therefore invisible to retrieval.
- **Attacks 1–14 above are not all covered by tests.** The numbered attacks
  are the review agenda and several are still open — particularly 4 (nested
  block comments against solc's own lexer) and 7 (U+2028 inside a line
  comment). Attack 9 was closed by `canonical_type()`.
- **Inline code spans are modelled per line, not per paragraph.** A CommonMark
  code span can cross a soft line break; a comment marker inside one of those
  is treated as a real comment. No such construct exists in the pinned corpus,
  and the failure direction is stripping visible text, not leaking hidden
  text.
- **Setext detection tracks paragraphs, not list items.** `- foo` then `bar`
  then `---` is lazy continuation to CommonMark and the `---` closes a list;
  this scanner reads `bar` as a fresh paragraph and makes it a heading. No
  such construct exists in the pinned corpus.
- **The anchor algorithm is fitted, not specified.** It reproduces all 465
  heading ids docs.wildcat.finance serves for the pinned commit — including
  the literal `undefined-N` ids GitBook emits for mention-only headings — but
  GitBook publishes no spec, so a renderer change can invalidate it silently.
  `chunkers/verify_anchors.py` re-checks the whole fit against the live site;
  run it when the docs platform changes and before touching `gitbook_id()`.
- **The ABI cross-check compares name multisets, not full signatures.** It
  catches missing or surplus entries — the actual failure class — but a
  wrong parameter *type* in the listing with the right name would pass. Types
  in the listing are human-oriented (`IHooks`, not `address`) by design.

---

# Round 2 — what a second review found

Eleven code findings and two about the tests, reviewing `7b901bd` — the commit
that closed Round 1. The pattern that survived a round of fixing: **fail-open
defaults, and checks derived from the thing they check.** The embed rebuild
recovered its input by parsing its own previous output; the fatal-condition
tests re-enacted the production logic instead of calling it; empty selections
and missing navigation were warnings. None of it crashed. All of it reported
success.

**Solidity**

**Natspec could truncate the embedding.** `rebuild_embed_text()` recovered the
base text by splitting on `\n\nexposed by: ` — a marker any natspec author can
write. Everything after it, function body included, vanished from `embed_text`
while `display_text` stayed intact and every check passed. *Fixed:
`compose_embed_text()` derives the whole string from breadcrumb, kind,
`model_text`, exposure and alias state. Nothing parses previous embed text,
ever.* (I18)

**Public constant getters were missing from surfaces.** The one chunk that
promises to answer "what can I call" excluded `constant` state variables, so
`MaximumLoanTerm()` was absent from the FixedTermHooks surface. *Fixed:
every public state variable is listed, tagged `[getter]`, `[getter, constant]`
or `[getter, immutable]` — and the whole listing is now cross-checked against
the compiler's ABI as a name multiset, fatally. The approximation is still
hand-built; divergence is no longer silent.* (I19)

**Constructors were attributed to derived contracts.** Inheritance resolution
treated them as inherited members, so four live constructor chunks claimed
exposure by contracts that cannot call them, or anything. *Fixed: constructors
carry no exposure and are excluded from the unreachable report — they run
once, at deployment.* (I20)

**Folded duplicates were unfindable under their folded names.** Dedupe recorded
alias IDs in `detail.aliases` and nothing downstream indexed them: 46 live
aliases, none retrievable. *Fixed: dedupe also records the alias breadcrumb,
and composition appends "also declared as:" lines to `embed_text`.* (I21)

**An empty selection was a successful build.** `--include 'typo/**'` produced
zero chunks, a green summary and exit 0 — while PIPELINE.md §2 promised the
opposite. *Fixed: a unit whose selection is empty, a pattern matching nothing
across all units, and a zero-chunk corpus are all fatal. A pattern matched by
only some units is fine; only one deployment input carries Ownable.sol.* (I22)

**Markdown**

**Inline comments corrupted headings and code.** A same-line comment blanked
everything before its close, so `# Visible <!-- x --> title` stopped being a
heading; and comment markers inside inline code spans were stripped out of
`model_text`. *Fixed: only comment bytes are blanked, and a `<!--` inside a
single-line code span is literal text.* (M13)

**Raw HTML was invisible to the scanner.** A `#` line inside `<div>…</div>`
became a heading and corrupted every breadcrumb after it. *Fixed: the scanner
tracks all seven CommonMark HTML block types; types 1/3/4/5 run to their
terminators, types 6/7 to the next blank line, and nothing inside is
structure.* (M14)

**Setext detection had no idea what a paragraph was.** `> quoted` followed by
`---` produced a heading of the quote; a two-line setext heading kept only its
last line. *Fixed: the scanner tracks open paragraphs. An underline heads the
whole paragraph above it or, absent one, `---` is a thematic break.* (M15)

**Anchors were slugged from raw markup and numbered over survivors.**
`[alpeh\_v](https://x.com/alpeh_v)…` slugged URL and all; duplicate numbering
skipped headings the size filter discarded, so citation fragments pointed at
the wrong section. *Fixed: anchors come from rendered inline text through the
renderer's own algorithm — fitted and verified against all 465 heading ids
docs.wildcat.finance serves for the pinned commit, GitBook's literal
`undefined-N` ids for mention-only headings included, because a fragment
that does not say what the renderer says does not resolve — counted over every parsed
heading, with `-1`/`-2` suffixes as GitBook numbers them and `None` for page
titles, which get no id at all.* (M16)

**A missing SUMMARY failed open.** A typo'd path was a warning and an
exit 0 corpus with no hierarchy. *Fixed: requested-but-unreadable navigation
is fatal, a hierarchy that places zero documents is fatal, and coverage is
reported both ways — included files the nav omits, nav entries pointing at
nothing. `--summary ''` remains the explicit opt-out.* (M17)

**The tests**

The fatal-condition tests re-enacted the merge loop and validated the
re-enactment; markdown had no fixtures for any of the above. *Fixed: build()
and chunk_tree() are the code the CLIs run and the code the tests call, plus
subprocess-level checks that a failed build exits 1 and writes nothing.*
(I15, I23, M17)

`chunkers/verify_anchors.py` re-runs the whole fit against the live site —
every SUMMARY page, every heading id, paired positionally against the pinned
sources through the same `assign_anchors()` the chunker uses. Zero mismatches
or the algorithm has been invalidated. It found two bugs the day it was
written: the renderer's `undefined` artifact, and its author's exit-code
check reading the wrong end of a pipeline.

---

## Current output, for reference

```
962 chunks from 5 compilation unit(s)  (46 duplicate bodies folded, 46 alias id(s) kept)
  schema        : 0 problem(s)
  oversize      : 0  (p99 2340 chars, max 5062, limit 24000)
  synthesised   : 68  (not quotable as source)
  inheritance   : 460 chunks attributed to a concrete contract
  unreachable   : 0 public/external fns on contracts exposed by nothing
  by kind       : Enum=2, Error=104, Event=75, Function=655, Modifier=15,
                  Struct=39, UserDefinedValueType=4, contract=19,
                  interface=13, library=23, surface=13
```

```
516 chunks from 63 document(s)
  hierarchy     : 63/63 included document(s) placed
  synthesised   : 63  (not quotable as source)
  nav hierarchy : 510 chunks placed in the SUMMARY tree
  size          : median 498, p99 3793, max 9524
  schema        : 0 problem(s)
```

Input: all five `deployments/mainnet/*/standard-input.json` at
`v2-protocol@v2.1.0` (`c7be403`), solc 0.8.25; `wildcat-docs@aleph-v0.1`
(`6c94fb3`) with `SUMMARY.md` as hierarchy and excludes from `manifest.yaml`.

Include set: `src/**` plus `lib/solady/src/auth/Ownable.sol`. See
`manifest.yaml` for why only one external library file is in.

Tests: `test_solidity.py --solc solc` — 100 assertions across I1–I23.
`test_markdown.py` — 78 assertions across M1–M17, no compiler needed. Exit code
is the failure count in both. I12–I17 and M7–M12 are Round 1 regressions;
I18–I23 and M13–M17 are Round 2.
