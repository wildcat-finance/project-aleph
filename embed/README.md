# Embedding

Corpus generation stops at `corpus/<build_id>/chunks.jsonl`. Everything here
consumes that and is deployed separately, because embedding is GPU-shaped and
slow while corpus builds are CPU-shaped and fast, and because a re-embed
should never require a re-chunk. `ingest/build.py` imports nothing from this
directory and never will.

```bash
python3 embed/index.py build  --corpus corpus/<build_id> \
                              --embedder ollama:bge-m3 --out index/
python3 embed/index.py search --index index/<build_id> \
                              --embedder ollama:bge-m3 --query "…"
```

## The one invariant

**The index and the query must come from the same embedder.** Not the same
model name — the same artefact. Two embedders that disagree still return
correctly shaped unit vectors, cosine similarity still returns a number
between -1 and 1, and retrieval silently ranks the wrong chunks. There is no
downstream check that can notice, because nothing about the output is
malformed.

So every set of vectors carries an `Identity` — backend, model, digest,
dimensions, normalisation — the index records it, and `search()` refuses a
query whose identity does not match. That refusal is the only thing standing
between a model substitution and confidently wrong answers.

This is why `backend` is part of the identity and not just the model name.
`manifest.yaml` pins bge-m3 by **Ollama digest at F16**, and the retrieval
evidence in that file was gathered through Ollama by `eval/embed_compare.py`.
The same weights loaded through sentence-transformers at fp32 are a different
artefact that will rank differently, and an index built with it inherits none
of that evidence.

## Backends

| spec | use |
|---|---|
| `ollama:bge-m3` | reference; what the eval measured, already a service on a port |
| `st:BAAI/bge-m3` | in-process convenience; a *different artefact*, see above |
| `https://host/…` | any service speaking the protocol below |
| `stub:name` | deterministic hashes; tests only, and says so in its identity |

A hosted service needs two endpoints:

```
GET  /identity  -> {"backend","model","dimensions","normalised","digest","query_prefix"}
POST /embed     <- {"input": ["…"], "kind": "document"|"query"}
                -> {"embeddings": [[…]]}
```

Small on purpose. An interface that can be reimplemented in an afternoon can
be replaced without renegotiating it. `ALEPH_EMBED_TOKEN` is sent as a bearer
token when set.

## Layout

```
index/<corpus_build_id>/
  tier-A.npy      float32 [n, d], L2-normalised
  tier-A.jsonl    one metadata row per vector, aligned by position
  tier-B.npy
  tier-B.jsonl
  index.json      embedder identity, corpus build id, counts, corpus waivers
```

One index per tier, never blended: a single ranked list across both lets a
paragraph of prose outrank the function it describes, because the prose was
written to be readable and the function was not. Callers ask each tier and
decide.

Metadata sits beside the vectors so that answering a query does not require
the corpus — including `effective_date` and `doc_version`, so a legal citation
can name the version it quotes.

Corpus waivers are copied into `index.json`. An index built from a corpus that
skipped a gate should not be able to forget that.

## Brute force, deliberately

~1,600 chunks at 1024 dimensions is a 6.6 MB matrix and one matmul, well under
a millisecond. An approximate index would add a dependency, a build step and a
recall cliff for no measurable gain. Revisit around a hundred thousand chunks,
two orders of magnitude away.
