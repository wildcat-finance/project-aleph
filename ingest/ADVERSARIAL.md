# Adversarial review: the chunkers

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
- **Attacks 1–14 above are not all covered by tests.** `test_solidity.py`
  covers I1–I5 with 24 assertions, all passing. The numbered attacks are the
  review agenda and most are still open — particularly 4 (nested block
  comments against solc's own lexer), 7 (U+2028 inside a line comment), and 9
  (struct parameters collapsing to `struct` in signatures, which is a latent
  collision nobody has hit yet).

---

## Current output, for reference

```
991 chunks from 5 compilation unit(s)  (46 duplicates dropped)
  id collisions : 0
  oversize      : 0
  synthesised   : 69  (not quotable as source)
  inheritance   : 457 chunks attributed to a concrete contract
  unreachable   : 0 public/external fns on contracts exposed by nothing
  by kind       : Function=679, Error=104, Event=75, Struct=43, library=24,
                  contract=19, Modifier=15, interface=13, surface=13,
                  UserDefinedValueType=4, Enum=2
```

Input: all five `deployments/mainnet/*/standard-input.json` at
`v2-protocol@v2.1.0` (`c7be403`), solc 0.8.25.

Include set: `src/**` plus `lib/solady/src/auth/Ownable.sol`. See
`manifest.yaml` for why only one external library file is in.

Tests: `python3 ingest/chunkers/test_solidity.py --solc solc` — 47 assertions
across I1–I5 and I8–I11, exit code is the failure count.
