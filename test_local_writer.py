#!/usr/bin/env python3
"""Adversarial tests for Aleph's fail-closed local shadow writer."""

from __future__ import annotations

import io
import json
import pathlib
import shutil
import sys
import tempfile

import agent
import local_writer
import retrieval
import test_agent


FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if ok else 'FAIL'} {name}"
          + (f" — {detail}" if detail and not ok else ""))
    if not ok:
        FAILURES.append(name)


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


class Ollama:
    def __init__(self, candidate: object,
                 digest: str = "a951a23b46a1" + "0" * 52):
        self.candidate = candidate
        self.digest = digest
        self.requests = []

    def __call__(self, request, timeout):
        self.requests.append((request, timeout))
        if request.full_url.endswith("/api/tags"):
            value = {"models": [{
                "name": "gpt-oss:120b", "digest": self.digest}]}
        else:
            body = json.loads(request.data)
            user = json.loads(body["messages"][1]["content"])
            check("model input has only question, route, and bounded evidence",
                  set(user) == {"question", "route", "evidence"})
            serialized = json.dumps(body).casefold()
            check("model input excludes operational and private metadata",
                  all(value not in serialized for value in (
                      "telegram", "token", "gateway", "expected_outcome",
                      "activation", "generation", "wallet address")))
            check("GPT-OSS reasoning is low and output is schema-bound",
                  body["think"] == "low" and body["stream"] is False
                  and isinstance(body["format"], dict))
            value = {
                "done_reason": "stop",
                "message": {
                    "content": json.dumps(self.candidate),
                    "thinking": "must never enter the observation",
                },
            }
        return Response(json.dumps(value).encode())


def evidence() -> tuple[retrieval.Evidence, ...]:
    text = (
        "A withdrawal cycle begins when the first lender queues a withdrawal. "
        "It ends after the configured cycle duration.")
    return (retrieval.Evidence(
        id="wildcat-docs:withdrawals", tier="A", score=0.9,
        semantic_score=0.9, semantic_rank=1, lexical_rank=1,
        lexical_score=1.0, kind="Section", source_type="markdown",
        path="overview/withdrawals.md", line=10,
        breadcrumb="Overview › Withdrawals", display_text=text,
        model_text=text, synthesised=False, corpus_build_id="build-1",
        source_ref="wildcat-docs@" + "a" * 40, protocol_version="v2.0",
        deployment_status="deployed", effective_date=None,
        doc_version=None, detail={}, release_id="release-1"),)


def route() -> agent.Route:
    return agent.Router().route("How does a withdrawal cycle begin?")


def observer(transport, monotonic=lambda: 1.0):
    return local_writer.OllamaEvidenceObserver(
        url="http://127.0.0.1:11435", model="gpt-oss:120b",
        model_id="a951a23b46a1", opener=transport,
        monotonic=monotonic)


def run(tmp: pathlib.Path) -> None:
    supplied = evidence()
    authoritative = agent.ExtractiveWriter().write(
        "How does a withdrawal cycle begin?", supplied, route())
    candidate = {
        "claims": [{
            "text": "The first lender request begins the cycle.",
            "evidence_id": supplied[0].id,
            "supporting_quote": (
                "A withdrawal cycle begins when the first lender queues a "
                "withdrawal."),
        }],
        "abstain_reason": None,
    }

    print("\nL1 — model identity and output are bounded and discarded")
    times = iter((1.0, 1.125))
    transport = Ollama(candidate)
    observed = observer(transport, lambda: next(times)).observe(
        "How does a withdrawal cycle begin?", supplied, route(), authoritative)
    public = observed.public()
    check("a supported structured candidate is diagnostically valid",
          observed.status == "valid" and observed.latency_ms == 125)
    check("semantic truth is explicitly not inferred from a matching quote",
          observed.semantic_status == "unverified")
    check("candidate prose, quote, evidence ID, and reasoning are discarded",
          all(value not in json.dumps(public) for value in (
              "first lender", supplied[0].id, "must never")))
    check("identity is checked before every generation",
          len(transport.requests) == 2
          and transport.requests[0][0].full_url.endswith("/api/tags"))

    print("\nL2 — invalid evidence and transport fail closed")
    bad_cases = (
        ({**candidate, "claims": [{**candidate["claims"][0],
          "evidence_id": "not-supplied"}]}, "unknown_evidence"),
        ({**candidate, "claims": [{**candidate["claims"][0],
          "supporting_quote": "invented quote"}]},
         "forged_supporting_quote"),
        ({"claims": [], "abstain_reason": None}, "empty_candidate"),
    )
    for value, reason in bad_cases:
        result = observer(Ollama(value)).observe(
            "How does a withdrawal cycle begin?", supplied, route(),
            authoritative)
        check(f"{reason} is rejected",
              result.status == "rejected" and reason in result.reasons,
              str(result.reasons))
    mismatch = observer(Ollama(candidate, "b" * 64)).observe(
        "How does a withdrawal cycle begin?", supplied, route(), authoritative)
    check("a changed model digest falls back",
          mismatch.status == "fallback"
          and "identity differs" in mismatch.reasons[0])

    def timeout(*_, **__):
        raise TimeoutError("private transport detail")

    timed_out = observer(timeout).observe(
        "How does a withdrawal cycle begin?", supplied, route(), authoritative)
    check("timeout details do not escape",
          timed_out.reasons == ("Ollama request failed or timed out",))

    print("\nL3 — shadow cannot change the authoritative answer")

    class StubObserver:
        model = "gpt-oss:120b"
        model_id = "a951a23b46a1"

        def observe(self, question, evidence, route, authoritative):
            return local_writer.WriterObservation(
                "shadow", "valid", (), self.model, self.model_id,
                evidence_count=len(evidence), claim_count=1,
                exact_claim_count=0, authoritative_evidence_overlap=1)

    components = tmp / "components"
    components.mkdir()
    retriever, live_client, _ = test_agent.components(components)
    extractive = agent.AnswerEngine(retriever, live_client)
    shadow_writer = local_writer.ShadowEvidenceWriter(StubObserver())
    shadow = agent.AnswerEngine(
        retriever, live_client, writer=shadow_writer)
    question = "How does the withdrawal cycle work?"
    expected = extractive.answer(question)
    actual = shadow.answer(question)
    check("shadow answer text remains byte-for-byte extractive",
          actual.text == expected.text)
    check("claims and citations remain authoritative",
          actual.claims == expected.claims
          and actual.citations == expected.citations)
    check("only scrubbed shadow metadata is attached",
          actual.writer_shadow is not None
          and all(value not in json.dumps(actual.writer_shadow) for value in (
              "first lender", "wildcat-docs:", "must never")))
    status = shadow_writer.status()["local_writer"]
    check("aggregate counters are available without generated content",
          status["counts"] == {
              "total": 1, "valid": 1, "rejected": 0, "fallback": 0})

    class BrokenObserver(StubObserver):
        def observe(self, *args, **kwargs):
            raise RuntimeError("generated secret")

    broken_writer = local_writer.ShadowEvidenceWriter(BrokenObserver())
    broken = agent.AnswerEngine(
        retriever, live_client, writer=broken_writer).answer(question)
    check("an unexpected shadow failure preserves the authoritative answer",
          broken.text == expected.text
          and broken.writer_shadow["status"] == "fallback"
          and "generated secret" not in json.dumps(broken.writer_shadow))

    print("\nL4 — disabled composition is inert")
    config = local_writer.LocalWriterConfig.from_env({})
    writer, status_provider = local_writer.compose_writer(config)
    check("disabled mode uses only the extractive writer",
          isinstance(writer, agent.ExtractiveWriter)
          and status_provider()["local_writer"]["mode"] == "disabled")
    refused = ""
    try:
        local_writer.LocalWriterConfig.from_env({
            "ALEPH_LOCAL_WRITER_MODEL": "gpt-oss:120b"})
    except local_writer.LocalWriterError as error:
        refused = str(error)
    check("partial disabled configuration fails closed",
          "must not configure" in refused, refused)


def main() -> int:
    root = pathlib.Path(tempfile.mkdtemp(prefix="aleph-local-writer-test-"))
    try:
        run(root)
    finally:
        shutil.rmtree(root)
    if FAILURES:
        print(f"\n{len(FAILURES)} failure(s):")
        for name in FAILURES:
            print(f"- {name}")
        return 1
    print("\nAll local-writer checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
