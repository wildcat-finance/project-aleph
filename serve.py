#!/usr/bin/env python3
"""Compose and run the production Aleph query and Telegram process."""

from __future__ import annotations

import argparse
import pathlib
import signal
import sys
import threading

from activation import ActivationError, ActivationStore
from agent import AnswerEngine
from audit import AuditError, AuditLogger, AuditedEngine
from live import GatewayClient, LiveError
from retrieval import Retriever, RetrievalError
from telegram import (OffsetStore, TelegramAdapter, TelegramError, TelegramHTTP,
                      peer_bot_ids, rich_messages_enabled)


def compose(manifest: str, artifacts: str, pointer: str, prerelease: str,
            embedder: str, audit_dir: str, retention_days: int,
            offset_file: str, max_workers: int):
    store = ActivationStore(artifacts, pointer, manifest)
    release_path, active, _ = store.load_active()
    prerelease_path = pathlib.Path(prerelease).resolve()
    try:
        prerelease_path.relative_to(pathlib.Path(artifacts).resolve() / "releases")
    except ValueError:
        raise ActivationError("prerelease is outside the artifact release store")
    retriever = Retriever(
        manifest, str(release_path), embedder, str(prerelease_path))
    live_client = GatewayClient(manifest)
    engine = AnswerEngine(retriever, live_client)
    logger = AuditLogger(audit_dir, active, retention_days=retention_days)
    logger.purge_expired()
    audited = AuditedEngine(engine, logger)
    api = TelegramHTTP()
    adapter = TelegramAdapter(
        audited, api, OffsetStore(offset_file), max_workers=max_workers,
        peer_bot_ids=peer_bot_ids(),
        rich_messages=rich_messages_enabled())
    return adapter, logger


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--manifest", default="manifest.yaml")
    parser.add_argument("--artifacts", default="artifacts")
    parser.add_argument("--pointer", default="state/active-release.json")
    parser.add_argument("--prerelease", required=True)
    parser.add_argument("--embedder", default="ollama:bge-m3")
    parser.add_argument("--audit-dir", default="var/audit")
    parser.add_argument("--audit-retention-days", type=int, default=30)
    parser.add_argument("--telegram-offset", default="state/telegram-offset.json")
    parser.add_argument("--max-workers", type=int, default=4)
    args = parser.parse_args()
    try:
        adapter, _ = compose(
            args.manifest, args.artifacts, args.pointer, args.prerelease,
            args.embedder, args.audit_dir, args.audit_retention_days,
            args.telegram_offset, args.max_workers)
    except (ActivationError, AuditError, LiveError, RetrievalError,
            TelegramError, OSError) as error:
        print(f"FATAL: {error}", file=sys.stderr)
        return 1
    stop = threading.Event()
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_: stop.set())
    try:
        adapter.run_forever(timeout=30, stop_event=stop)
    except TelegramError as error:
        print(f"FATAL: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
