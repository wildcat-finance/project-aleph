#!/usr/bin/env python3
"""Run and immutably record Aleph's blocking end-to-end product evaluation."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import shutil
import sys
import tempfile
from collections import defaultdict
from datetime import datetime, timezone

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from agent import AnswerEngine, RouteMode  # noqa: E402
from live import GatewayClient  # noqa: E402
from retrieval import RetrievalRequest, Retriever, RetrievalError  # noqa: E402
from eval.retrieval_eval import EvaluationError, evaluate as retrieval_evaluate  # noqa: E402


class ProductEvaluationError(Exception):
    """Evaluation inputs or outputs cannot support a promotion decision."""


def _canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tool_hashes() -> dict[str, str]:
    paths = (ROOT / "agent.py", ROOT / "retrieval.py", ROOT / "live.py",
             HERE / "retrieval_eval.py", HERE / "product_eval.py")
    return {str(path.relative_to(ROOT)): _sha256(path) for path in paths}


class FixtureTransport:
    """Replay checked-in GraphQL fixture data through the real live client."""

    _OPERATION = re.compile(r"\bquery\s+(Registry|Market|Account|Withdrawals|BorrowerMarkets)\b")
    _KEYS = {
        "Registry": "registry", "Market": "market", "Account": "account",
        "Withdrawals": "withdrawals", "BorrowerMarkets": "borrower_markets",
    }

    def __init__(self, fixture: dict):
        self.fixture = fixture

    def get_json(self, url: str) -> dict:
        return json.loads(json.dumps(self.fixture["health"]))

    def post_json(self, url: str, body: dict, token: str) -> dict:
        match = self._OPERATION.search(body.get("query") or "")
        if not match:
            return {"errors": [{"message": "fixture has no matching operation"}]}
        key = self._KEYS[match.group(1)]
        try:
            data = json.loads(json.dumps(self.fixture["responses"][key]))
        except KeyError:
            return {"errors": [{"message": f"fixture omits {key}"}]}
        requested = body.get("variables", {}).get("block", {}).get("number")
        actual = data.get("_meta", {}).get("block", {}).get("number")
        if requested != actual:
            return {"errors": [{"message":
                f"fixture block {actual} does not match request {requested}"}]}
        return {"data": data}


def _load_yaml(path: pathlib.Path):
    try:
        import yaml
    except ImportError:
        raise ProductEvaluationError("product_eval.py needs pyyaml")
    try:
        return yaml.safe_load(path.read_bytes())
    except (OSError, ValueError) as error:
        raise ProductEvaluationError(f"cannot load {path}: {error}")


def _policy(manifest_path: pathlib.Path) -> dict:
    configured = (_load_yaml(manifest_path).get("evaluation") or {})
    defaults = {
        "route_accuracy": 1.0,
        "outcome_accuracy": 1.0,
        "citation_validity": 1.0,
        "claim_support": 1.0,
        "live_determinism": 1.0,
        "refusal_accuracy": 1.0,
        "minimum_retrieval_label_passes": 23,
        "maximum_known_gap_answers": 0,
    }
    unknown = sorted(set(configured) - set(defaults))
    if unknown:
        raise ProductEvaluationError(
            f"manifest evaluation policy has unknown keys: {unknown}")
    policy = {**defaults, **configured}
    for key in ("route_accuracy", "outcome_accuracy", "citation_validity",
                "claim_support", "live_determinism", "refusal_accuracy"):
        try:
            value = float(policy[key])
        except (TypeError, ValueError):
            raise ProductEvaluationError(f"evaluation.{key} must be numeric")
        if not 0 <= value <= 1:
            raise ProductEvaluationError(f"evaluation.{key} must be from 0 to 1")
        policy[key] = value
    for key in ("minimum_retrieval_label_passes", "maximum_known_gap_answers"):
        try:
            policy[key] = int(policy[key])
        except (TypeError, ValueError):
            raise ProductEvaluationError(f"evaluation.{key} must be an integer")
        if policy[key] < 0:
            raise ProductEvaluationError(f"evaluation.{key} cannot be negative")
    return policy


def _risk(item: dict, mode: RouteMode) -> str:
    """Stable conservative risk grouping where the golden file has no field."""
    if mode in (RouteMode.REFUSE, RouteMode.CORRECT, RouteMode.PARTIAL):
        return "high"
    if item["id"][0] in "bcgklmn" or item.get("frequency") == "high":
        return "high"
    if mode in (RouteMode.LIVE, RouteMode.CORPUS_LIVE, RouteMode.TRIAGE):
        return "medium"
    if item.get("frequency") == "medium":
        return "medium"
    return "low"


def _question_with_fixture_entities(question: str, route, entities: dict) -> str:
    operation = route.live_operation
    if operation == "borrower_markets":
        return f"{question}\nBorrower address: {entities['borrower']}"
    if operation == "account":
        return (f"{question}\nMarket address: {entities['market']}\n"
                f"Wallet address: {entities['lender']}")
    if operation in ("market", "withdrawals"):
        return f"{question}\nMarket address: {entities['market']}"
    return question


def _expected_status(mode: RouteMode, corpus_gap: bool) -> set[str]:
    if corpus_gap:
        return {"unavailable", "refused"}
    if mode in (RouteMode.REFUSE, RouteMode.REFUSE_POINT):
        return {"refused"}
    if mode == RouteMode.TRIAGE:
        return {"needs_handoff"}
    return {"answered"}


def _case_checks(item: dict, answer, repeated, expected_mode: RouteMode) -> dict:
    gap = bool(item.get("corpus_gap"))
    corpus_mode = expected_mode in (
        RouteMode.CORPUS, RouteMode.CORPUS_LIVE, RouteMode.CORRECT)
    live_mode = expected_mode in (
        RouteMode.LIVE, RouteMode.CORPUS_LIVE, RouteMode.PARTIAL)
    refusal_mode = expected_mode in (RouteMode.REFUSE, RouteMode.REFUSE_POINT)

    citation_ok = ((not corpus_mode or gap or answer.status != "answered")
                   or bool(answer.citations))
    if refusal_mode or expected_mode == RouteMode.TRIAGE or gap:
        citation_ok = citation_ok and not answer.citations and answer.live is None

    citations = {citation.evidence_id: citation for citation in answer.citations}
    claim_ok = all(
        claim.evidence_id in citations
        and citations[claim.evidence_id].quote is not None
        and claim.supporting_quote in citations[claim.evidence_id].quote
        # Until a separately pinned semantic verifier exists, the promotion
        # gate accepts only extractive claims. Paraphrase is fail-closed.
        and claim.text == claim.supporting_quote
        for claim in answer.claims)
    if corpus_mode and answer.status == "answered":
        claim_ok = claim_ok and bool(answer.claims)

    live_ok = True
    if live_mode and not gap and answer.status == "answered":
        live_ok = (answer.live is not None and repeated.live is not None
                   and answer.live.text == repeated.live.text
                   and answer.live.block_number == repeated.live.block_number
                   and answer.live.gateway_release == repeated.live.gateway_release
                   and answer.live.text in answer.text)
    elif not live_mode:
        live_ok = answer.live is None

    return {
        "route": answer.mode == expected_mode,
        "outcome": answer.status in _expected_status(expected_mode, gap),
        "citations": citation_ok,
        "claim_support": claim_ok,
        "live_determinism": live_ok,
        "refusal": (answer.status == "refused" and not answer.citations
                    and answer.live is None) if refusal_mode else True,
    }


def evaluate(engine: AnswerEngine, retriever: Retriever, questions_path: str,
             labels_path: str, policy: dict, fixture: dict,
             prerelease_available: bool = True) -> dict:
    questions_doc = _load_yaml(pathlib.Path(questions_path))
    questions = questions_doc.get("questions") or []
    if not questions:
        raise ProductEvaluationError("golden question set is empty")
    expected_ids = [item.get("id") for item in questions]
    if len(set(expected_ids)) != len(expected_ids) or None in expected_ids:
        raise ProductEvaluationError("golden question IDs are missing or duplicated")

    fixture_entities = fixture.get("entities") or {}
    required_entities = {"market", "lender", "borrower"}
    if set(fixture_entities) < required_entities:
        raise ProductEvaluationError(
            f"live fixture omits entities: {sorted(required_entities-set(fixture_entities))}")

    router = engine.router
    cases = []
    for item in questions:
        original_route = router.route(item["question"])
        expected_mode = RouteMode(item["expected"])
        question = _question_with_fixture_entities(
            item["question"], original_route, fixture_entities)
        answer = engine.answer(question)
        repeated = engine.answer(question)
        checks = _case_checks(item, answer, repeated, expected_mode)
        # The reviewed mode applies to the original wording. Fixture addresses
        # must not change it, so both routes are covered by this check.
        checks["route"] = (checks["route"]
                           and original_route.mode == expected_mode)
        cases.append({
            "id": item["id"], "expected_mode": expected_mode.value,
            "actual_mode": answer.mode.value, "risk": _risk(item, expected_mode),
            "corpus_gap": bool(item.get("corpus_gap")),
            "status": answer.status, "checks": checks,
            "release_id": answer.corpus_release_id,
            "citation_ids": [citation.evidence_id for citation in answer.citations],
            "live": ({"operation": answer.live.operation,
                      "block_number": answer.live.block_number,
                      "gateway_release": answer.live.gateway_release}
                     if answer.live else None),
            "reason": answer.refusal_reason,
        })

    retrieval_report = retrieval_evaluate(
        retriever, questions_path, labels_path, k=5)

    isolation = {"general_excludes_prerelease": False,
                 "explicit_prerelease_isolated": False}
    general = retriever.search(RetrievalRequest(
        "newV25Feature()", 1, tiers=("A",), limit_per_tier=50))
    isolation["general_excludes_prerelease"] = all(
        evidence.protocol_version != "v2.5" for evidence in general.by_tier["A"])
    if prerelease_available:
        explicit = retriever.search(RetrievalRequest(
            "v2.5 newV25Feature()", 1, protocol_version="v2.5",
            version_explicit=True, tiers=("A",), limit_per_tier=5))
        isolation["explicit_prerelease_isolated"] = (
            explicit.protocol_version == "v2.5"
            and explicit.deployment_status == "not_deployed"
            and "unaudited" in (explicit.preamble or "")
            and all(item.protocol_version == "v2.5"
                    for item in explicit.by_tier["A"]))

    unsupported = engine.answer("What is the current reserve ratio on Base?")
    out_of_scope_ok = (unsupported.status == "refused"
                       and unsupported.route.refusal_reason == "unsupported_chain"
                       and unsupported.live is None and not unsupported.citations)
    registry = engine.answer(
        "Which Wildcat markets are currently registered?")
    registry_discovery_ok = (
        registry.status == "answered"
        and registry.mode == RouteMode.LIVE
        and registry.route.live_operation == "registry"
        and registry.live is not None
        and registry.live.operation == "registry"
        and not registry.citations)

    check_names = ("route", "outcome", "citations", "claim_support",
                   "live_determinism", "refusal")
    counts = {name: sum(case["checks"][name] for case in cases)
              for name in check_names}
    totals = {
        "route": len(cases), "outcome": len(cases),
        "citations": len(cases), "claim_support": len(cases),
        "live_determinism": len(cases), "refusal": len(cases),
    }
    rates = {name: counts[name] / totals[name] for name in check_names}
    by_mode = _group(cases, "expected_mode")
    by_risk = _group(cases, "risk")
    known_gap_answers = sum(
        case["corpus_gap"] and case["status"] == "answered" for case in cases)
    gates = {
        "route_accuracy": rates["route"] >= policy["route_accuracy"],
        "outcome_accuracy": rates["outcome"] >= policy["outcome_accuracy"],
        "citation_validity": rates["citations"] >= policy["citation_validity"],
        "claim_support": rates["claim_support"] >= policy["claim_support"],
        "live_determinism": (rates["live_determinism"]
                             >= policy["live_determinism"]),
        "refusal_accuracy": rates["refusal"] >= policy["refusal_accuracy"],
        "retrieval_labels": (retrieval_report["passed"]
                             >= policy["minimum_retrieval_label_passes"]),
        "known_gaps_abstain": (known_gap_answers
                               <= policy["maximum_known_gap_answers"]),
        "version_isolation": all(isolation.values()),
        "unsupported_chain_refused": out_of_scope_ok,
        "registry_discovery": registry_discovery_ok,
    }
    failures = [{"id": case["id"],
                 "failed_checks": [name for name, ok in case["checks"].items()
                                   if not ok]}
                for case in cases if not all(case["checks"].values())]
    return {
        "candidate_release_id": retriever.main.record["release_id"],
        "prerelease_release_id": (retriever.prerelease.record["release_id"]
                                  if retriever.prerelease else None),
        "golden": {"total": len(cases), "known_gaps": sum(
            case["corpus_gap"] for case in cases)},
        "policy": policy, "counts": counts, "rates": rates,
        "groups": {"by_mode": by_mode, "by_risk": by_risk},
        "retrieval": retrieval_report, "version_isolation": isolation,
        "unsupported_chain_refused": out_of_scope_ok,
        "registry_discovery": registry_discovery_ok,
        "known_gap_answers": known_gap_answers,
        "gates": gates, "passed": all(gates.values()),
        "failures": failures, "cases": cases,
    }


def _group(cases: list[dict], field: str) -> dict:
    groups = defaultdict(list)
    for case in cases:
        groups[case[field]].append(case)
    return {key: {
        "total": len(items),
        "passed": sum(all(item["checks"].values()) for item in items),
        "failed_ids": [item["id"] for item in items
                       if not all(item["checks"].values())],
    } for key, items in sorted(groups.items())}


def compute_evaluation_id(record: dict) -> str:
    basis = {key: value for key, value in record.items()
             if key not in ("evaluation_id", "created")}
    return hashlib.sha256(_canonical(basis)).hexdigest()[:20]


def publish(artifact_root: str, record: dict) -> dict:
    root = pathlib.Path(artifact_root).resolve() / "evaluations"
    root.mkdir(parents=True, exist_ok=True)
    evaluation_id = compute_evaluation_id(record)
    record = {**record, "evaluation_id": evaluation_id}
    out_dir = root / evaluation_id
    out_path = out_dir / "evaluation.json"
    if out_dir.exists():
        if not out_path.is_file():
            raise ProductEvaluationError(f"{out_dir}: incomplete immutable evaluation")
        try:
            existing = json.loads(out_path.read_text())
        except (OSError, json.JSONDecodeError) as error:
            raise ProductEvaluationError(f"{out_path}: invalid evaluation: {error}")
        left = {k: v for k, v in existing.items() if k != "created"}
        right = {k: v for k, v in record.items() if k != "created"}
        if left != right:
            raise ProductEvaluationError(
                f"{out_path}: evaluation id collision or modified artifact")
        return existing
    temp = pathlib.Path(tempfile.mkdtemp(prefix=f".{evaluation_id}.", dir=root))
    try:
        (temp / "evaluation.json").write_text(json.dumps(record, indent=2) + "\n")
        os.replace(temp, out_dir)
    finally:
        if temp.exists():
            shutil.rmtree(temp)
    return record


def build_record(report: dict, manifest: pathlib.Path, release: pathlib.Path,
                 prerelease: pathlib.Path, questions: pathlib.Path,
                 labels: pathlib.Path, fixture: pathlib.Path) -> dict:
    return {
        "evaluation_id": "",
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "candidate_release_id": report["candidate_release_id"],
        "prerelease_release_id": report["prerelease_release_id"],
        "inputs": {
            "paths": {
                "manifest": str(manifest), "release": str(release),
                "prerelease": str(prerelease), "questions": str(questions),
                "labels": str(labels), "live_fixture": str(fixture),
            },
            "manifest_sha256": _sha256(manifest),
            "release_sha256": _sha256(release),
            "prerelease_sha256": _sha256(prerelease),
            "questions_sha256": _sha256(questions),
            "labels_sha256": _sha256(labels),
            "live_fixture_sha256": _sha256(fixture),
        },
        "tools": _tool_hashes(),
        "report": report,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--manifest", default="manifest.yaml")
    parser.add_argument("--release", required=True)
    parser.add_argument("--prerelease", required=True)
    parser.add_argument("--embedder", required=True)
    parser.add_argument("--questions", default="eval/golden-v1.yaml")
    parser.add_argument("--labels", default="eval/labels.yaml")
    parser.add_argument("--live-fixture", default="eval/live-fixture-v1.json")
    parser.add_argument("--artifacts", default="artifacts")
    args = parser.parse_args()
    paths = {name: pathlib.Path(value).resolve() for name, value in {
        "manifest": args.manifest, "release": args.release,
        "prerelease": args.prerelease, "questions": args.questions,
        "labels": args.labels, "fixture": args.live_fixture}.items()}
    try:
        fixture = json.loads(paths["fixture"].read_text())
        retriever = Retriever(str(paths["manifest"]), str(paths["release"]),
                              args.embedder, str(paths["prerelease"]))
        live_client = GatewayClient(
            str(paths["manifest"]), FixtureTransport(fixture), token="fixture")
        report = evaluate(
            AnswerEngine(retriever, live_client), retriever,
            str(paths["questions"]), str(paths["labels"]),
            _policy(paths["manifest"]), fixture)
        record = publish(args.artifacts, build_record(
            report, paths["manifest"], paths["release"], paths["prerelease"],
            paths["questions"], paths["labels"], paths["fixture"]))
    except (OSError, json.JSONDecodeError, RetrievalError, EvaluationError,
            ProductEvaluationError) as error:
        print(f"FATAL: {error}", file=sys.stderr)
        return 1
    print(f"evaluation {record['evaluation_id']}  passed={report['passed']}")
    print(f"golden     {report['golden']['total']} questions, "
          f"{len(report['failures'])} failed")
    print(f"retrieval  {report['retrieval']['passed']}/"
          f"{report['retrieval']['total']} labels")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
