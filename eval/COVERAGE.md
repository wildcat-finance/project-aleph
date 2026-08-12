# Coverage silhouette

The coverage silhouette gives Project Null the rough shape of an evaluated
Aleph release without giving it corpus chunks or answer truth. Null can use the
shape to ask about neglected topics and route boundaries; a human still decides
whether an Aleph outcome is correct.

`eval/coverage.py` reads one promotable release and verifies its exact manifest,
corpus, evaluation, golden-question, and topic-map hashes before publishing an
immutable JSON artifact. The artifact identity is derived from all content
except its creation time.

## What it contains

- active evolution/generation, evolution contract, release, corpus, evaluation,
  golden-set, and topic-map identities;
- per-source and per-topic document/chunk counts;
- public protocol version, deployment class, source type, and authority tier;
- answer-case counts aggregated by topic;
- evaluated route, risk, frequency, register, live-operation, and question-shape
  counts; and
- declared gap counts aggregated by reviewed topic family.

Corpus document paths are reduced to topic slugs. Evaluation section names come
from the reviewed `coverage-topics-v1.yaml` map. Neither is factual answer
content.

## What it excludes

The schema rejects raw chunks, questions, answers, quotes, citations, source
paths, notes, reasons, URLs, addresses, and human identifiers. It explicitly
declares that the artifact is for question generation only. It cannot grade an
answer, approve a factual proposal, or authorize a corpus write.

## Publish for an evaluated release

From the repository root:

```bash
python3 -m eval.coverage \
  --release artifacts/releases/<release-id>/release.json \
  --pointer state/active-release.json
```

The result is written to:

```text
artifacts/coverage/<silhouette-id>/silhouette.json
```

An identical input reuses identical bytes. A modified directory with the same
identity is rejected rather than repaired. `test_coverage.py` provides the
determinism, reconciliation, immutability, tamper, and leakage gates.

## Handoff to Null

Transfer the single `silhouette.json` file through a read-only release channel.
Record its `silhouette_id`, bound Aleph `release_id`, and exact
`evolution N/generation M` in Null's run manifest.
Null must validate the schema, content hash, and release compatibility before
using it. Missing coverage falls back to Null's checked-in challenge catalogue;
malformed or tampered configured coverage fails closed.

Do not transfer the corpus directory, evaluation cases, golden questions, or
retrieval results alongside it. Those would let the challenger imitate answers
or self-grade and would collapse the independent-review boundary.
