#!/usr/bin/env python3
"""Integration tests for Telegram parsing, delivery, limits, and handoffs."""

from __future__ import annotations

import pathlib
import shutil
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import agent
import live
import telegram
import test_agent
import test_live


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
        self.rich_sent = []
        self.actions = []
        self.menus = []
        self.next_message_id = 1000
        self.fail_send = False
        self.fail_html = False
        self.fail_rich = False
        self.lose_rich_response = False
        self.poll_timeout = False
        self.send_timeout = False

    def call(self, method: str, payload=None):
        self.calls.append((method, payload or {}))
        if method == "getMe":
            return {"id": 99, "is_bot": True, "username": "AlephTestBot",
                    "can_read_all_group_messages": not self.privacy}
        if method == "getWebhookInfo":
            return {"url": self.webhook, "pending_update_count": 0}
        if method == "getUpdates":
            if self.poll_timeout:
                raise telegram.TelegramTimeout("fixture poll timed out")
            return self.updates
        if method == "sendChatAction":
            self.actions.append(payload)
            return True
        if method == "setMyCommands":
            self.menus.append(payload)
            return True
        if method == "sendMessage":
            if self.send_timeout:
                raise telegram.TelegramTimeout("fixture send timed out")
            if self.fail_send:
                raise telegram.TelegramError("fixture send failed")
            if self.fail_html and "parse_mode" in payload:
                raise telegram.TelegramRefused("fixture html send refused")
            self.sent.append(payload)
            self.next_message_id += 1
            return {"message_id": self.next_message_id}
        if method == "sendRichMessage":
            if self.fail_rich:
                raise telegram.TelegramRefused("fixture rich send refused")
            if self.lose_rich_response:
                raise telegram.TelegramError("fixture rich response lost")
            self.rich_sent.append(payload)
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
            peer_bot_ids: tuple[int, ...] = (),
            rich_messages: bool = False,
            ping_status=None, ping_status_provider=None,
            monotonic_clock=time.monotonic) -> telegram.TelegramAdapter:
    result = telegram.TelegramAdapter(
        engine, api, telegram.OffsetStore(str(tmp / "offset.json")),
        handoff_sink=sink, max_workers=3, user_limit=limit,
        peer_bot_ids=peer_bot_ids, rich_messages=rich_messages,
        ping_status=ping_status, ping_status_provider=ping_status_provider,
        monotonic_clock=monotonic_clock)
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
    check("the answer engine's citations reach Telegram with source links",
          "Sources" in text and "/blob/" in text)
    check("delivery replies to the triggering message and disables previews",
          api.sent[0]["reply_parameters"]["message_id"] == 110
          and api.sent[0]["link_preview_options"] == {"is_disabled": True})
    poll = next(payload for method, payload in api.calls if method == "getUpdates")
    check("polling is message-only and uses the durable offset",
          poll["allowed_updates"] == ["message"] and poll["offset"] == 0
          and poll["timeout"] == 30)
    check("startup registers the always-relevant command menu",
          api.menus
          and [item["command"] for item in api.menus[0]["commands"]]
          == ["ask", "ping", "help", "privacy"])

    ping_times = iter([100.0, 103.0])
    ping_api = FakeAPI([update(12, "/ping@AlephTestBot",
                               chat_type="supergroup", chat_id=-100)])
    ping_service = adapter(
        tmp / "ping", StaticEngine(), ping_api,
        ping_status={
            "identity": "evolution 2/generation 7",
            "evolution": 2,
            "generation": 7,
            "activation_sequence": 12,
            "release_id": "a" * 20,
            "corpus_build_id": "corpus-7",
            "index_namespace": "main",
            "evaluation_id": "b" * 20,
            "prerelease_release_id": "c" * 20,
            "gateway_release": "aleph-v0.4",
            "embedding": "bge-m3/790764642607",
            "manifest_sha256": "d" * 64,
            "source_pins": "wildcat-docs@fe0e50c079b2",
        }, ping_status_provider=lambda: {"local_writer": {
            "mode": "shadow", "alias": "gpt-oss:120b",
            "id": "a951a23b46a1", "counts": {
                "total": 3, "valid": 2, "rejected": 1, "fallback": 0}}},
        monotonic_clock=lambda: next(ping_times))
    check("ping replies Pong with uptime, generation and current pins",
          ping_service.run_once() == 1
          and ping_api.sent[-1]["text"].startswith("Pong!\nAlive: 00h 00m 03s")
          and "Identity: evolution 2/generation 7" in ping_api.sent[-1]["text"]
          and f"Release: {'a' * 20}" in ping_api.sent[-1]["text"]
          and "Gateway: aleph-v0.4" in ping_api.sent[-1]["text"]
          and "Mephistopheles: shadow" in ping_api.sent[-1]["text"]
          and "valid=2" in ping_api.sent[-1]["text"])

    ignored_ping_api = FakeAPI([update(
        13, "/ping@AnotherBot", chat_type="supergroup", chat_id=-100)])
    ignored_ping = adapter(tmp / "ignored-ping", StaticEngine(), ignored_ping_api)
    check("ping addressed to another bot is ignored",
          ignored_ping.run_once() == 1 and not ignored_ping_api.sent)

    bare_group_ping_api = FakeAPI([update(
        14, "/ping", chat_type="supergroup", chat_id=-100)])
    bare_group_ping = adapter(
        tmp / "bare-group-ping", StaticEngine(), bare_group_ping_api,
        monotonic_clock=lambda: 100.0)
    check("bare group ping is accepted like other Telegram commands",
          bare_group_ping.run_once() == 1
          and bare_group_ping_api.sent[-1]["text"].startswith("Pong!"))

    timeout_api = FakeAPI([update(10, "question")])
    timeout_service = adapter(
        tmp / "poll-timeout", StaticEngine(), timeout_api)
    timeout_api.poll_timeout = True
    check("a long-poll timeout is an empty iteration with no checkpoint move",
          timeout_service.run_once() == 0
          and timeout_service.offset_store.load() == 0)
    timeout_api.poll_timeout = False
    check("polling continues normally after a timeout",
          timeout_service.run_once() == 1
          and timeout_service.offset_store.load() == 11)

    original_urlopen = telegram.urllib.request.urlopen
    try:
        def plain_timeout(*_args, **_kwargs):
            raise TimeoutError("private transport detail")

        telegram.urllib.request.urlopen = plain_timeout
        transport_error = ""
        try:
            telegram.TelegramHTTP("fixture-token").call("getUpdates")
        except telegram.TelegramTimeout as error:
            transport_error = str(error)
        check("plain HTTP read timeouts have a safe typed boundary",
              transport_error == "Telegram getUpdates timed out")

        def wrapped_timeout(*_args, **_kwargs):
            raise telegram.urllib.error.URLError(
                TimeoutError("private transport detail"))

        telegram.urllib.request.urlopen = wrapped_timeout
        transport_error = ""
        try:
            telegram.TelegramHTTP("fixture-token").call("getUpdates")
        except telegram.TelegramTimeout as error:
            transport_error = str(error)
        check("URL-wrapped read timeouts use the same typed boundary",
              transport_error == "Telegram getUpdates timed out")
    finally:
        telegram.urllib.request.urlopen = original_urlopen

    rich_text = (
        "Explanation\n\nEvidence-backed answer. [1]\n\nSources\n\n"
        "[1] docs/file.md › Stable section: "
        "https://github.com/wildcat-finance/project-aleph/blob/abc/file.md#L1")
    rich_api = FakeAPI([update(11, "question", thread_id=88)])
    rich = adapter(
        tmp / "rich", StaticEngine(rich_text), rich_api, rich_messages=True)
    rich.run_once()
    rich_payload = rich_api.rich_sent[0]
    markdown = rich_payload["rich_message"]["markdown"]
    source_url = ("https://github.com/wildcat-finance/project-aleph"
                  "/blob/abc/file.md#L1")
    check("eligible answers use one escaped rich message with compact sources",
          len(rich_api.rich_sent) == 1 and not rich_api.sent
          and markdown == (
              f"Evidence\\-backed answer\\. [\\[1\\]]({source_url})\n\n"
              "## Sources\n\n"
              f"1. [file\\.md › Stable section]({source_url})"))
    check("rich citations hide long URLs behind readable numbered labels",
          "[1] docs/file.md" not in markdown
          and markdown.count(source_url) == 2)
    multi_section = telegram.rich_markdown(
        "Explanation\n\nCycles cover lenders. [1]\n\n"
        "Current state\n\nReserve ratio met at block 19.\n\n"
        "Sources\n\n[1] docs/a.md › A: https://github.com/w/d/blob/c/a.md")
    check("multi-section answers keep every reviewed heading",
          "## Explanation" in multi_section
          and "## Current state" in multi_section)
    injected = telegram.rich_markdown(
        "Explanation\n\n# Day-To-Day {% hint %} **bold** [x](y)\n\n"
        "Sources\n\n[1] a.md › A: https://example.invalid/a")
    check("corpus markdown renders as literal text, never as markup",
          "\\# Day\\-To\\-Day \\{% hint %\\} \\*\\*bold\\*\\* \\[x\\]\\(y\\)"
          in injected and "# Day-To-Day" not in injected)
    hexaddr = "0x" + "c9" * 20
    live_answer = (
        "Current state\n\n"
        "Wintermute Trading USD Coin (wmtUSDC)\n"
        f"Market: {hexaddr}\n"
        "APR: 8.50%\n"
        "Time delinquent: 0s\n\n"
        "Observed at Ethereum block 25,728,947 via Wildcat Data Gateway "
        "release v2.0.30.")
    live_md = telegram.rich_markdown(live_answer)
    check("live state renders as a stat card, one field per line",
          live_md == (
              "## Current state\n"
              "\n"
              "Wintermute Trading USD Coin \\(wmtUSDC\\)\\\n"
              f"**Market:** `{hexaddr}`\\\n"
              "**APR:** 8\\.50%\\\n"
              "**Time delinquent:** 0s\n"
              "\n"
              "Observed at Ethereum block 25,728,947 via Wildcat Data "
              "Gateway release v2\\.0\\.30\\."), repr(live_md))
    live_entity = telegram.format_message(live_answer)
    check("the entity rung renders the same stat card with copyable values",
          live_entity is not None and len(live_entity) == 1
          and "<b>Current state</b>" in live_entity[0].html
          and f"<b>Market:</b> <code>{hexaddr}</code>" in live_entity[0].html
          and "<b>APR:</b> 8.50%" in live_entity[0].html
          and live_entity[0].plain == live_answer)
    history_answer = (
        "Transaction history\n\nLatest 1 matching event(s):\n"
        f"- Borrow: 4 USDC; block 25,728,947; transaction {'0x' + 'a' * 64}\n\n"
        "Observed at Ethereum block 25,728,947 via Wildcat Data Gateway "
        "release v2.0.30.")
    history_md = telegram.rich_markdown(history_answer)
    history_entity = telegram.format_message(history_answer)
    check("transaction history retains its heading and copyable hash",
          "## Transaction history" in history_md
          and "`0x" in history_md
          and history_entity is not None
          and "<b>Transaction history</b>" in history_entity[0].html
          and "<code>0x" in history_entity[0].html)
    prose_md = telegram.rich_markdown(
        "Explanation\n\nNote: colons in prose stay unstyled. [1]\n\n"
        "Sources\n\n[1] docs/a.md › A: https://example.invalid/a")
    check("claim prose never grows bold state labels",
          "**Note:**" not in prose_md and "Note: colons" in prose_md)
    check("rich delivery preserves reply and forum-topic identity",
          rich_payload["reply_parameters"]["message_id"] == 111
          and rich_payload["message_thread_id"] == 88
          and rich.offset_store.load() == 12)

    fallback_api = FakeAPI([update(12, "question")])
    fallback_api.fail_rich = True
    fallback = adapter(
        tmp / "rich-fallback", StaticEngine(rich_text), fallback_api,
        rich_messages=True)
    fallback.run_once()
    check("a refused rich call falls back to entity-rendered delivery",
          not fallback_api.rich_sent and len(fallback_api.sent) == 1
          and fallback_api.sent[0].get("parse_mode") == "HTML"
          and "<blockquote expandable><b>Sources</b>" in fallback_api.sent[0]["text"]
          and fallback.offset_store.load() == 13)
    fully_plain_api = FakeAPI([update(12, "question")])
    fully_plain_api.fail_rich = fully_plain_api.fail_html = True
    fully_plain = adapter(
        tmp / "rich-plain-fallback", StaticEngine(rich_text), fully_plain_api,
        rich_messages=True)
    fully_plain.run_once()
    check("refused rich and html renderings still deliver the exact answer",
          not fully_plain_api.rich_sent and len(fully_plain_api.sent) == 1
          and fully_plain_api.sent[0]["text"] == rich_text
          and "parse_mode" not in fully_plain_api.sent[0]
          and fully_plain.offset_store.load() == 13)

    irregular = "Sources\n\nAn operator-authored source note"
    check("unrecognized source records survive, escaped but never dropped",
          telegram.rich_markdown(irregular)
          == "## Sources\n\nAn operator\\-authored source note")

    ambiguous_api = FakeAPI([update(14, "question")])
    ambiguous_api.lose_rich_response = True
    ambiguous = adapter(
        tmp / "rich-ambiguous", StaticEngine(rich_text), ambiguous_api,
        rich_messages=True)
    refused = ""
    try:
        ambiguous.run_once()
    except telegram.TelegramError as error:
        refused = str(error)
    check("an ambiguous rich failure never risks a duplicate plain fallback",
          "response lost" in refused and not ambiguous_api.sent
          and ambiguous.offset_store.load() == 0)

    command_api = FakeAPI([update(13, "/help")])
    command = adapter(
        tmp / "rich-command", StaticEngine(), command_api,
        rich_messages=True)
    command.run_once()
    check("commands remain on the plain-text contract",
          len(command_api.sent) == 1 and not command_api.rich_sent)

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
    peer_answer = ("Explanation\n\nPeer bots parse answer bytes. [1]\n\n"
                   "Sources\n\n[1] docs/a.md › A: "
                   "https://github.com/wildcat-finance/wildcat-docs/blob/c0ffee/docs/a.md")
    peer_engine = CountingEngine(StaticEngine(peer_answer))
    peer = adapter(tmp / "peer", peer_engine, peer_api,
                   peer_bot_ids=(500,), rich_messages=True)
    peer.process_updates(peer_api.updates)
    check("only allowlisted bots can issue explicitly targeted questions",
          peer_engine.questions == ["approved question"]
          and len(peer_api.sent) == 1)
    check("peer bots receive exact plain bytes, no markup, no typing hint",
          "parse_mode" not in peer_api.sent[0]
          and "reply_markup" not in peer_api.sent[0]
          and peer_api.sent[0]["text"] == peer_answer
          and not peer_api.actions)
    check("peer bots cannot use ambient, untargeted, or handoff paths",
          peer.offset_store.load() == 29 and not peer.pending)
    check("peer-bot answers remain plain for end-to-end outcome capture",
          len(peer_api.sent) == 1 and not peer_api.rich_sent)

    peer_burst_api = FakeAPI([
        update(100 + index, f"/ask@AlephTestBot probe {index}", chat_id=-1,
               chat_type="supergroup", user_id=500, is_bot=True)
        for index in range(1, 12)
    ])
    peer_burst_engine = CountingEngine(StaticEngine())
    peer_burst = adapter(
        tmp / "peer-burst", peer_burst_engine, peer_burst_api,
        peer_bot_ids=(500,))
    peer_burst.process_updates(peer_burst_api.updates)
    check("one bounded ten-probe peer burst is admitted",
          peer_burst_engine.questions == [
              f"probe {index}" for index in range(1, 11)])
    check("an eleventh peer probe is limited before the answer engine",
          len(peer_burst_api.sent) == 11
          and "rate-limited" in peer_burst_api.sent[-1]["text"])

    print("\nTG3 — length, failures, rate limits, and offsets fail safely")
    long_text = ("paragraph line\n\n" * 700) + "stable-source-link"
    chunks = telegram.split_message(long_text)
    check("4096-byte chunks reconstruct the exact answer",
          len(chunks) > 2 and max(map(len, chunks)) <= 4096
          and "".join(chunks) == long_text)
    registry_text = real_engine.engine.answer(
        "Which Wildcat markets are currently registered?").text
    registry_api = FakeAPI([update(300, "registry")])
    registry_service = adapter(
        tmp / "bounded-registry", StaticEngine(registry_text), registry_api)
    registry_service.run_once()
    check("a general registry answer is delivered as exactly one message",
          len(registry_api.sent) == 1
          and registry_api.sent[0]["parse_mode"] == "HTML"
          and "Registered markets (12; showing 1–10"
              in registry_api.sent[0]["text"]
          and "reply_parameters" in registry_api.sent[0]
          and registry_text.count("\n- ") == live.REGISTRY_PAGE_SIZE)
    borrower_text = real_engine.engine.answer(
        f"What markets has borrower {test_live.BORROWER} run?").text
    borrower_api = FakeAPI([update(301, "borrower markets")])
    borrower_service = adapter(
        tmp / "bounded-borrower", StaticEngine(borrower_text), borrower_api)
    borrower_service.run_once()
    check("borrower discovery is delivered as exactly one message",
          len(borrower_api.sent) == 1
          and borrower_api.sent[0]["parse_mode"] == "HTML"
          and "Markets for borrower" in borrower_api.sent[0]["text"]
          and "showing 1–10" in borrower_api.sent[0]["text"]
          and "reply_parameters" in borrower_api.sent[0]
          and borrower_text.count("\n- ")
              == live.BORROWER_MARKETS_PAGE_SIZE)
    long_api = FakeAPI([update(30, "question")])
    long_service = adapter(tmp / "long", StaticEngine(long_text), long_api)
    long_service.run_once()
    check("long replies chain to the preceding Telegram message",
          len(long_api.sent) == len(chunks)
          and long_api.sent[1]["reply_parameters"]["message_id"] == 1001)

    oversized_text = ("oversized paragraph\n\n" * 1800) + "final source"
    oversized_api = FakeAPI([update(31, "question")])
    oversized = adapter(
        tmp / "oversized-rich", StaticEngine(oversized_text), oversized_api,
        rich_messages=True)
    oversized.run_once()
    check("answers above the rich limit use the exact legacy chain",
          len(oversized_text) > telegram.RICH_MESSAGE_LIMIT
          and not oversized_api.rich_sent and len(oversized_api.sent) > 1
          and "".join(item["text"] for item in oversized_api.sent)
              == oversized_text)

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

    timed_send_api = FakeAPI([update(50, "question")])
    timed_send_service = adapter(
        tmp / "timed-send", StaticEngine(), timed_send_api)
    timed_send_api.send_timeout = True
    timed_out = ""
    try:
        timed_send_service.run_once()
    except telegram.TelegramTimeout as error:
        timed_out = str(error)
    check("an uncertain send timeout remains fatal and unconfirmed",
          "send timed out" in timed_out
          and timed_send_service.offset_store.load() == 0)

    failed_fallback_api = FakeAPI([update(51, "question")])
    failed_fallback_api.fail_rich = failed_fallback_api.fail_send = True
    failed_fallback = adapter(
        tmp / "failed-rich-fallback", StaticEngine(), failed_fallback_api,
        rich_messages=True)
    refused = ""
    try:
        failed_fallback.run_once()
    except telegram.TelegramError as error:
        refused = str(error)
    check("failed rich and plain sends leave the update unconfirmed",
          "send failed" in refused
          and failed_fallback.offset_store.load() == 0)

    check("the rich-message operator switch is fail-loud",
          telegram.rich_messages_enabled("true") is True
          and telegram.rich_messages_enabled("OFF") is False)
    refused = ""
    try:
        telegram.rich_messages_enabled("maybe")
    except telegram.TelegramError as error:
        refused = str(error)
    check("invalid rich-message configuration is rejected",
          "must be true or false" in refused)

    rate_api = FakeAPI([update(60, "one"), update(61, "two")])
    rate_engine = CountingEngine(StaticEngine())
    rate_service = adapter(tmp / "rate", rate_engine, rate_api, limit=1)
    rate_service.run_once()
    check("per-chat/user admission is bounded before the answer engine",
          rate_engine.questions == ["one"]
          and "rate-limited" in rate_api.sent[1]["text"])

    print("\nTG5 — human answers render richly, fall back safely, stay exact")
    answer_text = (
        "Explanation\n\n"
        "Cycles start with the first request & <cover> all lenders. [1]\n\n"
        "Escrow 0x" + "ab" * 20 + " releases funds. [2]\n\n"
        "Sources\n\n"
        "[1] overview/faqs.md › FAQs › Withdrawals: "
        "https://github.com/wildcat-finance/wildcat-docs/blob/abc/overview/faqs.md#when\n"
        "[2] docs/Terminology.md › Withdrawal Cycle: "
        "https://github.com/wildcat-finance/v2-protocol/blob/def/docs/Terminology.md#cycle")
    rendered = telegram.format_message(answer_text)
    check("structured answers render links and expandable sources",
          rendered is not None and len(rendered) == 1
          and rendered[0].html.startswith("Cycles start")
          and '<blockquote expandable><b>Sources</b>\n[1] <a href="'
          in rendered[0].html
          and rendered[0].html.endswith("</a></blockquote>")
          and '">[1]</a>' in rendered[0].html
          and "<code>0x" in rendered[0].html)
    check("a lone Explanation heading yields to the answer body",
          "<b>Explanation</b>" not in rendered[0].html)
    sectioned = telegram.format_message(
        "Explanation\n\nA claim. [1]\n\nCurrent state\n\nReserve met.\n\n"
        "Sources\n\n[1] docs/a.md › A: https://github.com/w/d/blob/c/a.md")
    check("multi-section answers keep bold headings in the entity rung",
          sectioned is not None
          and "<b>Explanation</b>" in sectioned[0].html
          and "<b>Current state</b>" in sectioned[0].html)
    check("markup never rewrites answer bytes",
          rendered[0].plain == answer_text
          and "&amp; &lt;cover&gt;" in rendered[0].html
          and rendered[0].html.count("https://") == 4)
    check("source labels shrink to file name and most specific segment",
          ">faqs.md › Withdrawals</a>" in rendered[0].html
          and ">Terminology.md › Withdrawal Cycle</a>" in rendered[0].html
          and "› FAQs" not in rendered[0].html)
    check("the two leading sources become url buttons on the final chunk",
          rendered[0].buttons == (
              ("[1] faqs.md",
               "https://github.com/wildcat-finance/wildcat-docs/blob/abc/overview/faqs.md#when"),
              ("[2] Terminology.md",
               "https://github.com/wildcat-finance/v2-protocol/blob/def/docs/Terminology.md#cycle")))
    stitched = "Explanation\n\n" + "\n\n".join(
        f"claim number {index} about the protocol. [1]" for index in range(300)
    ) + ("\n\nSources\n\n[1] docs/guide.md › Guide: "
         "https://github.com/wildcat-finance/wildcat-docs/blob/abc/docs/guide.md")
    packed = telegram.format_message(stitched)
    check("long rich answers pack into bounded chunks that rejoin exactly",
          packed is not None and len(packed) > 1
          and "\n\n".join(chunk.plain for chunk in packed) == stitched
          and all(chunk.html.count("<blockquote")
                  == chunk.html.count("</blockquote") for chunk in packed)
          and not packed[0].buttons
          and packed[-1].buttons == (
              ("[1] guide.md",
               "https://github.com/wildcat-finance/wildcat-docs/blob/abc/docs/guide.md"),))
    check("unstructured replies stay plain",
          telegram.format_message("Use /ask <question>.") is None)

    rich_api = FakeAPI([update(80, "/ask What does exactIdentifier(uint256) do?")])
    rich_service = adapter(tmp / "entity-rich", real_engine, rich_api)
    rich_service.run_once()
    ordered = [method for method, _ in rich_api.calls
               if method in ("sendChatAction", "sendMessage")]
    check("humans get a typing hint, then an HTML answer with tucked sources",
          ordered[0] == "sendChatAction"
          and rich_api.sent[0].get("parse_mode") == "HTML"
          and "<blockquote expandable><b>Sources</b>" in rich_api.sent[0]["text"]
          and rich_api.sent[0]["link_preview_options"] == {"is_disabled": True})
    keyboard = rich_api.sent[-1].get("reply_markup", {}).get("inline_keyboard")
    check("the final message carries url buttons for the leading sources",
          keyboard and len(keyboard) == 1 and 1 <= len(keyboard[0]) <= 2
          and all(button["url"].startswith("https://github.com/")
                  and button["text"].startswith("[")
                  for button in keyboard[0]))

    refresh_api = FakeAPI([])
    refresh_service = adapter(tmp / "refresh", StaticEngine(), refresh_api)
    asker = telegram.Incoming(
        update_id=1, chat_id=5, chat_type="private", message_id=2, user_id=9,
        text="q", thread_id=None, reply_to_bot=False, peer_bot=False)

    def slow_answer():
        deadline = time.monotonic() + 5
        while len(refresh_api.actions) < 3 and time.monotonic() < deadline:
            time.sleep(0.005)
        return telegram.Outgoing("slow answer")

    with ThreadPoolExecutor(max_workers=1) as slow_pool:
        collected = refresh_service._await_answer(
            asker, slow_pool.submit(slow_answer), interval=0.02)
    check("the typing hint refreshes while a slow answer is prepared",
          collected.text == "slow answer" and len(refresh_api.actions) >= 3
          and all(action["chat_id"] == 5 for action in refresh_api.actions))

    fallback_api = FakeAPI([update(81, "/ask What does exactIdentifier(uint256) do?")])
    fallback_api.fail_html = True
    fallback_service = adapter(tmp / "fallback", real_engine, fallback_api)
    fallback_service.run_once()
    check("a refused HTML rendering still delivers the exact plain answer",
          fallback_api.sent
          and all("parse_mode" not in payload and "reply_markup" not in payload
                  for payload in fallback_api.sent)
          and "Sources" in fallback_api.sent[-1]["text"]
          and fallback_service.offset_store.load() == 82)

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
