#!/usr/bin/env python3
"""Adversarial tests for activation, rollback, audit, and monitoring."""

from __future__ import annotations

import copy
import json
import os
import pathlib
import shutil
import stat
import sys
import tempfile

import activation
import agent
import audit
from eval import product_eval
import monitor
import promotion
import serve
import telegram
import test_agent


FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if ok else 'FAIL'} {name}"
          + (f" — {detail}" if detail and not ok else ""))
    if not ok:
        FAILURES.append(name)


class MonitorAPI:
    def call(self, method, payload=None):
        if method == "getMe":
            return {"id": 99, "is_bot": True, "username": "AlephMonitorBot",
                    "can_read_all_group_messages": False}
        if method == "getWebhookInfo":
            return {"url": "", "pending_update_count": 0}
        raise AssertionError(method)


def approved_fixture(tmp: pathlib.Path):
    retriever, live_client, _ = test_agent.components(tmp)
    # The fixture index intentionally uses meaningless stub vectors. Strict
    # topic isolation is exercised against controlled adversarial evidence in
    # test_agent.py and defaults on for the production embedder.
    engine = agent.AnswerEngine(
        retriever, live_client,
        writer=agent.ExtractiveWriter(require_topic_match=False))
    fixture_path = pathlib.Path("eval/live-fixture-v1.json").resolve()
    fixture = json.loads(fixture_path.read_text())
    policy = {
        "route_accuracy": 1.0, "outcome_accuracy": 1.0,
        "citation_validity": 1.0, "claim_support": 1.0,
        "live_determinism": 1.0, "refusal_accuracy": 1.0,
        "minimum_retrieval_label_passes": 1,
        "maximum_known_gap_answers": 0,
    }
    report = product_eval.evaluate(
        engine, retriever, "eval/golden-v1.yaml", "eval/labels.yaml",
        policy, fixture)
    root = retriever.main.release_path.parents[2]
    inputs = {
        "paths": {
            "manifest": str(retriever.main.manifest_path),
            "release": str(retriever.main.release_path),
            "prerelease": str(retriever.prerelease.release_path),
            "questions": str(pathlib.Path("eval/golden-v1.yaml").resolve()),
            "labels": str(pathlib.Path("eval/labels.yaml").resolve()),
            "live_fixture": str(fixture_path),
        },
        "manifest_sha256": product_eval._sha256(retriever.main.manifest_path),
        "release_sha256": product_eval._sha256(retriever.main.release_path),
        "prerelease_sha256": product_eval._sha256(
            retriever.prerelease.release_path),
        "questions_sha256": product_eval._sha256(
            pathlib.Path("eval/golden-v1.yaml")),
        "labels_sha256": product_eval._sha256(pathlib.Path("eval/labels.yaml")),
        "live_fixture_sha256": product_eval._sha256(fixture_path),
    }
    record = {
        "evaluation_id": "", "created": "2026-08-10T00:00:00+00:00",
        "candidate_release_id": report["candidate_release_id"],
        "prerelease_release_id": report["prerelease_release_id"],
        "inputs": inputs, "tools": product_eval._tool_hashes(),
        "report": report,
    }
    first_eval = product_eval.publish(str(root), record)
    first_path = root / "evaluations" / first_eval["evaluation_id"] / "evaluation.json"
    first = promotion.approve(
        str(retriever.main.release_path), str(first_path), str(root))

    second_record = copy.deepcopy(record)
    second_record["run_label"] = "independent-second-approval"
    second_eval = product_eval.publish(str(root), second_record)
    second_path = (root / "evaluations" / second_eval["evaluation_id"]
                   / "evaluation.json")
    second = promotion.approve(
        str(retriever.main.release_path), str(second_path), str(root))
    return retriever, live_client, engine, root, first, second


def run(tmp: pathlib.Path) -> None:
    retriever, live_client, engine, root, first, second = approved_fixture(tmp)
    pointer_path = tmp / "state" / "active-release.json"
    store = activation.ActivationStore(
        str(root), str(pointer_path), str(retriever.main.manifest_path))

    print("\nO1 — only a verified evaluated release can become active")
    refused = ""
    try:
        store.activate(retriever.main.record["release_id"], "operator", "raw")
    except activation.ActivationError as error:
        refused = str(error)
    check("a raw candidate with a null eval gate is refused",
          "not promotable" in refused, refused)
    first_pointer = store.activate(
        first["release_id"], "operator@example", "initial production release")
    active_path, active, loaded = store.load_active()
    check("activation atomically points at the exact promotable bytes",
          active["release_id"] == first["release_id"]
          and loaded == first_pointer and active_path.is_file())
    activation_path = root / first_pointer["activation_path"]
    activation_record = json.loads(activation_path.read_text())
    check("the immutable switch records actor, reason, evaluation and predecessor",
          activation_record["actor"] == "operator@example"
          and activation_record["reason"] == "initial production release"
          and activation_record["evaluation_id"] == first["evaluation"]["evaluation_id"]
          and activation_record["previous_release_id"] is None)
    refused = ""
    try:
        store.activate(second["release_id"], "operator", "race",
                       expected_active="stale-id")
    except activation.ActivationError as error:
        refused = str(error)
    check("compare-and-swap detects a concurrent or stale operator",
          "active release changed" in refused, refused)

    print("\nO2 — rollback is a new atomic generation, never a rebuild")
    second_pointer = store.activate(
        second["release_id"], "operator@example", "roll forward",
        expected_active=first["release_id"])
    rollback_pointer = store.rollback("operator@example", "regression observed")
    _, rolled_back, _ = store.load_active()
    check("rollback restores the previous retained release by pointer",
          rolled_back["release_id"] == first["release_id"]
          and rollback_pointer["generation"] == 3
          and second_pointer["generation"] == 2)
    rollback_record = json.loads(
        (root / rollback_pointer["activation_path"]).read_text())
    check("rollback remains attributable and preserves the bad candidate",
          rollback_record["kind"] == "rollback"
          and rollback_record["previous_release_id"] == second["release_id"]
          and (root / "releases" / second["release_id"]).is_dir())

    original_pointer = pointer_path.read_bytes()
    damaged = json.loads(pointer_path.read_text())
    damaged["release_id"] = second["release_id"]
    pointer_path.write_text(json.dumps(damaged))
    refused = ""
    try:
        store.load_active()
    except activation.ActivationError as error:
        refused = str(error)
    check("pointer corruption is detected before serving",
          "disagree" in refused, refused)
    pointer_path.write_bytes(original_pointer)

    print("\nO3 — audit records preserve provenance and discard content")
    logger = audit.AuditLogger(
        str(tmp / "audit"), first, hmac_key="k" * 32, retention_days=30)
    answer = engine.answer("What does exactIdentifier(uint256) do?")
    path = logger.write(logger.answer_record(
        "What does exactIdentifier(uint256) do?", answer))
    contents = path.read_text()
    row = json.loads(contents)
    check("audit names release, corpus, model, route and citations",
          row["active_release_id"] == first["release_id"]
          and row["corpus_build_id"] == first["corpus"]["build_id"]
          and row["embedding"] == first["embedding"]
          and row["route"]["mode"] == "corpus" and row["citations"])
    check("raw question, answer text, and addresses are never retained",
          "What does exactIdentifier" not in contents
          and "function exactIdentifier" not in contents
          and "0x1111111111111111111111111111111111111111" not in contents)
    check("audit files are owner-only",
          stat.S_IMODE(path.stat().st_mode) == 0o600)
    old = path.parent / "audit-2020-01-01.jsonl"
    old.write_text("old\n")
    removed = logger.purge_expired()
    check("the configured retention boundary deletes only expired audit days",
          old in removed and not old.exists() and path.exists())

    audited = audit.AuditedEngine(
        type("Broken", (), {"answer": lambda self, question:
                            (_ for _ in ()).throw(RuntimeError("secret"))})(),
        logger)
    try:
        audited.answer("private failure question")
    except RuntimeError:
        pass
    check("internal error records contain neither question nor exception text",
          "private failure question" not in path.read_text()
          and "secret" not in path.read_text())

    print("\nO4 — composition and monitoring verify every runtime dependency")
    check("peer bot allowlists are parsed, deduplicated, and default closed",
          serve.peer_bot_ids("") == ()
          and serve.peer_bot_ids("500, 501,500") == (500, 501))
    refused = ""
    try:
        serve.peer_bot_ids("500,not-an-id")
    except telegram.TelegramError as error:
        refused = str(error)
    check("malformed peer bot configuration fails closed",
          "positive integers" in refused, refused)
    previous = {name: os.environ.get(name) for name in (
        "ALEPH_GATEWAY_TOKEN", "ALEPH_TELEGRAM_TOKEN", "ALEPH_AUDIT_HMAC_KEY",
        "ALEPH_TELEGRAM_RICH_MESSAGES")}
    os.environ.update({"ALEPH_GATEWAY_TOKEN": "gateway-fixture",
                       "ALEPH_TELEGRAM_TOKEN": "telegram-fixture",
                       "ALEPH_AUDIT_HMAC_KEY": "a" * 32,
                       "ALEPH_TELEGRAM_RICH_MESSAGES": "false"})
    try:
        composed, _ = serve.compose(
            str(retriever.main.manifest_path), str(root), str(pointer_path),
            str(retriever.prerelease.release_path), "stub:test",
            str(tmp / "service-audit"), 30,
            str(tmp / "service-offset.json"), 2)
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
    check("production composition loads only the verified active release",
          isinstance(composed, telegram.TelegramAdapter)
          and composed.rich_messages is False)
    report = monitor.check(
        str(retriever.main.manifest_path), str(root), str(pointer_path),
        str(retriever.prerelease.release_path), "stub:test",
        api=MonitorAPI(), gateway_client=live_client)
    check("one-shot monitoring covers activation, model, gateway and Telegram",
          report["ok"] and set(report["checks"]) == {
              "active_release", "model_runtime", "gateway", "telegram"}
          and report["checks"]["telegram"]["rich_messages"] is True)

    print("\nO5 — production units keep the query identity unprivileged")
    required_hardening = {
        "CapabilityBoundingSet=", "DevicePolicy=closed",
        "MemoryDenyWriteExecute=true", "NoNewPrivileges=true",
        "PrivateDevices=true", "ProtectSystem=strict",
        "ProtectHome=true", "ProtectKernelModules=true",
        "ProtectKernelTunables=true", "ProtectProc=invisible",
        "RemoveIPC=true", "RestrictNamespaces=true",
        "RestrictSUIDSGID=true", "SystemCallArchitectures=native",
        "TimeoutStartSec=2min", "UMask=0077",
    }
    for name in ("aleph-monitor.service", "aleph-sdk-watch.service"):
        lines = set((pathlib.Path("ops/systemd") / name).read_text().splitlines())
        check(f"{name} retains the production sandbox",
              required_hardening <= lines,
              str(sorted(required_hardening - lines)))
    query_required = required_hardening - {"TimeoutStartSec=2min"}
    query_lines = set((pathlib.Path("ops/systemd") / "aleph.service").read_text(
        ).splitlines())
    check("aleph.service retains the production sandbox",
          query_required <= query_lines,
          str(sorted(query_required - query_lines)))


def main() -> int:
    tmp = pathlib.Path(tempfile.mkdtemp())
    try:
        run(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{len(FAILURES)} failure(s)"
          + (": " + ", ".join(FAILURES) if FAILURES else ""))
    return len(FAILURES)


if __name__ == "__main__":
    sys.exit(main())
