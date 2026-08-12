#!/usr/bin/env python3
"""Publish a content-addressed, answer-free Aleph coverage silhouette."""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import pathlib
import re
import shutil
import tempfile
from datetime import datetime, timezone


SCHEMA_VERSION = 2
_FORBIDDEN_KEYS = {
    "answer", "answer_shape", "breadcrumb", "citation_ids", "display_text",
    "embed_text", "line", "model_text", "note", "path", "question",
    "reason", "source_ref", "text", "url",
}
_ADDRESS = re.compile(r"(?i)0x[0-9a-f]{40}")
_URL = re.compile(r"https?://")
_SLUG = re.compile(r"[^a-z0-9]+")


class CoverageError(RuntimeError):
    """Inputs or output violate the coverage-silhouette boundary."""


def _canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: pathlib.Path) -> dict:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise CoverageError(f"cannot load JSON {path}: {error}") from error
    if not isinstance(value, dict):
        raise CoverageError(f"{path}: expected a JSON object")
    return value


def _load_yaml(path: pathlib.Path) -> dict:
    try:
        import yaml
    except ImportError as error:
        raise CoverageError("coverage.py needs pyyaml") from error
    try:
        value = yaml.safe_load(path.read_bytes())
    except (OSError, ValueError) as error:
        raise CoverageError(f"cannot load YAML {path}: {error}") from error
    if not isinstance(value, dict):
        raise CoverageError(f"{path}: expected a YAML mapping")
    return value


def _slug(value: str) -> str:
    return _SLUG.sub("-", value.casefold()).strip("-")


def _document_topic(path: str) -> str:
    pure = pathlib.PurePosixPath(path)
    stem = pure.stem
    parents = [part for part in pure.parts[:-1] if part.casefold() not in {
        "docs", "src", "overview", "using-wildcat", "technical-overview",
    }]
    parts = parents[-1:] + [stem]
    topic = _slug("-".join(parts))
    if not topic:
        raise CoverageError("corpus path cannot produce a safe topic slug")
    return topic


def _source_and_path(evidence_id: str) -> tuple[str, str] | None:
    source, separator, remainder = evidence_id.partition(":")
    if not separator or not source or not remainder:
        return None
    path = remainder.split("#", 1)[0]
    if ":" in path:
        path = path.split(":", 1)[0]
    return source, path


def _shape(question: str) -> tuple[str, ...]:
    shapes = []
    lowered = question.casefold()
    length = len(question)
    shapes.append("length-short" if length <= 60 else
                  "length-medium" if length <= 140 else "length-long")
    if question.count("?") > 1:
        shapes.append("multi-part")
    if "<market>" in lowered or "market address" in lowered:
        shapes.append("market-context")
    if "<borrower>" in lowered or "borrower address" in lowered:
        shapes.append("borrower-context")
    if any(token in lowered.split() for token in ("i", "my", "we", "our")):
        shapes.append("first-person")
    return tuple(shapes)


def _counts(values) -> dict[str, int]:
    return dict(sorted(collections.Counter(values).items()))


def _verify_public(value, trail: tuple[str, ...] = ()) -> None:
    if isinstance(value, dict):
        forbidden = _FORBIDDEN_KEYS.intersection(value)
        if forbidden:
            raise CoverageError(
                f"silhouette leaks forbidden keys at {'.'.join(trail) or '<root>'}: "
                + ", ".join(sorted(forbidden)))
        for key, item in value.items():
            _verify_public(item, (*trail, str(key)))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _verify_public(item, (*trail, str(index)))
    elif isinstance(value, str):
        if _ADDRESS.search(value) or _URL.search(value):
            raise CoverageError(
                f"silhouette contains an address or URL at {'.'.join(trail)}")


def _load_chunks(path: pathlib.Path, build_id: str) -> list[dict]:
    chunks = []
    try:
        lines = path.read_text().splitlines()
    except OSError as error:
        raise CoverageError(f"cannot read corpus chunks: {error}") from error
    for number, line in enumerate(lines, 1):
        try:
            item = json.loads(line)
        except json.JSONDecodeError as error:
            raise CoverageError(f"invalid chunk JSON at line {number}: {error}") from error
        if not isinstance(item, dict) or item.get("corpus_build_id") != build_id:
            raise CoverageError(f"chunk {number} is not bound to corpus {build_id}")
        for required in ("id", "path", "tier", "source_type"):
            if not isinstance(item.get(required), str) or not item[required]:
                raise CoverageError(f"chunk {number} lacks {required}")
        chunks.append(item)
    if not chunks:
        raise CoverageError("corpus has no chunks")
    return chunks


def build(release_path: pathlib.Path, manifest_path: pathlib.Path,
          questions_path: pathlib.Path, topics_path: pathlib.Path,
          pointer_path: pathlib.Path) -> dict:
    release_path = release_path.resolve()
    artifact_root = release_path.parents[2]
    release = _load_json(release_path)
    release_id = release.get("release_id")
    if (not isinstance(release_id, str)
            or release_path.parent.name != release_id):
        raise CoverageError("release path and release identity differ")
    if release.get("promotable") is not True:
        raise CoverageError("coverage requires a promotable release")
    pointer = _load_json(pointer_path.resolve())
    if (pointer.get("schema_version") != 2
            or pointer.get("release_id") != release_id
            or not isinstance(pointer.get("evolution"), int)
            or not isinstance(pointer.get("generation"), int)
            or pointer["evolution"] != release.get("evolution", {}).get("number")):
        raise CoverageError("coverage requires the matching active evolution/generation")

    manifest_sha = _sha256(manifest_path)
    if release.get("manifest", {}).get("sha256") != manifest_sha:
        raise CoverageError("manifest hash differs from release")
    corpus = release.get("corpus") or {}
    build_id = corpus.get("build_id")
    chunks_path = artifact_root / str(corpus.get("path")) / "chunks.jsonl"
    if _sha256(chunks_path) != corpus.get("chunks_sha256"):
        raise CoverageError("corpus chunk hash differs from release")
    chunks = _load_chunks(chunks_path, build_id)

    evaluation_ref = release.get("evaluation") or {}
    evaluation_path = artifact_root / str(evaluation_ref.get("path"))
    if _sha256(evaluation_path) != evaluation_ref.get("sha256"):
        raise CoverageError("evaluation hash differs from release")
    evaluation = _load_json(evaluation_path)
    if (evaluation.get("evaluation_id") != evaluation_ref.get("evaluation_id")
            or evaluation.get("report", {}).get("passed") is not True):
        raise CoverageError("release evaluation identity or status is invalid")
    questions_sha = _sha256(questions_path)
    inputs = evaluation.get("inputs") or {}
    if (inputs.get("questions_sha256") != questions_sha
            or inputs.get("manifest_sha256") != manifest_sha):
        raise CoverageError("evaluation is not bound to supplied questions and manifest")

    golden = _load_yaml(questions_path)
    questions = golden.get("questions")
    if not isinstance(questions, list) or not all(isinstance(x, dict) for x in questions):
        raise CoverageError("golden question list is invalid")
    report = evaluation.get("report") or {}
    if (len(questions) != report.get("golden", {}).get("total")
            or sum(bool(x.get("corpus_gap")) for x in questions)
            != report.get("golden", {}).get("known_gaps")):
        raise CoverageError("golden counts do not reconcile to evaluation")

    topic_doc = _load_yaml(topics_path)
    topic_map = topic_doc.get("topics")
    if topic_doc.get("schema_version") != 1 or not isinstance(topic_map, dict):
        raise CoverageError("coverage topic map is invalid")
    prefixes = {str(item.get("id", ""))[:1] for item in questions}
    if prefixes != set(topic_map) or any(_slug(value) != value
                                         for value in topic_map.values()):
        raise CoverageError("coverage topic map does not match golden sections")

    source_stats = collections.defaultdict(lambda: {
        "chunk_count": 0, "documents": set(), "tiers": set(),
        "source_types": set(), "protocol_versions": set(),
        "deployment_statuses": set(),
    })
    corpus_topics = collections.defaultdict(lambda: {
        "chunk_count": 0, "documents": set(), "tiers": set(),
        "source_types": set(), "protocol_versions": set(),
        "deployment_statuses": set(), "answer_case_count": 0,
    })
    for item in chunks:
        source = item["id"].partition(":")[0]
        path = item["path"]
        topic = _document_topic(path)
        for target in (source_stats[source], corpus_topics[(source, topic)]):
            target["chunk_count"] += 1
            target["documents"].add(path)
            target["tiers"].add(item["tier"])
            target["source_types"].add(item["source_type"])
            if item.get("protocol_version"):
                target["protocol_versions"].add(item["protocol_version"])
            if item.get("deployment_status"):
                target["deployment_statuses"].add(item["deployment_status"])

    cases = report.get("cases")
    if not isinstance(cases, list) or len(cases) != len(questions):
        raise CoverageError("evaluation case count is invalid")
    for case in cases:
        seen = set()
        for evidence_id in case.get("citation_ids") or []:
            parsed = _source_and_path(evidence_id)
            if parsed:
                seen.add((parsed[0], _document_topic(parsed[1])))
        for key in seen:
            if key in corpus_topics:
                corpus_topics[key]["answer_case_count"] += 1

    def public_stats(item):
        return {
            "chunk_count": item["chunk_count"],
            "document_count": len(item["documents"]),
            "tiers": sorted(item["tiers"]),
            "source_types": sorted(item["source_types"]),
            "protocol_versions": sorted(item["protocol_versions"]),
            "deployment_statuses": sorted(item["deployment_statuses"]),
        }

    evaluation_topics = []
    for prefix, label in sorted(topic_map.items()):
        members = [item for item in questions if item["id"].startswith(prefix)]
        case_members = [item for item in cases if item["id"].startswith(prefix)]
        live_operations = [item["live"]["operation"] for item in case_members
                           if item.get("live")]
        evaluation_topics.append({
            "topic": label,
            "total": len(members),
            "known_gaps": sum(bool(item.get("corpus_gap")) for item in members),
            "routes": _counts(item["expected"] for item in members),
            "risks": _counts(item["risk"] for item in case_members),
            "live_operations": _counts(live_operations),
        })

    record = {
        "schema_version": SCHEMA_VERSION,
        "silhouette_id": "",
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "binding": {
            "evolution": release["evolution"]["number"],
            "generation": pointer["generation"],
            "evolution_contract": release["evolution"]["contract"],
            "release_id": release_id,
            "release_sha256": _sha256(release_path),
            "manifest_sha256": manifest_sha,
            "corpus_build_id": build_id,
            "corpus_chunks_sha256": corpus["chunks_sha256"],
            "evaluation_id": evaluation["evaluation_id"],
            "evaluation_sha256": evaluation_ref["sha256"],
            "questions_sha256": questions_sha,
            "topic_map_sha256": _sha256(topics_path),
        },
        "corpus": {
            "total_chunks": len(chunks),
            "sources": [
                {"source": source, **public_stats(stats)}
                for source, stats in sorted(source_stats.items())
            ],
            "topics": [
                {
                    "topic_id": hashlib.sha256(
                        f"{source}:{topic}".encode()).hexdigest()[:16],
                    "source": source,
                    "topic": topic,
                    **public_stats(stats),
                    "answer_case_count": stats["answer_case_count"],
                }
                for (source, topic), stats in sorted(corpus_topics.items())
            ],
        },
        "evaluation": {
            "total": len(questions),
            "known_gaps": sum(bool(item.get("corpus_gap")) for item in questions),
            "routes": _counts(item["expected"] for item in questions),
            "risks": _counts(item["risk"] for item in cases),
            "frequencies": _counts(item.get("frequency", "unspecified")
                                   for item in questions),
            "registers": _counts(item.get("register", "ordinary")
                                 for item in questions),
            "live_operations": _counts(
                item["live"]["operation"] for item in cases if item.get("live")),
            "question_shapes": _counts(
                shape for item in questions for shape in _shape(item["question"])),
            "topics": evaluation_topics,
        },
        "boundary": {
            "answer_content": "excluded",
            "corpus_content": "excluded",
            "question_content": "excluded",
            "human_identity": "excluded",
            "purpose": "question-generation-only",
            "factual_grading": "forbidden",
            "autonomous_corpus_writes": "forbidden",
        },
    }
    _verify_public(record)
    record["silhouette_id"] = compute_id(record)
    return record


def compute_id(record: dict) -> str:
    basis = {key: value for key, value in record.items()
             if key not in ("silhouette_id", "created")}
    return hashlib.sha256(_canonical(basis)).hexdigest()[:20]


def publish(artifact_root: pathlib.Path, record: dict) -> pathlib.Path:
    _verify_public(record)
    expected = compute_id(record)
    if record.get("silhouette_id") != expected:
        raise CoverageError("silhouette identity does not match content")
    root = artifact_root.resolve() / "coverage"
    root.mkdir(parents=True, exist_ok=True)
    out_dir = root / expected
    out_path = out_dir / "silhouette.json"
    if out_dir.exists():
        existing = _load_json(out_path)
        left = {key: value for key, value in existing.items() if key != "created"}
        right = {key: value for key, value in record.items() if key != "created"}
        if left != right:
            raise CoverageError(f"{out_path}: modified immutable silhouette")
        return out_path
    temp = pathlib.Path(tempfile.mkdtemp(prefix=f".{expected}.", dir=root))
    try:
        (temp / "silhouette.json").write_text(
            json.dumps(record, indent=2, sort_keys=True) + "\n")
        os.replace(temp, out_dir)
    finally:
        if temp.exists():
            shutil.rmtree(temp)
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", required=True)
    parser.add_argument("--manifest", default="manifest.yaml")
    parser.add_argument("--questions", default="eval/golden-v1.yaml")
    parser.add_argument("--topics", default="eval/coverage-topics-v1.yaml")
    parser.add_argument("--artifacts", default="artifacts")
    parser.add_argument("--pointer", required=True)
    args = parser.parse_args()
    try:
        record = build(
            pathlib.Path(args.release), pathlib.Path(args.manifest).resolve(),
            pathlib.Path(args.questions).resolve(),
            pathlib.Path(args.topics).resolve(),
            pathlib.Path(args.pointer).resolve())
        out = publish(pathlib.Path(args.artifacts), record)
    except (CoverageError, OSError, KeyError, TypeError, ValueError) as error:
        print(f"FATAL: {error}")
        return 1
    print(f"coverage {record['silhouette_id']}  {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
