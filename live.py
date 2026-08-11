#!/usr/bin/env python3
"""Pinned live-state reads and deterministic renderers for Project Aleph."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import pathlib
import re
import tarfile
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Callable


class LiveError(Exception):
    """A live fact cannot be read or rendered safely."""


class AddressError(LiveError):
    """The SDK address artifact does not satisfy the manifest."""


class GatewayUnavailable(LiveError):
    """The pinned gateway release is absent, unhealthy, or lagging."""


_ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")
_TRANSACTION_HASH = re.compile(r"^0x[0-9a-fA-F]{64}$")
HISTORY_EVENT_TYPES = ("borrow", "repayment", "deposit", "withdrawal")
DEFAULT_HISTORY_EVENTS = 5
MAX_HISTORY_EVENTS = 10


def _address(value: str, field: str) -> str:
    if not isinstance(value, str) or not _ADDRESS.fullmatch(value):
        raise LiveError(f"{field} is not an Ethereum address: {value!r}")
    return value.lower()


def _transaction_hash(value: str) -> str:
    if not isinstance(value, str) or not _TRANSACTION_HASH.fullmatch(value):
        raise LiveError(f"transactionHash is malformed: {value!r}")
    return value.lower()


def _integer(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise LiveError(f"{field} is boolean, not an integer")
    try:
        result = int(value)
    except (TypeError, ValueError):
        raise LiveError(f"{field} is not an integer: {value!r}")
    if result < 0:
        raise LiveError(f"{field} is negative: {result}")
    return result


def _timestamp(value: Any, field: str) -> int:
    result = _integer(value, field)
    try:
        datetime.fromtimestamp(result, timezone.utc)
    except (OverflowError, OSError, ValueError) as error:
        raise LiveError(f"{field} is outside the supported UTC range") from error
    return result


def _boolean(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise LiveError(f"{field} is not boolean: {value!r}")
    return value


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise LiveError(f"{field} is empty or not text: {value!r}")
    return value


def _manifest(path: str) -> dict:
    try:
        import yaml
    except ImportError:
        raise LiveError("live.py needs pyyaml (pip install pyyaml)")
    return yaml.safe_load(pathlib.Path(path).read_bytes())


def _brace_block(text: str, start: int) -> str:
    index = text.index("{", start)
    depth = 0
    for cursor in range(index, len(text)):
        if text[cursor] == "{":
            depth += 1
        elif text[cursor] == "}":
            depth -= 1
            if depth == 0:
                return text[index:cursor + 1]
    raise AddressError("unbalanced Deployments object in SDK constants.js")


def _mainnet_addresses(constants_js: str) -> dict[str, str]:
    anchor = constants_js.find("exports.Deployments")
    if anchor == -1:
        raise AddressError("SDK has no exports.Deployments map")
    marker = re.search(r"SupportedChainId\.Mainnet\]\s*:",
                       constants_js[anchor:])
    if not marker:
        raise AddressError("SDK Deployments has no Mainnet entry")
    block = _brace_block(constants_js, anchor + marker.end())
    found = re.findall(r'(\w+)\s*:\s*"(0x[a-fA-F0-9]{40})"', block)
    if not found:
        raise AddressError("SDK Mainnet deployment map contains no addresses")
    return dict(found)


def _member_bytes(archive: tarfile.TarFile, name: str) -> bytes:
    try:
        member = archive.getmember(name)
    except KeyError:
        raise AddressError(f"SDK tarball is missing {name}")
    if not member.isfile():
        raise AddressError(f"SDK tar member is not a file: {name}")
    handle = archive.extractfile(member)
    if handle is None:
        raise AddressError(f"cannot read SDK tar member: {name}")
    return handle.read()


@dataclass(frozen=True)
class AddressBook:
    version: str
    integrity: str
    git_head: str
    tarball_sha512: str
    addresses: dict[str, str]
    assertions: dict[str, str]

    @classmethod
    def from_tarball(cls, manifest_path: str, tarball: bytes) -> "AddressBook":
        manifest = _manifest(manifest_path)
        policy = manifest.get("addresses") or {}
        expected_integrity = policy.get("integrity")
        digest = hashlib.sha512(tarball).digest()
        integrity = "sha512-" + base64.b64encode(digest).decode()
        if not expected_integrity or integrity != expected_integrity:
            raise AddressError(
                f"SDK tarball integrity {integrity} does not match manifest "
                f"{expected_integrity or '<missing>'}")
        try:
            with tarfile.open(fileobj=io.BytesIO(tarball), mode="r:gz") as archive:
                package = json.loads(_member_bytes(
                    archive, "package/package.json"))
                constants = _member_bytes(
                    archive, "package/dist/constants.js").decode(
                        "utf-8", errors="strict")
        except (tarfile.TarError, UnicodeError, json.JSONDecodeError) as error:
            raise AddressError(f"invalid SDK tarball: {error}")
        version = str(package.get("version") or "")
        if version != str(policy.get("pinned_version")):
            raise AddressError(
                f"SDK package is {version}, manifest pins "
                f"{policy.get('pinned_version')}")
        # npm does not include gitHead inside the tarball's package.json. The
        # SRI digest pins the bytes offline; fetch() separately binds that
        # digest to the registry's gitHead before calling this constructor.
        git_head = str(policy.get("git_head") or "")
        if not git_head:
            raise AddressError("manifest does not pin the SDK registry gitHead")
        addresses = _mainnet_addresses(constants)
        assertions = policy.get("assertions") or {}
        mismatches = []
        for key, expected in assertions.items():
            actual = addresses.get(key)
            if actual is None or actual.lower() != str(expected).lower():
                mismatches.append(f"{key}: expected {expected}, got {actual}")
        if mismatches:
            raise AddressError("SDK address assertions failed:\n  "
                               + "\n  ".join(mismatches))
        return cls(version=version, integrity=integrity, git_head=git_head,
                   tarball_sha512=hashlib.sha512(tarball).hexdigest(),
                   addresses=addresses, assertions=dict(assertions))

    @classmethod
    def fetch(cls, manifest_path: str, timeout: int = 30) -> "AddressBook":
        policy = _manifest(manifest_path).get("addresses") or {}
        version = policy.get("pinned_version")
        metadata_url = ("https://registry.npmjs.org/"
                        f"%40wildcatfi%2Fwildcat-sdk/{version}")
        try:
            with urllib.request.urlopen(metadata_url, timeout=timeout) as response:
                metadata = json.load(response)
            if metadata.get("dist", {}).get("integrity") != policy.get("integrity"):
                raise AddressError("npm registry integrity differs from manifest")
            if metadata.get("gitHead") != policy.get("git_head"):
                raise AddressError("npm registry gitHead differs from manifest")
            with urllib.request.urlopen(
                    metadata["dist"]["tarball"], timeout=timeout) as response:
                tarball = response.read()
        except (urllib.error.URLError, KeyError, json.JSONDecodeError) as error:
            raise AddressError(f"cannot fetch pinned SDK artifact: {error}")
        return cls.from_tarball(manifest_path, tarball)

    def resolve(self, key: str) -> str:
        """Resolve only manifest-approved map keys, never display names."""
        if key not in self.assertions:
            raise AddressError(
                f"{key!r} is not an asserted deployment key; allowed keys: "
                f"{sorted(self.assertions)}")
        return self.addresses[key]

    def gate_record(self) -> dict:
        return {"address_assertions_hold": True, "source_version": self.version,
                "integrity": self.integrity, "git_head": self.git_head,
                "resolved_by": "key", "assertions": self.assertions}


class HttpTransport:
    """Small injectable HTTP boundary used by GatewayClient."""

    def __init__(self, timeout: int = 20):
        self.timeout = timeout

    def get_json(self, url: str) -> dict:
        try:
            with urllib.request.urlopen(url, timeout=self.timeout) as response:
                return json.load(response)
        except (urllib.error.URLError, json.JSONDecodeError) as error:
            raise GatewayUnavailable(f"gateway health request failed: {error}")

    def post_json(self, url: str, body: dict, token: str) -> dict:
        request = urllib.request.Request(
            url, data=json.dumps(body).encode(), method="POST",
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {token}"})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            raise GatewayUnavailable(
                f"gateway query returned HTTP {error.code}")
        except (urllib.error.URLError, json.JSONDecodeError) as error:
            raise GatewayUnavailable(f"gateway query failed: {error}")


@dataclass(frozen=True)
class GatewayHealth:
    chain_id: int
    release: str
    state: str
    ready_providers: int
    indexed_block: int
    observed_head: int


@dataclass(frozen=True)
class TokenState:
    address: str
    symbol: str
    decimals: int


@dataclass(frozen=True)
class MarketSummary:
    address: str
    name: str
    symbol: str
    borrower: str
    asset: TokenState
    is_closed: bool
    is_registered: bool


@dataclass(frozen=True)
class RegistryState:
    markets: tuple[MarketSummary, ...]


@dataclass(frozen=True)
class MarketState:
    market: MarketSummary
    total_assets: int
    max_total_supply: int
    scaled_total_supply: int
    scaled_pending_withdrawals: int
    normalized_unclaimed_withdrawals: int
    pending_withdrawal_expiry: int
    annual_interest_bips: int
    reserve_ratio_bips: int
    delinquency_fee_bips: int
    delinquency_grace_period: int
    withdrawal_batch_duration: int
    is_delinquent: bool
    time_delinquent: int


@dataclass(frozen=True)
class AccountState:
    market_address: str
    market_name: str
    market_symbol: str
    asset: TokenState
    lender: str
    scaled_balance: int
    total_deposited: int
    total_interest_earned: int
    pending_withdrawal_batches: int
    claimable_withdrawals: int
    role: str


@dataclass(frozen=True)
class WithdrawalBatchState:
    expiry: int
    is_closed: bool
    is_completed: bool
    scaled_total_amount: int
    scaled_amount_burned: int
    normalized_amount_paid: int
    normalized_total_amount: int
    total_interest_earned: int


@dataclass(frozen=True)
class WithdrawalQueueState:
    market_address: str
    market_name: str
    asset: TokenState
    batches: tuple[WithdrawalBatchState, ...]


@dataclass(frozen=True)
class BorrowerMarketsState:
    borrower: str
    markets: tuple[MarketSummary, ...]


@dataclass(frozen=True)
class MarketHistoryEvent:
    kind: str
    amount: int
    event_index: int
    block_number: int
    block_timestamp: int
    transaction_hash: str
    block_log_index: int


@dataclass(frozen=True)
class MarketHistoryState:
    market_address: str
    market_name: str
    asset: TokenState
    requested_limit: int
    event_types: tuple[str, ...]
    events: tuple[MarketHistoryEvent, ...]


@dataclass(frozen=True)
class LiveResult:
    operation: str
    chain_id: int
    gateway_release: str
    block_number: int
    observed_head: int
    value: Any

    def to_dict(self) -> dict:
        return {**asdict(self), "value": asdict(self.value)}


_MARKET_FIELDS = """
  id name symbol borrower isClosed isRegistered decimals
  asset { address symbol decimals }
"""

_QUERIES = {
    "registry": f"""query Registry($block: Block_height!, $first: Int!) {{
      _meta(block: $block) {{ block {{ number }} }}
      markets(block: $block, first: $first, orderBy: id, orderDirection: asc,
              where: {{ isRegistered: true }}) {{ {_MARKET_FIELDS} }}
    }}""",
    "market": f"""query Market($block: Block_height!, $market: ID!) {{
      _meta(block: $block) {{ block {{ number }} }}
      market(block: $block, id: $market) {{
        {_MARKET_FIELDS}
        totalAssets maxTotalSupply scaledTotalSupply scaledPendingWithdrawals
        normalizedUnclaimedWithdrawals pendingWithdrawalExpiry
        annualInterestBips reserveRatioBips delinquencyFeeBips
        delinquencyGracePeriod withdrawalBatchDuration isDelinquent timeDelinquent
      }}
    }}""",
    "account": """query Account($block: Block_height!, $market: ID!, $lender: Bytes!) {
      _meta(block: $block) { block { number } }
      market(block: $block, id: $market) {
        id name symbol decimals asset { address symbol decimals }
        lenders(where: { address: $lender }, first: 1) {
          address scaledBalance totalDeposited totalInterestEarned
          numPendingWithdrawalBatches role
          withdrawals(where: { isCompleted: false }, first: 1000,
                      orderBy: id, orderDirection: asc) {
            scaledAmount normalizedAmountWithdrawn isCompleted
            batch { scaledTotalAmount normalizedAmountPaid }
          }
        }
      }
    }""",
    "withdrawals": """query Withdrawals($block: Block_height!, $market: ID!) {
      _meta(block: $block) { block { number } }
      market(block: $block, id: $market) {
        id name asset { address symbol decimals }
        withdrawalBatches(where: { isClosed: false }, orderBy: expiry,
                          orderDirection: asc) {
          expiry isClosed isCompleted scaledTotalAmount scaledAmountBurned
          normalizedAmountPaid normalizedTotalAmount totalInterestEarned
        }
      }
    }""",
    "borrower_markets": f"""query BorrowerMarkets(
        $block: Block_height!, $borrower: Bytes!, $first: Int!) {{
      _meta(block: $block) {{ block {{ number }} }}
      markets(block: $block, where: {{ borrower: $borrower }}, first: $first,
              orderBy: id, orderDirection: asc) {{ {_MARKET_FIELDS} }}
    }}""",
    "history": """query History(
        $block: Block_height!, $market: ID!, $first: Int!) {
      _meta(block: $block) { block { number } }
      market(block: $block, id: $market) {
        id name asset { address symbol decimals }
        borrowRecords(first: $first, orderBy: eventIndex,
                      orderDirection: desc) {
          eventIndex assetAmount blockNumber blockTimestamp
          transactionHash blockLogIndex
        }
        repaymentRecords(first: $first, orderBy: eventIndex,
                         orderDirection: desc) {
          eventIndex assetAmount blockNumber blockTimestamp
          transactionHash blockLogIndex
        }
        depositRecords(first: $first, orderBy: eventIndex,
                       orderDirection: desc) {
          eventIndex assetAmount blockNumber blockTimestamp
          transactionHash blockLogIndex
        }
        withdrawalRequestRecords(first: $first, orderBy: eventIndex,
                                 orderDirection: desc) {
          eventIndex normalizedAmount blockNumber blockTimestamp
          transactionHash blockLogIndex
        }
      }
    }""",
}


class GatewayClient:
    """Health-gated reads against exactly one manifest-pinned release."""

    def __init__(self, manifest_path: str, transport=None,
                 token: str | None = None):
        manifest = _manifest(manifest_path)
        live = manifest.get("live_state") or {}
        chains = ((manifest.get("policy") or {}).get("scope") or {}).get(
            "chains") or []
        if chains != [1]:
            raise LiveError(f"live client requires the mainnet-only scope, got {chains}")
        self.chain_id = 1
        self.release = (live.get("pinned_releases") or {}).get("mainnet")
        if not self.release:
            raise LiveError("manifest has no pinned mainnet gateway release")
        self.health_url = live.get("health")
        graph = live.get("graph")
        if not self.health_url or not graph:
            raise LiveError("manifest gateway URLs are incomplete")
        self.endpoint = graph.format(network="mainnet", release=self.release)
        env_name = (live.get("auth") or {}).get("env")
        self.token = token if token is not None else os.environ.get(env_name or "")
        self.transport = transport or HttpTransport()

    def check_health(self) -> GatewayHealth:
        payload = self.transport.get_json(self.health_url)
        matches = [deployment for deployment in payload.get("deployments") or []
                   if deployment.get("chainId") == self.chain_id
                   and deployment.get("releaseName") == self.release]
        if len(matches) != 1:
            raise GatewayUnavailable(
                f"health does not name exactly one mainnet/{self.release} deployment")
        deployment = matches[0]
        if deployment.get("state") != "ready" or int(
                deployment.get("readyProviders") or 0) < 1:
            raise GatewayUnavailable(
                f"mainnet/{self.release} is {deployment.get('state')}, not ready")
        ready = [replica for replica in deployment.get("replicas") or []
                 if replica.get("state") == "ready"]
        if not ready:
            raise GatewayUnavailable("gateway reports no ready replica")
        if int(deployment.get("readyProviders")) != len(ready):
            raise GatewayUnavailable(
                "gateway readyProviders count disagrees with replica states")
        for replica in ready:
            if replica.get("integrity") != "verified":
                raise GatewayUnavailable(
                    f"gateway replica {replica.get('providerId')} is unverified")
            if replica.get("circuit") != "closed":
                raise GatewayUnavailable(
                    f"gateway replica {replica.get('providerId')} circuit is open")
            if replica.get("lagBlocks") != 0:
                raise GatewayUnavailable(
                    f"gateway replica {replica.get('providerId')} is lagging by "
                    f"{replica.get('lagBlocks')} block(s)")
            indexed_block = _integer(replica.get("indexedBlock"), "indexedBlock")
            observed_head = _integer(replica.get("observedHead"), "observedHead")
            if indexed_block > observed_head:
                raise GatewayUnavailable(
                    f"gateway replica {replica.get('providerId')} indexed past "
                    "its observed head")
        indexed = min(_integer(replica.get("indexedBlock"), "indexedBlock")
                      for replica in ready)
        observed = max(_integer(replica.get("observedHead"), "observedHead")
                       for replica in ready)
        return GatewayHealth(
            chain_id=1, release=self.release, state="ready",
            ready_providers=len(ready), indexed_block=indexed,
            observed_head=observed)

    def _query(self, operation: str, variables: dict,
               parse: Callable[[dict], Any]) -> LiveResult:
        health = self.check_health()
        if not self.token:
            raise GatewayUnavailable(
                "gateway bearer token is absent; set ALEPH_GATEWAY_TOKEN")
        variables = {**variables, "block": {"number": health.indexed_block}}
        payload = self.transport.post_json(
            self.endpoint, {"query": _QUERIES[operation],
                            "variables": variables}, self.token)
        if payload.get("errors"):
            messages = "; ".join(str(error.get("message") or error)
                                 for error in payload["errors"])
            raise GatewayUnavailable(f"gateway GraphQL error: {messages}")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise GatewayUnavailable("gateway response has no data object")
        try:
            block = _integer(data["_meta"]["block"]["number"],
                             "_meta.block.number")
        except (KeyError, TypeError):
            raise GatewayUnavailable("gateway response omits _meta block number")
        if block != health.indexed_block:
            raise GatewayUnavailable(
                f"gateway returned block {block}, requested {health.indexed_block}")
        try:
            value = parse(data)
        except LiveError:
            raise
        except (KeyError, TypeError, ValueError) as error:
            raise LiveError(f"malformed {operation} response: {error}")
        return LiveResult(
            operation=operation, chain_id=1, gateway_release=self.release,
            block_number=block, observed_head=health.observed_head,
            value=value)

    def registry(self, limit: int = 100) -> LiveResult:
        if not 1 <= limit <= 1000:
            raise LiveError("registry limit must be between 1 and 1000")
        return self._query("registry", {"first": limit},
                           lambda data: RegistryState(tuple(
                               _market_summary(item) for item in data["markets"])))

    def market(self, market: str) -> LiveResult:
        market = _address(market, "market")
        def parse(data):
            item = data.get("market")
            if item is None:
                raise LiveError(f"market {market} is absent at the observed block")
            return MarketState(
                market=_market_summary(item),
                total_assets=_integer(item["totalAssets"], "totalAssets"),
                max_total_supply=_integer(item["maxTotalSupply"], "maxTotalSupply"),
                scaled_total_supply=_integer(item["scaledTotalSupply"], "scaledTotalSupply"),
                scaled_pending_withdrawals=_integer(
                    item["scaledPendingWithdrawals"], "scaledPendingWithdrawals"),
                normalized_unclaimed_withdrawals=_integer(
                    item["normalizedUnclaimedWithdrawals"],
                    "normalizedUnclaimedWithdrawals"),
                pending_withdrawal_expiry=_integer(
                    item["pendingWithdrawalExpiry"], "pendingWithdrawalExpiry"),
                annual_interest_bips=_integer(item["annualInterestBips"], "annualInterestBips"),
                reserve_ratio_bips=_integer(item["reserveRatioBips"], "reserveRatioBips"),
                delinquency_fee_bips=_integer(item["delinquencyFeeBips"], "delinquencyFeeBips"),
                delinquency_grace_period=_integer(
                    item["delinquencyGracePeriod"], "delinquencyGracePeriod"),
                withdrawal_batch_duration=_integer(
                    item["withdrawalBatchDuration"], "withdrawalBatchDuration"),
                is_delinquent=_boolean(item["isDelinquent"], "isDelinquent"),
                time_delinquent=_integer(item["timeDelinquent"], "timeDelinquent"))
        return self._query("market", {"market": market}, parse)

    def account(self, market: str, lender: str) -> LiveResult:
        market = _address(market, "market")
        lender = _address(lender, "lender")
        def parse(data):
            item = data.get("market")
            if item is None:
                raise LiveError(f"market {market} is absent at the observed block")
            accounts = item.get("lenders") or []
            account = accounts[0] if accounts else {}
            pending = _integer(
                account.get("numPendingWithdrawalBatches", 0),
                "numPendingWithdrawalBatches")
            statuses = account.get("withdrawals") or []
            if len(statuses) != pending:
                raise LiveError(
                    "account response returned "
                    f"{len(statuses)} of {pending} pending withdrawal batches")
            claimable = 0
            for index, status in enumerate(statuses):
                batch = status["batch"]
                scaled_total = _integer(
                    batch["scaledTotalAmount"],
                    f"withdrawals[{index}].batch.scaledTotalAmount")
                scaled_amount = _integer(
                    status["scaledAmount"],
                    f"withdrawals[{index}].scaledAmount")
                normalized_paid = _integer(
                    batch["normalizedAmountPaid"],
                    f"withdrawals[{index}].batch.normalizedAmountPaid")
                withdrawn = _integer(
                    status["normalizedAmountWithdrawn"],
                    f"withdrawals[{index}].normalizedAmountWithdrawn")
                if scaled_total == 0:
                    if scaled_amount != 0:
                        raise LiveError(
                            "pending withdrawal has a share of an empty batch")
                    allocated = 0
                else:
                    allocated = normalized_paid * scaled_amount // scaled_total
                if withdrawn > allocated:
                    raise LiveError(
                        "pending withdrawal exceeds its paid batch allocation")
                claimable += allocated - withdrawn
            return AccountState(
                market_address=market, market_name=_text(item["name"], "market name"),
                market_symbol=_text(item["symbol"], "market symbol"),
                asset=_token(item["asset"]),
                lender=lender,
                scaled_balance=_integer(account.get("scaledBalance", 0), "scaledBalance"),
                total_deposited=_integer(account.get("totalDeposited", 0), "totalDeposited"),
                total_interest_earned=_integer(
                    account.get("totalInterestEarned", 0), "totalInterestEarned"),
                pending_withdrawal_batches=pending,
                claimable_withdrawals=claimable,
                role=_text(account.get("role") or "Null", "account role"))
        return self._query("account", {"market": market, "lender": lender}, parse)

    def withdrawals(self, market: str) -> LiveResult:
        market = _address(market, "market")
        def parse(data):
            item = data.get("market")
            if item is None:
                raise LiveError(f"market {market} is absent at the observed block")
            batches = tuple(WithdrawalBatchState(
                expiry=_integer(batch["expiry"], "expiry"),
                is_closed=_boolean(batch["isClosed"], "isClosed"),
                is_completed=_boolean(batch["isCompleted"], "isCompleted"),
                scaled_total_amount=_integer(batch["scaledTotalAmount"], "scaledTotalAmount"),
                scaled_amount_burned=_integer(batch["scaledAmountBurned"], "scaledAmountBurned"),
                normalized_amount_paid=_integer(
                    batch["normalizedAmountPaid"], "normalizedAmountPaid"),
                normalized_total_amount=_integer(
                    batch["normalizedTotalAmount"], "normalizedTotalAmount"),
                total_interest_earned=_integer(
                    batch["totalInterestEarned"], "totalInterestEarned"))
                for batch in item.get("withdrawalBatches") or [])
            return WithdrawalQueueState(
                market_address=market,
                market_name=_text(item["name"], "market name"),
                asset=_token(item["asset"]), batches=batches)
        return self._query("withdrawals", {"market": market}, parse)

    def borrower_markets(self, borrower: str, limit: int = 100) -> LiveResult:
        borrower = _address(borrower, "borrower")
        if not 1 <= limit <= 1000:
            raise LiveError("borrower market limit must be between 1 and 1000")
        return self._query(
            "borrower_markets", {"borrower": borrower, "first": limit},
            lambda data: BorrowerMarketsState(
                borrower=borrower,
                markets=tuple(_market_summary(item) for item in data["markets"])))

    def history(self, market: str, limit: int = DEFAULT_HISTORY_EVENTS,
                event_types: tuple[str, ...] = ()) -> LiveResult:
        market = _address(market, "market")
        if not 1 <= limit <= MAX_HISTORY_EVENTS:
            raise LiveError(
                f"history limit must be between 1 and {MAX_HISTORY_EVENTS}")
        selected = event_types or HISTORY_EVENT_TYPES
        if (not isinstance(selected, tuple) or not selected
                or len(set(selected)) != len(selected)
                or any(kind not in HISTORY_EVENT_TYPES for kind in selected)):
            raise LiveError("history event types are empty, duplicated, or unsupported")
        selected_set = set(selected)
        selected = tuple(kind for kind in HISTORY_EVENT_TYPES
                         if kind in selected_set)

        def parse(data):
            item = data.get("market")
            if item is None:
                raise LiveError(f"market {market} is absent at the observed block")
            families = (
                ("borrow", "borrowRecords", "assetAmount"),
                ("repayment", "repaymentRecords", "assetAmount"),
                ("deposit", "depositRecords", "assetAmount"),
                ("withdrawal", "withdrawalRequestRecords", "normalizedAmount"),
            )
            events = []
            for kind, field, amount_field in families:
                records = item.get(field)
                if not isinstance(records, list):
                    raise LiveError(f"history response omits {field}")
                if len(records) > limit:
                    raise LiveError(f"history response exceeds the {field} limit")
                if kind not in selected_set:
                    continue
                for record in records:
                    events.append(MarketHistoryEvent(
                        kind=kind,
                        amount=_integer(record[amount_field], amount_field),
                        event_index=_integer(record["eventIndex"], "eventIndex"),
                        block_number=_integer(record["blockNumber"], "blockNumber"),
                        block_timestamp=_timestamp(
                            record["blockTimestamp"], "blockTimestamp"),
                        transaction_hash=_transaction_hash(
                            record["transactionHash"]),
                        block_log_index=_integer(
                            record["blockLogIndex"], "blockLogIndex")))
            identities = {(event.transaction_hash, event.block_log_index)
                          for event in events}
            if len(identities) != len(events):
                raise LiveError("history response contains duplicate log identities")
            events.sort(key=lambda event: (
                event.event_index, event.block_number, event.block_log_index,
                event.transaction_hash, event.kind), reverse=True)
            return MarketHistoryState(
                market_address=market,
                market_name=_text(item["name"], "market name"),
                asset=_token(item["asset"]),
                requested_limit=limit,
                event_types=selected,
                events=tuple(events[:limit]))

        result = self._query(
            "history", {"market": market, "first": limit}, parse)
        if any(event.block_number > result.block_number
               for event in result.value.events):
            raise LiveError(
                "history event block is later than the pinned response block")
        return result


def _token(item: dict) -> TokenState:
    return TokenState(address=_address(item["address"], "asset"),
                      symbol=_text(item["symbol"], "asset symbol"),
                      decimals=_integer(item["decimals"], "asset decimals"))


def _market_summary(item: dict) -> MarketSummary:
    return MarketSummary(
        address=_address(item["id"], "market"),
        name=_text(item["name"], "market name"),
        symbol=_text(item["symbol"], "market symbol"),
        borrower=_address(item["borrower"], "borrower"),
        asset=_token(item["asset"]),
        is_closed=_boolean(item["isClosed"], "isClosed"),
        is_registered=_boolean(item["isRegistered"], "isRegistered"))


@dataclass(frozen=True)
class RenderedLive:
    operation: str
    text: str
    chain_id: int
    gateway_release: str
    block_number: int


def format_units(value: int, decimals: int, places: int | None = None) -> str:
    value = _integer(value, "amount")
    decimals = _integer(decimals, "decimals")
    if decimals > 255:
        raise LiveError("token decimals exceeds 255")
    scale = 10 ** decimals
    whole, fraction = divmod(value, scale)
    digits = f"{fraction:0{decimals}d}" if decimals else ""
    if places is not None:
        if places < 0:
            raise LiveError("places must be non-negative")
        digits = digits[:places]
    digits = digits.rstrip("0")
    return f"{whole:,}" + (f".{digits}" if digits else "")


def format_bips(value: int) -> str:
    value = _integer(value, "basis points")
    whole, fraction = divmod(value, 100)
    return f"{whole}.{fraction:02d}%" if fraction else f"{whole}%"


def format_duration(seconds: int) -> str:
    seconds = _integer(seconds, "duration")
    days, remainder = divmod(seconds, 86_400)
    hours, remainder = divmod(remainder, 3_600)
    minutes, seconds = divmod(remainder, 60)
    parts = []
    for value, unit in ((days, "d"), (hours, "h"), (minutes, "m"),
                        (seconds, "s")):
        if value or not parts and unit == "s":
            parts.append(f"{value}{unit}")
    return " ".join(parts) if parts else "0s"


def _observed(result: LiveResult) -> str:
    return (f"Observed at Ethereum block {result.block_number:,} via Wildcat "
            f"Data Gateway release {result.gateway_release}.")


def render_live(result: LiveResult, field: str | None = None) -> RenderedLive:
    value = result.value
    if field is not None and not isinstance(value, MarketState):
        raise LiveError(
            f"field-specific rendering is unavailable for {type(value).__name__}")
    if isinstance(value, RegistryState):
        lines = [f"Registered markets ({len(value.markets)}):"]
        lines += [f"- {market.name} ({market.symbol}) — {market.address}"
                  for market in value.markets]
    elif isinstance(value, MarketState):
        market, token = value.market, value.market.asset
        remaining_capacity = max(0, value.max_total_supply - value.total_assets)
        field_lines = {
            "apr": [f"APR: {format_bips(value.annual_interest_bips)}"],
            "reserve_ratio": [
                f"Reserve ratio: {format_bips(value.reserve_ratio_bips)}"],
            "capacity": [
                "Remaining capacity: "
                f"{format_units(remaining_capacity, token.decimals)} "
                f"{token.symbol}"],
            "grace_period": [
                "Delinquency grace period: "
                f"{format_duration(value.delinquency_grace_period)}"],
            "delinquency": [
                f"Delinquent: {'yes' if value.is_delinquent else 'no'}",
                f"Time delinquent: {format_duration(value.time_delinquent)}",
                f"Delinquency fee: {format_bips(value.delinquency_fee_bips)}",
                "Delinquency grace period: "
                f"{format_duration(value.delinquency_grace_period)}"],
        }
        if field is not None:
            if field not in field_lines:
                raise LiveError(f"unsupported market field {field!r}")
            lines = [f"{market.name} ({market.symbol})", *field_lines[field]]
        else:
            lines = [
                f"{market.name} ({market.symbol})",
                f"Market: {market.address}", f"Borrower: {market.borrower}",
                f"Total assets: {format_units(value.total_assets, token.decimals)} {token.symbol}",
                f"Maximum supply: {format_units(value.max_total_supply, token.decimals)} {token.symbol}",
                *field_lines["capacity"],
                *field_lines["apr"],
                *field_lines["reserve_ratio"],
                *field_lines["delinquency"],
            ]
    elif isinstance(value, AccountState):
        token = value.asset
        lines = [f"Account {value.lender} in {value.market_name}",
                 f"Scaled balance: {format_units(value.scaled_balance, token.decimals)} {token.symbol}",
                 f"Total deposited: {format_units(value.total_deposited, token.decimals)} {token.symbol}",
                 f"Interest earned: {format_units(value.total_interest_earned, token.decimals)} {token.symbol}",
                 f"Pending withdrawal batches: {value.pending_withdrawal_batches}",
                 f"Claimable withdrawals: {format_units(value.claimable_withdrawals, token.decimals)} {token.symbol}",
                 f"Role: {value.role}"]
    elif isinstance(value, WithdrawalQueueState):
        lines = [f"Open withdrawal batches for {value.market_name} "
                 f"({len(value.batches)}):"]
        for batch in value.batches:
            expiry = datetime.fromtimestamp(batch.expiry, timezone.utc).isoformat()
            lines.append(
                f"- expires {expiry}; paid "
                f"{format_units(batch.normalized_amount_paid, value.asset.decimals)} / "
                f"{format_units(batch.normalized_total_amount, value.asset.decimals)} "
                f"{value.asset.symbol}; completed: {'yes' if batch.is_completed else 'no'}")
    elif isinstance(value, BorrowerMarketsState):
        lines = [f"Markets for borrower {value.borrower} ({len(value.markets)}):"]
        lines += [f"- {market.name} ({market.symbol}) — {market.address}; "
                  f"closed: {'yes' if market.is_closed else 'no'}"
                  for market in value.markets]
    elif isinstance(value, MarketHistoryState):
        names = {
            "borrow": "borrow", "repayment": "repayment",
            "deposit": "deposit", "withdrawal": "withdrawal request",
        }
        scope = ", ".join(names[kind] for kind in value.event_types)
        lines = [
            f"Latest {len(value.events)} matching event(s) for "
            f"{value.market_name} (limit {value.requested_limit}; {scope}):"]
        if not value.events:
            lines.append("- No matching events found at the observed block.")
        for event in value.events:
            timestamp = datetime.fromtimestamp(
                event.block_timestamp, timezone.utc).isoformat()
            lines.append(
                f"- {names[event.kind].capitalize()}: "
                f"{format_units(event.amount, value.asset.decimals)} "
                f"{value.asset.symbol}; {timestamp}; block "
                f"{event.block_number:,}; transaction {event.transaction_hash}")
    else:
        raise LiveError(f"no deterministic renderer for {type(value).__name__}")
    lines += ["", _observed(result)]
    return RenderedLive(
        operation=result.operation, text="\n".join(lines), chain_id=result.chain_id,
        gateway_release=result.gateway_release, block_number=result.block_number)
