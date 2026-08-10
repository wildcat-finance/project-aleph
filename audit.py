#!/usr/bin/env python3
"""Scrubbed, append-only answer audit records for the Aleph query service."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import pathlib
import threading
import uuid
from datetime import datetime, timedelta, timezone


class AuditError(Exception):
    """The audit boundary cannot safely record or retain an event."""


class AuditLogger:
    def __init__(self, directory: str, active_release: dict,
                 hmac_key: str | bytes | None = None,
                 retention_days: int = 30, clock=None):
        key = hmac_key if hmac_key is not None else os.environ.get(
            "ALEPH_AUDIT_HMAC_KEY", "")
        key = key.encode() if isinstance(key, str) else key
        if not isinstance(key, bytes) or len(key) < 32:
            raise AuditError("ALEPH_AUDIT_HMAC_KEY must contain at least 32 bytes")
        if not 1 <= retention_days <= 365:
            raise AuditError("audit retention must be between 1 and 365 days")
        self.directory = pathlib.Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.key = key
        self.retention_days = retention_days
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.release_id = active_release["release_id"]
        self.corpus_build_id = active_release["corpus"]["build_id"]
        self.embedding = active_release["embedding"]
        self.lock = threading.Lock()

    def _fingerprint(self, question: str) -> str:
        normalized = " ".join(question.split()).casefold().encode()
        return hmac.new(self.key, normalized, hashlib.sha256).hexdigest()

    def answer_record(self, question: str, answer) -> dict:
        route = answer.route
        return {
            "schema_version": 1,
            "timestamp": self.clock().isoformat(timespec="seconds"),
            "request_id": uuid.uuid4().hex,
            "question": {
                "hmac_sha256": self._fingerprint(question),
                "characters": len(question),
            },
            "active_release_id": self.release_id,
            "corpus_build_id": self.corpus_build_id,
            "embedding": self.embedding,
            "status": answer.status,
            "route": {
                "mode": answer.mode.value,
                "reason": route.reason,
                "chain_id": route.entities.chain_id,
                "protocol_version": route.entities.protocol_version,
                "version_explicit": route.entities.version_explicit,
                "live_operation": route.live_operation,
                "destination": route.destination,
            },
            "citations": [{
                "evidence_id": citation.evidence_id,
                "release_id": citation.release_id,
                "corpus_build_id": citation.corpus_build_id,
                "source_url": citation.source_url,
            } for citation in answer.citations],
            "live": ({
                "operation": answer.live.operation,
                "chain_id": answer.live.chain_id,
                "gateway_release": answer.live.gateway_release,
                "block_number": answer.live.block_number,
            } if answer.live else None),
            "refusal_reason": answer.refusal_reason,
            "triage_kind": answer.triage.kind if answer.triage else None,
        }

    def error_record(self, question: str) -> dict:
        return {
            "schema_version": 1,
            "timestamp": self.clock().isoformat(timespec="seconds"),
            "request_id": uuid.uuid4().hex,
            "question": {"hmac_sha256": self._fingerprint(question),
                         "characters": len(question)},
            "active_release_id": self.release_id,
            "corpus_build_id": self.corpus_build_id,
            "embedding": self.embedding,
            "status": "internal_error",
        }

    def write(self, record: dict) -> pathlib.Path:
        timestamp = record.get("timestamp")
        try:
            day = datetime.fromisoformat(timestamp).astimezone(timezone.utc).date()
        except (TypeError, ValueError):
            raise AuditError("audit record has no valid timestamp")
        path = self.directory / f"audit-{day.isoformat()}.jsonl"
        payload = json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
        with self.lock:
            descriptor = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
            try:
                remaining = memoryview(payload.encode())
                while remaining:
                    written = os.write(descriptor, remaining)
                    if written <= 0:
                        raise AuditError("audit append made no progress")
                    remaining = remaining[written:]
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        return path

    def purge_expired(self) -> tuple[pathlib.Path, ...]:
        cutoff = self.clock().date() - timedelta(days=self.retention_days)
        removed = []
        with self.lock:
            for path in sorted(self.directory.glob("audit-????-??-??.jsonl")):
                try:
                    day = datetime.strptime(path.stem[6:], "%Y-%m-%d").date()
                except ValueError:
                    continue
                if day < cutoff:
                    path.unlink()
                    removed.append(path)
        return tuple(removed)


class AuditedEngine:
    """Log typed metadata while never logging raw question or answer text."""

    def __init__(self, engine, logger: AuditLogger):
        self.engine = engine
        self.logger = logger

    def answer(self, question: str):
        try:
            answer = self.engine.answer(question)
        except Exception:
            self.logger.write(self.logger.error_record(question))
            raise
        self.logger.write(self.logger.answer_record(question, answer))
        return answer
