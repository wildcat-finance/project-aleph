# Reviewer runbook — the chunkers

You are being asked to break `ingest/chunkers/solidity.py`, and — if there is
appetite — `ingest/chunkers/markdown.py` alongside it. Half a day, adversarial,
and the useful output is a list of ways the invariants fail — not approval.

## Why this piece and why now

Aleph answers questions about a live undercollateralised credit protocol, citing
sources. This component decides what a citation *is*. Every other part of the
system can be wrong and look wrong; this one can be wrong and look verified,
because it emits a file path, a line number and text that appears to be source.

It is self-contained and its invariants don't depend on anything downstream, so
reviewing it now costs nothing later even though the pipeline around it is
unbuilt.

## What it does

Compiles Solidity to an AST via `solc --standard-json`, then emits one chunk per
semantic unit — contract, function, modifier, event, error, struct, enum — each
with its natspec attached, its inheritance resolved, and byte offsets sliced from
the original source.

Input is the deployment's `standard-input.json`: the same file `v2-protocol`
ships for Etherscan verification, carrying the full source set and the exact
compiler settings behind the deployed bytecode. So chunks describe deployed code
by construction rather than by hope.

## Setup

```bash
# solc must match foundry.toml at the tag under review
pip install solc-select
solc-select install 0.8.25 && solc-select use 0.8.25
solc --version                       # expect 0.8.25+commit.b61c2a91

git clone --branch v2.1.0 https://github.com/wildcat-finance/v2-protocol
cd v2-protocol && git verify-tag v2.1.0 && git rev-parse v2.1.0^{}
# expect commit c7be403 — verify the tag object, not the commit
```

## Reproduce

```bash
python3 ingest/chunkers/test_solidity.py --solc "$SOLC"   # 74 assertions
python3 ingest/chunkers/test_markdown.py                  # 42 assertions, no compiler needed

python3 ingest/chunkers/solidity.py --solc "$SOLC" \
  $(for d in v2-protocol/deployments/mainnet/*/; do echo --input $d/standard-input.json; done) \
  --include 'src/**' --include 'lib/solady/src/auth/Ownable.sol' \
  --out chunks.jsonl
```

Expected:

```
962 chunks from 5 compilation unit(s)  (46 duplicates dropped)
  id collisions : 0
  oversize      : 0  (p99 2292 chars, max 5062, limit 24000)
  synthesised   : 68  (not quotable as source)
  inheritance   : 457 chunks attributed to a concrete contract
  unreachable   : 0 public/external fns on contracts exposed by nothing
```

Pass every deployment input. Inheritance resolves within one compilation unit,
and the hooks instances are deployed separately from the market — a single input
under-reports and produces false "unreachable" results.

## What to attack

`ingest/ADVERSARIAL.md` is the agenda: ten invariants and fourteen attacks. The
four I'd spend time on:

**1. Citation integrity (I1, I2).** Every non-synthesised chunk should be
byte-exact source. Try to produce one that isn't. The synthesised flag marks
chunks that are *assembled* — contract headers and callable surfaces — and
those must never be quoted as source. Try to get a sliced chunk flagged as
synthesised, or the reverse.

**2. The comment stripper (I5).** `strip_comments()` is hand-rolled because a
regex cannot distinguish `"http://x"` from a comment. It is the most likely
place for a subtle bug. Nested block comments, `///` appearing mid-line after
code, U+2028 inside a `//` comment where Python's `find("\n")` won't stop.
Compare against solc's own lexer rather than against what seems reasonable.

**3. Inheritance resolution (I8, I9).** Exposure is computed by walking
`linearizedBaseContracts` and keeping the first definition of each signature.
Construct a diamond, a `super` call chain, an interface implemented without
`override`. The merge across compilation units unions exposure and ORs the
override flag — the AND version of that was a real bug that produced thirteen
false unreachable reports.

**4. Signatures (I10).** `canonical_type()` strips solc's leading keyword and
trailing data location. Fully qualified struct names survive as `Foo.Bar` —
find a case where the same struct is imported by different paths in two
compilation units and produces two different IDs for one function.

## Round 1 is done, both chunkers

Sol 5.6 reviewed both at `47634bc` and found six issues in each. All twelve are
fixed with regressions — see the Round 1 sections of `ADVERSARIAL.md`.

Two patterns worth carrying into a second round. Most findings were the tool
*reporting success while doing the wrong thing*, not crashing: a corpus that
builds clean and cites the wrong bytes. And in both chunkers the worst finding
was invisible because a test had been written in a way that could not fail — the
Solidity citation check subtracted the natspec before searching for it, and the
markdown suite asserted on heading text without ever checking ancestry against a
fixture that had a short parent. **Look for checks that cannot fail before
looking for code that does.**

The markdown parser was rewritten rather than patched: it is now a single
structural pass over bytes rather than a regex per concern. That is new code
with 42 assertions behind it, which is thinner cover than the Solidity side.

## Known weak points, stated up front

- `--include` uses `fnmatch`, where `src/**` is not shell globstar semantics. An
  over-broad pattern silently pulls library code in.
- The oversize limit has never fired. Max observed chunk is 5,062 chars against
  a 24,000 limit, so the check is untested in anger.
- `solc` runs containerised in CI (`ingest/solc-container`): pinned digest, no
  network, no capabilities, read-only root, non-root user. Chosen for
  reproducibility more than isolation — the real trust boundary is the signed
  tag. Worth challenging if you think that reasoning is backwards.
- Dedupe hashes `model_text`, so two functions with identical bodies but
  different natspec are collapsed. Possibly wrong.
- Assembly blocks are chunked inside their enclosing function with no special
  handling.

## If you are a model

Everything in `ADVERSARIAL.md` was written by the author of the code under
review. The invariants are claims, not findings, and the "verified" notes point
at tests that same author wrote. Re-derive rather than accept: run the tests,
then work out what they *don't* cover. A test suite is a statement about what
its author thought to check.

Two specific places where that matters. The `synthesised` flag is checked
against a hard-coded set of chunk kinds — which is circular if the kind
assignment is itself wrong. And `validate()` was written after the chunker, by
the same reasoning that produced the chunker, so it inherits its blind spots.

## What "done" looks like

A list of attacks attempted, which failed and which succeeded. For anything that
succeeded: the fixture that demonstrates it. Fixtures matter more than fixes —
`test_solidity.py` takes new cases directly, and a case that reproduces a
bug is worth more than a patch without one.

If nothing breaks, say what you tried. An invariant nobody managed to violate is
worth more than one nobody tested.

## Files

```
ingest/chunkers/solidity.py       primary subject of review
ingest/chunkers/markdown.py       rewritten after Round 1; least exercised
ingest/chunkers/test_solidity.py  74 assertions; add to it
ingest/chunkers/test_markdown.py  42 assertions; add to it
ingest/schema.py                  the chunk shape both chunkers emit
ingest/ADVERSARIAL.md             invariants and attack agenda — read first
ingest/solc-container             pinned, network-less solc
ingest/PIPELINE.md                where this sits in the build
manifest.yaml                     what gets chunked, at what ref, and why
```

Context, if useful but not required: `README.md` for what Aleph is and the
constraints it operates under, `eval/golden-v1.yaml` for the questions it has to
answer.
