#!/usr/bin/env python3
"""Adversarial tests for the resumable local Ouroboros controller."""

from __future__ import annotations

import copy
import json
import pathlib
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
                 "null_paused": True, "model_mode": "shadow",
                 "model_identity_ok": True}
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
                  "evaluation_id": "c" * 20, "prior_release_retained": True}
    state = ouroboros.record(store, str(record_file(
        tmp, receipt(state["pending_action"], identity(), evaluation))),
        "operator@wildcat.finance")
    after = copy.deepcopy(identity("b" * 20, generation=3, sequence=12))
    # Null coverage remains on the release it actually knows until verification.
    activation = {"approved_by": "human@wildcat.finance", "reason": "issue-99",
                  "expected_active": "a" * 20,
                  "activated_release_id": "b" * 20}
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

    print("\nC5 — proposal boundary and tamper evidence")
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


def main() -> int:
    with tempfile.TemporaryDirectory() as directory:
        run(pathlib.Path(directory))
    if FAILURES:
        print(f"\n{len(FAILURES)} failure(s): " + ", ".join(FAILURES))
        return 1
    print("\nAll local Ouroboros controller tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
