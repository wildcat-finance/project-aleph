#!/usr/bin/env python3
"""One-shot production dependency checks for supervisor and alerting systems."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from datetime import datetime, timezone

from activation import ActivationError, ActivationStore
from embed.embedder import Identity, require_match, EmbeddingError
from live import GatewayClient, LiveError
from retrieval import Retriever, RetrievalError
from telegram import (OffsetStore, TelegramAdapter, TelegramError, TelegramHTTP,
                      peer_bot_ids, rich_messages_enabled)


class NullEngine:
    def answer(self, question):
        raise RuntimeError("monitor does not answer questions")


def check(manifest: str, artifacts: str, pointer: str, prerelease: str,
          embedder: str, api=None, gateway_client=None) -> dict:
    checks = {}
    store = ActivationStore(artifacts, pointer, manifest)
    release_path, active, active_pointer = store.load_active()
    checks["active_release"] = {
        "ok": True, "release_id": active["release_id"],
        "generation": active_pointer["generation"],
        "evaluation_id": active["evaluation"]["evaluation_id"],
    }
    retriever = Retriever(manifest, str(release_path), embedder, prerelease)
    runtime_identity = retriever.embedders["v2.0"].identity()
    require_match(Identity.from_dict(active["embedding"]), runtime_identity)
    checks["model_runtime"] = {"ok": True,
                               "identity": runtime_identity.to_dict()}
    gateway = gateway_client or GatewayClient(manifest)
    health = gateway.check_health()
    registry_probe = gateway.registry(limit=1)
    if not registry_probe.value.markets:
        raise LiveError("gateway history probe has no registered market")
    history_probe = gateway.history(
        registry_probe.value.markets[0].address, limit=1)
    checks["gateway"] = {
        "ok": True, "release": health.release,
        "indexed_block": health.indexed_block,
        "observed_head": health.observed_head,
        "ready_providers": health.ready_providers,
        "history_probe": {
            "ok": True,
            "block_number": history_probe.block_number,
            "events_returned": len(history_probe.value.events),
            "maximum_events": 1,
        },
    }
    telegram_api = api or TelegramHTTP()
    peers = peer_bot_ids()
    rich_messages = rich_messages_enabled()
    adapter = TelegramAdapter(
        NullEngine(), telegram_api, OffsetStore("state/monitor-unused.json"),
        peer_bot_ids=peers, rich_messages=rich_messages)
    identity = adapter.startup()
    checks["telegram"] = {"ok": True, "bot_id": identity.id,
                           "username": identity.username,
                           "privacy_mode": "enabled", "webhook": "absent",
                           "peer_bot_count": len(peers),
                           "rich_messages": rich_messages}
    return {"ok": True,
            "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "checks": checks}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--manifest", default="manifest.yaml")
    parser.add_argument("--artifacts", default="artifacts")
    parser.add_argument("--pointer", default="state/active-release.json")
    parser.add_argument("--prerelease", required=True)
    parser.add_argument("--embedder", default="ollama:bge-m3")
    args = parser.parse_args()
    try:
        report = check(args.manifest, args.artifacts, args.pointer,
                       args.prerelease, args.embedder)
    except (ActivationError, EmbeddingError, LiveError, RetrievalError,
            TelegramError, OSError) as error:
        report = {
            "ok": False,
            "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "error": str(error),
        }
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
