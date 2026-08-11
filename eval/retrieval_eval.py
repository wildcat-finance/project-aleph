#!/usr/bin/env python3
"""Run retrieval labels against a real immutable Aleph release artifact."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from retrieval import RetrievalRequest, Retriever, RetrievalError  # noqa: E402


class EvaluationError(Exception):
    """The evaluation inputs are incomplete or incoherent."""


def evaluate(retriever: Retriever, questions_path: str, labels_path: str,
             k: int = 5) -> dict:
    try:
        import yaml
    except ImportError:
        raise EvaluationError("retrieval_eval.py needs pyyaml")
    questions_doc = yaml.safe_load(pathlib.Path(questions_path).read_bytes())
    labels = yaml.safe_load(pathlib.Path(labels_path).read_bytes())
    questions = {item["id"]: item for item in questions_doc["questions"]}
    missing = sorted(set(labels) - set(questions))
    if missing:
        raise EvaluationError(f"labels name unknown questions: {missing}")

    cases = []
    for question_id, needles in labels.items():
        question = questions[question_id]["question"]
        response = retriever.search(RetrievalRequest(
            query=question, chain_id=1, tiers=("A", "B"), limit_per_tier=k))
        evidence = [item for items in response.by_tier.values() for item in items]
        matches = [needle for needle in needles
                   if any(needle.lower() in item.model_text.lower()
                          for item in evidence)]
        cases.append({
            "id": question_id, "question": question, "passed": bool(matches),
            "matched_labels": matches,
            "evidence_ids": [item.id for item in evidence],
        })
    passed = sum(case["passed"] for case in cases)
    return {"release_id": retriever.main.record["release_id"], "k_per_tier": k,
            "passed": passed, "total": len(cases),
            "recall": passed / len(cases) if cases else 1.0, "cases": cases}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--manifest", default="manifest.yaml")
    parser.add_argument("--release", required=True,
                        help="path to the main release.json")
    parser.add_argument("--embedder", required=True)
    parser.add_argument("--questions", default="eval/golden-v1.yaml")
    parser.add_argument("--labels", default="eval/labels.yaml")
    parser.add_argument("-k", type=int, default=5)
    parser.add_argument("--json", dest="json_path")
    args = parser.parse_args()
    try:
        retriever = Retriever(args.manifest, args.release, args.embedder)
        report = evaluate(retriever, args.questions, args.labels, args.k)
    except (RetrievalError, EvaluationError) as error:
        print(f"FATAL: {error}", file=sys.stderr)
        return 1
    for case in report["cases"]:
        print(f"{'ok  ' if case['passed'] else 'FAIL'} {case['id']}"
              + ("" if case["passed"] else
                 f"  top: {', '.join(case['evidence_ids'][:4])}"))
    print(f"\n{report['passed']}/{report['total']} labels passed "
          f"at k={report['k_per_tier']} per tier")
    if args.json_path:
        pathlib.Path(args.json_path).write_text(
            json.dumps(report, indent=2) + "\n")
    return report["total"] - report["passed"]


if __name__ == "__main__":
    sys.exit(main())
