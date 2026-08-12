#!/usr/bin/env python3
"""Resumable, receipt-driven control plane for one local Ouroboros cycle.

The controller never performs Telegram, GitHub, corpus, release, or production
mutations.  It publishes one bounded action and accepts a validated receipt
from an attributable executor.  That keeps interactive agents and unattended
daemons on the same replayable protocol without giving either release authority.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import pathlib
import re
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Mapping


SCHEMA_VERSION = 1
CONTROLLER_VERSION = "ouroboros-controller-v1"
PHASES = ("preflight", "wave", "review", "candidate_drain",
          "implementation", "evaluation", "activation", "verification",
          "complete")
MODEL_PROPOSAL_KINDS = ("wave_plan", "feedback", "next_action")
OUTCOMES = {"answered", "abstained", "refused", "pointed", "failed"}
DECISIONS = {"regression", "rejection_test", "corpus_gap", "routing_change",
             "live_data_requirement", "discard"}
HEX_12 = re.compile(r"[0-9a-f]{12}")
HEX_20 = re.compile(r"[0-9a-f]{20}")
SHA256 = re.compile(r"[0-9a-f]{64}")
RESULT_FIELDS = {
    "preflight": ("aleph_monitor_ok", "null_monitor_ok", "null_paused",
                  "model_mode", "model_identity_ok"),
    "wave": ("requested", "delivered", "correlated", "null_paused",
             "boundary_id"),
    "review": ("expected", "recorded", "finalized", "malformed",
               "all_explained", "continue_waves"),
    "candidate_drain": ("pile_before", "pile_after", "report_id",
                        "change_required"),
    "implementation": ("issue_urls", "pull_requests", "reviewed_source_ids",
                       "source_revision"),
    "evaluation": ("passed", "candidate_release_id", "evaluation_id",
                   "prior_release_retained"),
    "activation": ("approved_by", "reason", "expected_active",
                   "activated_release_id"),
    "verification": ("aleph_monitor_ok", "null_monitor_ok", "canary_ok",
                     "report_applied", "candidate_pile", "null_paused"),
}


class OuroborosError(RuntimeError):
    """A local cycle cannot advance without weakening its contract."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _hash(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _object(path: str | pathlib.Path, label: str) -> dict:
    try:
        value = json.loads(pathlib.Path(path).read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise OuroborosError(f"cannot load {label}: {error}") from error
    if not isinstance(value, dict):
        raise OuroborosError(f"{label} must be a JSON object")
    return value


def _keys(value: Mapping, expected: set[str], label: str) -> None:
    if set(value) != expected:
        extra = sorted(set(value) - expected)
        missing = sorted(expected - set(value))
        raise OuroborosError(
            f"{label} fields differ (missing={missing}, extra={extra})")


def _positive(value: object, label: str, *, zero: bool = False) -> int:
    minimum = 0 if zero else 1
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise OuroborosError(f"{label} must be an integer >= {minimum}")
    return value


def validate_identity(value: object, *, require_synchronized: bool = False) -> dict:
    if not isinstance(value, dict):
        raise OuroborosError("identity must be an object")
    _keys(value, {"aleph", "null"}, "identity")
    aleph, null = value["aleph"], value["null"]
    if not isinstance(aleph, dict) or not isinstance(null, dict):
        raise OuroborosError("Aleph and Null identities must be objects")
    _keys(aleph, {"source_revision", "release_id", "evolution", "generation",
                  "activation_sequence"}, "Aleph identity")
    _keys(null, {"source_revision", "run_id", "mode", "paused",
                 "candidate_pile", "queue_count", "coverage_release_id",
                 "evolution", "generation"}, "Null identity")
    if not all(isinstance(aleph[key], str) and aleph[key].strip()
               for key in ("source_revision", "release_id")):
        raise OuroborosError("Aleph source and release identities are required")
    if not HEX_20.fullmatch(aleph["release_id"]):
        raise OuroborosError("Aleph release ID must be 20 lowercase hexadecimal characters")
    for key in ("evolution", "generation", "activation_sequence"):
        _positive(aleph[key], f"Aleph {key}")
    if not all(isinstance(null[key], str) and null[key].strip()
               for key in ("source_revision", "run_id", "mode")):
        raise OuroborosError("Null source, run, and mode identities are required")
    if not isinstance(null["paused"], bool):
        raise OuroborosError("Null paused state must be boolean")
    for key in ("candidate_pile", "queue_count"):
        _positive(null[key], f"Null {key}", zero=True)
    if not HEX_20.fullmatch(null["coverage_release_id"]):
        raise OuroborosError("Null coverage release must be a 20-character ID")
    for key in ("evolution", "generation"):
        _positive(null[key], f"Null {key}")
    synchronized = ((aleph["release_id"], aleph["evolution"],
                     aleph["generation"])
                    == (null["coverage_release_id"], null["evolution"],
                        null["generation"]))
    null_position = (null["evolution"], null["generation"])
    aleph_position = (aleph["evolution"], aleph["generation"])
    if require_synchronized and not synchronized:
        raise OuroborosError("Aleph identity and Null coverage identity disagree")
    if not synchronized and null_position >= aleph_position:
        raise OuroborosError(
            "Null coverage may lag Aleph after activation but cannot lead it")
    return json.loads(json.dumps(value, sort_keys=True))


def _action(phase: str, cycle_id: str, sequence: int, identity: dict) -> dict:
    instructions = {
        "preflight": "Run both monitors; verify the model/tunnel identity if used; leave Null paused.",
        "wave": "Select a bounded coverage-driven wave, run it once, correlate every reply, and pause Null.",
        "review": "Review every correlated response and record one complete feedback/finalisation result per code.",
        "candidate_drain": "Export and disposition the complete immutable candidate pile; do not treat proposals as evidence.",
        "implementation": "Land reviewed source, routing, live-data, or evaluation changes through issue-first review.",
        "evaluation": "Build and evaluate the exact candidate and source bytes; retain the prior release.",
        "activation": "Obtain human approval and activate the evaluated release with compare-and-swap.",
        "verification": "Run monitors and canaries, apply the complete report to Null, and verify candidate_pile=0.",
    }
    value = {
        "schema_version": SCHEMA_VERSION, "cycle_id": cycle_id,
        "sequence": sequence, "phase": phase, "identity": identity,
        "instruction": instructions[phase],
        "required_result_fields": list(RESULT_FIELDS[phase]),
        "execution_authority": "external_attributable_receipt_only",
    }
    value["action_id"] = _hash(value)[:20]
    return value


def _validate_result(phase: str, result: object) -> tuple[str, bool]:
    if not isinstance(result, dict):
        raise OuroborosError("receipt result must be an object")
    branch = False
    if phase == "preflight":
        _keys(result, {"aleph_monitor_ok", "null_monitor_ok", "null_paused",
                       "model_mode", "model_identity_ok"}, "preflight result")
        if (result["aleph_monitor_ok"] is not True
                or result["null_monitor_ok"] is not True
                or result["null_paused"] is not True):
            raise OuroborosError("preflight monitors must pass and Null must be paused")
        if result["model_mode"] not in {"disabled", "shadow"}:
            raise OuroborosError("model_mode must be disabled or shadow")
        if not isinstance(result["model_identity_ok"], bool):
            raise OuroborosError("model_identity_ok must be boolean")
        if result["model_mode"] == "shadow" and not result["model_identity_ok"]:
            raise OuroborosError("shadow mode requires a verified pinned model")
    elif phase == "wave":
        _keys(result, {"requested", "delivered", "correlated", "null_paused",
                       "boundary_id"}, "wave result")
        requested = _positive(result["requested"], "requested")
        if (result["delivered"] != requested or result["correlated"] != requested
                or result["null_paused"] is not True
                or not isinstance(result["boundary_id"], str)
                or not result["boundary_id"].strip()):
            raise OuroborosError("wave must be completely delivered, correlated, and paused")
    elif phase == "review":
        _keys(result, {"expected", "recorded", "finalized", "malformed",
                       "all_explained", "continue_waves"}, "review result")
        expected = _positive(result["expected"], "expected")
        if (result["recorded"] != expected or result["finalized"] != expected
                or result["malformed"] != 0 or result["all_explained"] is not True
                or not isinstance(result["continue_waves"], bool)):
            raise OuroborosError("review counts must match with no malformed or unexplained result")
        branch = result["continue_waves"]
    elif phase == "candidate_drain":
        _keys(result, {"pile_before", "pile_after", "report_id",
                       "change_required"}, "candidate result")
        _positive(result["pile_before"], "pile_before", zero=True)
        if result["pile_after"] != 0:
            raise OuroborosError("candidate pile must be zero before advancing")
        if (not isinstance(result["report_id"], str)
                or not result["report_id"].strip()
                or not isinstance(result["change_required"], bool)):
            raise OuroborosError("candidate result is incomplete")
        branch = result["change_required"]
    elif phase == "implementation":
        _keys(result, {"issue_urls", "pull_requests", "reviewed_source_ids",
                       "source_revision"}, "implementation result")
        for key in ("issue_urls", "pull_requests", "reviewed_source_ids"):
            if not isinstance(result[key], list) or not all(
                    isinstance(item, str) and item.strip() for item in result[key]):
                raise OuroborosError(f"{key} must be a list of non-empty strings")
        if not result["issue_urls"] or not result["pull_requests"]:
            raise OuroborosError("implementation requires issue and pull-request provenance")
        if not isinstance(result["source_revision"], str) or not result["source_revision"].strip():
            raise OuroborosError("implementation source revision is required")
    elif phase == "evaluation":
        _keys(result, {"passed", "candidate_release_id", "evaluation_id",
                       "prior_release_retained"}, "evaluation result")
        if (result["passed"] is not True or result["prior_release_retained"] is not True
                or not HEX_20.fullmatch(result["candidate_release_id"])
                or not HEX_20.fullmatch(result["evaluation_id"])):
            raise OuroborosError("evaluation must pass with pinned IDs and retained rollback")
    elif phase == "activation":
        _keys(result, {"approved_by", "reason", "expected_active",
                       "activated_release_id"}, "activation result")
        if not all(isinstance(result[key], str) and result[key].strip()
                   for key in result):
            raise OuroborosError("activation requires attributable approval and exact IDs")
        if not HEX_20.fullmatch(result["expected_active"]) or not HEX_20.fullmatch(
                result["activated_release_id"]):
            raise OuroborosError("activation release IDs are invalid")
    elif phase == "verification":
        _keys(result, {"aleph_monitor_ok", "null_monitor_ok", "canary_ok",
                       "report_applied", "candidate_pile", "null_paused"},
              "verification result")
        if (any(result[key] is not True for key in (
                "aleph_monitor_ok", "null_monitor_ok", "canary_ok",
                "report_applied", "null_paused")) or result["candidate_pile"] != 0):
            raise OuroborosError("final verification is incomplete")
    else:
        raise OuroborosError(f"phase {phase} cannot accept a receipt")
    return phase, branch


def validate_receipt(receipt: object, action: dict, current_identity: dict) -> dict:
    if not isinstance(receipt, dict):
        raise OuroborosError("receipt must be an object")
    _keys(receipt, {"schema_version", "action_id", "actor", "completed_at",
                    "before", "after", "result"}, "receipt")
    if receipt["schema_version"] != SCHEMA_VERSION or receipt["action_id"] != action["action_id"]:
        raise OuroborosError("receipt schema or action identity differs")
    if not isinstance(receipt["actor"], str) or not receipt["actor"].strip():
        raise OuroborosError("receipt actor is required")
    try:
        datetime.fromisoformat(str(receipt["completed_at"]).replace("Z", "+00:00"))
    except ValueError as error:
        raise OuroborosError("receipt completed_at is invalid") from error
    before, after = validate_identity(receipt["before"]), validate_identity(receipt["after"])
    if before != current_identity:
        raise OuroborosError("receipt was produced from a stale cycle identity")
    phase, branch = _validate_result(action["phase"], receipt["result"])
    if phase not in {"activation", "verification"} and after != before:
        raise OuroborosError(f"{phase} is not allowed to change runtime identity")
    if phase == "activation":
        result = receipt["result"]
        if (result["expected_active"] != before["aleph"]["release_id"]
                or result["activated_release_id"] != after["aleph"]["release_id"]
                or after["aleph"]["activation_sequence"]
                <= before["aleph"]["activation_sequence"]
                or (after["aleph"]["evolution"] == before["aleph"]["evolution"]
                    and after["aleph"]["generation"]
                    <= before["aleph"]["generation"])):
            raise OuroborosError("activation identity did not advance coherently")
        # Null must not pretend to cover a release before the final report is applied.
        if after["null"] != before["null"]:
            raise OuroborosError("activation cannot silently change Null's coverage identity")
    if phase == "verification" and after != before:
        mutable = {"coverage_release_id", "evolution", "generation"}
        before_null = {key: value for key, value in before["null"].items()
                       if key not in mutable}
        after_null = {key: value for key, value in after["null"].items()
                      if key not in mutable}
        if (after["aleph"] != before["aleph"] or after_null != before_null
                or (after["null"]["coverage_release_id"],
                    after["null"]["evolution"], after["null"]["generation"])
                != (after["aleph"]["release_id"],
                    after["aleph"]["evolution"], after["aleph"]["generation"])):
            raise OuroborosError(
                "verification may only synchronize Null's coverage identity")
    value = json.loads(json.dumps(receipt, sort_keys=True))
    value["branch"] = branch
    return value


class CycleStore:
    def __init__(self, root: str | pathlib.Path):
        self.root = pathlib.Path(root).resolve()
        self.state_path = self.root / "cycle.json"
        self.lock_path = self.root / "cycle.lock"

    @contextmanager
    def lock(self, *, blocking: bool = False):
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        with open(self.lock_path, "a+", encoding="utf-8") as handle:
            operation = fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
            try:
                fcntl.flock(handle, operation)
            except BlockingIOError as error:
                raise OuroborosError("another local controller holds the cycle lock") from error
            yield

    def load(self) -> dict:
        state = _object(self.state_path, "cycle state")
        if state.get("schema_version") != SCHEMA_VERSION:
            raise OuroborosError("cycle state schema is unsupported")
        expected = state.get("state_sha256")
        basis = {key: value for key, value in state.items() if key != "state_sha256"}
        if expected != _hash(basis):
            raise OuroborosError("cycle state hash differs")
        validate_identity(state.get("identity"))
        self.verify_ledger(state)
        return state

    def save(self, state: dict) -> None:
        basis = {key: value for key, value in state.items() if key != "state_sha256"}
        value = {**basis, "state_sha256": _hash(basis)}
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, name = tempfile.mkstemp(prefix=".cycle.", dir=self.root)
        try:
            with os.fdopen(fd, "w") as handle:
                json.dump(value, handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(name, 0o600)
            os.replace(name, self.state_path)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    @staticmethod
    def receipt_record(value: dict, previous_hash: str | None) -> dict:
        record = {"previous_receipt_sha256": previous_hash,
                  "receipt": json.loads(json.dumps(value, sort_keys=True))}
        record["receipt_sha256"] = _hash(record)
        return record

    def verify_ledger(self, state: dict) -> None:
        previous, count = None, 0
        records = state.get("receipts")
        if not isinstance(records, list):
            raise OuroborosError("cycle receipt ledger is absent")
        for record in records:
                if not isinstance(record, dict):
                    raise OuroborosError("receipt ledger record must be an object")
                expected = record.get("receipt_sha256")
                basis = {key: value for key, value in record.items()
                         if key != "receipt_sha256"}
                if (expected != _hash(basis)
                        or record.get("previous_receipt_sha256") != previous):
                    raise OuroborosError("receipt ledger hash chain differs")
                previous, count = expected, count + 1
        if (state.get("last_receipt_sha256") != previous
                or state.get("completed_actions") != count):
            raise OuroborosError("cycle state and receipt ledger disagree")


def initialise(store: CycleStore, actor: str, identity: dict, *, persist: bool = True) -> dict:
    if store.state_path.exists():
        raise OuroborosError("cycle already exists; use status or resume")
    identity = validate_identity(identity, require_synchronized=True)
    if not actor.strip():
        raise OuroborosError("an attributable actor is required")
    created = _now()
    cycle_id = _hash({"actor": actor, "created": created, "identity": identity})[:20]
    action = _action("preflight", cycle_id, 1, identity)
    state = {
        "schema_version": SCHEMA_VERSION, "controller": CONTROLLER_VERSION,
        "cycle_id": cycle_id, "created_at": created, "updated_at": created,
        "owner": actor, "phase": "preflight", "sequence": 1,
        "lease": {"status": "active", "holder": actor, "epoch": 1,
                  "acquired_at": created},
        "lease_history": [{"kind": "acquire", "actor": actor,
                           "at": created, "epoch": 1}],
        "identity": identity, "pending_action": action,
        "completed_actions": 0, "last_receipt_sha256": None,
        "status": "active", "receipts": [],
    }
    if persist:
        store.save(state)
    return state


def require_holder(state: dict, actor: str) -> None:
    lease = state.get("lease")
    if (not isinstance(lease, dict) or lease.get("status") != "active"
            or not isinstance(actor, str) or actor != lease.get("holder")):
        raise OuroborosError("mutation requires the active local cycle holder")


def update_lease(store: CycleStore, command: str, actor: str,
                 reason: str | None = None) -> dict:
    state = store.load()
    lease = state.get("lease")
    if not isinstance(lease, dict):
        raise OuroborosError("cycle lease is absent")
    now = _now()
    history = list(state.get("lease_history") or [])
    if command == "release":
        require_holder(state, actor)
        lease = {**lease, "status": "released", "released_at": now}
        history.append({"kind": "release", "actor": actor, "at": now,
                        "epoch": lease["epoch"]})
    elif command == "acquire":
        if lease.get("status") != "released":
            raise OuroborosError("active lease must be released or explicitly taken over")
        epoch = _positive(lease.get("epoch"), "lease epoch") + 1
        lease = {"status": "active", "holder": actor, "epoch": epoch,
                 "acquired_at": now}
        history.append({"kind": "acquire", "actor": actor, "at": now,
                        "epoch": epoch})
    elif command == "takeover":
        if lease.get("status") != "active":
            raise OuroborosError("takeover requires an active prior holder")
        if actor == lease.get("holder"):
            raise OuroborosError("current holder cannot take over its own lease")
        if not isinstance(reason, str) or not reason.strip():
            raise OuroborosError("takeover requires an attributable reason")
        epoch = _positive(lease.get("epoch"), "lease epoch") + 1
        prior = lease.get("holder")
        lease = {"status": "active", "holder": actor, "epoch": epoch,
                 "acquired_at": now}
        history.append({"kind": "takeover", "actor": actor, "at": now,
                        "epoch": epoch, "prior_holder": prior,
                        "reason": reason.strip()})
    else:
        raise OuroborosError("unknown lease operation")
    updated = {**state, "owner": actor if command != "release" else state["owner"],
               "lease": lease, "lease_history": history, "updated_at": now}
    store.save(updated)
    return updated


def _next_phase(phase: str, branch: bool) -> str:
    if phase == "review" and branch:
        return "wave"
    if phase == "candidate_drain" and not branch:
        return "verification"
    return PHASES[PHASES.index(phase) + 1]


def record(store: CycleStore, receipt_path: str, controller_actor: str,
           *, persist: bool = True) -> dict:
    state = store.load()
    require_holder(state, controller_actor)
    if state["status"] != "active" or state["phase"] == "complete":
        raise OuroborosError("cycle has no pending action")
    receipt = validate_receipt(
        _object(receipt_path, "receipt"), state["pending_action"], state["identity"])
    branch = receipt.pop("branch")
    receipt_record = store.receipt_record(receipt, state["last_receipt_sha256"])
    receipt_hash = receipt_record["receipt_sha256"]
    phase = _next_phase(state["phase"], branch)
    identity = receipt["after"]
    sequence = state["sequence"] + 1
    action = None if phase == "complete" else _action(
        phase, state["cycle_id"], sequence, identity)
    updated = {
        **state, "updated_at": _now(), "phase": phase, "sequence": sequence,
        "identity": identity, "pending_action": action,
        "completed_actions": state["completed_actions"] + 1,
        "last_receipt_sha256": receipt_hash,
        "receipts": [*state["receipts"], receipt_record],
        "status": "complete" if phase == "complete" else "active",
    }
    if persist:
        store.save(updated)
    return updated


def validate_proposal(kind: str, value: object) -> dict:
    if kind not in MODEL_PROPOSAL_KINDS or not isinstance(value, dict):
        raise OuroborosError("model proposal kind or object is invalid")
    if any(key in value for key in ("reasoning", "thinking", "chain_of_thought")):
        raise OuroborosError("model reasoning must not enter the control plane")
    if kind == "wave_plan":
        _keys(value, {"questions"}, "wave proposal")
        questions = value["questions"]
        if not isinstance(questions, list) or not 1 <= len(questions) <= 10:
            raise OuroborosError("wave proposal must contain 1-10 questions")
        for item in questions:
            if not isinstance(item, dict):
                raise OuroborosError("wave question must be an object")
            _keys(item, {"family", "expected", "question"}, "wave question")
            if (item["expected"] not in OUTCOMES or not isinstance(item["family"], str)
                    or not item["family"].strip() or not isinstance(item["question"], str)
                    or not item["question"].strip().endswith("?")
                    or len(item["question"]) > 1000):
                raise OuroborosError("wave question is outside the bounded schema")
    elif kind == "feedback":
        _keys(value, {"entries"}, "feedback proposal")
        entries = value["entries"]
        if not isinstance(entries, list) or not 1 <= len(entries) <= 20:
            raise OuroborosError("feedback proposal must contain 1-20 entries")
        for item in entries:
            if not isinstance(item, dict):
                raise OuroborosError("feedback entry must be an object")
            _keys(item, {"code", "decision", "expected", "note"}, "feedback entry")
            if (not HEX_12.fullmatch(item["code"]) or item["decision"] not in DECISIONS
                    or item["expected"] not in OUTCOMES
                    or not isinstance(item["note"], str) or len(item["note"]) > 500):
                raise OuroborosError("feedback entry is outside the bounded schema")
    else:
        _keys(value, {"phase", "recommendation", "stop"}, "next-action proposal")
        if (value["phase"] not in PHASES or not isinstance(value["recommendation"], str)
                or not value["recommendation"].strip()
                or len(value["recommendation"]) > 1000
                or not isinstance(value["stop"], bool)):
            raise OuroborosError("next-action proposal is outside the bounded schema")
    return json.loads(json.dumps(value, sort_keys=True))


def proposal(store: CycleStore, kind: str, path: str, actor: str,
             *, persist: bool = True) -> dict:
    state = store.load()
    require_holder(state, actor)
    value = validate_proposal(kind, _object(path, "model proposal"))
    record = {"schema_version": SCHEMA_VERSION, "cycle_id": state["cycle_id"],
              "phase": state["phase"], "kind": kind, "proposed_by": actor,
              "created_at": _now(), "advisory_only": True,
              "proposal_sha256": _hash(value), "proposal": value}
    if not persist:
        return {key: record[key] for key in record if key != "proposal"}
    destination = store.root / "proposals"
    destination.mkdir(mode=0o700, exist_ok=True)
    path_out = destination / f"{record['proposal_sha256'][:20]}.json"
    if path_out.exists():
        existing = _object(path_out, "stored proposal")
        stable = {key: value for key, value in record.items()
                  if key != "created_at"}
        if ({key: value for key, value in existing.items()
             if key != "created_at"} != stable):
            raise OuroborosError("proposal identity collision")
        return {key: existing[key] for key in existing if key != "proposal"}
    path_out.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    path_out.chmod(0o600)
    return {key: record[key] for key in record if key != "proposal"}


def summary(state: dict) -> dict:
    return {key: state[key] for key in (
        "schema_version", "controller", "cycle_id", "owner", "status",
        "phase", "sequence", "completed_actions", "identity",
        "lease", "pending_action", "last_receipt_sha256")}


def receipt_template(state: dict) -> dict:
    action = state.get("pending_action")
    if action is None:
        return {"status": "complete"}
    return {"schema_version": SCHEMA_VERSION, "action_id": action["action_id"],
            "actor": "REPLACE_WITH_EXECUTOR_IDENTITY",
            "completed_at": "REPLACE_WITH_RFC3339_TIMESTAMP",
            "before": state["identity"], "after": state["identity"],
            "result": {key: None for key in action["required_result_fields"]}}


def handoff(state: dict) -> dict:
    action = state.get("pending_action")
    return {"schema_version": SCHEMA_VERSION, "controller": state["controller"],
            "cycle_id": state["cycle_id"], "status": state["status"],
            "phase": state["phase"], "sequence": state["sequence"],
            "created_at": state["created_at"], "updated_at": state["updated_at"],
            "lease": state["lease"], "identity": state["identity"],
            "completed_actions": state["completed_actions"],
            "receipt_chain_head": state["last_receipt_sha256"],
            "next_action": (None if action is None else {
                "action_id": action["action_id"], "phase": action["phase"],
                "instruction": action["instruction"]})}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--state-dir", default="state/ouroboros")
    parser.add_argument("--dry-run", action="store_true",
                        help="validate and preview without changing cycle state")
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init")
    init.add_argument("--actor", required=True)
    init.add_argument("--identity", required=True)
    commands.add_parser("status")
    commands.add_parser("plan")
    commands.add_parser("resume")
    commands.add_parser("receipt-template")
    commands.add_parser("handoff")
    receive = commands.add_parser("record")
    receive.add_argument("--receipt", required=True)
    receive.add_argument("--controller-actor", required=True)
    propose = commands.add_parser("propose")
    propose.add_argument("--kind", choices=MODEL_PROPOSAL_KINDS, required=True)
    propose.add_argument("--input", required=True)
    propose.add_argument("--actor", required=True)
    for name in ("acquire", "release", "takeover"):
        lease = commands.add_parser(name)
        lease.add_argument("--actor", required=True)
        if name == "takeover":
            lease.add_argument("--reason", required=True)
    args = parser.parse_args()
    store = CycleStore(args.state_dir)
    try:
        with store.lock():
            if args.command == "init":
                result = initialise(store, args.actor, _object(args.identity, "identity"),
                                    persist=not args.dry_run)
            elif args.command in {"status", "resume"}:
                result = store.load()
            elif args.command == "plan":
                result = store.load()["pending_action"]
                if result is None:
                    result = {"status": "complete"}
            elif args.command == "receipt-template":
                result = receipt_template(store.load())
            elif args.command == "handoff":
                result = handoff(store.load())
            elif args.command == "record":
                result = record(store, args.receipt, args.controller_actor,
                                persist=not args.dry_run)
            elif args.command in {"acquire", "release", "takeover"}:
                if args.dry_run:
                    raise OuroborosError("lease changes do not support dry-run")
                result = update_lease(store, args.command, args.actor,
                                      getattr(args, "reason", None))
            else:
                result = proposal(store, args.kind, args.input, args.actor,
                                  persist=not args.dry_run)
    except OuroborosError as error:
        parser.error(str(error))
    print(json.dumps(summary(result) if "controller" in result else result,
                     indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
