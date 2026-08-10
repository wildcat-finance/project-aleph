#!/usr/bin/env python3
"""Run one authenticated, block-pinned Data Gateway preflight query."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

from live import GatewayClient, LiveError, RegistryState


def check(manifest: str = "manifest.yaml", limit: int = 1,
          client: GatewayClient | None = None) -> dict:
    """Return a credential-free report after a real registry query."""
    result = (client or GatewayClient(manifest)).registry(limit=limit)
    if not isinstance(result.value, RegistryState):
        raise LiveError("gateway preflight did not return registry state")
    return {
        "ok": True,
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "chain_id": result.chain_id,
        "gateway_release": result.gateway_release,
        "block_number": result.block_number,
        "observed_head": result.observed_head,
        "sampled_markets": len(result.value.markets),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--manifest", default="manifest.yaml")
    parser.add_argument("--limit", type=int, default=1)
    args = parser.parse_args()
    try:
        report = check(args.manifest, args.limit)
    except (LiveError, OSError) as error:
        report = {
            "ok": False,
            "checked_at": datetime.now(timezone.utc).isoformat(
                timespec="seconds"),
            "error": str(error),
        }
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
