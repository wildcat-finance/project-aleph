#!/usr/bin/env python3
"""
embedder.py — Project Aleph

The embedding boundary. Corpus indexing and query answering are different
programs on different machines with different lifecycles, and the one thing
they must agree on absolutely is the function that turns text into a vector.
Everything here exists to make that agreement checkable rather than assumed.

    from embed.embedder import make_embedder
    e = make_embedder("ollama:bge-m3")
    v = e.embed(["what happens when a market goes delinquent?"], kind="query")

A vector is meaningless without knowing what produced it. Two embedders that
disagree still return the same shape of float array, cosine similarity still
returns a number between -1 and 1, and the answers are quietly wrong — no
exception, no empty result, just plausible retrieval of the wrong chunks.
`Identity` is therefore carried alongside every set of vectors, written into
every index, and compared before any search. It is the only defence, because
nothing downstream can detect the failure on its own.

Backends
    ollama:MODEL            HTTP to a local or remote Ollama, the reference
    st:MODEL                sentence-transformers in-process
    http://HOST/...         any service speaking the small JSON protocol below
    stub:NAME               deterministic, dependency-free, tests only

`build.py` knows nothing about any of this. Corpus generation produces
`corpus/<build_id>/chunks.jsonl` and stops; embedding consumes it. That way the
embedding runtime can move to GPU infrastructure or a hosted API without
touching corpus generation, and a re-embed does not require a re-chunk.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import struct
import urllib.error
import urllib.request
from dataclasses import dataclass, asdict


class EmbeddingError(Exception):
    """Raised for conditions that must stop an embed or a query."""


@dataclass(frozen=True)
class Identity:
    """
    What produced a vector, in enough detail to notice a substitution.

    `backend` and `digest` matter as much as `model`. The manifest pins
    bge-m3 by Ollama digest at F16 quantisation, and the same weights loaded
    through sentence-transformers at fp32 are a different artefact that will
    place different chunks first. The eval evidence in manifest.yaml was
    gathered against one of them; an index built with the other inherits none
    of it.
    """
    backend: str
    model: str
    dimensions: int
    normalised: bool
    digest: str = ""          # backend-specific: Ollama digest, HF revision
    query_prefix: str = ""    # empty when the model wants none, as bge-m3 does

    def key(self) -> str:
        """A short stable string for logs and directory names."""
        prefix = (hashlib.sha256(self.query_prefix.encode()).hexdigest()[:8]
                  if self.query_prefix else "none")
        return f"{self.backend}:{self.model}@{self.digest or 'unpinned'}" \
               f"/{self.dimensions}{'n' if self.normalised else ''}" \
               f"/q:{prefix}"

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Identity":
        return Identity(**{k: d[k] for k in
                           ("backend", "model", "dimensions", "normalised",
                            "digest", "query_prefix") if k in d})


def require_match(index_identity: Identity, query_identity: Identity) -> None:
    """
    Refuse a query whose vectors came from a different embedder.

    This is the whole reason Identity exists. A mismatch does not degrade
    retrieval, it silently randomises it: the vectors occupy the same space
    arithmetically and none of them mean the same thing.
    """
    if index_identity != query_identity:
        raise EmbeddingError(
            "the query was embedded by a different model than the index\n"
            f"  index : {index_identity.key()} {index_identity.to_dict()}\n"
            f"  query : {query_identity.key()} {query_identity.to_dict()}\n"
            "  Cosine similarity between these is arithmetic, not meaning. "
            "Re-embed the corpus or point the query at the matching runtime.")


def _l2_normalise(vectors):
    import numpy as np
    arr = np.asarray(vectors, dtype="float32")
    if arr.ndim == 1:
        arr = arr.reshape(1, -1)
    if arr.ndim != 2 or not arr.size or not np.isfinite(arr).all():
        raise EmbeddingError("embedding backend returned non-finite or empty vectors")
    # Accumulate in float64. Some platform BLAS implementations can overflow
    # float32 reductions despite finite unit-scale inputs; an embedding
    # boundary must not turn that into a plausible vector.
    norms = np.linalg.norm(arr.astype("float64"), axis=1, keepdims=True)
    if not np.isfinite(norms).all() or np.any(norms <= 0):
        raise EmbeddingError("embedding backend returned a zero or invalid vector")
    normalised = arr / norms.astype("float32")
    if not np.isfinite(normalised).all():
        raise EmbeddingError("embedding normalization produced non-finite values")
    return normalised


# --------------------------------------------------------------------------
# backends
# --------------------------------------------------------------------------

class OllamaEmbedder:
    """
    The reference backend, and the one the manifest's evidence was gathered
    against — `eval/embed_compare.py` chose bge-m3 by measurement through
    exactly this interface.

    Ollama is already a service on a port, which is the shape this needs to
    take anyway: the same class points at localhost during development and at
    a GPU box in production by changing one URL.
    """

    def __init__(self, model: str, host: str | None = None,
                 expect_digest: str | None = None, timeout: int = 120):
        self.model = model
        self.host = (host or os.environ.get("ALEPH_OLLAMA_HOST")
                     or "http://localhost:11434").rstrip("/")
        self.timeout = timeout
        self._identity: Identity | None = None
        self._expect_digest = expect_digest

    def _show(self) -> dict:
        try:
            req = urllib.request.Request(
                f"{self.host}/api/show",
                data=json.dumps({"model": self.model}).encode(),
                headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            raise EmbeddingError(
                f"{self.model}: HTTP {e.code} from {self.host}/api/show — "
                f"is it pulled? `ollama pull {self.model}`")
        except urllib.error.URLError as e:
            raise EmbeddingError(f"cannot reach Ollama at {self.host}: {e}")

    def _tags(self) -> dict:
        try:
            with urllib.request.urlopen(
                    f"{self.host}/api/tags", timeout=self.timeout) as response:
                return json.load(response)
        except urllib.error.HTTPError as e:
            raise EmbeddingError(
                f"{self.model}: HTTP {e.code} from {self.host}/api/tags")
        except urllib.error.URLError as e:
            raise EmbeddingError(f"cannot reach Ollama at {self.host}: {e}")

    def _reported_digest(self, info: dict) -> str:
        digest = str(info.get("digest") or "").removeprefix("sha256:")
        if digest:
            return digest
        # Current Ollama releases omit digest from /api/show. Resolve the exact
        # loaded tag through /api/tags instead of silently weakening identity.
        aliases = {self.model}
        if ":" not in self.model:
            aliases.add(self.model + ":latest")
        matches = [item for item in self._tags().get("models") or []
                   if item.get("name") in aliases or item.get("model") in aliases]
        if len(matches) != 1:
            raise EmbeddingError(
                f"{self.model}: /api/tags names {len(matches)} exact model "
                "matches; cannot establish one artifact digest")
        digest = str(matches[0].get("digest") or "").removeprefix("sha256:")
        if not re.fullmatch(r"[0-9a-fA-F]{12,64}", digest):
            raise EmbeddingError(
                f"{self.model}: /api/tags returned an invalid artifact digest")
        return digest

    def identity(self) -> Identity:
        if self._identity is None:
            info = self._show()
            details = info.get("details") or {}
            model_info = info.get("model_info") or {}
            dims = 0
            for k, v in model_info.items():
                if k.endswith(".embedding_length"):
                    dims = int(v)
                    break
            digest = self._reported_digest(info)[:12]
            if self._expect_digest and not digest.startswith(
                    self._expect_digest[:12]):
                raise EmbeddingError(
                    f"{self.model}: Ollama reports digest {digest}, "
                    f"manifest pins {self._expect_digest[:12]}\n"
                    "  A model pulled today is not necessarily the model the "
                    "retrieval evidence was gathered against.")
            self._identity = Identity(
                backend="ollama", model=self.model, dimensions=dims,
                normalised=True, digest=digest,
                query_prefix="")
        return self._identity

    def embed(self, texts: list[str], kind: str = "document", batch: int = 16):
        import numpy as np
        if kind not in ("document", "query"):
            raise EmbeddingError(f"unknown embed kind {kind!r}")
        out = []
        for i in range(0, len(texts), batch):
            chunk = texts[i:i + batch]
            req = urllib.request.Request(
                f"{self.host}/api/embed",
                data=json.dumps({"model": self.model, "input": chunk}).encode(),
                headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    payload = json.load(r)
            except urllib.error.HTTPError as e:
                raise EmbeddingError(f"{self.model}: HTTP {e.code} embedding "
                                     f"batch at offset {i}")
            except urllib.error.URLError as e:
                raise EmbeddingError(f"cannot reach Ollama at {self.host}: {e}")
            vectors = payload.get("embeddings")
            if not vectors or len(vectors) != len(chunk):
                raise EmbeddingError(
                    f"{self.model}: asked for {len(chunk)} vectors, got "
                    f"{0 if not vectors else len(vectors)}")
            out.extend(vectors)
        arr = _l2_normalise(out)
        expected = self.identity().dimensions
        if expected and arr.shape[1] != expected:
            raise EmbeddingError(
                f"{self.model}: returned {arr.shape[1]} dimensions, "
                f"identity says {expected}")
        return arr


def _st_dimensions(model) -> int:
    """
    sentence-transformers renamed this between versions; support both rather
    than pin a version, since this backend is the convenience option and the
    pinned artefact lives elsewhere.
    """
    for name in ("get_embedding_dimension", "get_sentence_embedding_dimension"):
        fn = getattr(model, name, None)
        if callable(fn):
            return fn()
    raise EmbeddingError("cannot determine embedding dimension from this "
                         "sentence-transformers model")


class SentenceTransformersEmbedder:
    """
    In-process sentence-transformers. Convenient, and *not* interchangeable
    with the Ollama backend even for the same model name: quantisation and
    packaging differ, so it gets its own backend string and its own identity.
    Whichever one builds an index must also serve queries against it.
    """

    def __init__(self, model: str, revision: str | None = None,
                 device: str | None = None):
        self.model_name = model
        self.revision = revision
        self._device = device
        self._model = None
        self._identity: Identity | None = None

    def _load(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError:
                raise EmbeddingError(
                    "the st: backend needs sentence-transformers "
                    "(pip install sentence-transformers)")
            kwargs = {}
            if self.revision:
                kwargs["revision"] = self.revision
            if self._device:
                kwargs["device"] = self._device
            self._model = SentenceTransformer(self.model_name, **kwargs)
        return self._model

    def identity(self) -> Identity:
        if self._identity is None:
            m = self._load()
            self._identity = Identity(
                backend="sentence-transformers", model=self.model_name,
                dimensions=int(_st_dimensions(m)),
                normalised=True, digest=self.revision or "",
                query_prefix="")
        return self._identity

    def embed(self, texts: list[str], kind: str = "document", batch: int = 16):
        if kind not in ("document", "query"):
            raise EmbeddingError(f"unknown embed kind {kind!r}")
        m = self._load()
        vectors = m.encode(texts, batch_size=batch,
                           normalize_embeddings=True,
                           show_progress_bar=False)
        return _l2_normalise(vectors)


class HttpEmbedder:
    """
    Any service speaking a two-endpoint JSON protocol, for when embedding moves
    somewhere with a GPU:

        GET  {base}/identity  -> {"backend","model","dimensions",
                                  "normalised","digest","query_prefix"}
        POST {base}/embed     <- {"input": [...], "kind": "document"|"query"}
                              -> {"embeddings": [[...], ...]}

    Deliberately small. A service that can be reimplemented in an afternoon is
    one that can be replaced without renegotiating the interface.
    """

    def __init__(self, base: str, token_env: str = "ALEPH_EMBED_TOKEN",
                 timeout: int = 120):
        self.base = base.rstrip("/")
        self.token_env = token_env
        self.timeout = timeout
        self._identity: Identity | None = None

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        token = os.environ.get(self.token_env)
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def identity(self) -> Identity:
        if self._identity is None:
            req = urllib.request.Request(f"{self.base}/identity",
                                         headers=self._headers())
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    self._identity = Identity.from_dict(json.load(r))
            except urllib.error.URLError as e:
                raise EmbeddingError(f"cannot reach {self.base}: {e}")
        return self._identity

    def embed(self, texts: list[str], kind: str = "document", batch: int = 16):
        out = []
        for i in range(0, len(texts), batch):
            body = json.dumps({"input": texts[i:i + batch], "kind": kind})
            req = urllib.request.Request(f"{self.base}/embed",
                                         data=body.encode(),
                                         headers=self._headers())
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    out.extend(json.load(r)["embeddings"])
            except urllib.error.URLError as e:
                raise EmbeddingError(f"cannot reach {self.base}: {e}")
        return _l2_normalise(out)


class StubEmbedder:
    """
    Deterministic hashed vectors. No model, no network, no gigabytes.

    For tests, and for exercising the pipeline end to end where a real model
    cannot run. Its identity says `stub` in the backend, so an index built
    with it announces itself as a test artefact everywhere it appears — the
    one thing worse than not having a real model is having an index that
    cannot be told apart from one built with a real model.
    """

    def __init__(self, name: str = "stub", dimensions: int = 64):
        self.name = name
        self.dimensions = dimensions

    def identity(self) -> Identity:
        return Identity(backend="stub", model=self.name,
                        dimensions=self.dimensions, normalised=True,
                        digest="", query_prefix="")

    def embed(self, texts: list[str], kind: str = "document", batch: int = 16):
        import numpy as np
        rows = []
        for text in texts:
            seed = hashlib.sha256(text.encode("utf-8")).digest()
            # Stretch the digest to the target width, then map each four-byte
            # group into [-1, 1]. Reinterpreting digest bytes as IEEE floats
            # would be shorter and would produce infinities and NaNs, because
            # most bit patterns are not sensible floats.
            raw = b""
            counter = 0
            while len(raw) < self.dimensions * 4:
                raw += hashlib.sha256(seed + struct.pack(">I", counter)).digest()
                counter += 1
            words = struct.unpack(f">{self.dimensions}I",
                                  raw[:self.dimensions * 4])
            rows.append([(w / 0xFFFFFFFF) * 2.0 - 1.0 for w in words])
        return _l2_normalise(np.asarray(rows, dtype="float64"))


# --------------------------------------------------------------------------

def make_embedder(spec: str, **kwargs):
    """
    Build an embedder from a string, so the runtime is configuration rather
    than an import. `ollama:bge-m3`, `st:BAAI/bge-m3`, `stub:test`, or a URL.
    """
    if spec.startswith(("http://", "https://")):
        return HttpEmbedder(spec, **kwargs)
    backend, _, name = spec.partition(":")
    if not name:
        raise EmbeddingError(
            f"embedder spec {spec!r} needs a model, e.g. 'ollama:bge-m3'")
    if backend == "ollama":
        return OllamaEmbedder(name, **kwargs)
    if backend in ("st", "sentence-transformers"):
        return SentenceTransformersEmbedder(name, **kwargs)
    if backend == "stub":
        return StubEmbedder(name, **kwargs)
    raise EmbeddingError(
        f"unknown embedder backend {backend!r} in {spec!r}; "
        "expected ollama, st, stub or a URL")
