# Chunker verification guide

This guide reproduces the current chunker checks and identifies the residual
review surface. The four completed adversarial review rounds are summarized in
`ADVERSARIAL.md`; their resolved findings are regression fixtures in the test
suites.

The chunkers define what a citation points to. Their dangerous failure mode is
not a crash—the build stops on a crash—but a plausible chunk that attributes
the wrong bytes, path, anchor, contract, or version to a source.

## Components under review

`ingest/chunkers/solidity.py` compiles deployment verification inputs and emits
semantic chunks with natspec, byte-exact source slices, resolved inheritance,
and ABI-checked callable surfaces.

`ingest/chunkers/markdown.py` emits heading-based chunks with GitBook navigation,
rendered anchors, comment-stripped model text, and byte-exact display text.

Both emit `ingest/schema.py::Chunk`; `ingest/build.py` namespaces their IDs,
stamps provenance, validates the merged set, and writes corpus artifacts.

## Reproduce the checks

Set up the Python dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install pyyaml numpy
```

Run the dependency-light suites:

```bash
python3 ingest/chunkers/test_markdown.py
python3 ingest/chunkers/test_solidity.py
python3 ingest/test_build.py
python3 embed/test_embed.py
python3 test_release.py
python3 test_retrieval.py
python3 test_live.py
python3 test_agent.py
python3 test_evaluation.py
```

The Solidity suite skips compiler-backed cases unless `--solc` is supplied.
Use the pinned container for the reproducible path:

```bash
python3 ingest/chunkers/test_solidity.py \
  --solc ingest/solc-container
```

The source fixture used for a full corpus reproduction is the signed
`v2-protocol@aleph-v2.1.0` tag. Its commit is
`c7be4039f8f383a9dda4e45f63331c17d63f9ed9`; the manifest also pins the annotated
tag object and signer fingerprint. The docs fixture is
`wildcat-docs@aleph-v0.3`, commit
`fe0e50c079b227cdd3ac14f8a1657a7c072b6446`.

Build the canonical corpus/index candidate through the release driver rather
than retyping component options:

```bash
python3 release.py \
  --manifest manifest.yaml \
  --solc ingest/solc-container \
  --artifacts artifacts
```

Use `--source-path v2-protocol=/path/to/checkout` and
`--source-path wildcat-docs=/path/to/checkout` to avoid new clones during local
review. The build records that acquisition method.

## Expected pinned-corpus baseline

The last recorded direct chunker runs produced:

```text
Solidity
  962 chunks from 5 compilation units
  46 duplicate bodies folded with searchable aliases
  68 synthesized chunks
  0 schema problems
  0 unreachable public/external functions
  p99 2,340 characters; maximum 5,062

Markdown
  545 chunks from 64 documents
  64/64 emitted documents placed in the SUMMARY hierarchy
  64 synthesized document indexes
  0 schema problems
  p99 3,793 characters; maximum 9,524
```

These counts are regression clues, not a substitute for reading the diff. A
legitimate source promotion or chunking correction can change them.

The recorded suites contain 142 Solidity assertions and 113 Markdown
assertions. Exit code is the failure count. Compiler-backed Solidity assertions
must run before treating the full 142 as exercised.

## Review priorities

### Citation integrity

For every non-synthesized chunk, verify that `display_text` is a byte-exact slice
of the pinned source. Check multibyte text, natspec attachment, paths, line
numbers, duplicate headings, and rendered anchors. Ensure every assembled header,
surface, or document index is synthesized and no ordinary slice is mislabeled.

### Model/display separation

Verify that comment removal changes only `model_text`, never `display_text`.
Solidity documentation must be determined from solc's attached documentation
range rather than comment syntax. Markdown hidden text must not enter model
context through malformed fences, code spans, raw HTML, lazy continuation, or
comments.

### Inheritance and ABI agreement

Exercise diamonds, overrides, public state-variable getters, constructors,
interfaces, overloads, structs, enums, and contracts used as parameter types.
Exposure merging across compilation units must union concrete contracts and OR
override state. Callable surfaces must agree with the compiler ABI by full
signature, not only by name.

### Fail-loud boundaries

Confirm that missing include matches, zero-chunk units, unreadable navigation,
path traversal, symlinks, duplicate IDs, empty model text, oversize embedding
text, schema disagreement, dirty local checkouts, wrong refs, and signature
failures stop the build without publishing a partial artifact.

Tests should call the production entry point rather than reimplementing the
logic under test. Several historical regressions stayed green because a test
asserted on its own copy of a merge or coverage calculation.

## Residual weak points

- Include matching uses Python `fnmatch`, not shell globstar semantics. Review
  the actual selected paths after any pattern change.
- Assembly blocks remain inside their enclosing function and receive no special
  retrieval treatment.
- Solidity callable-surface validation checks inputs and exposure but not return
  types or mutability.
- The Markdown inline scanner is deliberately narrower than a complete
  CommonMark parser. It covers constructs that can hide headings or comments;
  ambiguous code-span cases resolve toward stripping visible text rather than
  admitting hidden text.
- GitBook anchor generation is fitted to the live renderer, which has no public
  slug specification. Run `ingest/chunkers/verify_anchors.py` after a docs or
  renderer change.
- Whole-document fallback chunks are coarser than ordinary section chunks, and
  retrieval quality for that grain has not been isolated in evaluation.
- A developer can bypass the pinned compiler wrapper by passing a local solc.
  `--expect-solc` checks the version when used; only the container pins the
  compiler artifact.
- The corpus builder has broader responsibilities and less independent review
  history than the two chunkers. Signature, watch, metadata, output-reuse, and
  diff behavior deserve the same adversarial attention.

## Review output

A useful review report names each attempted invariant, records the fixture and
result, and adds a regression fixture for every successful attack. A patch
without a fixture leaves the failure mode easy to reintroduce.

Relevant files:

```text
ingest/build.py
ingest/schema.py
ingest/chunkers/solidity.py
ingest/chunkers/markdown.py
ingest/chunkers/verify_anchors.py
ingest/chunkers/test_solidity.py
ingest/chunkers/test_markdown.py
ingest/test_build.py
ingest/ADVERSARIAL.md
ingest/PIPELINE.md
manifest.yaml
```
