#!/usr/bin/env python3
"""Thin long-polling Telegram adapter for Aleph's typed answer engine."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass
from typing import Mapping, Protocol


class TelegramError(Exception):
    """Telegram transport or adapter policy cannot be satisfied."""


class TelegramRefused(TelegramError):
    """Telegram definitively refused a request before accepting delivery."""


class TelegramTimeout(TelegramError):
    """Telegram timed out before returning a Bot API response."""


RICH_MESSAGE_LIMIT = 32768
_RICH_HEADINGS = frozenset({
    "Explanation", "Current state", "Transaction history",
    "Premise correction", "Sources",
})
_SOURCE_CITATION = re.compile(
    r"^\[(?P<number>[1-9][0-9]*)\]\s+"
    r"(?P<label>.+?):\s+(?P<url>https://\S+)$")


def _uptime(seconds: float) -> str:
    """Render monotonic process age without implying wall-clock precision."""
    total = max(0, int(seconds))
    days, remainder = divmod(total, 86_400)
    hours, remainder = divmod(remainder, 3_600)
    minutes, secs = divmod(remainder, 60)
    if days:
        return f"{days}d {hours:02d}h {minutes:02d}m {secs:02d}s"
    return f"{hours:02d}h {minutes:02d}m {secs:02d}s"


def peer_bot_ids(value: str | None = None) -> tuple[int, ...]:
    """Parse the default-closed peer-bot allowlist without exposing IDs."""
    raw = os.environ.get("ALEPH_PEER_BOT_IDS", "") if value is None else value
    if not raw.strip():
        return ()
    values = []
    for item in raw.split(","):
        item = item.strip()
        if not item.isdecimal() or int(item) <= 0:
            raise TelegramError(
                "ALEPH_PEER_BOT_IDS must be comma-separated positive integers")
        values.append(int(item))
    return tuple(dict.fromkeys(values))


def rich_messages_enabled(value: str | None = None) -> bool:
    """Parse the operator kill switch; production prefers rich delivery."""
    raw = (os.environ.get("ALEPH_TELEGRAM_RICH_MESSAGES", "true")
           if value is None else value).strip().casefold()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise TelegramError(
        "ALEPH_TELEGRAM_RICH_MESSAGES must be true or false")


_MARKDOWN_SPECIAL = re.compile(r"[_*\[\]()~`>#+\-=|{}.!\\]")
_ESCAPED_MARKER = re.compile(r"\\\[(\d+)\\\]")
# A `Label: value` line inside a Current state section. Anchored to the line
# start and requiring content after the colon, so a sentence ending in a
# colon, a bullet, or prose with mid-sentence colons never grows a label.
_STATE_LABEL = re.compile(r"^([A-Za-z][^:<\n]{0,60}?): (?=\S)")
_STATE_LABEL_HTML = re.compile(r"^([A-Za-z][^:<\n]{0,60}?): (?=\S)", re.M)


def _escape_rich(text: str) -> str:
    """Backslash-escape rich Markdown so answer bytes render as literal text."""
    return _MARKDOWN_SPECIAL.sub(lambda matched: "\\" + matched.group(0), text)


def _rich_url(url: str) -> str:
    """Escape a URL for a rich Markdown link destination."""
    return url.replace("\\", "\\\\").replace(")", "\\)")


def rich_markdown(text: str) -> str:
    """Map reviewed sections and citations to native rich Markdown.

    Only adapter-generated constructs carry markup: reviewed section headings,
    the numbered source list with compact labels, and linked citation markers.
    Every other byte is escaped so corpus text can never be reinterpreted as
    markdown. A lone Explanation heading is dropped from the rendered view —
    the body speaks for itself and Sources still anchors the message — while
    multi-section answers keep every heading.
    """
    if not text:
        raise TelegramError("cannot format an empty rich message")
    lines = text.split("\n")
    links = _trailing_sources(text.split("\n\n")) or {}
    body_headings = [line for line in lines
                     if line in _RICH_HEADINGS and line != "Sources"]
    omit_explanation = body_headings == ["Explanation"]
    rendered = []
    in_sources = False
    in_state = False
    skip_blank = False
    for index, line in enumerate(lines):
        if skip_blank and not line:
            skip_blank = False
            continue
        skip_blank = False
        if line in _RICH_HEADINGS:
            in_sources = line == "Sources"
            in_state = line == "Current state"
            if omit_explanation and line == "Explanation":
                skip_blank = True
                continue
            rendered.append(f"## {line}")
            continue
        citation = _SOURCE_CITATION.fullmatch(line) if in_sources else None
        if citation:
            label = _escape_rich(_short_label(citation.group("label")))
            rendered.append(f'{citation.group("number")}. [{label}]'
                            f'({_rich_url(citation.group("url"))})')
            continue
        escaped = _escape_rich(line)
        escaped = _HEX_VALUE.sub(
            lambda matched: f"`{matched.group(0)}`", escaped)
        if in_state:
            escaped = _STATE_LABEL.sub(r"**\1:** ", escaped, count=1)
        if links and not in_sources:
            escaped = _ESCAPED_MARKER.sub(
                lambda matched: (
                    f"[\\[{matched.group(1)}\\]]"
                    f"({_rich_url(links[int(matched.group(1))][1])})"
                    if int(matched.group(1)) in links else matched.group(0)),
                escaped)
        # The rich dialect soft-wraps a single newline into a space, which
        # collapsed live state into one run-on paragraph. A trailing
        # backslash is a hard break, keeping one field per line whenever the
        # next line is more escaped content.
        following = lines[index + 1] if index + 1 < len(lines) else ""
        if (escaped.strip() and following.strip()
                and following not in _RICH_HEADINGS
                and not (in_sources and _SOURCE_CITATION.fullmatch(following))):
            escaped += "\\"
        rendered.append(escaped)
    return "\n".join(rendered)


class BotAPI(Protocol):
    def call(self, method: str, payload: dict | None = None): ...


class TelegramHTTP:
    """Dependency-free Bot API transport that never exposes its token in errors."""

    def __init__(self, token: str | None = None, timeout: int = 45):
        self.token = token if token is not None else os.environ.get(
            "ALEPH_TELEGRAM_TOKEN", "")
        if not self.token:
            raise TelegramError(
                "Telegram token is absent; set ALEPH_TELEGRAM_TOKEN")
        self.timeout = timeout

    def call(self, method: str, payload: dict | None = None):
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", method):
            raise TelegramError(f"invalid Bot API method {method!r}")
        url = f"https://api.telegram.org/bot{self.token}/{method}"
        request = urllib.request.Request(
            url, data=json.dumps(payload or {}).encode(), method="POST",
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                result = json.load(response)
        except urllib.error.HTTPError as error:
            error_type = (TelegramRefused if 400 <= error.code < 500
                          else TelegramError)
            raise error_type(f"Telegram {method} returned HTTP {error.code}")
        except TimeoutError as error:
            raise TelegramTimeout(f"Telegram {method} timed out") from error
        except urllib.error.URLError as error:
            if isinstance(error.reason, TimeoutError):
                raise TelegramTimeout(f"Telegram {method} timed out") from error
            raise TelegramError(f"Telegram {method} failed: {error}")
        except json.JSONDecodeError as error:
            raise TelegramError(f"Telegram {method} failed: {error}")
        if result.get("ok") is not True:
            description = str(result.get("description") or "unknown API error")
            raise TelegramRefused(
                f"Telegram {method} refused the request: {description}")
        return result.get("result")


@dataclass(frozen=True)
class BotIdentity:
    id: int
    username: str


@dataclass(frozen=True)
class Incoming:
    update_id: int
    chat_id: int
    chat_type: str
    message_id: int
    user_id: int
    text: str
    thread_id: int | None
    reply_to_bot: bool
    peer_bot: bool


@dataclass(frozen=True)
class Outgoing:
    text: str
    pending_handoff: tuple[str, tuple[str, ...], tuple[str, ...]] | None = None
    rich: bool = False


@dataclass(frozen=True)
class HandoffPayload:
    handoff_id: str
    kind: str
    chat_id: int
    user_id: int
    fields: dict[str, str]


class HandoffSink(Protocol):
    def send(self, payload: HandoffPayload) -> str: ...


class DisabledHandoffSink:
    def send(self, payload: HandoffPayload) -> str:
        raise TelegramError("no human handoff destination is configured")


@dataclass
class PendingHandoff:
    handoff_id: str
    kind: str
    allowed: tuple[str, ...]
    required: tuple[str, ...]
    fields: dict[str, str]


class OffsetStore:
    """Atomically persist the next update ID; it contains no message text."""

    def __init__(self, path: str):
        self.path = pathlib.Path(path).resolve()

    def load(self) -> int:
        if not self.path.exists():
            return 0
        try:
            value = json.loads(self.path.read_text()).get("next_update_id")
        except (OSError, json.JSONDecodeError, AttributeError) as error:
            raise TelegramError(f"invalid Telegram offset checkpoint: {error}")
        if not isinstance(value, int) or value < 0:
            raise TelegramError("Telegram offset checkpoint is not a nonnegative integer")
        return value

    def save(self, value: int) -> None:
        if not isinstance(value, int) or value < 0:
            raise TelegramError("cannot checkpoint an invalid Telegram offset")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{self.path.name}.", dir=self.path.parent)
        try:
            with os.fdopen(descriptor, "w") as handle:
                json.dump({"next_update_id": value}, handle)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


class RateLimiter:
    """In-memory fixed-window admission control with an injectable clock."""

    def __init__(self, limit: int, window_seconds: int, clock=time.monotonic):
        if limit < 1 or window_seconds < 1:
            raise TelegramError("rate limit and window must be positive")
        self.limit = limit
        self.window = window_seconds
        self.clock = clock
        self.events: dict[tuple[int, int], deque[float]] = defaultdict(deque)
        self.lock = threading.Lock()

    def allow(self, key: tuple[int, int]) -> bool:
        now = self.clock()
        with self.lock:
            events = self.events[key]
            while events and events[0] <= now - self.window:
                events.popleft()
            if len(events) >= self.limit:
                return False
            events.append(now)
            return True


_CITATION_MARKER = re.compile(r"\[(\d+)\]")
_HEX_VALUE = re.compile(r"\b0x(?:[0-9a-fA-F]{64}|[0-9a-fA-F]{40})\b")


def _escape_html(text: str) -> str:
    """Escape text so Telegram's HTML parser cannot reinterpret answer bytes."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


@dataclass(frozen=True)
class RenderedChunk:
    """One sendMessage payload: HTML text plus its exact plain-text fallback."""
    html: str
    plain: str
    buttons: tuple[tuple[str, str], ...] = ()


def _short_label(label: str) -> str:
    """Compress a breadcrumb to its file name and most specific segment."""
    segments = label.split(" › ")
    if len(segments) < 2:
        return label
    name = segments[0].rsplit("/", 1)[-1].strip() or segments[0]
    return f"{name} › {segments[-1]}"


def _button_label(number: int, label: str) -> str:
    """Name a source button by citation number and file name."""
    name = label.split(" › ", 1)[0].rsplit("/", 1)[-1].strip() or "source"
    return f"[{number}] {name}"[:64]


def _trailing_sources(paragraphs: list[str]) -> dict[int, tuple[str, str]] | None:
    """Parse a final 'Sources' section into {number: (label, url)}."""
    if len(paragraphs) < 2 or paragraphs[-2] != "Sources":
        return None
    links: dict[int, tuple[str, str]] = {}
    for line in paragraphs[-1].split("\n"):
        matched = _SOURCE_CITATION.fullmatch(line)
        if matched is None or int(matched.group("number")) in links:
            return None
        links[int(matched.group("number"))] = (
            matched.group("label"), matched.group("url"))
    return links or None


def format_message(text: str, limit: int = 3900) -> tuple[RenderedChunk, ...] | None:
    """Render a structured answer as Telegram HTML chunks, or None to stay plain.

    The visible text is the answer's own bytes: markup only bolds the section
    headings, links citation markers, makes hex values copyable, and tucks the
    source URLs behind their labels inside a collapsed expandable quotation.
    Every chunk carries its exact plain bytes as a fallback rendering. The
    visible-length limit stays under Telegram's 4096 so that astral characters,
    which Telegram counts double, cannot push a chunk over the wire limit.
    """
    if not 1 <= limit <= 4096:
        raise TelegramError("Telegram message limit must be between 1 and 4096")
    paragraphs = text.split("\n\n")
    links = _trailing_sources(paragraphs)
    if links is None and not any(item in _RICH_HEADINGS for item in paragraphs):
        return None
    body = paragraphs[:-2] if links else paragraphs
    body_headings = [item for item in body if item in _RICH_HEADINGS]
    # A lone Explanation heading is dropped from the rendered view; its bytes
    # ride along in the plain fallback of the paragraph that follows it.
    omit_explanation = (body_headings == ["Explanation"]
                        and body and body[-1] != "Explanation")

    fragments: list[tuple[str, str, int]] = []
    carried = ""
    in_state = False
    for paragraph in body:
        if omit_explanation and paragraph == "Explanation" and not carried:
            carried = "Explanation\n\n"
            continue
        plain = carried + paragraph
        carried = ""
        if paragraph in _RICH_HEADINGS:
            in_state = paragraph == "Current state"
            fragments.append(
                (plain, f"<b>{_escape_html(paragraph)}</b>", len(paragraph)))
            continue
        html = _HEX_VALUE.sub(
            lambda matched: f"<code>{matched.group(0)}</code>",
            _escape_html(paragraph))
        if in_state:
            html = _STATE_LABEL_HTML.sub(r"<b>\1:</b> ", html)
        if links:
            html = _CITATION_MARKER.sub(
                lambda matched: (
                    f'<a href="{_escape_html(links[int(matched.group(1))][1])}">'
                    f"{matched.group(0)}</a>"
                    if int(matched.group(1)) in links else matched.group(0)),
                html)
        fragments.append((plain, html, len(paragraph)))
    if links:
        lines = ["<b>Sources</b>"]
        visible = len("Sources")
        for number in sorted(links):
            label, url = links[number]
            display = _short_label(label)
            lines.append(f'[{number}] <a href="{_escape_html(url)}">'
                         f"{_escape_html(display)}</a>")
            visible += 1 + len(f"[{number}] {display}")
        fragments.append(("\n\n".join(paragraphs[-2:]),
                          "<blockquote expandable>" + "\n".join(lines)
                          + "</blockquote>", visible))

    chunks: list[RenderedChunk] = []
    plain_parts: list[str] = []
    html_parts: list[str] = []
    used = 0
    for plain, html, visible in fragments:
        if visible > limit:
            return None
        if plain_parts and used + 2 + visible > limit:
            chunks.append(RenderedChunk(
                "\n\n".join(html_parts), "\n\n".join(plain_parts)))
            plain_parts, html_parts, used = [], [], 0
        used += (2 if plain_parts else 0) + visible
        plain_parts.append(plain)
        html_parts.append(html)
    chunks.append(RenderedChunk("\n\n".join(html_parts), "\n\n".join(plain_parts)))
    if links:
        # The two leading sources repeat as buttons under the final message,
        # reachable without expanding the quotation.
        buttons = tuple((_button_label(number, links[number][0]),
                         links[number][1]) for number in sorted(links)[:2])
        chunks[-1] = RenderedChunk(chunks[-1].html, chunks[-1].plain, buttons)
    if "\n\n".join(chunk.plain for chunk in chunks) != text:
        raise TelegramError("message renderer changed answer bytes")
    return tuple(chunks)


def split_message(text: str, limit: int = 4096) -> tuple[str, ...]:
    """Split without changing bytes, preferring paragraph and line boundaries."""
    if not text:
        raise TelegramError("cannot send an empty message")
    if not 1 <= limit <= 4096:
        raise TelegramError("Telegram message limit must be between 1 and 4096")
    chunks = []
    cursor = 0
    while len(text) - cursor > limit:
        ceiling = cursor + limit
        boundary = text.rfind("\n\n", cursor + 1, ceiling + 1)
        width = 2
        if boundary < cursor + max(1, limit // 3):
            boundary = text.rfind("\n", cursor + 1, ceiling + 1)
            width = 1
        if boundary < cursor + max(1, limit // 3):
            boundary = text.rfind(" ", cursor + 1, ceiling + 1)
            width = 1
        end = boundary + width if boundary >= cursor + 1 else ceiling
        chunks.append(text[cursor:end])
        cursor = end
    chunks.append(text[cursor:])
    if any(not chunk or len(chunk) > limit for chunk in chunks):
        raise TelegramError("message splitter produced an invalid chunk")
    if "".join(chunks) != text:
        raise TelegramError("message splitter changed answer bytes")
    return tuple(chunks)


class TelegramAdapter:
    """Map relevant Telegram messages to typed AnswerEngine calls."""

    _COMMAND = re.compile(r"^/(\w+)(?:@([A-Za-z0-9_]+))?(?:\s+(.*))?$", re.S)

    def __init__(self, engine, api: BotAPI, offset_store: OffsetStore,
                 handoff_sink: HandoffSink | None = None,
                 max_workers: int = 4, user_limit: int = 5,
                 user_window_seconds: int = 60,
                 peer_bot_limit: int = 10,
                 peer_bot_window_seconds: int = 60,
                 peer_bot_ids: tuple[int, ...] = (),
                 rich_messages: bool = False,
                 ping_status: Mapping[str, object] | None = None,
                 ping_status_provider: (
                     Callable[[], Mapping[str, object]] | None) = None,
                 monotonic_clock=time.monotonic):
        if not 1 <= max_workers <= 32:
            raise TelegramError("max_workers must be between 1 and 32")
        if any(isinstance(peer_id, bool) or not isinstance(peer_id, int)
               or peer_id <= 0 for peer_id in peer_bot_ids):
            raise TelegramError("peer bot IDs must be positive integers")
        self.engine = engine
        self.api = api
        self.offset_store = offset_store
        self.handoff_sink = handoff_sink or DisabledHandoffSink()
        self.max_workers = max_workers
        self.limiter = RateLimiter(user_limit, user_window_seconds)
        self.peer_limiter = RateLimiter(
            peer_bot_limit, peer_bot_window_seconds)
        self.peer_bot_ids = frozenset(peer_bot_ids)
        self.rich_messages = bool(rich_messages)
        self.ping_status = dict(ping_status or {})
        self.ping_status_provider = ping_status_provider
        self.monotonic_clock = monotonic_clock
        self.started_monotonic = monotonic_clock()
        self.identity: BotIdentity | None = None
        self.pending: dict[tuple[int, int], PendingHandoff] = {}

    def startup(self) -> BotIdentity:
        me = self.api.call("getMe")
        if not isinstance(me, dict) or me.get("is_bot") is not True:
            raise TelegramError("getMe did not return a bot identity")
        username = me.get("username")
        if not isinstance(username, str) or not username:
            raise TelegramError("Telegram bot has no username")
        if me.get("can_read_all_group_messages") is True:
            raise TelegramError(
                "Telegram privacy mode is disabled; enable it in BotFather")
        webhook = self.api.call("getWebhookInfo")
        if not isinstance(webhook, dict) or webhook.get("url"):
            raise TelegramError(
                "a Telegram webhook is active; remove it before long polling")
        try:
            bot_id = int(me["id"])
        except (KeyError, TypeError, ValueError):
            raise TelegramError("Telegram bot identity has no valid ID")
        self.identity = BotIdentity(bot_id, username)
        if bot_id in self.peer_bot_ids:
            raise TelegramError("Aleph's own bot ID cannot be a peer bot")
        self._register_commands()
        return self.identity

    def _register_commands(self) -> None:
        """Best-effort command-menu registration; failure never blocks startup.

        Only the always-relevant commands appear in the menu. The handoff
        trio is contextual and is introduced by the triage answer itself.
        """
        try:
            self.api.call("setMyCommands", {"commands": [
                {"command": "ask",
                 "description": "Ask a Wildcat Protocol question"},
                {"command": "ping",
                 "description": "Check Aleph runtime and pins"},
                {"command": "help",
                 "description": "How Aleph answers and cites sources"},
                {"command": "privacy",
                 "description": "What Aleph reads"},
            ]})
        except TelegramError:
            pass

    def run_once(self, timeout: int = 30) -> int:
        if self.identity is None:
            raise TelegramError("adapter startup checks have not run")
        offset = self.offset_store.load()
        try:
            updates = self.api.call("getUpdates", {
                "offset": offset, "limit": 100, "timeout": timeout,
                "allowed_updates": ["message"],
            })
        except TelegramTimeout:
            # Telegram long polling may end locally before the Bot API returns.
            # No update was observed, so this is an empty iteration and the
            # durable offset must remain unchanged.
            return 0
        if not isinstance(updates, list):
            raise TelegramError("getUpdates did not return a list")
        return self.process_updates(updates)

    def run_forever(self, timeout: int = 30, stop_event=None) -> None:
        self.startup()
        stop = stop_event or threading.Event()
        while not stop.is_set():
            self.run_once(timeout)

    def process_updates(self, updates: list[dict]) -> int:
        if self.identity is None:
            raise TelegramError("adapter startup checks have not run")
        if any(not isinstance(update, dict)
               or not isinstance(update.get("update_id"), int)
               or update["update_id"] < 0 for update in updates):
            raise TelegramError("update batch contains an invalid update_id")
        ordered = sorted(updates, key=lambda update: update["update_id"])
        seen = set()
        processed = 0
        checkpoint = self.offset_store.load()
        # Answers are bounded by the configured pool. Sending and checkpointing
        # remain ordered, so a transport failure never confirms a later update.
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            cursor = 0
            while cursor < len(ordered):
                update = ordered[cursor]
                update_id = update.get("update_id")
                if update_id < checkpoint:
                    cursor += 1
                    continue
                if update_id in seen:
                    cursor += 1
                    continue
                seen.add(update_id)
                incoming = self._incoming(update)
                if incoming is None:
                    self.offset_store.save(update_id + 1)
                    checkpoint = update_id + 1
                    processed += 1
                    cursor += 1
                    continue
                question = self._question(incoming)
                if question is None:
                    self.offset_store.save(update_id + 1)
                    checkpoint = update_id + 1
                    processed += 1
                    cursor += 1
                    continue
                if question.startswith("\0"):
                    response = Outgoing(self._command(incoming, question[1:]))
                elif not (self.peer_limiter if incoming.peer_bot else self.limiter).allow(
                        (incoming.chat_id, incoming.user_id)):
                    response = Outgoing(
                        "Aleph is rate-limited for this chat and user. "
                        "Please wait before asking again.")
                else:
                    future = pool.submit(self._answer, question)
                    response = self._await_answer(incoming, future)
                self._send(incoming, response)
                self.offset_store.save(update_id + 1)
                checkpoint = update_id + 1
                processed += 1
                cursor += 1
        return processed

    def _incoming(self, update: dict) -> Incoming | None:
        message = update.get("message")
        if not isinstance(message, dict):
            return None
        sender = message.get("from") or {}
        chat = message.get("chat") or {}
        text = message.get("text")
        if (not isinstance(text, str) or not text.strip()
                or chat.get("type") not in ("private", "group", "supergroup")):
            return None
        try:
            user_id = int(sender["id"])
            peer_bot = sender.get("is_bot") is True
            if peer_bot and user_id not in self.peer_bot_ids:
                return None
            return Incoming(
                update_id=int(update["update_id"]), chat_id=int(chat["id"]),
                chat_type=chat["type"], message_id=int(message["message_id"]),
                user_id=user_id, text=text,
                thread_id=(int(message["message_thread_id"])
                           if "message_thread_id" in message else None),
                reply_to_bot=(
                    (message.get("reply_to_message") or {}).get("from", {}).get(
                        "id") == self.identity.id),
                peer_bot=peer_bot)
        except (KeyError, TypeError, ValueError):
            raise TelegramError("message identifiers are malformed")

    def _question(self, incoming: Incoming) -> str | None:
        text = incoming.text.strip()
        command = self._COMMAND.match(text)
        if incoming.peer_bot:
            if not command:
                return None
            name, target, body = command.groups()
            if (name.lower() != "ask" or not target
                    or target.lower() != self.identity.username.lower()):
                return None
            return (body or "").strip() or None
        if command:
            name, target, body = command.groups()
            if target and target.lower() != self.identity.username.lower():
                return None
            name = name.lower()
            if name == "ask":
                return (body or "").strip() or "\0usage"
            if name in ("start", "help", "privacy", "ping", "handoff",
                        "confirm_handoff", "cancel_handoff"):
                suffix = (body or "").strip()
                return "\0" + name + ((" " + suffix) if suffix else "")
            return "\0unknown"
        if incoming.chat_type == "private":
            return text
        if incoming.reply_to_bot:
            return text
        mention = re.match(
            rf"^@{re.escape(self.identity.username)}\b[,:]?\s*(.*)$",
            text, re.I | re.S)
        return mention.group(1).strip() if mention and mention.group(1).strip() else None

    def _answer(self, question: str) -> Outgoing:
        try:
            answer = self.engine.answer(question)
        except Exception:
            return Outgoing(
                "Aleph could not safely process that request. No answer or "
                "handoff was produced.")
        if answer.status == "needs_handoff" and answer.triage is not None:
            required = tuple(field for field in answer.triage.requested_fields
                             if field not in ("transaction_hash", "screenshot"))
            # Installed immediately before the response is sent; confirmation is
            # always a distinct later update from the same chat and user.
            return Outgoing(
                answer.text + "\n\nTo prepare it here, reply with /handoff "
                "field=value; field=value. Review the preview, then use "
                "/confirm_handoff. Use /cancel_handoff to discard it.",
                (answer.triage.kind, answer.triage.requested_fields, required),
                rich=True)
        return Outgoing(answer.text, rich=True)

    def _command(self, incoming: Incoming, command: str) -> str:
        name, _, body = command.partition(" ")
        key = (incoming.chat_id, incoming.user_id)
        if name == "start":
            return ("Aleph — evidence-bound answers about the Wildcat Protocol.\n\n"
                    "Try: /ask How do withdrawal cycles work?\n\n"
                    "In a private chat, plain questions work too. Every answer "
                    "cites pinned documentation, and live on-chain values name "
                    "the Ethereum block they were read at. /help covers groups "
                    "and handoffs; /privacy covers what Aleph reads.")
        if name == "help":
            return ("Ask with /ask <question>, or plain text in a private chat. "
                    f"In groups, use /ask@{self.identity.username} or reply to "
                    "an Aleph message.\n\n"
                    "Answers cite pinned Wildcat documentation and contract "
                    "sources — tap a citation to open the exact document. Live "
                    "values are read from Ethereum and labelled with their "
                    "block.\n\n"
                    "Use /ping to check process uptime and the active release "
                    "pins. If something needs a human — a stuck transaction, a UI "
                    "failure — Aleph prepares a handoff and sends nothing until "
                    "you issue /confirm_handoff.")
        if name == "privacy":
            return ("Aleph processes only messages Telegram delivers to this bot. "
                    "Group privacy mode must remain enabled. Handoffs are never "
                    "sent without /confirm_handoff.")
        if name == "ping":
            return self._ping()
        if name == "usage":
            return ("Usage: /ask <Wildcat Protocol question>\n"
                    "Example: /ask How do withdrawal cycles work?")
        if name == "unknown":
            return "Unknown command. Try /ask <question> or /help."
        if name == "cancel_handoff":
            self.pending.pop(key, None)
            return "The pending handoff was discarded. Nothing was sent."
        if name == "handoff":
            pending = self.pending.get(key)
            if pending is None:
                return "There is no pending handoff for you in this chat."
            try:
                supplied = self._handoff_fields(body)
            except TelegramError as error:
                return str(error) + " Nothing was sent."
            unknown = sorted(set(supplied) - set(pending.allowed))
            if unknown:
                return ("Unknown handoff field(s): " + ", ".join(unknown)
                        + ". Nothing was sent.")
            pending.fields.update(supplied)
            missing = [field for field in pending.required
                       if not pending.fields.get(field)]
            preview = "; ".join(f"{field}={value}"
                                for field, value in pending.fields.items())
            if missing:
                return ("Handoff draft: " + (preview or "empty")
                        + "\nStill required: " + ", ".join(missing)
                        + ". Nothing was sent.")
            return ("Handoff draft: " + preview
                    + "\nNothing has been sent. Use /confirm_handoff to send it "
                    "or /cancel_handoff to discard it.")
        if name == "confirm_handoff":
            pending = self.pending.get(key)
            if pending is None:
                return "There is no pending handoff for you in this chat."
            missing = [field for field in pending.required
                       if not pending.fields.get(field)]
            if missing:
                return ("The handoff is missing: " + ", ".join(missing)
                        + ". Nothing was sent.")
            try:
                reference = self.handoff_sink.send(HandoffPayload(
                    pending.handoff_id, pending.kind,
                    incoming.chat_id, incoming.user_id,
                    dict(pending.fields)))
            except TelegramError as error:
                return f"Handoff unavailable: {error}. Nothing was sent."
            del self.pending[key]
            return f"Handoff sent. Reference: {reference}"
        raise TelegramError(f"unsupported adapter command {name!r}")

    def _ping(self) -> str:
        """Return bounded public process and immutable artifact identity."""
        status = self.ping_status
        dynamic = (dict(self.ping_status_provider())
                   if self.ping_status_provider is not None else {})
        lines = [
            "Pong!",
            f"Alive: {_uptime(self.monotonic_clock() - self.started_monotonic)}",
        ]
        fields = (
            ("Identity", "identity"),
            ("Activation sequence", "activation_sequence"),
            ("Activation", "activation_id"),
            ("Release", "release_id"),
            ("Corpus", "corpus_build_id"),
            ("Index", "index_namespace"),
            ("Evaluation", "evaluation_id"),
            ("Prerelease", "prerelease_release_id"),
            ("Gateway", "gateway_release"),
            ("Embedding", "embedding"),
            ("Manifest", "manifest_sha256"),
            ("Sources", "source_pins"),
        )
        present = 0
        for label, key in fields:
            value = status.get(key)
            if value is None or value == "":
                continue
            text = str(value)
            if len(text) > 1000 or "\n" in text:
                continue
            lines.append(f"{label}: {text}")
            present += 1
        if not present:
            lines.append("Runtime pins: unavailable")
        local_writer = dynamic.get("local_writer")
        if isinstance(local_writer, Mapping):
            mode = str(local_writer.get("mode", "disabled"))
            alias = str(local_writer.get("alias") or "none")
            model_id = str(local_writer.get("id") or "none")
            counts = local_writer.get("counts")
            line = f"Mephistopheles: {mode}; alias={alias}; id={model_id}"
            if isinstance(counts, Mapping):
                line += (f"; shadow total={counts.get('total', 0)}, "
                         f"valid={counts.get('valid', 0)}, "
                         f"rejected={counts.get('rejected', 0)}, "
                         f"fallback={counts.get('fallback', 0)}")
            if len(line) <= 1000 and "\n" not in line:
                lines.append(line)
        return "\n".join(lines)

    @staticmethod
    def _handoff_fields(body: str) -> dict[str, str]:
        if not body.strip():
            raise TelegramError("Use /handoff field=value; field=value.")
        fields = {}
        for part in body.split(";"):
            name, separator, value = part.strip().partition("=")
            if not separator or not re.fullmatch(r"[a-z_]+", name):
                raise TelegramError(f"Invalid handoff field {part.strip()!r}.")
            value = value.strip()
            if not value or len(value) > 1000:
                raise TelegramError(f"Invalid value for handoff field {name!r}.")
            if name in fields:
                raise TelegramError(f"Duplicate handoff field {name!r}.")
            fields[name] = value
        return fields

    def _send(self, incoming: Incoming, outgoing: Outgoing) -> None:
        if self._send_rich(incoming, outgoing):
            self._install_handoff(incoming, outgoing)
            return
        reply_to = incoming.message_id
        # Engine answers for humans carry cosmetic entity rendering; peer
        # bots and command replies keep exact plain bytes.
        rendered = (format_message(outgoing.text)
                    if outgoing.rich and not incoming.peer_bot else None)
        if rendered is None:
            for chunk in split_message(outgoing.text):
                reply_to = self._send_chunk(incoming, chunk, reply_to)
        else:
            for chunk in rendered:
                reply_to = self._send_rendered(incoming, chunk, reply_to)
        self._install_handoff(incoming, outgoing)

    def _send_rich(self, incoming: Incoming, outgoing: Outgoing) -> bool:
        if (not self.rich_messages or not outgoing.rich or incoming.peer_bot
                or len(outgoing.text) > RICH_MESSAGE_LIMIT):
            return False
        payload = {
            "chat_id": incoming.chat_id,
            "rich_message": {"markdown": rich_markdown(outgoing.text)},
            "reply_parameters": {
                "message_id": incoming.message_id,
                "allow_sending_without_reply": False,
            },
        }
        if incoming.thread_id is not None:
            payload["message_thread_id"] = incoming.thread_id
        try:
            self.api.call("sendRichMessage", payload)
        except TelegramRefused:
            return False
        return True

    def _send_chunk(self, incoming: Incoming, text: str, reply_to: int,
                    parse_mode: str | None = None,
                    buttons: tuple[tuple[str, str], ...] = ()) -> int:
        payload = {
            "chat_id": incoming.chat_id, "text": text,
            "reply_parameters": {
                "message_id": reply_to,
                "allow_sending_without_reply": False,
            },
            "link_preview_options": {"is_disabled": True},
        }
        if parse_mode is not None:
            payload["parse_mode"] = parse_mode
        if buttons:
            payload["reply_markup"] = {"inline_keyboard": [
                [{"text": label, "url": url} for label, url in buttons]]}
        if incoming.thread_id is not None:
            payload["message_thread_id"] = incoming.thread_id
        sent = self.api.call("sendMessage", payload)
        if isinstance(sent, dict) and isinstance(sent.get("message_id"), int):
            return sent["message_id"]
        return reply_to

    def _send_rendered(self, incoming: Incoming, chunk: RenderedChunk,
                       reply_to: int) -> int:
        # Markup is cosmetic: if Telegram definitively refuses the HTML
        # rendering, the exact plain bytes still ship, split as any oversized
        # answer is. Ambiguous transport failures propagate instead, leaving
        # the update unconfirmed rather than risking a duplicate delivery.
        try:
            return self._send_chunk(incoming, chunk.html, reply_to, "HTML",
                                    chunk.buttons)
        except TelegramRefused:
            for piece in split_message(chunk.plain):
                reply_to = self._send_chunk(incoming, piece, reply_to)
            return reply_to

    def _await_answer(self, incoming: Incoming, future,
                      interval: float = 4.5) -> Outgoing:
        """Collect the engine's answer, refreshing the typing hint meanwhile.

        Telegram shows a chat action for about five seconds, so slow answers
        need the hint renewed until the reply is ready to send.
        """
        if not 0 < interval <= 60:
            raise TelegramError("typing refresh interval must be within (0, 60]")
        if incoming.peer_bot:
            return future.result()
        while True:
            self._typing(incoming)
            try:
                return future.result(timeout=interval)
            except FutureTimeout:
                continue

    def _typing(self, incoming: Incoming) -> None:
        """Best-effort typing hint; a failure never blocks or delays the answer."""
        payload = {"chat_id": incoming.chat_id, "action": "typing"}
        if incoming.thread_id is not None:
            payload["message_thread_id"] = incoming.thread_id
        try:
            self.api.call("sendChatAction", payload)
        except TelegramError:
            pass

    def _install_handoff(self, incoming: Incoming, outgoing: Outgoing) -> None:
        if outgoing.pending_handoff is None:
            return
        kind, allowed, required = outgoing.pending_handoff
        handoff_id = hashlib.sha256(
            f"{incoming.chat_id}:{incoming.user_id}:{incoming.update_id}".encode()
        ).hexdigest()[:16]
        self.pending[(incoming.chat_id, incoming.user_id)] = PendingHandoff(
            handoff_id, kind, tuple(allowed), tuple(required), {})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--offset-file", default="state/telegram-offset.json")
    parser.add_argument("--max-workers", type=int, default=4)
    args = parser.parse_args()
    print("FATAL: construct TelegramAdapter with a configured AnswerEngine", file=sys.stderr)
    print("telegram.py is an adapter module; production composition is stage 7",
          file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
