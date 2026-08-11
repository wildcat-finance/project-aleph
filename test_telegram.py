#!/usr/bin/env python3
"""Integration tests for Telegram parsing, delivery, limits, and handoffs."""

from __future__ import annotations

import pathlib
import shutil
import sys
import tempfile
from types import SimpleNamespace

import agent
import telegram
import test_agent


FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if ok else 'FAIL'} {name}"
          + (f" — {detail}" if detail and not ok else ""))
    if not ok:
        FAILURES.append(name)


class FakeAPI:
    def __init__(self, updates=None, privacy=True, webhook=""):
        self.updates = updates or []
        self.privacy = privacy
        self.webhook = webhook
        self.calls = []
        self.sent = []
        self.next_message_id = 1000
        self.fail_send = False

    def call(self, method: str, payload=None):
        self.calls.append((method, payload or {}))
        if method == "getMe":
            return {"id": 99, "is_bot": True, "username": "AlephTestBot",
                    "can_read_all_group_messages": not self.privacy}
        if method == "getWebhookInfo":
            return {"url": self.webhook, "pending_update_count": 0}
        if method == "getUpdates":
            return self.updates
        if method == "sendMessage":
            if self.fail_send:
                raise telegram.TelegramError("fixture send failed")
            self.sent.append(payload)
            self.next_message_id += 1
            return {"message_id": self.next_message_id}
        raise AssertionError(method)


class CountingEngine:
    def __init__(self, engine):
        self.engine = engine
        self.questions = []

    def answer(self, question):
        self.questions.append(question)
        return self.engine.answer(question)


class StaticEngine:
    def __init__(self, text: str = "answer", error: Exception | None = None):
        self.text = text
        self.error = error

    def answer(self, question):
        if self.error:
            raise self.error
        return SimpleNamespace(status="answered", triage=None, text=self.text)


class FakeSink:
    def __init__(self):
        self.payloads = []

    def send(self, payload):
        self.payloads.append(payload)
        return "SUP-123"


def update(update_id: int, text: str, *, chat_id: int = 1,
           user_id: int = 7, chat_type: str = "private",
           message_id: int | None = None, thread_id: int | None = None,
           reply_to_bot: bool = False, is_bot: bool = False) -> dict:
    message = {
        "message_id": message_id or update_id + 100,
        "from": {"id": user_id, "is_bot": is_bot},
        "chat": {"id": chat_id, "type": chat_type}, "text": text,
    }
    if thread_id is not None:
        message["message_thread_id"] = thread_id
    if reply_to_bot:
        message["reply_to_message"] = {
            "message_id": 55,
            "from": {"id": 99, "is_bot": True, "username": "AlephTestBot"},
        }
    return {"update_id": update_id, "message": message}


def adapter(tmp: pathlib.Path, engine, api: FakeAPI,
            sink=None, limit: int = 20,
            peer_bot_ids: tuple[int, ...] = ()) -> telegram.TelegramAdapter:
    result = telegram.TelegramAdapter(
        engine, api, telegram.OffsetStore(str(tmp / "offset.json")),
        handoff_sink=sink, max_workers=3, user_limit=limit,
        peer_bot_ids=peer_bot_ids)
    result.startup()
    return result


def run(tmp: pathlib.Path) -> None:
    retriever, live_client, _ = test_agent.components(tmp)
    real_engine = CountingEngine(agent.AnswerEngine(retriever, live_client))

    print("\nTG1 — startup enforces long polling and group privacy")
    refused = ""
    try:
        adapter(tmp / "privacy", real_engine, FakeAPI(privacy=False))
    except telegram.TelegramError as error:
        refused = str(error)
    check("privacy mode disabled is a startup failure",
          "privacy mode is disabled" in refused, refused)
    refused = ""
    try:
        adapter(tmp / "webhook", real_engine,
                FakeAPI(webhook="https://example.invalid/hook"))
    except telegram.TelegramError as error:
        refused = str(error)
    check("an active webhook is never silently deleted",
          "webhook is active" in refused, refused)

    print("\nTG2 — relevant messages preserve answer and reply identity")
    api = FakeAPI([update(10, "/ask What does exactIdentifier(uint256) do?")])
    service = adapter(tmp / "private", real_engine, api)
    check("one update is answered and checkpointed", service.run_once() == 1
          and service.offset_store.load() == 11)
    text = "".join(payload["text"] for payload in api.sent)
    check("the answer engine's citation text reaches Telegram unchanged",
          "Sources" in text and "/blob/" in text)
    check("delivery replies to the triggering message and disables previews",
          api.sent[0]["reply_parameters"]["message_id"] == 110
          and api.sent[0]["link_preview_options"] == {"is_disabled": True})
    poll = next(payload for method, payload in api.calls if method == "getUpdates")
    check("polling is message-only and uses the durable offset",
          poll["allowed_updates"] == ["message"] and poll["offset"] == 0
          and poll["timeout"] == 30)

    group_api = FakeAPI([
        update(20, "ambient room text", chat_id=-1, chat_type="supergroup"),
        update(21, "@AlephTestBot How does the withdrawal cycle work?",
               chat_id=-1, chat_type="supergroup", thread_id=88),
        update(22, "What does reserve ratio mean?", chat_id=-1,
               chat_type="supergroup", reply_to_bot=True),
        update(23, "/ask@AnotherBot ignore me", chat_id=-1,
               chat_type="supergroup"),
    ])
    before = len(real_engine.questions)
    group = adapter(tmp / "group", real_engine, group_api)
    group.process_updates(group_api.updates)
    check("ambient group text and commands for other bots are ignored",
          len(real_engine.questions) - before == 2)
    check("mentions and replies are handled inside the original topic",
          len(group_api.sent) == 2
          and all(item["message_thread_id"] == 88
                  for item in group_api.sent[:1]))

    peer_api = FakeAPI([
        update(24, "/ask@AlephTestBot approved question", chat_id=-1,
               chat_type="supergroup", user_id=500, is_bot=True),
        update(25, "/ask@AlephTestBot unapproved question", chat_id=-1,
               chat_type="supergroup", user_id=501, is_bot=True),
        update(26, "ambient bot text", chat_id=-1, chat_type="supergroup",
               user_id=500, is_bot=True),
        update(27, "/ask untargeted", chat_id=-1, chat_type="supergroup",
               user_id=500, is_bot=True),
        update(28, "/confirm_handoff", chat_id=-1, chat_type="supergroup",
               user_id=500, is_bot=True),
    ])
    peer_engine = CountingEngine(StaticEngine())
    peer = adapter(tmp / "peer", peer_engine, peer_api,
                   peer_bot_ids=(500,))
    peer.process_updates(peer_api.updates)
    check("only allowlisted bots can issue explicitly targeted questions",
          peer_engine.questions == ["approved question"]
          and len(peer_api.sent) == 1)
    check("peer bots cannot use ambient, untargeted, or handoff paths",
          peer.offset_store.load() == 29 and not peer.pending)

    print("\nTG3 — length, failures, rate limits, and offsets fail safely")
    long_text = ("paragraph line\n\n" * 700) + "stable-source-link"
    chunks = telegram.split_message(long_text)
    check("4096-byte chunks reconstruct the exact answer",
          len(chunks) > 2 and max(map(len, chunks)) <= 4096
          and "".join(chunks) == long_text)
    long_api = FakeAPI([update(30, "question")])
    long_service = adapter(tmp / "long", StaticEngine(long_text), long_api)
    long_service.run_once()
    check("long replies chain to the preceding Telegram message",
          len(long_api.sent) == len(chunks)
          and long_api.sent[1]["reply_parameters"]["message_id"] == 1001)

    error_api = FakeAPI([update(40, "question")])
    error_service = adapter(
        tmp / "error", StaticEngine(error=RuntimeError("secret internals")),
        error_api)
    error_service.run_once()
    check("unexpected errors expose no internal detail",
          "secret internals" not in error_api.sent[0]["text"]
          and "No answer or handoff" in error_api.sent[0]["text"])

    send_api = FakeAPI([update(50, "question")])
    send_service = adapter(tmp / "send", StaticEngine(), send_api)
    send_api.fail_send = True
    refused = ""
    try:
        send_service.run_once()
    except telegram.TelegramError as error:
        refused = str(error)
    check("a failed send does not confirm the update",
          "send failed" in refused and send_service.offset_store.load() == 0)

    rate_api = FakeAPI([update(60, "one"), update(61, "two")])
    rate_engine = CountingEngine(StaticEngine())
    rate_service = adapter(tmp / "rate", rate_engine, rate_api, limit=1)
    rate_service.run_once()
    check("per-chat/user admission is bounded before the answer engine",
          rate_engine.questions == ["one"]
          and "rate-limited" in rate_api.sent[1]["text"])

    print("\nTG4 — handoff requires a separate explicit confirmation")
    sink = FakeSink()
    triage_api = FakeAPI([
        update(70, "Deposit fails with an error — screenshot attached."),
        update(71, "/handoff page_or_action=deposit; chain_id=1; "
               "wallet_type=browser; exact_error=reverted"),
        update(72, "/confirm_handoff"),
    ])
    triage = adapter(tmp / "triage", real_engine, triage_api, sink=sink)
    triage.process_updates([triage_api.updates[0]])
    check("triage prepares state but contacts nobody",
          not sink.payloads and (1, 7) in triage.pending)
    triage.process_updates([triage_api.updates[1]])
    check("field collection returns a preview and still contacts nobody",
          not sink.payloads and "Nothing has been sent" in triage_api.sent[-1]["text"])
    triage.process_updates([triage_api.updates[2]])
    check("only explicit confirmation invokes the configured sink",
          len(sink.payloads) == 1 and sink.payloads[0].fields["chain_id"] == "1"
          and len(sink.payloads[0].handoff_id) == 16
          and "SUP-123" in triage_api.sent[-1]["text"]
          and (1, 7) not in triage.pending)


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
