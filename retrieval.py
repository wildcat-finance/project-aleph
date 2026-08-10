#!/usr/bin/env python3
"""Scoped hybrid retrieval and byte-verified citation resolution for Aleph."""

from __future__ import annotations

import hashlib
import json
import math
import pathlib
import re
from dataclasses import asdict, dataclass
from urllib.parse import quote

from embed.embedder import Identity, make_embedder
from embed.index import Index, IndexError_
from release import compute_release_id


class RetrievalError(Exception):
    """A request or artifact that cannot safely produce evidence."""


class ScopeError(RetrievalError):
    """The request falls outside the manifest's chain or version policy."""


class CitationError(RetrievalError):
    """Evidence cannot be proven against the named corpus."""


@dataclass(frozen=True)
class RetrievalRequest:
    query: str
    chain_id: int
    protocol_version: str | None = None
    version_explicit: bool = False
    tiers: tuple[str, ...] = ("A", "B")
    limit_per_tier: int = 5

    def validate(self) -> None:
        if not self.query.strip():
            raise ScopeError("retrieval query is empty")
        if not self.tiers or any(tier not in ("A", "B") for tier in self.tiers):
            raise ScopeError("tiers must be a non-empty subset of ('A', 'B')")
        if len(set(self.tiers)) != len(self.tiers):
            raise ScopeError("tiers must not contain duplicates")
        if not 1 <= self.limit_per_tier <= 50:
            raise ScopeError("limit_per_tier must be between 1 and 50")


@dataclass(frozen=True)
class Evidence:
    id: str
    tier: str
    score: float
    semantic_score: float
    semantic_rank: int | None
    lexical_rank: int | None
    lexical_score: float
    kind: str
    source_type: str
    path: str
    line: int
    breadcrumb: str
    display_text: str
    model_text: str
    synthesised: bool
    corpus_build_id: str
    source_ref: str
    protocol_version: str | None
    deployment_status: str | None
    effective_date: str | None
    doc_version: str | None
    detail: dict
    release_id: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RetrievalResponse:
    release_id: str
    chain_id: int
    protocol_version: str
    deployment_status: str
    preamble: str | None
    by_tier: dict[str, tuple[Evidence, ...]]
    mandatory_source_paths: tuple[str, ...]
    always_cite_candidates: tuple[Evidence, ...]
    minimum_semantic_score: float | None


@dataclass(frozen=True)
class Citation:
    evidence_id: str
    label: str
    source_url: str
    source_ref: str
    corpus_build_id: str
    release_id: str
    quote: str | None
    effective_date: str | None
    doc_version: str | None


def _sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _safe_child(root: pathlib.Path, relative: str) -> pathlib.Path:
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        raise RetrievalError(f"artifact path escapes its root: {relative!r}")
    return candidate


class ReleaseArtifact:
    """A loaded release whose corpus, index and manifest hashes agree."""

    def __init__(self, release_json: str, manifest_path: str):
        self.release_path = pathlib.Path(release_json).resolve()
        try:
            self.record = json.loads(self.release_path.read_text())
        except (OSError, json.JSONDecodeError) as error:
            raise RetrievalError(f"cannot load release {self.release_path}: {error}")
        if self.release_path.parent.name != self.record.get("release_id"):
            raise RetrievalError("release directory does not match release_id")
        try:
            computed_release_id = compute_release_id(self.record)
        except (KeyError, TypeError, ValueError) as error:
            raise RetrievalError(f"release identity fields are invalid: {error}")
        if computed_release_id != self.record["release_id"]:
            raise RetrievalError("release record does not match its release_id")
        self.root = self.release_path.parents[2]
        self.manifest_path = pathlib.Path(manifest_path).resolve()
        if _sha256(self.manifest_path) != self.record["manifest"]["sha256"]:
            raise RetrievalError("loaded manifest does not match the release")
        try:
            import yaml
        except ImportError:
            raise RetrievalError("retrieval.py needs pyyaml (pip install pyyaml)")
        self.manifest = yaml.safe_load(self.manifest_path.read_bytes())

        corpus_info = self.record["corpus"]
        index_info = self.record["index"]
        self.corpus_dir = _safe_child(self.root, corpus_info["path"])
        self.index_dir = _safe_child(self.root, index_info["path"])
        checks = (
            (self.corpus_dir / "chunks.jsonl", corpus_info["chunks_sha256"]),
            (self.corpus_dir / "build.json", corpus_info["record_sha256"]),
            (self.index_dir / "index.json", index_info["record_sha256"]),
        )
        for path, expected in checks:
            if not path.is_file() or _sha256(path) != expected:
                raise RetrievalError(f"{path}: release artifact hash mismatch")
        try:
            self.index = Index(str(self.index_dir))
        except IndexError_ as error:
            raise RetrievalError(str(error))
        if self.index.corpus_build_id != corpus_info["build_id"]:
            raise RetrievalError("index and release name different corpus builds")
        release_identity = Identity.from_dict(self.record["embedding"])
        if self.index.identity != release_identity:
            raise RetrievalError("index and release name different embedders")

        self.chunks: dict[str, dict] = {}
        for line in open(self.corpus_dir / "chunks.jsonl"):
            chunk = json.loads(line)
            if chunk["id"] in self.chunks:
                raise RetrievalError(f"duplicate corpus chunk {chunk['id']}")
            self.chunks[chunk["id"]] = chunk
        if len(self.chunks) != self.index.manifest["total_chunks"]:
            raise RetrievalError("corpus and index chunk counts differ")

        self.sources = {source["id"]: source
                        for source in self.manifest.get("sources") or []}
        self.always_cite_paths = tuple(
            path for source in self.manifest.get("sources") or []
            if ((source.get("index") == "separate")
                == (self.record.get("kind") == "prerelease"))
            for path in source.get("always_cite") or [])


_TOKEN = re.compile(
    r"0x[0-9a-fA-F]{40}|[A-Za-z_]\w*\([^()]*\)|[A-Za-z_]\w+|\d+")


def _normalise_term(term: str) -> str:
    return re.sub(r"\s+", "", term).lower()


def _terms(text: str) -> list[str]:
    return [_normalise_term(term) for term in _TOKEN.findall(text)]


def _lexical_scores(rows: list[dict], query: str) -> dict[str, float]:
    query_terms = _terms(query)
    if not query_terms:
        return {}
    documents = [_terms(" ".join(str(row.get(field) or "") for field in
                                 ("id", "breadcrumb", "model_text")))
                 for row in rows]
    average_length = sum(map(len, documents)) / max(1, len(documents))
    document_frequency = {
        term: sum(term in set(document) for document in documents)
        for term in set(query_terms)}
    scores: dict[str, float] = {}
    normalised_query = _normalise_term(query)
    for row, document in zip(rows, documents):
        score = 0.0
        for term in query_terms:
            frequency = document.count(term)
            if not frequency:
                continue
            df = document_frequency[term]
            inverse = math.log(1 + (len(rows) - df + 0.5) / (df + 0.5))
            denominator = frequency + 1.2 * (
                0.25 + 0.75 * len(document) / max(1.0, average_length))
            score += inverse * frequency * 2.2 / denominator
        target = _normalise_term(
            f"{row.get('id', '')} {row.get('breadcrumb', '')}")
        haystack = _normalise_term(
            f"{row.get('id', '')} {row.get('breadcrumb', '')} "
            f"{row.get('model_text', '')}")
        for term in set(query_terms):
            if term.startswith("0x") and len(term) == 42 and term in haystack:
                score += 20.0
            elif "(" in term and term in target:
                score += 14.0
            elif re.match(r"^[a-z_]\w+$", term) and term in target:
                score += 2.0
        if len(normalised_query) >= 4 and normalised_query in _normalise_term(
                f"{row.get('breadcrumb', '')} {row.get('model_text', '')}"):
            score += 5.0
        if score > 0:
            scores[row["id"]] = score
    return scores


def _select_fused_candidates(fused: list[tuple], limit: int) -> list[tuple]:
    """Keep hybrid ordering without discarding the semantic winner.

    Lexical fusion is valuable for signatures and addresses, but a noisy term
    match can otherwise fill every limited result slot before the strongest
    semantic result reaches the answer boundary. Reserve one slot per tier for
    that winner and use fused order for the rest.
    """
    selected = list(fused[:limit])
    semantic = sorted((item for item in fused if item[2] is not None),
                      key=lambda item: (item[2], item[1]))
    # Keep the fused winner and reserve at most two of the remaining slots for
    # semantic winners. A five-result answer context therefore remains mostly
    # hybrid while retaining enough semantic coverage for multi-part evidence.
    semantic = semantic[:min(2, max(0, limit - 1))]
    for winner in semantic:
        if winner in selected:
            continue
        replaceable = next(
            (item for item in reversed(selected)
             if item != fused[0] and item not in semantic), None)
        if replaceable is None:
            break
        selected.remove(replaceable)
        selected.append(winner)
    selected.sort(key=lambda item: (-item[0], item[1]))
    return selected


class Retriever:
    """Manifest-scoped hybrid search over main and optional prerelease releases."""

    def __init__(self, manifest_path: str, main_release: str,
                 embedder_spec: str,
                 prerelease_release: str | None = None,
                 prerelease_embedder_spec: str | None = None):
        self.main = ReleaseArtifact(main_release, manifest_path)
        self.prerelease = (ReleaseArtifact(prerelease_release, manifest_path)
                           if prerelease_release else None)
        self.embedders = {
            "v2.0": make_embedder(embedder_spec),
            "v2.5": make_embedder(prerelease_embedder_spec or embedder_spec),
        }
        scope = (self.main.manifest.get("policy") or {}).get("scope") or {}
        self.chains = tuple(scope.get("chains") or [])

    def _select(self, request: RetrievalRequest) -> tuple[ReleaseArtifact, str]:
        if request.chain_id not in self.chains:
            raise ScopeError(
                f"chain {request.chain_id} is outside this release; "
                f"supported chains: {list(self.chains)}")
        version = request.protocol_version or "v2.0"
        if version == "v2.0":
            return self.main, version
        if version == "v2.5":
            if not request.version_explicit:
                raise ScopeError("v2.5 retrieval requires an explicit user request")
            if self.prerelease is None:
                raise ScopeError("no isolated v2.5 release is loaded")
            return self.prerelease, version
        raise ScopeError(f"unsupported public protocol version {version!r}")

    @staticmethod
    def _eligible(row: dict, version: str) -> bool:
        row_version = row.get("protocol_version")
        if row.get("tier") == "A":
            return row_version == version
        return row_version in (None, version)

    @staticmethod
    def _minimum_semantic_score(artifact: ReleaseArtifact) -> float | None:
        """Return an evaluation-calibrated floor for the pinned real model.

        A rank always has a winner, even for an unrelated question. The raw
        cosine score is what lets the answer boundary distinguish a winner
        from evidence that is actually close enough to quote. Stub indexes do
        not use a production floor because their vectors are deliberately
        meaningless and exist only to exercise the machinery.
        """
        identity = artifact.record.get("embedding") or {}
        if (identity.get("backend") == "ollama"
                and identity.get("model") == "bge-m3"
                and identity.get("dimensions") == 1024
                and identity.get("normalised") is True):
            return 0.48
        return None

    def search(self, request: RetrievalRequest) -> RetrievalResponse:
        request.validate()
        artifact, version = self._select(request)
        embedder = self.embedders[version]
        vector = embedder.embed([request.query], kind="query")[0]
        identity = embedder.identity()
        results: dict[str, tuple[Evidence, ...]] = {}

        for tier in request.tiers:
            rows = [row for row in artifact.index.meta.get(tier, [])
                    if self._eligible(row, version)]
            if not rows:
                results[tier] = ()
                continue
            try:
                semantic_hits = artifact.index.search(
                    vector, identity, tier=tier,
                    k=len(artifact.index.meta[tier]))
            except IndexError_ as error:
                raise RetrievalError(
                    f"semantic index search failed: {error}") from error
            semantic_hits = [hit for hit in semantic_hits
                             if self._eligible(hit, version)]
            semantic_rank = {hit["id"]: rank for rank, hit in
                             enumerate(semantic_hits, 1)}
            semantic_scores = {hit["id"]: float(hit["score"])
                               for hit in semantic_hits}
            lexical_scores = _lexical_scores(rows, request.query)
            lexical_order = sorted(lexical_scores,
                                   key=lambda key: (-lexical_scores[key], key))
            lexical_rank = {key: rank for rank, key in enumerate(lexical_order, 1)}
            max_lexical = max(lexical_scores.values(), default=0.0)
            by_id = {row["id"]: row for row in rows}
            candidates = set(semantic_rank) | set(lexical_rank)
            fused = []
            for chunk_id in candidates:
                srank = semantic_rank.get(chunk_id)
                lrank = lexical_rank.get(chunk_id)
                lexical = lexical_scores.get(chunk_id, 0.0)
                score = ((1.0 / (60 + srank)) if srank else 0.0)
                score += ((1.25 / (60 + lrank)) if lrank else 0.0)
                if max_lexical:
                    score += 0.05 * lexical / max_lexical
                fused.append((score, chunk_id, srank, lrank, lexical))
            fused.sort(key=lambda item: (-item[0], item[1]))
            selected = _select_fused_candidates(
                fused, request.limit_per_tier)
            results[tier] = tuple(
                self._evidence(artifact, by_id[chunk_id], score,
                               semantic_scores.get(chunk_id, 0.0),
                               srank, lrank, lexical)
                for score, chunk_id, srank, lrank, lexical
                in selected)

        all_returned = [item for tier in results.values() for item in tier]
        required = []
        for path in artifact.always_cite_paths:
            matching = [item for item in all_returned if item.path == path]
            if matching:
                required.append(matching[0])
                continue
            rows = [row for rows in artifact.index.meta.values() for row in rows
                    if row.get("path") == path and self._eligible(row, version)]
            scores = _lexical_scores(rows, request.query)
            if rows:
                best = max(rows, key=lambda row: (scores.get(row["id"], 0.0),
                                                  row["id"]))
                required.append(self._evidence(
                    artifact, best, 0.0, 0.0, None, None,
                    scores.get(best["id"], 0.0)))

        prerelease = artifact.record.get("kind") == "prerelease"
        preamble = ("v2.5 is an unaudited prerelease and is not deployed on "
                    "Ethereum mainnet." if prerelease else None)
        return RetrievalResponse(
            release_id=artifact.record["release_id"], chain_id=request.chain_id,
            protocol_version=version,
            deployment_status="not_deployed" if prerelease else "deployed",
            preamble=preamble, by_tier=results,
            mandatory_source_paths=artifact.always_cite_paths,
            always_cite_candidates=tuple(required),
            minimum_semantic_score=self._minimum_semantic_score(artifact))

    @staticmethod
    def _evidence(artifact: ReleaseArtifact, row: dict, score: float,
                  semantic_score: float,
                  semantic_rank: int | None, lexical_rank: int | None,
                  lexical_score: float) -> Evidence:
        return Evidence(
            id=row["id"], tier=row["tier"], score=score,
            semantic_score=semantic_score,
            semantic_rank=semantic_rank, lexical_rank=lexical_rank,
            lexical_score=lexical_score, kind=row["kind"],
            source_type=row["source_type"], path=row["path"],
            line=int(row.get("line") or 0), breadcrumb=row["breadcrumb"],
            display_text=row["display_text"], model_text=row["model_text"],
            synthesised=bool(row["synthesised"]),
            corpus_build_id=row["corpus_build_id"],
            source_ref=row["source_ref"],
            protocol_version=row.get("protocol_version"),
            deployment_status=row.get("deployment_status"),
            effective_date=row.get("effective_date"),
            doc_version=row.get("doc_version"), detail=row.get("detail") or {},
            release_id=artifact.record["release_id"])

    def citation_resolver(self, protocol_version: str = "v2.0"):
        artifact = self.prerelease if protocol_version == "v2.5" else self.main
        if artifact is None:
            raise ScopeError(f"no {protocol_version} release is loaded")
        return CitationResolver(artifact)


class CitationResolver:
    """Prove evidence against corpus bytes and emit a stable source location."""

    def __init__(self, artifact: ReleaseArtifact):
        self.artifact = artifact

    def resolve(self, evidence: Evidence, include_quote: bool = True) -> Citation:
        if evidence.release_id != self.artifact.record["release_id"]:
            raise CitationError("evidence belongs to a different release")
        original = self.artifact.chunks.get(evidence.id)
        if original is None:
            raise CitationError(f"{evidence.id}: absent from the named corpus")
        fields = ("display_text", "model_text", "path", "line", "breadcrumb",
                  "source_ref", "corpus_build_id", "synthesised")
        for field in fields:
            if getattr(evidence, field) != original.get(field):
                raise CitationError(
                    f"{evidence.id}: indexed {field} differs from corpus bytes")
        if evidence.corpus_build_id != self.artifact.record["corpus"]["build_id"]:
            raise CitationError("evidence names a different corpus build")
        if include_quote and evidence.synthesised:
            raise CitationError(
                f"{evidence.id}: synthesised retrieval aids cannot be quoted")

        source_id = evidence.id.split(":", 1)[0]
        source = self.artifact.sources.get(source_id)
        resolution = (self.artifact.record.get("sources") or {}).get(source_id)
        if not source or not resolution or not resolution.get("commit"):
            raise CitationError(f"{evidence.id}: source repository is unresolved")
        url = (f"https://github.com/{source['repo']}/blob/"
               f"{resolution['commit']}/{quote(evidence.path, safe='/')}")
        if evidence.source_type == "markdown" and evidence.detail.get("anchor"):
            url += "#" + quote(str(evidence.detail["anchor"]), safe="-_")
        elif evidence.line:
            url += f"#L{evidence.line}"
        return Citation(
            evidence_id=evidence.id, label=evidence.breadcrumb, source_url=url,
            source_ref=evidence.source_ref,
            corpus_build_id=evidence.corpus_build_id,
            release_id=evidence.release_id,
            quote=evidence.display_text if include_quote else None,
            effective_date=evidence.effective_date,
            doc_version=evidence.doc_version)
