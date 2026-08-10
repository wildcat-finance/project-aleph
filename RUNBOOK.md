# Runbook: choosing the embedding model

Decide between `qwen3-embedding` and `bge-m3` by measurement rather than
argument. Half a day, mostly waiting.

The output you act on is not a score. It is the list of ~20 questions where the
two models retrieve different things. Where they agree, neither is telling you
anything.

---

## 1. Prerequisites

```bash
ollama --version

python3 -m venv .venv
source .venv/bin/activate
pip install numpy pyyaml
```

Use a virtualenv. macOS has no bare `pip`, and a Homebrew or system Python will
refuse `python3 -m pip install` outright with `externally-managed-environment`.
Add `.venv/` to `.gitignore`.

Corpus is a few megabytes, so indexing runs comfortably on a laptop and indexing
speed is irrelevant. Only the *query* side is on the bot's hot path later — one
short string per question — so throughput doesn't matter either.

The constraint that does matter is **resident memory on the bot host**, since the
model stays loaded to embed queries: 639MB for `0.6b` against 4.7GB for `8b`.
That is the whole trade, and §5 is how you decide whether it's worth paying.

## 2. Pull the models

```bash
ollama pull bge-m3                  # 1024 dims, 8K context
ollama pull qwen3-embedding:0.6b    # 639MB, 32K context
ollama pull qwen3-embedding:8b      # 4.7GB, 40K context
```

Pull all three. The whole set is under 7GB and the comparison costs one extra
coffee, so there is no reason to guess which size is enough.

**Never use `qwen3-embedding` bare or `:latest`** — `latest` resolves to `8b`
today and may not tomorrow. Same reasoning as every other pin in this repo.

Verify both are actually embedding models and note the dimensions — the numbers
below are from memory and worth confirming rather than trusting:

```bash
for m in bge-m3 qwen3-embedding:0.6b; do
  echo -n "$m: "
  curl -s localhost:11434/api/embed \
    -d "{\"model\":\"$m\",\"input\":[\"test\"]}" \
  | python3 -c 'import json,sys; print(len(json.load(sys.stdin)["embeddings"][0]), "dims")'
done
```

Sizes and contexts from the Ollama library: `0.6b` is 639MB / 32K, `4b` is
2.5GB / 40K, `8b` is 4.7GB / 40K. Dimensions are what the curl above prints —
expect 1024 for both `bge-m3` and `qwen3-embedding:0.6b`, and larger for `8b`.

## 3. Get the corpus at the pinned ref

Embed what Aleph will actually serve, not what's on `main`:

```bash
git clone https://github.com/wildcat-finance/v2-protocol
cd v2-protocol && git checkout v2.1.0

git clone https://github.com/wildcat-finance/wildcat-docs
cd wildcat-docs && git checkout aleph-v0
```

Start with the protocol `docs/` directory. It is small, it is prose, and most of
section A and B of the golden set should be answerable from it. Add the GitBook
docs once the harness works, and Solidity last — chunking that properly needs
the AST path from `ingest/PIPELINE.md`, not the markdown splitter in this script.

## 4. Run the comparison

```bash
python3 eval/embed_compare.py \
  --docs v2-protocol/docs \
  --questions eval/golden-v1.yaml
```

Defaults to all three models. Output is pairwise disagreement rates, then full
detail on the questions where *every* model picks something different — those
are where the choice actually matters — then the remaining disagreements between
the first two.

It filters the golden set to the 61 questions expecting a corpus answer —
refusals and triage items have no correct chunk, so scoring them is meaningless.

Output is a disagreement list: every question where the two models put a
different chunk in first place, with each model's pick and the top-5 overlap.

## 5. Read the disagreements

For each one, ask a single question: *which chunk would let you answer this?*

**Watch the chunk type, not just the topic.** bge-m3 leans toward long prose
sections from Core Behavior; Qwen leans toward short Terminology definitions. A
glossary entry can be topically perfect and still make a bad answer — "why isn't
my balance claimable" answered from `Terminology › Claim` yields a definition
where the asker needed an explanation. Judge what an answer built from the top-5
would look like, not whether the label sounds right.

You are not looking for a model that wins on average. You are looking for the
one that fails less badly on the questions that matter — `a01` (partial
claimability), `b01`/`b02` (interest on deposits), `a07` (interest stops at
cycle start). If a model retrieves a plausible-but-wrong chunk on those, that is
disqualifying regardless of how it scores elsewhere.

**Ignore my earlier guess of 15–30%.** The first real run produced 64%, 74% and
39%. On a small corpus with many near-duplicate chunks, top-1 disagreement is a
weak signal — several chunks can be equally reasonable answers. Concentration
(§5a) turned out to be the diagnostic that matters.

**The specific thing to watch for between `0.6b` and `8b`:** on a corpus this
small and this domain-specific, they may barely differ. If the disagreement rate
between them is low and the disagreements are ties rather than errors, take the
`0.6b` — 639MB resident on the bot host instead of 4.7GB, for nothing given up.
If `8b` is clearly better on the questions in §5 that matter, take it; the
memory is affordable, it just has to be earned rather than assumed.

## 5a. Check concentration first

The report opens with how many *distinct* chunks each model ever ranks first. A
healthy model spreads first place widely. A model that returns the same chunk for
unrelated questions — "how do I enumerate markets", "do you have a Discord",
"what's the default recovery process" all landing on `Terminology › Lender` — is
not being opinionated, it is failing to discriminate. The script calls this hub
collapse and flags it.

Hub collapse invalidates everything downstream. Do not compare quality between a
collapsed model and a healthy one; fix the collapse or drop the model.

The first thing to try is removing the instruction prefix:

```bash
python3 eval/embed_compare.py --docs v2-protocol/docs --no-prefix
```

**Result on this corpus: the prefix was actively harmful.** With it,
`Terminology › Lender` won first place for twelve unrelated queries spanning six
sections of the golden set — "do you have a Discord", "is there an API to
enumerate markets", "where's the loan agreement". Without it, Qwen's picks became
topically sensible: `Withdrawal Cycle` for cycle questions, `Delinquency` for
delinquency, `Capacity` for capacity. **Run Qwen without the instruct prefix.**
The GGUF packaging does not preserve the prompt convention of the original
weights.

Note also that raw repetition is not itself failure. Section A is eighteen
withdrawal questions, so a withdrawal chunk winning seven times is correct. The
script now judges by how many *different sections* a repeated chunk absorbs:
four or more unrelated sections is collapse, two adjacent ones is a topical
cluster. The first version of this check flagged everything and was useless.

## 6. Optional: a number to gate builds on

Once you have a preference, label a subset so CI can detect regressions:

```yaml
# eval/labels.yaml — question id → substrings that must appear in a retrieved chunk
a01: ["withdrawal batch", "claimable"]
a07: ["interest", "cycle"]
b01: ["lender deposits"]
```

```bash
python3 eval/embed_compare.py --docs v2-protocol/docs --labels eval/labels.yaml
```

Thirty labelled questions is enough to catch a regression. This is the
`eval_not_regressed` gate in `ingest/PIPELINE.md` becoming real.

## 6a. Results on this corpus (2026-08-10)

87 chunks from `v2-protocol/docs`, 52 scored questions, 25 labelled, `--no-prefix`.

| model | distinct top-1 | @1 | @3 | @5 | resident | dims | context |
|---|---|---|---|---|---|---|---|
| **bge-m3** | **28/52** | **20/25** | 23/25 | 23/25 | ~1.2GB | 1024 | 8K |
| qwen3-embedding:0.6b | 25/52 | 18/25 | 22/25 | **24/25** | 639MB | 1024 | 32K |
| qwen3-embedding:8b | 25/52 | 17/25 | 22/25 | 23/25 | 4.7GB | 4096 | 40K |

**`8b` is out.** Same recall as `bge-m3`, worse than the 0.6b, at seven times the
resident memory and four times the vector width. Scale buys nothing on a corpus
this small and this narrow — which is worth remembering the next time a bigger
model looks like the safe default.

**Decision: `bge-m3`.** Recorded in `manifest.yaml`.

@5 is saturated — all three within one question — so it discriminates nothing.
@1 separates them and puts bge-m3 ahead by two, which agrees with its wider
spread of first-place chunks and its preference for explanatory prose over
glossary definitions. Two questions out of 25 is not statistical significance;
it is the only signal available, and nothing contradicts it.

The counter-argument, on the record: qwen 0.6b wins @5 by one, and since five
chunks go into the model's context, @5 is arguably the operative metric. It is
also half the size with four times the context.

What actually settled it was not a number. `bge-m3` performs as documented.
`qwen3-embedding:0.6b` performs only with its documented instruct prefix
*removed* — a configuration that works today and breaks silently the next time
the GGUF is rebuilt. Pinning the digest mitigates that; relying on it does not.

**Revisit when Solidity enters the corpus.** bge-m3's 8K context is comfortable
for prose. Contract chunks carrying full natspec may not be, and truncation is
silent. Assert chunk length at ingest; if it bites, qwen's 32K is the reason to
re-run this whole exercise.

## 7. Pin the winner

In `manifest.yaml`:

```yaml
embedding:
  model: qwen3-embedding:0.6b
  digest: sha256:...          # NOT just the tag
  dimensions: 1024
```

Get the digest with `ollama show qwen3-embedding:0.6b --modelfile`, or from
`ollama list`. **Ollama tags are mutable** — `bge-m3` today and `bge-m3` in six
months can be different weights. Pinning the tag alone breaks the pipeline's
central promise that the same manifest produces the same corpus.

---

## Gotchas

**The prefix asymmetry.** Qwen3-Embedding expects an instruction on the *query*
side and bare text on the document side. bge-m3 expects no prefix at all.
Applying the wrong convention doesn't error — retrieval just quietly gets worse,
with nothing in any log to explain it. The script handles this; if you
reimplement, don't drop it.

**Dimension changes are corpus rebuilds.** Vectors from different models are not
comparable and pgvector columns are fixed-width. Switching from a 1024-dim model
to a 2560-dim one means a new column and a full re-embed. Cheap at this corpus
size, but not a config toggle.

**Quantisation.** Default Ollama tags are usually quantised, and for embeddings
that loss lands directly on retrieval accuracy. Checked for the chosen model:
`ollama show bge-m3` reports **F16**, 566.70M parameters, bert architecture — so
this one ships full precision and there is nothing to compare against. Re-check
if the model or its packaging ever changes; do not assume it holds.

**Context length silently truncates.** A chunk longer than the model's window is
cut without warning. bge-m3's 8k is comfortable for prose but Solidity chunks
with full natspec can be long. Assert chunk length at ingest rather than
discovering it in a bad answer.

**A fast laptop is not the deployment target.** On Apple Silicon the 8B model
runs on Metal and feels instant, which tells you nothing about a headless x86 VPS
with no GPU holding 4.7GB resident next to Postgres. Choose on retrieval quality
here; decide the size question against the host the bot will actually run on.

**Ollama version.** The `/api/embed` endpoint (batched, returns `embeddings`)
superseded `/api/embeddings` (single, returns `embedding`). If you get a shape
error, that's why.

**This harness is markdown-only.** It uses a heading splitter, not the AST
chunker from `ingest/PIPELINE.md`. Fine for choosing a model on prose; do not
use its Solidity results to conclude anything about Solidity retrieval.

---

## What I couldn't test

The script's chunking, question filtering, prefix selection and ranking are
verified — 51 chunks with correct breadcrumbs from the four protocol docs, 61
questions filtered, ranking shape correct. The HTTP path to Ollama is *not*
tested, because there's no Ollama in the environment this was written in. If it
falls over on first run it will be there, and it will be obvious.
