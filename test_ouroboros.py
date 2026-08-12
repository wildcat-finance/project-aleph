#!/usr/bin/env python3
"""Adversarial tests for the resumable local Ouroboros controller."""

from __future__ import annotations

import copy
import json
import pathlib
import subprocess
import sys
import tempfile

import ouroboros


FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if ok else 'FAIL'} {name}"
          + (f" — {detail}" if detail and not ok else ""))
    if not ok:
        FAILURES.append(name)


def identity(release: str = "a" * 20, evolution: int = 2,
             generation: int = 2, sequence: int = 11) -> dict:
    return {
        "aleph": {"source_revision": "abc123", "release_id": release,
                  "evolution": evolution, "generation": generation,
                  "activation_sequence": sequence},
        "null": {"source_revision": "def456", "run_id": "run-1",
                 "mode": "coverage", "paused": True,
                 "candidate_pile": 0, "queue_count": 0,
                 "coverage_release_id": "a" * 20,
                 "evolution": 2, "generation": 2},
    }


def receipt(action: dict, before: dict, result: dict,
            after: dict | None = None) -> dict:
    return {"schema_version": 1, "action_id": action["action_id"],
            "actor": "operator@wildcat.finance",
            "completed_at": "2026-08-12T08:00:00+00:00",
            "before": before, "after": after or before, "result": result}


def record_file(tmp: pathlib.Path, value: dict) -> pathlib.Path:
    path = tmp / "receipt.json"
    path.write_text(json.dumps(value))
    return path


def expect_error(callable_, phrase: str) -> bool:
    try:
        callable_()
    except ouroboros.OuroborosError as error:
        return phrase in str(error)
    return False


def competing_lock(store: ouroboros.CycleStore) -> None:
    with store.lock():
        pass


def run(tmp: pathlib.Path) -> None:
    store = ouroboros.CycleStore(tmp / "state")
    state = ouroboros.initialise(store, "operator@wildcat.finance", identity())
    print("\nC1 — durable identity and one exact pending action")
    check("initial state is hash-bound and resumable",
          store.load()["cycle_id"] == state["cycle_id"])
    check("preflight action binds cycle, sequence, and identity",
          state["pending_action"]["phase"] == "preflight"
          and state["pending_action"]["identity"] == identity()
          and set(state["pending_action"]["required_result_fields"])
          == set(ouroboros.RESULT_FIELDS["preflight"]))
    check("a second init cannot overwrite state", expect_error(
        lambda: ouroboros.initialise(store, "other", identity()), "already exists"))
    with store.lock():
        check("a competing controller cannot acquire the cycle",
              expect_error(lambda: competing_lock(store), "another local controller"))

    print("\nC2 — receipts fail closed and advance idempotently")
    action = state["pending_action"]
    preflight = {"aleph_monitor_ok": True, "null_monitor_ok": True,
                 "null_paused": True, "mephistopheles": {
                     "mode": "shadow", "alias": "gpt-oss:120b",
                     "id": "a951a23b46a1", "identity_ok": True}}
    stale = identity()
    stale["aleph"]["generation"] = 1
    check("stale identity is refused", expect_error(lambda: ouroboros.validate_receipt(
        receipt(action, stale, preflight), action, identity()), "cannot lead"))
    changed = copy.deepcopy(identity())
    changed["null"]["queue_count"] = 1
    check("preflight cannot smuggle an identity change", expect_error(
        lambda: ouroboros.validate_receipt(
            receipt(action, identity(), preflight, changed), action, identity()),
        "not allowed"))
    unpinned = copy.deepcopy(preflight)
    unpinned["mephistopheles"]["identity_ok"] = False
    check("Mephistopheles shadow mode requires the observed model pin",
          expect_error(lambda: ouroboros.validate_receipt(
              receipt(action, identity(), unpinned), action, identity()),
              "verified alias and pin"))
    state = ouroboros.record(store, str(record_file(
        tmp, receipt(action, identity(), preflight))), "operator@wildcat.finance")
    check("accepted receipt advances exactly once",
          state["phase"] == "wave" and state["completed_actions"] == 1)
    check("replay is rejected by action identity", expect_error(
        lambda: ouroboros.record(store, str(tmp / "receipt.json"),
                                 "operator@wildcat.finance"), "action identity"))

    wave = {"requested": 3, "delivered": 3, "correlated": 3,
            "null_paused": True, "boundary_id": "wave-1"}
    state = ouroboros.record(store, str(record_file(
        tmp, receipt(state["pending_action"], identity(), wave))),
        "operator@wildcat.finance")
    review = {"expected": 3, "recorded": 3, "finalized": 3,
              "malformed": 0, "all_explained": True, "continue_waves": True}
    state = ouroboros.record(store, str(record_file(
        tmp, receipt(state["pending_action"], identity(), review))),
        "operator@wildcat.finance")
    check("reviewer can explicitly schedule another bounded wave",
          state["phase"] == "wave")
    state = ouroboros.record(store, str(record_file(
        tmp, receipt(state["pending_action"], identity(), wave))),
        "operator@wildcat.finance")
    review["continue_waves"] = False
    state = ouroboros.record(store, str(record_file(
        tmp, receipt(state["pending_action"], identity(), review))),
        "operator@wildcat.finance")
    check("completed waves advance to candidate drain",
          state["phase"] == "candidate_drain")

    print("\nC3 — branch gates and activation authority")
    drain = {"pile_before": 4, "pile_after": 1, "report_id": "report-1",
             "change_required": True}
    check("non-empty pile blocks progress", expect_error(lambda: ouroboros.validate_receipt(
        receipt(state["pending_action"], identity(), drain),
        state["pending_action"], identity()), "must be zero"))
    drain["pile_after"] = 0
    state = ouroboros.record(store, str(record_file(
        tmp, receipt(state["pending_action"], identity(), drain))),
        "operator@wildcat.finance")
    check("reviewed changes take the implementation path",
          state["phase"] == "implementation")
    implementation = {"issue_urls": ["https://github.com/x/issues/1"],
                      "pull_requests": ["https://github.com/x/pull/2"],
                      "reviewed_source_ids": ["docs-v1"],
                      "source_revision": "new-source"}
    state = ouroboros.record(store, str(record_file(
        tmp, receipt(state["pending_action"], identity(), implementation))),
        "operator@wildcat.finance")
    evaluation = {"passed": True, "candidate_release_id": "b" * 20,
                  "evaluation_id": "c" * 20, "source_revision": "new-source",
                  "prior_release_retained": True}
    state = ouroboros.record(store, str(record_file(
        tmp, receipt(state["pending_action"], identity(), evaluation))),
        "operator@wildcat.finance")
    after = copy.deepcopy(identity("b" * 20, generation=3, sequence=12))
    # Null coverage remains on the release it actually knows until verification.
    activation = {"approved_by": "human@wildcat.finance", "reason": "issue-99",
                  "expected_active": "a" * 20,
                  "activated_release_id": "b" * 20,
                  "evaluation_id": "c" * 20}
    state = ouroboros.record(store, str(record_file(
        tmp, receipt(state["pending_action"], identity(), activation, after))),
        "operator@wildcat.finance")
    check("only activation changes Aleph identity",
          state["phase"] == "verification"
          and state["identity"]["aleph"]["release_id"] == "b" * 20
          and state["identity"]["null"]["coverage_release_id"] == "a" * 20)
    verification_after = copy.deepcopy(after)
    verification_after["null"].update({
        "coverage_release_id": "b" * 20, "generation": 3})
    final = {"aleph_monitor_ok": True, "null_monitor_ok": True,
             "canary_ok": True, "report_applied": True,
             "candidate_pile": 0, "null_paused": True}
    forged = copy.deepcopy(verification_after)
    forged["null"]["candidate_pile"] = 99
    check("verification cannot forge unrelated Null state", expect_error(
        lambda: ouroboros.validate_receipt(
            receipt(state["pending_action"], after, final, forged),
            state["pending_action"], after), "only synchronize"))
    state = ouroboros.record(store, str(record_file(
        tmp, receipt(state["pending_action"], after, final,
                     verification_after))), "operator@wildcat.finance")
    check("fully verified cycle completes with a zero pile",
          state["status"] == state["phase"] == "complete"
          and state["identity"]["null"]["coverage_release_id"] == "b" * 20)

    print("\nC4 — durable ownership and scrubbed handoff")
    second = ouroboros.CycleStore(tmp / "second")
    leased = ouroboros.initialise(second, "first@wildcat.finance", identity())
    check("non-holder cannot mutate", expect_error(lambda: ouroboros.record(
        second, str(record_file(tmp, receipt(
            leased["pending_action"], identity(), preflight))),
        "second@wildcat.finance"), "active local cycle holder"))
    leased = ouroboros.update_lease(second, "takeover", "second@wildcat.finance",
                                   "first operator unavailable")
    check("explicit takeover advances the lease epoch and records its reason",
          leased["lease"]["epoch"] == 2
          and leased["lease_history"][-1]["reason"] == "first operator unavailable")
    template = ouroboros.receipt_template(leased)
    view = ouroboros.handoff(leased)
    check("templates and handoffs expose no receipts or proposal content",
          template["action_id"] == leased["pending_action"]["action_id"]
          and "receipts" not in view and "proposal" not in json.dumps(view))

    print("\nC5 — Aleph and Null snapshot identities must agree")
    aleph = {"ok": True, "checks": {
        "active_release": {"ok": True, "release_id": "a" * 20,
                           "evolution": 2, "generation": 2,
                           "activation_sequence": 11},
        "model_runtime": {"ok": True}, "gateway": {"ok": True},
        "telegram": {"ok": True}}}
    null_basis = {"schema_version": 1, "source_revision": "def456",
                  "run_id": "run-1", "mode": "coverage", "paused": True,
                  "queue_count": 0, "candidate_pile": 0,
                  "candidate_resolved": 5,
                  "coverage_release_id": "a" * 20,
                  "evolution": 2, "generation": 2}
    null = {**null_basis, "snapshot_sha256": __import__("hashlib").sha256(
        ouroboros._canonical(null_basis) + b"\n").hexdigest()}
    check("scrubbed reports produce the exact init identity",
          ouroboros.identity_snapshot(aleph, null, "abc123") == identity())
    drifted_snapshot = {**null, "generation": 1}
    drifted_basis = {key: value for key, value in drifted_snapshot.items()
                     if key != "snapshot_sha256"}
    drifted_snapshot["snapshot_sha256"] = __import__("hashlib").sha256(
        ouroboros._canonical(drifted_basis) + b"\n").hexdigest()
    check("cross-system identity drift blocks initialization", expect_error(
        lambda: ouroboros.identity_snapshot(aleph, drifted_snapshot, "abc123"),
        "disagree"))

    print("\nC6 — proposal boundary and tamper evidence")
    good = {"questions": [{"family": "ordinary", "expected": "answered",
                            "question": "How does a withdrawal cycle begin?"}]}
    check("bounded model proposal validates but remains advisory",
          ouroboros.validate_proposal("wave_plan", good) == good)
    poisoned = {**good, "reasoning": "secret chain of thought"}
    check("reasoning cannot enter a proposal", expect_error(
        lambda: ouroboros.validate_proposal("wave_plan", poisoned), "reasoning"))
    damaged = json.loads(store.state_path.read_text())
    damaged["receipts"][0]["receipt"]["actor"] = "attacker"
    basis = {key: value for key, value in damaged.items()
             if key != "state_sha256"}
    damaged["state_sha256"] = ouroboros._hash(basis)
    store.state_path.write_text(json.dumps(damaged))
    check("receipt tampering prevents resume", expect_error(store.load, "hash chain"))


def cli(tmp: pathlib.Path) -> None:
    print("\nC7 — public CLI dry-run, restart, and no-change cycle")
    root = tmp / "cli-state"
    identity_path = tmp / "identity.json"
    identity_path.write_text(json.dumps(identity()))
    executable = pathlib.Path(ouroboros.__file__).resolve()

    def command(*args: str, expected: int = 0) -> tuple[int, dict | None]:
        process = subprocess.run(
            [sys.executable, str(executable), "--state-dir", str(root), *args],
            text=True, capture_output=True)
        if process.returncode != expected:
            raise AssertionError(
                f"CLI {args} returned {process.returncode}: {process.stderr}")
        value = json.loads(process.stdout) if process.stdout.strip() else None
        return process.returncode, value

    _, initial = command("init", "--actor", "operator@wildcat.finance",
                         "--identity", str(identity_path))
    _, restarted = command("status")
    check("new process resumes the same action",
          restarted["pending_action"]["action_id"]
          == initial["pending_action"]["action_id"])

    results = [
        {"aleph_monitor_ok": True, "null_monitor_ok": True,
         "null_paused": True, "mephistopheles": {
             "mode": "disabled", "alias": None, "id": None,
             "identity_ok": True}},
        {"requested": 1, "delivered": 1, "correlated": 1,
         "null_paused": True, "boundary_id": "cli-wave"},
        {"expected": 1, "recorded": 1, "finalized": 1,
         "malformed": 0, "all_explained": True,
         "continue_waves": False},
        {"pile_before": 0, "pile_after": 0, "report_id": "empty-report",
         "change_required": False},
        {"aleph_monitor_ok": True, "null_monitor_ok": True,
         "canary_ok": True, "report_applied": True,
         "candidate_pile": 0, "null_paused": True},
    ]
    first_receipt = None
    for index, result in enumerate(results):
        _, template = command("receipt-template")
        template.update({"actor": "executor@wildcat.finance",
                         "completed_at": f"2026-08-12T08:0{index}:00+00:00",
                         "result": result})
        path = tmp / f"cli-receipt-{index}.json"
        path.write_text(json.dumps(template))
        before = root.joinpath("cycle.json").read_bytes()
        _, preview = command("--dry-run", "record", "--controller-actor",
                             "operator@wildcat.finance", "--receipt", str(path))
        check(f"dry-run {index + 1} previews without persistence",
              root.joinpath("cycle.json").read_bytes() == before
              and preview["phase"] != restarted["phase"] if index == 0 else
              root.joinpath("cycle.json").read_bytes() == before)
        _, restarted = command("record", "--controller-actor",
                               "operator@wildcat.finance", "--receipt", str(path))
        first_receipt = first_receipt or path
        _, restarted_again = command("status")
        check(f"restart {index + 1} preserves the advanced phase",
              restarted_again["phase"] == restarted["phase"])
    check("no-change CLI cycle skips implementation and completes",
          restarted["phase"] == restarted["status"] == "complete"
          and restarted["completed_actions"] == 5)
    process = subprocess.run(
        [sys.executable, str(executable), "--state-dir", str(root), "record",
         "--controller-actor", "operator@wildcat.finance", "--receipt",
         str(first_receipt)], text=True, capture_output=True)
    check("completed cycle rejects receipt replay",
          process.returncode != 0 and "no pending action" in process.stderr)


def main() -> int:
    with tempfile.TemporaryDirectory() as directory:
        root = pathlib.Path(directory)
        run(root)
        cli(root)
    if FAILURES:
        print(f"\n{len(FAILURES)} failure(s): " + ", ".join(FAILURES))
        return 1
    print("\nAll local Ouroboros controller tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
