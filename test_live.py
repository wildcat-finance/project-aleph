#!/usr/bin/env python3
"""Adversarial tests for SDK address checks, live reads, and renderers."""

from __future__ import annotations

import base64
import copy
import hashlib
import io
import json
import pathlib
import shutil
import sys
import tarfile
import tempfile

import gateway_smoke
import live

FAILURES: list[str] = []
MARKET = "0x1111111111111111111111111111111111111111"
BORROWER = "0x2222222222222222222222222222222222222222"
ASSET = "0x3333333333333333333333333333333333333333"
LENDER = "0x4444444444444444444444444444444444444444"
LENS = "0xfDA5C5B96bb198D2fca1A01d759620B64Ae5afE7"


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if ok else 'FAIL'} {name}"
          + (f" — {detail}" if detail and not ok else ""))
    if not ok:
        FAILURES.append(name)


def sdk_tarball() -> bytes:
    files = {
        "package/package.json": json.dumps({"version": "3.1.17"}).encode(),
        "package/dist/constants.js": (
            'exports.Deployments = {\n'
            '  [exports.SupportedChainId.Mainnet]: {\n'
            f'    MarketLens: "0x9999999999999999999999999999999999999999",\n'
            f'    MarketLensV2: "{LENS}",\n'
            f'    WildcatArchController: "{BORROWER}"\n'
            '  }\n};\n').encode(),
    }
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as archive:
        for name, content in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
    return output.getvalue()


def write_manifest(tmp: pathlib.Path, tarball: bytes) -> pathlib.Path:
    integrity = "sha512-" + base64.b64encode(
        hashlib.sha512(tarball).digest()).decode()
    path = tmp / "manifest.yaml"
    path.write_text(
        "version: 1\npolicy:\n  scope:\n    chains: [1]\n"
        "live_state:\n  graph: 'https://graph.example/{network}/{release}'\n"
        "  health: 'https://graph.example/health'\n"
        "  auth: {scheme: bearer, env: ALEPH_GATEWAY_TOKEN}\n"
        "  pinned_releases: {mainnet: v2.0.30}\n"
        "addresses:\n  source: 'npm:@wildcatfi/wildcat-sdk'\n"
        "  pinned_version: '3.1.17'\n"
        f"  integrity: '{integrity}'\n  git_head: '{'a' * 40}'\n"
        "  resolve_by: key\n  assertions:\n"
        f"    MarketLensV2: '{LENS}'\n"
        f"    WildcatArchController: '{BORROWER}'\n")
    return path


def market_summary() -> dict:
    return {"id": MARKET, "name": "Example Market", "symbol": "WILD-USDC",
            "borrower": BORROWER, "isClosed": False, "isRegistered": True,
            "decimals": 6,
            "asset": {"address": ASSET, "symbol": "USDC", "decimals": 6}}


def registry_markets(count: int = 12) -> list[dict]:
    markets = []
    for index in range(count, 0, -1):
        item = market_summary()
        item.update({
            "id": f"0x{index:040x}",
            "name": ("Registry Market " + str(index)) * (20 if index == 12 else 1),
            "symbol": ("WILD-" + str(index)) * (20 if index == 12 else 1),
        })
        markets.append(item)
    return markets


def healthy() -> dict:
    return {"deployments": [{
        "chainId": 1, "releaseName": "v2.0.30", "state": "ready",
        "readyProviders": 2, "replicas": [
            {"providerId": "one", "state": "ready", "integrity": "verified",
             "circuit": "closed", "lagBlocks": 0, "indexedBlock": 100,
             "observedHead": 100},
            {"providerId": "two", "state": "ready", "integrity": "verified",
             "circuit": "closed", "lagBlocks": 0, "indexedBlock": 100,
             "observedHead": 100},
        ]}]}


class FakeTransport:
    def __init__(self, health=None, block=100):
        self.health = health or healthy()
        self.block = block
        self.get_calls = []
        self.post_calls = []

    def get_json(self, url: str) -> dict:
        self.get_calls.append(url)
        return copy.deepcopy(self.health)

    def post_json(self, url: str, body: dict, token: str) -> dict:
        self.post_calls.append((url, copy.deepcopy(body), token))
        query = body["query"]
        data = {"_meta": {"block": {"number": self.block}}}
        if "query Registry(" in query:
            data["markets"] = registry_markets()
        elif "query Market(" in query:
            data["market"] = {**market_summary(),
                "totalAssets": "123456789", "maxTotalSupply": "1000000000",
                "scaledTotalSupply": "110000000", "scaledPendingWithdrawals": "10",
                "normalizedUnclaimedWithdrawals": "20", "pendingWithdrawalExpiry": "0",
                "annualInterestBips": 1125, "reserveRatioBips": 1000,
                "delinquencyFeeBips": 500, "delinquencyGracePeriod": 86400,
                "withdrawalBatchDuration": 86400, "isDelinquent": True,
                "timeDelinquent": 3661}
        elif "query Account(" in query:
            data["market"] = {
                "id": MARKET, "name": "Example Market", "symbol": "WILD-USDC",
                "decimals": 6, "asset": market_summary()["asset"],
                "lenders": [{"address": LENDER, "scaledBalance": "1200000",
                             "totalDeposited": "5000000",
                             "totalInterestEarned": "12000",
                             "numPendingWithdrawalBatches": 2, "role": "Null"}]}
            data["market"]["lenders"][0]["withdrawals"] = [
                {"scaledAmount": "2000000",
                 "normalizedAmountWithdrawn": "500000",
                 "isCompleted": False,
                 "batch": {"scaledTotalAmount": "4000000",
                           "normalizedAmountPaid": "3000000"}},
                {"scaledAmount": "1000000",
                 "normalizedAmountWithdrawn": "0",
                 "isCompleted": False,
                 "batch": {"scaledTotalAmount": "2000000",
                           "normalizedAmountPaid": "500000"}},
            ]
        elif "query Withdrawals(" in query:
            data["market"] = {
                "id": MARKET, "name": "Example Market",
                "asset": market_summary()["asset"],
                "withdrawalBatches": [{"expiry": 1_700_000_000,
                    "isClosed": False, "isCompleted": False,
                    "scaledTotalAmount": "5000000", "scaledAmountBurned": "1000000",
                    "normalizedAmountPaid": "2000000",
                    "normalizedTotalAmount": "5000000",
                    "totalInterestEarned": "1000"}]}
        elif "query BorrowerMarkets(" in query:
            data["markets"] = registry_markets()
        elif "query History(" in query:
            first = body["variables"]["first"]
            def event(index, amount, transaction, log_index):
                return {
                    "eventIndex": index, "assetAmount": str(amount),
                    "blockNumber": 60 + index, "blockTimestamp": 1_700_000_000 + index,
                    "transactionHash": "0x" + transaction * 64,
                    "blockLogIndex": log_index,
                }
            borrows = [
                event(40, 4_000_000, "a", 4),
                event(32, 3_200_000, "b", 3),
                event(20, 2_000_000, "c", 2),
            ]
            repayments = [event(39, 3_900_000, "d", 3)]
            deposits = [event(38, 3_800_000, "e", 2)]
            withdrawals = [event(37, 3_700_000, "f", 1)]
            withdrawals[0]["normalizedAmount"] = withdrawals[0].pop(
                "assetAmount")
            data["market"] = {
                "id": MARKET, "name": "Example Market",
                "asset": market_summary()["asset"],
                "borrowRecords": borrows[:first],
                "repaymentRecords": repayments[:first],
                "depositRecords": deposits[:first],
                "withdrawalRequestRecords": withdrawals[:first],
            }
        else:
            return {"errors": [{"message": "unknown fixture query"}]}
        return {"data": data}


def run(tmp: pathlib.Path) -> None:
    tarball = sdk_tarball()
    manifest = write_manifest(tmp, tarball)

    print("\nL1 — the SDK artifact is pinned and addresses resolve by map key")
    book = live.AddressBook.from_tarball(str(manifest), tarball)
    check("every manifest assertion is enforced",
          book.gate_record()["address_assertions_hold"] is True)
    check("MarketLensV2 resolves to the asserted production key",
          book.resolve("MarketLensV2").lower() == LENS.lower())
    refused = ""
    try:
        book.resolve("MarketLens")
    except live.AddressError as error:
        refused = str(error)
    check("a legacy display name cannot be used as an address key",
          "not an asserted deployment key" in refused, refused)
    original = manifest.read_text()
    manifest.write_text(original.replace(LENS, "0x" + "0" * 40))
    refused = ""
    try:
        live.AddressBook.from_tarball(str(manifest), tarball)
    except live.AddressError as error:
        refused = str(error)
    check("an SDK address move fails the gate", "assertions failed" in refused,
          refused[:160])
    manifest.write_text(original)
    damaged = tarball + b"damage"
    refused = ""
    try:
        live.AddressBook.from_tarball(str(manifest), damaged)
    except live.AddressError as error:
        refused = str(error)
    check("a tarball differing from the pinned SRI digest is refused",
          "does not match manifest" in refused, refused[:160])

    print("\nL2 — every live read is health-gated and pinned to one block")
    transport = FakeTransport()
    client = live.GatewayClient(str(manifest), transport=transport, token="test")
    market = client.market(MARKET)
    registry = client.registry()
    account = client.account(MARKET, LENDER)
    withdrawals = client.withdrawals(MARKET)
    borrower = client.borrower_markets(BORROWER)
    history = client.history(MARKET, limit=3, event_types=("borrow",))
    check("all six narrow operations return typed facts",
          isinstance(market.value, live.MarketState)
          and isinstance(registry.value, live.RegistryState)
          and isinstance(account.value, live.AccountState)
          and isinstance(withdrawals.value, live.WithdrawalQueueState)
          and isinstance(borrower.value, live.BorrowerMarketsState)
          and isinstance(history.value, live.MarketHistoryState))
    check("health is checked immediately before every query",
          len(transport.get_calls) == len(transport.post_calls) == 6)
    check("the pinned release is explicit in every request URL",
          all(url.endswith("/mainnet/v2.0.30")
              for url, _, _ in transport.post_calls))
    check("every GraphQL operation requests the checked block",
          all(call[1]["variables"]["block"] == {"number": 100}
              for call in transport.post_calls))
    check("every typed result propagates the observed block and release",
          all(result.block_number == 100 and result.gateway_release == "v2.0.30"
              for result in (
                  market, registry, account, withdrawals, borrower, history)))
    registry_render = live.render_live(registry)
    registry_lines = registry_render.text.splitlines()
    check("registry rendering states the total and deterministic first page",
          registry_lines[0] == (
              "Registered markets (12; showing 1–10 in contract-address order):")
          and len([line for line in registry_lines if line.startswith("- ")])
              == live.REGISTRY_PAGE_SIZE
          and "0x0000000000000000000000000000000000000001"
              in registry_lines[1]
          and "0x000000000000000000000000000000000000000a"
              in registry_lines[10]
          and "000000000000000000000000000000000000000b"
              not in registry_render.text)
    check("registry rendering is byte-stable and fits one Telegram message",
          registry_render == live.render_live(registry)
          and len(registry_render.text) <= 4096
          and registry_render.text.endswith(
              "Data Gateway release v2.0.30."))
    check("registry labels and the fetched-result ceiling are explicit",
          len(live._registry_label("x" * 200)) == live.REGISTRY_LABEL_LIMIT
          and live._registry_label("line one\n- forged line")
              == "line one - forged line"
          and registry.value.query_limit == live.DEFAULT_REGISTRY_LIMIT)
    borrower_render = live.render_live(borrower)
    borrower_lines = borrower_render.text.splitlines()
    check("borrower discovery states the total and deterministic first page",
          borrower_lines[0] == (
              f"Markets for borrower {BORROWER} "
              "(12; showing 1–10 in contract-address order):")
          and len([line for line in borrower_lines if line.startswith("- ")])
              == live.BORROWER_MARKETS_PAGE_SIZE
          and "0x0000000000000000000000000000000000000001"
              in borrower_lines[1]
          and "0x000000000000000000000000000000000000000a"
              in borrower_lines[10]
          and "000000000000000000000000000000000000000b"
              not in borrower_render.text)
    check("borrower discovery is byte-stable and fits one Telegram message",
          borrower_render == live.render_live(borrower)
          and len(borrower_render.text) <= 4096
          and borrower.value.query_limit == 100
          and borrower_render.text.endswith(
              "Data Gateway release v2.0.30."))
    check("account claimable is allocated exactly across pending batches",
          account.value.claimable_withdrawals == 1_250_000)
    smoke_transport = FakeTransport()
    smoke = gateway_smoke.check(
        str(manifest), client=live.GatewayClient(
            str(manifest), transport=smoke_transport, token="smoke-secret"))
    check("the operator preflight performs one authenticated pinned query",
          smoke["ok"] and smoke["block_number"] == 100
          and smoke["gateway_release"] == "v2.0.30"
          and len(smoke_transport.get_calls) == 1
          and len(smoke_transport.post_calls) == 1)
    check("the operator preflight report never contains its bearer token",
          "smoke-secret" not in json.dumps(smoke))
    borrower_fields = set(borrower.value.__dataclass_fields__)
    check("borrower aggregation contains facts, never scores or rankings",
          not borrower_fields.intersection(
              {"score", "rank", "reliability", "trust", "risk"}))
    check("history is bounded, typed, and newest-first across requested events",
          len(history.value.events) == 3
          and tuple(event.event_index for event in history.value.events)
          == (40, 32, 20)
          and all(event.kind == "borrow" for event in history.value.events))
    bounded = client.history(MARKET, limit=2)
    check("mixed history returns no more than the requested overall limit",
          len(bounded.value.events) == 2
          and tuple(event.event_index for event in bounded.value.events)
          == (40, 39))
    refused = ""
    try:
        client.history(MARKET, limit=live.MAX_HISTORY_EVENTS + 1)
    except live.LiveError as error:
        refused = str(error)
    check("history limits above the fixed contract fail before a gateway read",
          "between 1 and 10" in refused, refused)

    print("\nL3 — unhealthy, lagging, or incoherent data fails closed")
    lagging_health = healthy()
    lagging_health["deployments"][0]["replicas"][0]["lagBlocks"] = 1
    lagging_transport = FakeTransport(lagging_health)
    refused = ""
    try:
        live.GatewayClient(str(manifest), lagging_transport, "test").market(MARKET)
    except live.GatewayUnavailable as error:
        refused = str(error)
    check("one routable lagging replica blocks the answer",
          "lagging" in refused and not lagging_transport.post_calls, refused)
    wrong_block = FakeTransport(block=99)
    refused = ""
    try:
        live.GatewayClient(str(manifest), wrong_block, "test").market(MARKET)
    except live.GatewayUnavailable as error:
        refused = str(error)
    check("a response from a block other than the requested one is refused",
          "requested 100" in refused, refused)
    no_token = FakeTransport()
    refused = ""
    try:
        live.GatewayClient(str(manifest), no_token, token="").market(MARKET)
    except live.GatewayUnavailable as error:
        refused = str(error)
    check("the client never falls back when its dedicated token is absent",
          "token is absent" in refused and not no_token.post_calls, refused)
    class IncompleteAccountTransport(FakeTransport):
        def post_json(self, url: str, body: dict, token: str) -> dict:
            payload = super().post_json(url, body, token)
            if "query Account(" in body["query"]:
                payload["data"]["market"]["lenders"][0][
                    "numPendingWithdrawalBatches"] = 3
            return payload
    incomplete = IncompleteAccountTransport()
    refused = ""
    try:
        live.GatewayClient(
            str(manifest), incomplete, "test").account(MARKET, LENDER)
    except live.LiveError as error:
        refused = str(error)
    check("an incomplete account withdrawal page fails closed",
          "2 of 3 pending withdrawal batches" in refused, refused)
    class IncoherentHistoryTransport(FakeTransport):
        def post_json(self, url: str, body: dict, token: str) -> dict:
            payload = super().post_json(url, body, token)
            if "query History(" in body["query"]:
                payload["data"]["market"]["borrowRecords"][0][
                    "blockNumber"] = 101
            return payload
    refused = ""
    try:
        live.GatewayClient(
            str(manifest), IncoherentHistoryTransport(), "test").history(
                MARKET, limit=1, event_types=("borrow",))
    except live.LiveError as error:
        refused = str(error)
    check("a history event later than the pinned response block fails closed",
          "later than the pinned response block" in refused, refused)
    class MalformedHistoryTransport(FakeTransport):
        def post_json(self, url: str, body: dict, token: str) -> dict:
            payload = super().post_json(url, body, token)
            if "query History(" in body["query"]:
                payload["data"]["market"]["borrowRecords"][0][
                    "transactionHash"] = "not-a-transaction"
            return payload
    refused = ""
    try:
        live.GatewayClient(
            str(manifest), MalformedHistoryTransport(), "test").history(
                MARKET, limit=1, event_types=("borrow",))
    except live.LiveError as error:
        refused = str(error)
    check("malformed transaction provenance fails closed",
          "transactionHash is malformed" in refused, refused)

    print("\nL4 — numeric and state prose is produced only by deterministic code")
    rendered_market = live.render_live(market)
    rendered_account = live.render_live(account)
    rendered_withdrawals = live.render_live(withdrawals)
    rendered_history = live.render_live(history)
    check("integer token units are formatted without floating point",
          "123.456789 USDC" in rendered_market.text
          and "Claimable withdrawals: 1.25 USDC" in rendered_account.text,
          rendered_account.text)
    check("basis points and durations have stable exact formatting",
          "APR: 11.25%" in rendered_market.text
          and "Time delinquent: 1h 1m 1s" in rendered_market.text)
    check("market summaries expose capacity and grace deterministically",
          "Remaining capacity: 876.543211 USDC" in rendered_market.text
          and "Delinquency grace period: 1d" in rendered_market.text)
    compact_apr = live.render_live(market, field="apr")
    compact_grace = live.render_live(market, field="grace_period")
    check("field renderers return only the requested market fact",
          "APR: 11.25%" in compact_apr.text
          and "Reserve ratio" not in compact_apr.text
          and "Delinquency grace period: 1d" in compact_grace.text
          and "APR:" not in compact_grace.text)
    check("every renderer appends the block and pinned release",
          "Ethereum block 100" in rendered_market.text
          and "release v2.0.30" in rendered_market.text
          and "Ethereum block 100" in rendered_withdrawals.text
          and "Ethereum block 100" in rendered_history.text)
    check("every history event renders amount, transaction, and block provenance",
          rendered_history.text.count("transaction 0x") == 3
          and rendered_history.text.count("; block ") == 3
          and "4 USDC" in rendered_history.text)
    check("re-rendering the same typed result is byte-identical",
          live.render_live(market).text == rendered_market.text)


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
