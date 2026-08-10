#!/usr/bin/env python3
"""Atomically activate and roll back fully verified Aleph release artifacts."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import pathlib
import re
import shutil
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone

import release
from eval.product_eval import compute_evaluation_id
from retrieval import ReleaseArtifact, RetrievalError


class ActivationError(Exception):
    """A release cannot safely become or remain active."""


def _canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path: pathlib.Path, label: str) -> dict:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ActivationError(f"cannot load {label} {path}: {error}")
    if not isinstance(value, dict):
        raise ActivationError(f"{label} {path} is not an object")
    return value


def _manifest_gates(path: pathlib.Path) -> list[str]:
    try:
        import yaml
        manifest = yaml.safe_load(path.read_bytes())
    except (ImportError, OSError, ValueError) as error:
        raise ActivationError(f"cannot load manifest policy: {error}")
    policy = manifest.get("gates") or []
    return list(policy) if isinstance(policy, list) else list(policy.keys())


def verify_promotable(path: pathlib.Path, root: pathlib.Path,
                      manifest_override: pathlib.Path | None = None) -> dict:
    path = path.resolve()
    root = root.resolve()
    try:
        path.relative_to(root / "releases")
    except ValueError:
        raise ActivationError("release is outside the artifact release store")
    record = _json(path, "release")
    manifest_path = (manifest_override.resolve() if manifest_override else
                     pathlib.Path(record.get("manifest", {}).get("path", "")))
    if not manifest_path.is_file() or _sha256(manifest_path) != record.get(
            "manifest", {}).get("sha256"):
        raise ActivationError("release manifest is absent or changed")
    try:
        ReleaseArtifact(str(path), str(manifest_path))
    except RetrievalError as error:
        raise ActivationError(f"release artifacts do not verify: {error}")
    required = _manifest_gates(manifest_path)
    if not required or record.get("required_gates") != required:
        raise ActivationError("release required gates differ from manifest policy")
    failed = {name: record.get("gates", {}).get(name) for name in required
              if record.get("gates", {}).get(name) is not True}
    if failed or record.get("promotable") is not True:
        detail = ", ".join(f"{key}={value}" for key, value in failed.items())
        raise ActivationError("release is not promotable"
                              + (f": {detail}" if detail else ""))
    if record.get("kind") != "main":
        raise ActivationError("a prerelease cannot become the active main release")
    evaluation_info = record.get("evaluation") or {}
    evaluation_path = (root / evaluation_info.get("path", "")).resolve()
    try:
        evaluation_path.relative_to(root / "evaluations")
    except ValueError:
        raise ActivationError("release evaluation escapes the evaluation store")
    if (not evaluation_path.is_file()
            or _sha256(evaluation_path) != evaluation_info.get("sha256")):
        raise ActivationError("release evaluation is absent or changed")
    evaluation = _json(evaluation_path, "evaluation")
    evaluation_gates = evaluation.get("report", {}).get("gates") or {}
    if (evaluation.get("evaluation_id") != evaluation_info.get("evaluation_id")
            or compute_evaluation_id(evaluation) != evaluation.get("evaluation_id")
            or evaluation.get("report", {}).get("passed") is not True
            or not evaluation_gates
            or not all(value is True for value in evaluation_gates.values())):
        raise ActivationError("release evaluation identity or gates do not verify")
    return record


def compute_activation_id(record: dict) -> str:
    basis = {key: value for key, value in record.items()
             if key not in ("activation_id", "created")}
    return hashlib.sha256(_canonical(basis)).hexdigest()[:20]


class ActivationStore:
    def __init__(self, artifact_root: str = "artifacts",
                 pointer_path: str = "state/active-release.json",
                 manifest_path: str | None = None):
        self.root = pathlib.Path(artifact_root).resolve()
        self.pointer = pathlib.Path(pointer_path).resolve()
        self.manifest = (pathlib.Path(manifest_path).resolve()
                         if manifest_path else None)
        self.lock_path = self.pointer.with_suffix(self.pointer.suffix + ".lock")

    @contextmanager
    def _lock(self):
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.lock_path, "a+") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            yield

    def _release_path(self, release_id: str) -> pathlib.Path:
        if not isinstance(release_id, str) or not re.fullmatch(
                r"[0-9a-f]{20}", release_id):
            raise ActivationError("release_id is invalid")
        return self.root / "releases" / release_id / "release.json"

    def load_pointer(self) -> dict | None:
        if not self.pointer.exists():
            return None
        pointer = _json(self.pointer, "active pointer")
        activation_path = (self.root / pointer.get("activation_path", "")).resolve()
        try:
            activation_path.relative_to(self.root / "activations")
        except ValueError:
            raise ActivationError("active pointer escapes the activation store")
        if (not activation_path.is_file()
                or _sha256(activation_path) != pointer.get("activation_sha256")):
            raise ActivationError("active pointer names an absent or changed record")
        activation = _json(activation_path, "activation")
        if (activation.get("activation_id") != pointer.get("activation_id")
                or compute_activation_id(activation) != activation.get("activation_id")
                or activation.get("release_id") != pointer.get("release_id")
                or activation.get("generation") != pointer.get("generation")):
            raise ActivationError("active pointer and activation record disagree")
        return pointer

    def load_active(self) -> tuple[pathlib.Path, dict, dict]:
        pointer = self.load_pointer()
        if pointer is None:
            raise ActivationError("no Aleph release is active")
        path = self._release_path(pointer["release_id"])
        return path, verify_promotable(path, self.root, self.manifest), pointer

    def activate(self, release_id: str, actor: str, reason: str,
                 expected_active: str | None = None,
                 kind: str = "promotion") -> dict:
        if not actor.strip() or not reason.strip():
            raise ActivationError("activation requires a non-empty actor and reason")
        if len(actor) > 200 or len(reason) > 1000:
            raise ActivationError("activation actor or reason is too long")
        if kind not in ("promotion", "rollback"):
            raise ActivationError("activation kind must be promotion or rollback")
        with self._lock():
            current = self.load_pointer()
            current_id = current.get("release_id") if current else None
            if expected_active is not None and current_id != expected_active:
                raise ActivationError(
                    f"active release changed: expected {expected_active}, got {current_id}")
            if current_id == release_id:
                raise ActivationError(f"release {release_id} is already active")
            release_path = self._release_path(release_id)
            record = verify_promotable(release_path, self.root, self.manifest)
            generation = (int(current["generation"]) + 1) if current else 1
            activation = {
                "activation_id": "",
                "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "generation": generation, "kind": kind,
                "release_id": release_id,
                "release_sha256": _sha256(release_path),
                "evaluation_id": record["evaluation"]["evaluation_id"],
                "previous_release_id": current_id,
                "actor": actor.strip(), "reason": reason.strip(),
            }
            activation["activation_id"] = compute_activation_id(activation)
            activation_path = self._publish_activation(activation)
            pointer = {
                "schema_version": 1,
                "activation_id": activation["activation_id"],
                "activation_path": str(activation_path.relative_to(self.root)),
                "activation_sha256": _sha256(activation_path),
                "release_id": release_id, "generation": generation,
                "updated": activation["created"],
            }
            self._write_pointer(pointer)
            return pointer

    def rollback(self, actor: str, reason: str,
                 to_release_id: str | None = None) -> dict:
        current = self.load_pointer()
        if current is None:
            raise ActivationError("cannot roll back without an active release")
        activation_path = self.root / current["activation_path"]
        activation = _json(activation_path, "activation")
        target = to_release_id or activation.get("previous_release_id")
        if not target:
            raise ActivationError("the active release has no previous release")
        return self.activate(target, actor, reason,
                             expected_active=current["release_id"],
                             kind="rollback")

    def _publish_activation(self, record: dict) -> pathlib.Path:
        root = self.root / "activations"
        root.mkdir(parents=True, exist_ok=True)
        out_dir = root / record["activation_id"]
        out_path = out_dir / "activation.json"
        if out_dir.exists():
            if not out_path.is_file():
                raise ActivationError("immutable activation is incomplete or changed")
            existing = _json(out_path, "activation")
            without_created = lambda value: {
                key: item for key, item in value.items() if key != "created"}
            if without_created(existing) != without_created(record):
                raise ActivationError("immutable activation is incomplete or changed")
            return out_path
        temporary = pathlib.Path(tempfile.mkdtemp(
            prefix=f".{record['activation_id']}.", dir=root))
        try:
            (temporary / "activation.json").write_text(
                json.dumps(record, indent=2) + "\n")
            os.replace(temporary, out_dir)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
        return out_path

    def _write_pointer(self, pointer: dict) -> None:
        self.pointer.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{self.pointer.name}.", dir=self.pointer.parent)
        try:
            with os.fdopen(descriptor, "w") as handle:
                json.dump(pointer, handle, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.pointer)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--artifacts", default="artifacts")
    parser.add_argument("--pointer", default="state/active-release.json")
    parser.add_argument("--manifest", default="manifest.yaml")
    sub = parser.add_subparsers(dest="command", required=True)
    activate = sub.add_parser("activate")
    activate.add_argument("release_id")
    activate.add_argument("--actor", required=True)
    activate.add_argument("--reason", required=True)
    activate.add_argument("--expected-active")
    rollback = sub.add_parser("rollback")
    rollback.add_argument("--to-release")
    rollback.add_argument("--actor", required=True)
    rollback.add_argument("--reason", required=True)
    sub.add_parser("status")
    args = parser.parse_args()
    store = ActivationStore(args.artifacts, args.pointer, args.manifest)
    try:
        if args.command == "activate":
            result = store.activate(args.release_id, args.actor, args.reason,
                                    args.expected_active)
        elif args.command == "rollback":
            result = store.rollback(args.actor, args.reason, args.to_release)
        else:
            _, release_record, pointer = store.load_active()
            result = {"pointer": pointer, "release": release_record}
    except ActivationError as error:
        print(f"FATAL: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
