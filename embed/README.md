# Embedding

Corpus generation stops at `corpus/<build_id>/chunks.jsonl`. The embedding
layer consumes that artifact separately because embedding is model-runtime
work while corpus builds are source-processing work, and because a re-embed
does not require a re-chunk. `ingest/build.py` has no dependency on this
directory.

The implementation is a tiered NumPy index with exact cosine search. It does
not implement Postgres, pgvector, BM25, hybrid fusion, answer generation, or
deployment promotion.

```bash
python3 embed/index.py build  --corpus corpus/<build_id> \
                              --embedder ollama:bge-m3 --out index/
python3 embed/index.py search --index index/<build_id> \
                              --embedder ollama:bge-m3 --query "…"
```

`numpy` is required for every backend. The `st:` backend additionally requires
`sentence-transformers`; Ollama and HTTP backends use the Python standard
library for transport.

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
artifact that can rank differently, and an index built with it inherits none
of that evidence.

The Ollama backend records the digest it actually loads, and search requires
that same digest. The CLI does not read the expected digest from
`manifest.yaml`; confirm the local digest matches the manifest before building
a release index.

## Backends

| spec | use |
|---|---|
| `ollama:bge-m3` | reference; what the eval measured, already a service on a port |
| `st:BAAI/bge-m3` | in-process convenience; a *different artefact*, see above |
| `https://host/…` | any service speaking the protocol below |
| `stub:name` | deterministic hashes; plumbing tests only, and says so in its identity |

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

About 1,600 chunks at 1,024 dimensions is a 6.6 MB matrix and one matrix
multiplication. An approximate index would add a dependency, a build step, and
a recall boundary without a useful gain at this size. Revisit this choice if
the corpus approaches one hundred thousand chunks.
