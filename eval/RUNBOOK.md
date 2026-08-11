# Embedding evaluation runbook

This runbook records the `bge-m3` model decision and provides a repeatable way to
re-evaluate it when the corpus or model artifact changes.

The harness is diagnostic, not a production gate. It compares models over a
Markdown corpus, reports retrieval disagreements and concentration, and computes
recall for labelled questions. It remains useful for model comparison, but it
does not use the ingestion pipeline's full corpus or chunk schema.

`eval/retrieval_eval.py` is the release-level retrieval check. It loads a real
immutable corpus/index release, applies chain/version/tier policy and hybrid
ranking, and evaluates the same labels against the chunks the product retrieves.

## Recorded decision

The comparison recorded on 2026-08-10 used 87 chunks from
`v2-protocol/docs`, 52 corpus-answer questions, 25 labels, and no query prefix.

| Model | Distinct top-1 | Recall@1 | Recall@3 | Recall@5 | Resident memory | Dimensions |
|---|---:|---:|---:|---:|---:|---:|
| **bge-m3** | **28/52** | **20/25** | 23/25 | 23/25 | ~1.2 GB | 1024 |
| qwen3-embedding:0.6b | 25/52 | 18/25 | 22/25 | **24/25** | 639 MB | 1024 |
| qwen3-embedding:8b | 25/52 | 17/25 | 22/25 | 23/25 | 4.7 GB | 4096 |

`bge-m3` is the selected artifact and is pinned in `manifest.yaml`. Its recall@1
was highest and its first-place choices were spread across more distinct chunks.
The 8B Qwen model added memory and vector width without improving retrieval.

The numerical margin is small. The stronger reproducibility reason is that
`bge-m3` performs without an instruction prefix, while the tested Qwen Ollama
packaging performed better only when its documented query prefix was removed.
That packaging-specific inversion is easy to lose during a model refresh.

Recall@5 is effectively saturated in this comparison, so it does not distinguish
the candidates. The selected model should be reconsidered when the evaluated
corpus, labels, model digest, or chunking method changes—not because a larger
model becomes available.

## Prerequisites

```bash
ollama --version

python3 -m venv .venv
source .venv/bin/activate
pip install numpy pyyaml
```

Pull the three recorded candidates:

```bash
ollama pull bge-m3
ollama pull qwen3-embedding:0.6b
ollama pull qwen3-embedding:8b
ollama list
```

Ollama tags are mutable. Record the digest reported by `ollama list` and compare
the chosen artifact with `embedding.digest` in `manifest.yaml`. A matching name
with a different digest is a different retrieval artifact.

## Prepare the pinned Markdown corpus

Use the refs named by the manifest rather than repository default branches:

```bash
git clone https://github.com/wildcat-finance/v2-protocol.git
git -C v2-protocol checkout aleph-v2.1.0
git -C v2-protocol rev-parse HEAD

git clone https://github.com/wildcat-finance/wildcat-docs.git
git -C wildcat-docs checkout aleph-v0.3
git -C wildcat-docs rev-parse HEAD
```

The recorded result uses only `v2-protocol/docs`. The harness accepts one docs
root at a time, so adding `wildcat-docs` is a different experiment and should be
reported separately.

## Reproduce the comparison

From the Project Aleph repository root:

```bash
python3 eval/embed_compare.py \
  --docs /path/to/v2-protocol/docs \
  --questions eval/golden-v1.yaml \
  --labels eval/labels.yaml \
  --no-prefix
```

`--no-prefix` is required to reproduce the recorded table. It disables the
default Qwen query prefix; bge-m3 has no prefix either way.

The harness automatically excludes `refuse`, `triage`, and `corpus_gap` entries
because none has a correct retrieval chunk. Use `--all-questions` only when
inspecting behavior, not when reporting recall.

To compare a different candidate set:

```bash
python3 eval/embed_compare.py \
  --docs /path/to/v2-protocol/docs \
  --questions eval/golden-v1.yaml \
  --labels eval/labels.yaml \
  --models bge-m3 another-model \
  --no-prefix
```

## Interpret the report

### Read disagreements, not only scores

For each disagreement, inspect whether the retrieved chunk could support the
answer. A glossary definition may match a topic while failing to explain the
behavior the user asked about. Consequential withdrawal and interest questions
deserve more weight than harmless navigation questions.

### Check top-1 concentration

The report counts distinct first-place chunks and flags a chunk that absorbs
questions from unrelated sections. Repetition within one topic can be correct;
the withdrawal section contains many related questions. Repetition across
withdrawals, defaults, APIs, and community links indicates hub collapse.

A collapsed model should not be compared by aggregate recall until the query
format or packaging issue is understood.

### Treat labels as regression checks

`eval/labels.yaml` maps a question ID to substrings expected in at least one
retrieved chunk. The labels are intentionally small and high-value. Changes to
them should reflect evidence review, not tuning to make a model score higher.

## Admit a Project Null regression export

Null exports regression candidates and factual proposals in separate files.
Aleph's regression importer validates the complete immutable export before it
reads reviewer dispositions: directory identity, canonical JSON, file hashes,
manifest counts, candidate ordering, schemas, and the content-derived export
ID must all agree. A non-empty factual-proposal file is a hard failure on this
path.

Each candidate then needs one checked-in disposition: `accepted`, `duplicate`,
`deferred`, `rejected`, or `needs_review`. Accepted cases must preserve the Null
question byte-for-byte in the golden set and carry both the export and candidate
IDs. Duplicate cases bind to an existing golden route. Deferred cases require a
tracking issue. Any undispositioned or silently reworded candidate fails closed.

```bash
python3 eval/null_import.py \
  --export eval/null-exports/e168ea3628343c39c9cf \
  --dispositions eval/null-dispositions-v1.yaml \
  --golden eval/golden-v1.yaml
```

The command exits `0` only when every candidate is dispositioned and none still
has `needs_review`. It does not edit the golden file, write corpus evidence, or
mark anything resolved in Null. Run `python3 test_evaluation.py` after admitting
accepted cases so every new question traverses the real product path.

## Build and evaluate the selected release

The manifest records:

- model name;
- Ollama digest;
- dimensions;
- precision/quantization;
- context limit; and
- query-prefix behavior.

`release.py` reads the complete expected identity from `manifest.yaml` and
refuses a runtime mismatch before publishing the candidate:

```bash
ollama list

python3 release.py --manifest manifest.yaml \
  --solc ingest/solc-container --artifacts artifacts
```

Run the retrieval labels against the resulting `release.json`:

```bash
python3 eval/retrieval_eval.py \
  --manifest manifest.yaml \
  --release artifacts/releases/<release_id>/release.json \
  --embedder ollama:bge-m3
```

The command exits with the failure count and can write the complete evidence
report with `--json <path>`.

## When to rerun

Rerun the comparison when:

- the promoted docs or protocol source changes materially;
- chunking changes the evaluated text or breadcrumbs;
- the selected Ollama digest changes;
- labels are added or corrected;
- the corpus gains a source with materially different language or chunk length;
  or
- a chunk approaches the selected model's context limit.

The current measured Solidity maximum is 5,062 characters and the Markdown
maximum is 9,524 characters, both below bge-m3's 8,192-token context. The
ingestion schema rejects oversize embedding text rather than relying on silent
model truncation.

## Harness boundaries

`eval/embed_compare.py` uses a small heading splitter that is intentionally
independent from `ingest/chunkers/markdown.py`. It does not process Solidity,
GitBook navigation, tier separation, corpus provenance, the real vector-index
artifact, answer synthesis, citation validity, calibrated abstention, or live
state.

A running Ollama service and the exact model artifacts are external
prerequisites. The repository does not include an automated test suite for this
comparison harness, so inspect its reported corpus and question counts before
using a result as evidence.

`ingest/build.py` correctly leaves `eval_not_regressed` as `null`: the corpus
builder has no answer engine. Run `eval/product_eval.py` against completed main
and prerelease artifacts, then bind its passing immutable record with
`promotion.py`. The product evaluator is the promotion gate; this comparison
harness remains a diagnostic model-selection tool.
