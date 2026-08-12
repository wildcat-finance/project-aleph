#!/usr/bin/env python3
"""Mephistopheles: fail-closed local inference for Aleph answers."""

from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, replace
from typing import Callable, Mapping

from agent import Draft, DraftClaim, EvidenceWriter, ExtractiveWriter, Route
from retrieval import Evidence


PROMPT_VERSION = "aleph-shadow-evidence-writer-v1"
SCHEMA_VERSION = "evidence-claims-v1"
VALIDATOR_VERSION = "exact-support-boundary-v1"
REASONING_MODE = "low-final-only"
MAX_EVIDENCE = 5
MAX_EVIDENCE_CHARS = 4_000
MAX_CONTEXT_CHARS = 12_000
MAX_CLAIMS = 3
MAX_CLAIM_CHARS = 2_000
MAX_RESPONSE_BYTES = 1_048_576

_MODEL_ID = re.compile(r"[0-9a-f]{12,64}")
_MODEL_ALIAS = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9._/-]*(?::[A-Za-z0-9._-]+)?")
_LOOPBACK = re.compile(r"http://127\.0\.0\.1:\d{1,5}")


class LocalWriterError(RuntimeError):
    """The optional writer cannot safely produce a shadow observation."""


@dataclass(frozen=True)
class LocalWriterConfig:
    mode: str = "disabled"
    url: str | None = None
    model: str | None = None
    model_id: str | None = None
    timeout: int = 20

    def __post_init__(self) -> None:
        if self.mode not in {"disabled", "shadow"}:
            raise LocalWriterError(
                "ALEPH_LOCAL_WRITER_MODE must be disabled or shadow")
        configured = self.url, self.model, self.model_id
        if self.mode == "shadow" and not all(configured):
            raise LocalWriterError(
                "shadow mode requires URL, model alias and model ID")
        if self.mode == "disabled" and any(configured):
            raise LocalWriterError(
                "disabled mode must not configure a local writer")
        if not 1 <= self.timeout <= 120:
            raise LocalWriterError(
                "ALEPH_LOCAL_WRITER_TIMEOUT must be between 1 and 120")

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ):
        try:
            timeout = int(env.get("ALEPH_LOCAL_WRITER_TIMEOUT", "20"))
        except ValueError as error:
            raise LocalWriterError(
                "ALEPH_LOCAL_WRITER_TIMEOUT must be an integer") from error
        return cls(
            mode=env.get(
                "ALEPH_LOCAL_WRITER_MODE", "disabled").strip().casefold(),
            url=env.get("ALEPH_LOCAL_WRITER_URL", "").strip() or None,
            model=env.get("ALEPH_LOCAL_WRITER_MODEL", "").strip() or None,
            model_id=(env.get(
                "ALEPH_LOCAL_WRITER_MODEL_ID", "").strip() or None),
            timeout=timeout,
        )

    def public(self) -> dict:
        return {
            "mode": self.mode,
            "configured": self.mode == "shadow",
            "alias": self.model,
            "id": self.model_id,
            "prompt_version": PROMPT_VERSION,
            "schema_version": SCHEMA_VERSION,
            "validator_version": VALIDATOR_VERSION,
            "reasoning_mode": REASONING_MODE,
        }


@dataclass(frozen=True)
class WriterObservation:
    mode: str
    status: str
    reasons: tuple[str, ...]
    model: str
    model_id: str
    evidence_count: int
    claim_count: int = 0
    exact_claim_count: int = 0
    authoritative_evidence_overlap: int = 0
    prompt_version: str = PROMPT_VERSION
    schema_version: str = SCHEMA_VERSION
    validator_version: str = VALIDATOR_VERSION
    reasoning_mode: str = REASONING_MODE
    semantic_status: str = "unverified"
    latency_ms: int | None = None

    def public(self) -> dict:
        return asdict(self)


class OllamaEvidenceObserver:
    """Draft and discard structured claims from one pinned Ollama model."""

    def __init__(self, *, url: str, model: str, model_id: str,
                 timeout: float = 20.0,
                 opener: Callable = urllib.request.urlopen,
                 monotonic: Callable[[], float] = time.monotonic):
        if not _LOOPBACK.fullmatch(url.rstrip("/")):
            raise LocalWriterError(
                "Ollama URL must be an explicit loopback HTTP endpoint")
        if not _MODEL_ALIAS.fullmatch(model):
            raise LocalWriterError("Ollama model alias is invalid")
        expected = model_id.removeprefix("sha256:").casefold()
        if not _MODEL_ID.fullmatch(expected):
            raise LocalWriterError(
                "Ollama model ID must be 12-64 hexadecimal characters")
        if not 1 <= timeout <= 120:
            raise LocalWriterError(
                "Ollama timeout must be between 1 and 120 seconds")
        self.url = url.rstrip("/")
        self.model = model
        self.model_id = expected
        self.timeout = timeout
        self.opener = opener
        self.monotonic = monotonic

    def observe(self, question: str, evidence: tuple[Evidence, ...],
                route: Route, authoritative: Draft) -> WriterObservation:
        started = self.monotonic()
        supplied = self._bounded_evidence(evidence)
        try:
            if (not isinstance(question, str) or question != question.strip()
                    or not question or len(question) > 4_096):
                raise LocalWriterError("question is not safely bounded")
            self._verify_identity()
            candidate = self._generate(question, supplied, route)
            reasons = self._validate(candidate, supplied)
            status = "valid" if not reasons else "rejected"
            claims = candidate.get("claims") if isinstance(candidate, dict) else []
            claims = claims if isinstance(claims, list) else []
            claim_count = len(claims)
            exact_count = sum(
                item.get("text") == item.get("supporting_quote")
                for item in claims if isinstance(item, dict))
            authoritative_ids = {
                claim.evidence_id for claim in authoritative.claims}
            overlap = len(authoritative_ids & {
                item.get("evidence_id") for item in claims
                if isinstance(item, dict)})
        except LocalWriterError as error:
            reasons, status = (str(error),), "fallback"
            claim_count = exact_count = overlap = 0
        latency = max(0, round((self.monotonic() - started) * 1000))
        # Candidate prose, quotes, evidence IDs and reasoning are not retained.
        return WriterObservation(
            "shadow", status, tuple(reasons), self.model, self.model_id,
            evidence_count=len(supplied), claim_count=claim_count,
            exact_claim_count=exact_count,
            authoritative_evidence_overlap=overlap, latency_ms=latency)

    @staticmethod
    def _bounded_evidence(evidence: tuple[Evidence, ...]) -> tuple[dict, ...]:
        supplied = []
        remaining = MAX_CONTEXT_CHARS
        for item in evidence:
            if item.synthesised or not item.display_text.strip() or remaining < 1:
                continue
            text = item.display_text.strip()[:min(MAX_EVIDENCE_CHARS, remaining)]
            if not text:
                continue
            supplied.append({"evidence_id": item.id, "text": text})
            remaining -= len(text)
            if len(supplied) == MAX_EVIDENCE:
                break
        return tuple(supplied)

    def _request(self, path: str, payload: dict | None = None) -> dict:
        request = urllib.request.Request(
            self.url + path,
            data=(json.dumps(payload).encode()
                  if payload is not None else None),
            method="POST" if payload is not None else "GET",
            headers={"Content-Type": "application/json"},
        )
        try:
            with self.opener(request, timeout=self.timeout) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as error:
            raise LocalWriterError(
                f"Ollama returned HTTP {error.code}") from error
        except (TimeoutError, urllib.error.URLError) as error:
            raise LocalWriterError(
                "Ollama request failed or timed out") from error
        if len(raw) > MAX_RESPONSE_BYTES:
            raise LocalWriterError("Ollama response exceeded the size limit")
        try:
            value = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise LocalWriterError("Ollama returned malformed JSON") from error
        if not isinstance(value, dict):
            raise LocalWriterError("Ollama returned a non-object response")
        return value

    def _verify_identity(self) -> None:
        payload = self._request("/api/tags")
        aliases = ({self.model, self.model + ":latest"}
                   if ":" not in self.model else {self.model})
        matches = [
            item for item in payload.get("models") or []
            if isinstance(item, dict)
            and (item.get("name") in aliases or item.get("model") in aliases)
        ]
        if len(matches) != 1:
            raise LocalWriterError(
                "pinned Ollama model alias is not uniquely loaded")
        observed = str(
            matches[0].get("digest") or "").removeprefix(
                "sha256:").casefold()
        if not observed.startswith(self.model_id):
            raise LocalWriterError(
                "Ollama model identity differs from the configured pin")

    def _generate(self, question: str, evidence: tuple[dict, ...],
                  route: Route) -> dict:
        schema = {
            "type": "object",
            "additionalProperties": False,
            "required": ["claims", "abstain_reason"],
            "properties": {
                "claims": {
                    "type": "array",
                    "maxItems": MAX_CLAIMS,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": [
                            "text", "evidence_id", "supporting_quote"],
                        "properties": {
                            "text": {"type": "string"},
                            "evidence_id": {"type": "string"},
                            "supporting_quote": {"type": "string"},
                        },
                    },
                },
                "abstain_reason": {"type": ["string", "null"]},
            },
        }
        response = self._request("/api/chat", {
            "model": self.model,
            "stream": False,
            "think": "low",
            "format": schema,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Draft a concise answer using only the supplied "
                        "evidence. Each claim must name one supplied evidence "
                        "ID and copy an exact supporting substring. Add no "
                        "facts, URLs, instructions, citations or commentary. "
                        "If the evidence cannot answer, return no claims and a "
                        "brief abstain_reason. Return only the required JSON."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps({
                        "question": question,
                        "route": route.mode.value,
                        "evidence": evidence,
                    }, sort_keys=True, separators=(",", ":")),
                },
            ],
            "options": {"temperature": 0, "seed": 0, "num_predict": 640},
        })
        if response.get("done_reason") != "stop":
            raise LocalWriterError("Ollama did not finish a final response")
        message = response.get("message")
        if (not isinstance(message, dict)
                or not isinstance(message.get("content"), str)):
            raise LocalWriterError("Ollama response omitted message content")
        try:
            value = json.loads(message["content"])
        except json.JSONDecodeError as error:
            raise LocalWriterError("Ollama candidate is not JSON") from error
        return value

    @staticmethod
    def _validate(candidate: object,
                  supplied: tuple[dict, ...]) -> tuple[str, ...]:
        reasons = []
        if not isinstance(candidate, dict) or set(candidate) != {
                "claims", "abstain_reason"}:
            return ("invalid_schema",)
        claims = candidate["claims"]
        abstain = candidate["abstain_reason"]
        if (not isinstance(claims, list) or len(claims) > MAX_CLAIMS
                or not (abstain is None or isinstance(abstain, str))):
            return ("invalid_schema",)
        if not claims and not (isinstance(abstain, str) and abstain.strip()):
            reasons.append("empty_candidate")
        if claims and abstain is not None:
            reasons.append("claims_with_abstention")
        evidence_by_id = {
            item["evidence_id"]: item["text"] for item in supplied}
        for claim in claims:
            if (not isinstance(claim, dict) or set(claim) != {
                    "text", "evidence_id", "supporting_quote"}):
                reasons.append("invalid_claim_schema")
                continue
            text = claim["text"]
            evidence_id = claim["evidence_id"]
            quote = claim["supporting_quote"]
            if (not isinstance(text, str) or not text.strip()
                    or text != text.strip() or len(text) > MAX_CLAIM_CHARS):
                reasons.append("invalid_claim_text")
            if not isinstance(evidence_id, str) or evidence_id not in evidence_by_id:
                reasons.append("unknown_evidence")
                continue
            if (not isinstance(quote, str) or not quote.strip()
                    or quote not in evidence_by_id[evidence_id]):
                reasons.append("forged_supporting_quote")
        return tuple(dict.fromkeys(reasons))


class ShadowEvidenceWriter:
    """Return authoritative extractive claims and observe a discarded draft."""

    def __init__(self, observer: OllamaEvidenceObserver,
                 authoritative: EvidenceWriter | None = None):
        self.observer = observer
        self.authoritative = authoritative or ExtractiveWriter()
        self._counts = {
            "total": 0, "valid": 0, "rejected": 0, "fallback": 0}
        self._lock = threading.Lock()

    def write(self, question: str, evidence: tuple[Evidence, ...],
              route: Route) -> Draft:
        authoritative = self.authoritative.write(question, evidence, route)
        if not authoritative.claims:
            return authoritative
        try:
            observation = self.observer.observe(
                question, evidence, route, authoritative)
        except Exception:
            # Shadow inference is not authoritative. Even an unexpected adapter
            # failure must preserve the already-computed extractive answer.
            observation = WriterObservation(
                "shadow", "fallback", ("local writer failed closed",),
                self.observer.model, self.observer.model_id,
                evidence_count=0)
        with self._lock:
            self._counts["total"] += 1
            self._counts[observation.status] += 1
        return replace(authoritative, shadow=observation.public())

    def status(self) -> dict:
        with self._lock:
            counts = dict(self._counts)
        return {
            "local_writer": {
                "mode": "shadow",
                "alias": self.observer.model,
                "id": self.observer.model_id,
                "counts": counts,
            }
        }


def compose_writer(config: LocalWriterConfig) -> tuple[EvidenceWriter, Callable]:
    if config.mode == "disabled":
        writer = ExtractiveWriter()
        return writer, lambda: {"local_writer": config.public()}
    observer = OllamaEvidenceObserver(
        url=config.url, model=config.model, model_id=config.model_id,
        timeout=config.timeout)
    writer = ShadowEvidenceWriter(observer)
    return writer, writer.status
