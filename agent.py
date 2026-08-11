#!/usr/bin/env python3
"""Question routing and evidence-checked answer assembly for Project Aleph."""

from __future__ import annotations

import re
import secrets
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Callable, Protocol

from live import (
    DEFAULT_HISTORY_EVENTS, HISTORY_EVENT_TYPES, MAX_HISTORY_EVENTS,
    GatewayUnavailable, LiveError, RenderedLive, render_live,
)
from retrieval import (Citation, CitationError, Evidence, RetrievalError,
                       RetrievalRequest, ScopeError, expand_query)


class AnswerError(Exception):
    """An answer cannot leave the process because its support is invalid."""


class RouteMode(str, Enum):
    CORPUS = "corpus"
    LIVE = "live"
    CORPUS_LIVE = "corpus+live"
    CORRECT = "correct"
    REFUSE = "refuse"
    REFUSE_POINT = "refuse+point"
    TRIAGE = "triage"
    PARTIAL = "partial"
    CLARIFY = "clarify"
    EASTER_EGG = "easter_egg"


@dataclass(frozen=True)
class Entities:
    chain_id: int
    protocol_version: str | None
    version_explicit: bool
    market_address: str | None
    account_address: str | None
    borrower_address: str | None
    all_addresses: tuple[str, ...]


@dataclass(frozen=True)
class Route:
    mode: RouteMode
    reason: str
    entities: Entities
    live_operation: str | None = None
    live_field: str | None = None
    live_limit: int | None = None
    live_event_types: tuple[str, ...] = ()
    destination: str | None = None
    refusal_reason: str | None = None
    triage_kind: str | None = None


@dataclass(frozen=True)
class TriagePayload:
    kind: str
    requested_fields: tuple[str, ...]
    collected: dict[str, str]


@dataclass(frozen=True)
class DraftClaim:
    text: str
    evidence_id: str
    supporting_quote: str


@dataclass(frozen=True)
class Draft:
    claims: tuple[DraftClaim, ...]
    abstain_reason: str | None = None


class EvidenceWriter(Protocol):
    def write(self, question: str, evidence: tuple[Evidence, ...],
              route: Route) -> Draft: ...


@dataclass(frozen=True)
class Answer:
    status: str
    mode: RouteMode
    text: str
    route: Route
    citations: tuple[Citation, ...] = ()
    claims: tuple[DraftClaim, ...] = ()
    live: RenderedLive | None = None
    triage: TriagePayload | None = None
    corpus_release_id: str | None = None
    refusal_reason: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


_ETH_ADDRESS = re.compile(r"0x[0-9a-fA-F]{40}")
_CHAIN_NAMES = {
    "ethereum": 1, "mainnet": 1, "base": 8453, "arbitrum": 42161,
    "optimism": 10, "polygon": 137, "sepolia": 11155111,
}


def extract_entities(question: str) -> Entities:
    lower = question.lower()
    chain_id = 1
    explicit_chains = {chain for name, chain in _CHAIN_NAMES.items()
                       if re.search(rf"\b{re.escape(name)}\b", lower)}
    numeric = re.search(r"\bchain(?:\s*id)?\s*[:=#]?\s*(\d+)\b", lower)
    if numeric:
        explicit_chains.add(int(numeric.group(1)))
    if len(explicit_chains) > 1:
        # Multiple chains are outside the one-chain request contract. Zero is
        # deliberately unsupported and routes to a refusal before retrieval.
        chain_id = 0
    elif explicit_chains:
        chain_id = explicit_chains.pop()

    version_match = re.search(r"\bv\s*(2(?:\.\s*(?:0|5))?)\b", lower)
    version = None
    if version_match:
        compact = re.sub(r"\s+", "", version_match.group(1))
        version = "v2.5" if compact == "2.5" else "v2.0"

    addresses = tuple(dict.fromkeys(
        match.group(0).lower() for match in _ETH_ADDRESS.finditer(question)))
    market = _labelled_address(question, r"market(?:\s+address)?", addresses)
    borrower = _labelled_address(question, r"borrower(?:\s+address)?", addresses)
    account = _labelled_address(
        question, r"(?:lender|wallet|account)(?:\s+address)?", addresses)
    unassigned = [address for address in addresses
                  if address not in (market, borrower, account)]
    if unassigned:
        if borrower is None and "borrower" in lower and "market" not in lower:
            borrower = unassigned.pop(0)
        elif market is None and "market" in lower:
            market = unassigned.pop(0)
        elif account is None and re.search(r"\b(my|wallet|lender|account)\b", lower):
            account = unassigned.pop(0)
        elif market is None:
            market = unassigned.pop(0)
    if unassigned and account is None:
        account = unassigned.pop(0)
    return Entities(chain_id=chain_id, protocol_version=version,
                    version_explicit=version is not None,
                    market_address=market, account_address=account,
                    borrower_address=borrower, all_addresses=addresses)


def _labelled_address(question: str, label: str,
                      addresses: tuple[str, ...]) -> str | None:
    match = re.search(rf"\b{label}\b[^0-9a-fA-F]{{0,24}}"
                      r"(0x[0-9a-fA-F]{40})", question, re.IGNORECASE)
    value = match.group(1).lower() if match else None
    return value if value in addresses else None


class Router:
    """Policy-first router. It never calls retrieval, live state, or a model."""

    _content_safety = re.compile(
        r"\bsuicid(?:e|al)\b|\bself[- ]?harm\b|"
        r"\b(?:kill|hurt|shoot)\s+(?:myself|me)\b|"
        r"\bblow\s+(?:my\s+)?(?:head|brains|shit)\s+off\b|"
        r"\bn[ -]?word\b|\bhard[ -]?r\b|\bracial\s+slur\b", re.I)
    _unsafe = re.compile(
        r"system prompt|ignore (?:your|all|previous) instructions|what files|"
        r"last person|previous user|repeat exactly|as a wildcat employee|"
        r"guarantees? all deposits", re.I)
    _abusive_targeting = re.compile(
        r"\b(?:humiliat\w*|demean\w*|insult\w*|mock\w*|sham\w*|harass\w*)\b",
        re.I)
    _historical_activity = re.compile(
        r"\b(?:last|latest|most recent)\b.{0,100}"
        r"\b(?:transactions?|events?|borrow(?:ed|ing)?|"
        r"withdr(?:aw|ew|awn|awal)|repa(?:y|id|yment)|deposit(?:ed)?)\b|"
        r"\bwhen\b.{0,100}\b(?:last|latest|most recent)\b.{0,100}"
        r"\b(?:borrow(?:ed|ing)?|withdr(?:aw|ew|awn|awal)|"
        r"repa(?:y|id|yment)|deposit(?:ed)?)\b|"
        r"\b(?:show|list|read|give me)\b.{0,40}"
        r"\b(?:transaction|activity)\s+history\b", re.I)
    _history_count = re.compile(
        r"\b(?:last|latest|most recent)\s+(?:the\s+)?"
        r"(?P<count>[0-9]+|one|two|three|four|five|six|seven|eight|nine|ten)\b",
        re.I)
    _advice = re.compile(
        r"should i (?:lend|invest)|trustworth|best repayment|best borrower|"
        r"repayment record|pattern of late|short an asset|guarantee.*apr|"
        r"risk score|recommend|penalty rate (?:are|do) other|"
        r"\brank\b.{0,80}\bborrowers?\b|\bsafest\s+borrower\b|"
        r"\bpersonally\s+trust\b", re.I)
    _address_like = re.compile(r"\b0x[0-9a-z]+\b", re.I)
    _private = re.compile(r"give me (?:the )?lender addresses|list.*lenders", re.I)
    _intent = re.compile(
        r"any plans|plan(?:s|ning)? to|does .* plan|plans? (?:another|a|any)|"
        r"is .* aware|will (?:the )?borrower|"
        r"borrower intend|speak to .* intention", re.I)
    _triage = re.compile(
        r"site is down|not loading|walletconnect|popup|fails? to sign|"
        r"failing to sign|deposit fails|deposited but no market token|"
        r"screen keeps appearing|error|screenshot|history is lagging|"
        r"can't see .*tabs|cannot see .*tabs", re.I)
    _action = re.compile(r"\bbump my withdrawal|expedite my withdrawal", re.I)
    _point = re.compile(
        r"generate a csv|portfolio tracker|whitelist(?:ing)? new wallets|"
        r"notified when capacity|mla signed.*off-platform|grant us access manually|"
        r"which legal entity|agreements .* signed|onboard as a borrower|"
        r"deploy a market|public subgraph|feed of changes|bot that tracks|"
        r"careers?|job opening|are you hiring|audit report|bug bounty|rewards?|"
        r"vulnerability|third-party incident|best person to dm|can i dm|"
        r"listing proposal|set up .*discord|be a moderator|community management|conference|"
        r"looking to integrate|who should we talk to|planning a token|points? |"
        r"claiming to be an admin|tokens were drained|revoke this approval|"
        r"link/site legitimate|writing to the contract directly|who maintains you|"
        r"telegram handles|aware that both", re.I)
    _correction = re.compile(
        r"collateral back|liquidat(?:e|ed|ion)|governance vote|auto-?repay|"
        r"wildcat changed the apr|rates? (?:are|is) immutable|locked.*debt|"
        r"reserve ratio .* zero.*confirm|you're wrong.*reserve|"
        r"debt (?:is )?['\"]?locked|rates? were immutable", re.I)
    _corpus_live = re.compile(
        r"why is not all .*balance claimable|when will i be able to claim|"
        r"how many hours are left .*ongoing cycle|best way to let the borrower know|"
        r"remainder has to wait for the next cycle|total to repay to close|"
        r"protocol fee figure or the total interest|currently marked delinquent|"
        r"pending for so long|withdrawal before .*penalty.*claim|"
        r"repaid but it still shows penalty|lender must meet specific criteria|"
        r"track loan history.*original deposit.*current balance", re.I)
    _corpus_only = re.compile(
        r"programmatically|from an api|calling balanceof|downside to claiming now|"
        r"does penalty status affect", re.I)
    _live = re.compile(
        r"\b(current|currently|now|today|repaid yet|what markets has|"
        r"market status|penalty status|remaining capacity)\b|"
        r"when will .*claim|how many hours|no longer accruing|"
        r"market is in penalty|ever been delinquent", re.I)
    _market_url = re.compile(
        r"https?://app\.wildcat\.finance/lender/market/"
        r"0x[0-9a-f]{40}(?:[/?#][^\s]*)?", re.I)
    _market_summary = re.compile(
        r"\b(?:market summary|summari[sz]e (?:this|the) market|"
        r"what can you tell me about (?:this|the) market|"
        r"tell me about (?:this|the) market)\b", re.I)
    _account_state_request = re.compile(
        r"\b(?:how much|what(?:'s|\s+is)|show|check|read|give me)\b", re.I)
    _account_state_term = re.compile(
        r"\b(?:claimable|balance)\b", re.I)
    _account_identity_term = re.compile(
        r"\b(?:account|wallet|lender)\b", re.I)
    _mechanism = re.compile(
        r"\b(why|how|what does|what happens|difference|criteria|process|"
        r"include|mean|when does|do i need)\b", re.I)
    _known_gap = re.compile(
        r"how do i ping the market|why does the minimum deposit exist|"
        r"how do i get access to the app|sdk require ethers|"
        r"track loan history.*original deposit.*current balance|"
        r"findings from the audit.*resolved|do you have a discord|"
        r"checking on the platform every day", re.I)
    _underspecified_followup = re.compile(
        r"^\s*(?:"
        r"why\s+(?:is|does|did)\s+(?:it|this|that)\s+"
        r"(?:do(?:ing|es|ne)?\s+)?(?:it|this|that|so|again)"
        r"(?:\s+again)?|"
        r"why\s+did\s+(?:it|this|that)\s+happen(?:\s+again)?|"
        r"how\s+does\s+(?:it|this|that)\s+work|"
        r"what\s+does\s+(?:it|this|that)\s+mean"
        r")\s*[?.!]*\s*$", re.I)
    _domain = re.compile(
        r"wildcat|protocol|market|borrow|lender|withdr|deposit|repa(?:y|id)|"
        r"interest|\bapr\b|rate|reserve|delinquen|penalt|claim|cycle|capacity|"
        r"liquid|collateral|hook|fee|sanction|\bkyc\b|\bmla\b|access|wallet|"
        r"transaction|token|asset|balance|debt|loan|pool|ethers|\bsdk\b|"
        r"contract|on.?chain|subgraph|\bcsv\b|audit|security|bug|vulnerab|"
        r"\bapi\b|address|whitelist|app|website|site|platform|history|"
        r"notification|agreement|legal|entity|sign|admin|approval|discord|"
        r"telegram|chain|0x[0-9a-f]{8,}|[A-Za-z_]\w*\([^)]*\)", re.I)
    _vegan = re.compile(
        r"^\s*(?:(?:is\s+(?:it|aleph|wildcat))|(?:are\s+you))"
        r"\s+vegan\s*[?!.]*\s*$", re.I)

    @classmethod
    def known_gap(cls, question: str) -> str | None:
        return ("the pinned corpus does not document this recurring question"
                if cls._known_gap.search(question) else None)

    @staticmethod
    def evidence_query(question: str, route: Route) -> str:
        """Return a deterministic evidence query for a reviewed correction.

        A false premise often names the mechanism that does *not* exist, so a
        literal search can be least useful exactly when a correction is
        required. The expansion states the protocol concepts that can support
        the correction; it does not supply answer prose.
        """
        if (route.mode == RouteMode.CORRECT
                and re.search(r"liquidat(?:e|ed|ion)", question, re.I)):
            return ("Wildcat protocol does not liquidate lender positions or "
                    "participate in liquidation")
        if (route.mode == RouteMode.CORRECT
                and re.search(
                    r"wildcat changed the apr|governance vote.*(?:apr|rate)",
                    question, re.I)):
            return ("borrower can change APR set annual interest and reserve "
                    "ratio")
        if (route.mode == RouteMode.CORPUS
                and re.search(
                    r"(?:csv|market csv).*\bverif|\bverif.*(?:csv|exporter)",
                    question, re.I)):
            return ("Wildcat Market CSV Exporter What the Verification Proves "
                    "exact invariant event history transaction receipts contract "
                    "state snapshot block")
        # Presentation requests are not evidence topics. Sending them to the
        # embedder can make an otherwise exact protocol question retrieve
        # semantically adjacent legal, medical, or stylistic prose.
        focused = re.sub(
            r"(?:[,;]\s*|\band\s+)explain(?:\s+(?:it|this|that))?"
            r"(?:\s+to me)?\s+(?:like|as if)\b.*$", "", question,
            flags=re.I).strip(" \t,;:.-")
        return expand_query(focused or question)

    def route(self, question: str) -> Route:
        if not question.strip():
            raise AnswerError("question is empty")
        entities = extract_entities(question)
        if self._vegan.fullmatch(question):
            return Route(RouteMode.EASTER_EGG, "vegan coin flip", entities)
        if self._content_safety.search(question):
            return Route(RouteMode.REFUSE, "content safety boundary", entities,
                         refusal_reason="unsafe_or_abusive")
        if self._unsafe.search(question):
            return Route(RouteMode.REFUSE, "prompt/privacy boundary", entities,
                         refusal_reason="system_or_private_context")
        if self._abusive_targeting.search(question):
            return Route(RouteMode.REFUSE, "abusive personal targeting", entities,
                         refusal_reason="unsafe_or_abusive")
        if self._private.search(question):
            return Route(RouteMode.REFUSE, "lender privacy boundary", entities,
                         refusal_reason="bulk_lender_disclosure")
        if self._advice.search(question):
            return Route(RouteMode.REFUSE, "advice or borrower assessment", entities,
                         refusal_reason="advice_or_assessment")
        if any(not _ETH_ADDRESS.fullmatch(token)
               for token in self._address_like.findall(question)):
            return Route(RouteMode.REFUSE, "malformed address-like input", entities,
                         refusal_reason="malformed_address")
        if entities.chain_id != 1:
            return Route(RouteMode.REFUSE_POINT, "unsupported chain", entities,
                         destination="Wildcat support",
                         refusal_reason="unsupported_chain")
        if self._action.search(question):
            return Route(RouteMode.TRIAGE, "requested operational action", entities,
                         triage_kind="withdrawal_action")
        if self._triage.search(question):
            return Route(RouteMode.TRIAGE, "user-visible operational failure", entities,
                         triage_kind="technical_failure")
        if self._historical_activity.search(question):
            return Route(
                RouteMode.LIVE, "bounded market transaction history", entities,
                live_operation="history",
                live_limit=self._history_limit(question),
                live_event_types=self._history_event_types(question))
        if self._corpus_live.search(question):
            return Route(RouteMode.CORPUS_LIVE, "mechanism plus current state",
                         entities, live_operation=self._operation(question),
                         live_field=self._market_field(question))
        if self._correction.search(question):
            return Route(RouteMode.CORRECT, "false or inapplicable premise", entities)
        if self._point.search(question):
            return Route(RouteMode.REFUSE_POINT, "different owner or tool", entities,
                         destination=self._destination(question),
                         refusal_reason="outside_answer_boundary")
        if self._intent.search(question):
            if self._live.search(question):
                return Route(RouteMode.PARTIAL, "public fact plus private intent",
                             entities, live_operation=self._operation(question),
                             live_field=self._market_field(question))
            return Route(RouteMode.REFUSE, "borrower intent is unknowable", entities,
                         refusal_reason="inferred_intent")
        if self._corpus_only.search(question):
            return Route(RouteMode.CORPUS, "pinned protocol knowledge", entities)
        if self._addressed_account(question, entities):
            return Route(
                RouteMode.LIVE, "addressed account state", entities,
                live_operation="account")
        live_field = self._market_field(question)
        addressed = (
            self._addressed_market(question, entities)
            or (entities.market_address is not None and live_field is not None)
        )
        field_request = self._market_field_request(question, live_field)
        field_mechanism = self._market_field_mechanism(question, live_field)
        if field_request and not addressed and field_mechanism:
            return Route(RouteMode.CORPUS, "unaddressed market mechanism", entities)
        if addressed or field_request:
            if addressed and field_mechanism:
                return Route(
                    RouteMode.CORPUS_LIVE,
                    "market mechanism plus addressed live field", entities,
                    live_operation="market", live_field=live_field)
            return Route(
                RouteMode.LIVE, "addressed market state", entities,
                live_operation="market", live_field=live_field)
        live = bool(self._live.search(question))
        mechanism = bool(self._mechanism.search(question))
        if live and mechanism:
            return Route(RouteMode.CORPUS_LIVE, "mechanism plus current state",
                         entities, live_operation=self._operation(question),
                         live_field=live_field)
        if live:
            return Route(RouteMode.LIVE, "current public state", entities,
                         live_operation=self._operation(question),
                         live_field=live_field)
        if (self._underspecified_followup.search(question)
                and not self._domain.search(question)):
            return Route(RouteMode.CLARIFY, "underspecified follow-up", entities,
                         refusal_reason="missing_context")
        if not self._domain.search(question):
            return Route(RouteMode.REFUSE, "outside Wildcat scope", entities,
                         refusal_reason="outside_answer_boundary")
        return Route(RouteMode.CORPUS, "pinned protocol knowledge", entities)

    @staticmethod
    def _operation(question: str) -> str:
        lower = question.lower()
        if re.search(r"what markets has|markets (?:has|for) .*borrower", lower):
            return "borrower_markets"
        if re.search(
                r"enumerate.*markets|all active markets|market registry|"
                r"(?:which|list|show)\b.*\bmarkets\b.*\bregistered\b",
                lower):
            return "registry"
        if re.search(r"claimable|my balance|my deposit|my account", lower):
            return "account"
        if re.search(r"withdrawal|batch|queue|ongoing cycle", lower):
            return "withdrawals"
        return "market"

    @classmethod
    def _history_limit(cls, question: str) -> int:
        matched = cls._history_count.search(question)
        if matched is None:
            return (1 if re.search(r"\b(?:last|latest|most recent)\b",
                                   question, re.I)
                    else DEFAULT_HISTORY_EVENTS)
        words = {
            "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
            "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
        }
        raw = matched.group("count").casefold()
        requested = words.get(raw, int(raw) if raw.isdecimal() else 0)
        return min(max(requested, 1), MAX_HISTORY_EVENTS)

    @staticmethod
    def _history_event_types(question: str) -> tuple[str, ...]:
        patterns = {
            "borrow": r"\bborrow(?:ed|ing|s)?\b",
            "repayment": r"\brepa(?:y|id|ys|ying|yment|yments)\b",
            "deposit": r"\bdeposit(?:ed|ing|s)?\b",
            "withdrawal": r"\bwithdr(?:aw|aws|awn|ew|awal|awals|awing)\b",
        }
        selected = tuple(kind for kind in HISTORY_EVENT_TYPES
                         if re.search(patterns[kind], question, re.I))
        return selected or HISTORY_EVENT_TYPES

    @classmethod
    def _addressed_market(cls, question: str, entities: Entities) -> bool:
        if entities.market_address is None:
            return False
        stripped = question.strip().strip(".,;:!?()[]{}<>")
        return bool(
            _ETH_ADDRESS.fullmatch(stripped)
            or cls._market_url.search(question)
            or cls._market_summary.search(question))

    @classmethod
    def _addressed_account(cls, question: str, entities: Entities) -> bool:
        return bool(
            entities.all_addresses
            and cls._account_state_request.search(question)
            and (cls._account_state_term.search(question)
                 or (entities.account_address is not None
                     and cls._account_identity_term.search(question))))

    @staticmethod
    def _market_field(question: str) -> str | None:
        lower = question.lower()
        fields = (
            ("grace_period", r"\b(?:delinquency\s+)?grace\s+period\b|\bgrace\b"),
            ("reserve_ratio", r"\breserve\s+ratio\b"),
            ("capacity", r"\b(?:remaining\s+)?capacity\b"),
            ("delinquency", r"\bdelinquen\w*\b|\bpenalty\s+status\b"),
            ("apr", r"\bapr\b|\bannual\s+interest(?:\s+rate)?\b"),
        )
        for name, pattern in fields:
            if re.search(pattern, lower):
                return name
        return None

    @staticmethod
    def _market_field_request(question: str, field: str | None) -> bool:
        if field is None:
            return False
        lower = question.lower()
        return bool(re.search(
            r"^\s*(?:what(?:'s|\s+is)|show|check|give me|read|"
            r"how\s+(?:long|much))\b", lower))

    @staticmethod
    def _market_field_mechanism(question: str, field: str | None) -> bool:
        if field is None or re.search(r"\bhow\s+(?:long|much)\b", question, re.I):
            return False
        return bool(re.search(
            r"\b(?:how does|why|what does|when does|explain|difference between)\b", question,
            re.I))

    @staticmethod
    def _destination(question: str) -> str:
        lower = question.lower()
        if "csv" in lower:
            return "Wildcat market CSV exporter"
        if re.search(r"onboard|deploy a market", lower):
            return "Wildcat borrower onboarding"
        if re.search(r"subgraph|feed|bot|notified", lower):
            return "Wildcat developer and notifications documentation"
        if re.search(r"audit|bug bounty", lower):
            return "Wildcat security documentation"
        if re.search(r"career|job", lower):
            return "Wildcat careers"
        return "Wildcat support"


class ExtractiveWriter:
    """Dependency-free safe writer: only emits corpus substrings."""

    _TOPIC_STOP = frozenset({
        "about", "actually", "also", "could", "does", "explain", "have",
        "help", "like", "please", "should", "tell", "that", "their",
        "there", "these", "this", "understand", "what", "when", "where",
        "which", "with", "would", "your",
    })
    _GENERIC_TOPICS = frozenset({
        "answer", "contract", "function", "market", "protocol", "question",
        "wildcat",
    })
    _ORPHAN_MARKUP = re.compile(
        r"^\s*(?:[-*+]|\d+[.)]|#{1,6}|`{3,}|~{3,})\s*$")

    def __init__(self, max_claims: int = 1, max_chars: int = 800,
                 require_topic_match: bool = True):
        self.max_claims = max_claims
        self.max_chars = max_chars
        self.require_topic_match = require_topic_match

    @classmethod
    def _topic_terms(cls, text: str) -> set[str]:
        terms = set()
        for raw in re.findall(r"[a-z0-9_]+", text.casefold()):
            if len(raw) < 4 or raw in cls._TOPIC_STOP:
                continue
            if raw.endswith("ies") and len(raw) > 4:
                raw = raw[:-3] + "y"
            elif raw.endswith("s") and not raw.endswith("ss") and len(raw) > 4:
                raw = raw[:-1]
            terms.add(raw)
        return terms

    @classmethod
    def _topic_relevance(cls, question: str, item: Evidence,
                         quote: str) -> int:
        topics = cls._topic_terms(question)
        specific = topics - cls._GENERIC_TOPICS
        if not specific:
            # Generic requests such as "What is Wildcat?" still need a safe
            # semantic path. Specific requests must match their own subject.
            return 1
        anchor = cls._topic_terms(f"{item.id} {item.breadcrumb}")
        excerpt = cls._topic_terms(quote)
        # A heading/path match is much harder for incidental phrasing to fake
        # than a body-text match. This also makes a focused glossary section
        # beat a semantically nearby legal paragraph.
        return 4 * len(specific & anchor) + min(1, len(specific & excerpt))

    def _excerpt(self, text: str, question: str) -> str:
        """Select one relevant, exact paragraph from a corpus chunk."""
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text)
                      if part.strip()]
        prose = [part for part in paragraphs if not part.lstrip().startswith(
            ("#", "<figure", "```"))]
        candidates = prose or paragraphs
        stop = {"what", "when", "where", "which", "why", "how", "does",
                "did", "the", "this", "that", "with", "from", "into",
                "your", "have", "actually", "should", "position"}
        terms = {term for term in re.findall(r"[a-z0-9_]+", question.lower())
                 if len(term) >= 4 and term not in stop}

        def score(part: str) -> tuple[int, int]:
            lower = part.casefold()
            matched = 0
            for term in terms:
                # A conservative stem lets liquidate/liquidation and similar
                # forms meet without introducing a paraphrase.
                stem = term[:6] if len(term) >= 7 else term
                matched += lower.count(stem)
            return matched, min(len(part), self.max_chars)

        quote = max(candidates, key=score)
        if len(quote) > self.max_chars:
            boundary = max(quote.rfind(". ", 0, self.max_chars + 1),
                           quote.rfind("\n", 0, self.max_chars + 1),
                           quote.rfind(" ", 0, self.max_chars + 1))
            if boundary < 1:
                boundary = self.max_chars
            quote = quote[:boundary + (1 if quote[boundary:boundary + 2]
                                       == ". " else 0)].rstrip()
        lines = quote.splitlines()
        while lines and self._ORPHAN_MARKUP.fullmatch(lines[-1]):
            lines.pop()
        quote = "\n".join(lines).rstrip()
        return quote

    def write(self, question: str, evidence: tuple[Evidence, ...],
              route: Route) -> Draft:
        code_query = bool(re.search(
            r"\b(?:contract|function|event|error|solidity|selector|abi|interface)\b|"
            r"0x[0-9a-fA-F]{8}\b|[A-Za-z_]\w*\([^)]*\)", question))
        semantically_ranked = sorted(
            (item for item in evidence
             if code_query or item.source_type != "solidity"),
            key=lambda item: (-item.semantic_score, -item.score,
                              item.tier, item.id))
        prepared = []
        for item in semantically_ranked:
            if item.synthesised or not item.display_text.strip():
                continue
            quote = self._excerpt(item.display_text.strip(), question)
            relevance = self._topic_relevance(question, item, quote)
            if not quote or (self.require_topic_match and relevance <= 0):
                continue
            prepared.append((relevance, item, quote))
        prepared.sort(key=lambda candidate: (
            -candidate[0], -candidate[1].semantic_score,
            -candidate[1].score, candidate[1].tier, candidate[1].id))

        claims = []
        seen = set()
        for _, item, quote in prepared:
            fingerprint = re.sub(r"\s+", " ", quote).casefold()
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            claims.append(DraftClaim(text=quote, evidence_id=item.id,
                                     supporting_quote=quote))
            if len(claims) == self.max_claims:
                break
        return (Draft(tuple(claims)) if claims else
                Draft((), abstain_reason="no quotable evidence"))


class AnswerEngine:
    """Assemble answers while keeping model claims and live bytes separated."""

    def __init__(self, retriever, live_client, writer: EvidenceWriter | None = None,
                 router: Router | None = None,
                 coin_flip: Callable[[], bool] | None = None):
        self.retriever = retriever
        self.live_client = live_client
        self.writer = writer or ExtractiveWriter()
        self.router = router or Router()
        self.coin_flip = coin_flip or (lambda: bool(secrets.randbits(1)))

    def answer(self, question: str) -> Answer:
        route = self.router.route(question)
        if route.mode == RouteMode.EASTER_EGG:
            verdict = ("Yes. Categorically vegan. I refuse to elaborate."
                       if self.coin_flip() else
                       "No. Categorically not vegan. I refuse to elaborate.")
            return Answer(
                status="answered", mode=route.mode, text=verdict, route=route)
        if route.mode == RouteMode.CLARIFY:
            return Answer(
                status="needs_input", mode=route.mode,
                text=("I need the subject and behaviour you mean before I can "
                      "answer with evidence."),
                route=route, refusal_reason="missing_context")
        if route.mode == RouteMode.REFUSE:
            return self._refusal(route)
        if route.mode == RouteMode.REFUSE_POINT:
            return self._refusal(route, destination=route.destination)
        if route.mode == RouteMode.TRIAGE:
            return self._triage(route)
        known_gap = self.router.known_gap(question)
        if known_gap:
            return self._abstain(route, f"known corpus gap: {known_gap}")

        retrieval_response = None
        evidence_query = question
        evidence: tuple[Evidence, ...] = ()
        if route.mode in (RouteMode.CORPUS, RouteMode.CORPUS_LIVE,
                          RouteMode.CORRECT):
            try:
                evidence_query = self.router.evidence_query(question, route)
                retrieval_response = self.retriever.search(RetrievalRequest(
                    query=evidence_query,
                    chain_id=route.entities.chain_id,
                    protocol_version=route.entities.protocol_version,
                    version_explicit=route.entities.version_explicit,
                    tiers=("A", "B"), limit_per_tier=5))
            except (RetrievalError, ScopeError) as error:
                return self._abstain(route, f"evidence unavailable: {error}")
            evidence = tuple(item for tier in retrieval_response.by_tier.values()
                             for item in tier if not item.synthesised)
            floor = retrieval_response.minimum_semantic_score
            if floor is not None:
                evidence = tuple(item for item in evidence
                                 if item.semantic_score >= floor)
            if not evidence:
                return self._abstain(
                    route, "no retrieved evidence met the evaluated relevance floor")
            symbols = {name.casefold() for name in re.findall(
                r"\b([A-Za-z_]\w*)\s*\([^)]*\)", question)}
            if symbols:
                searchable = "\n".join(
                    f"{item.id} {item.breadcrumb} {item.model_text}".casefold()
                    for item in evidence)
                absent = sorted(name for name in symbols if name not in searchable)
                if absent:
                    return self._abstain(
                        route, "named code symbol is absent from the pinned corpus")

        live_rendered = None
        if route.mode in (RouteMode.LIVE, RouteMode.CORPUS_LIVE,
                          RouteMode.PARTIAL):
            missing = self._missing_entity(route)
            if missing:
                return Answer(
                    status="needs_input", mode=route.mode,
                    text=f"I need {missing} before I can read current state.",
                    route=route, refusal_reason="missing_entity")
            try:
                live_rendered = render_live(
                    self._read_live(route), field=route.live_field)
            except (GatewayUnavailable, LiveError) as error:
                return self._abstain(route, f"current state unavailable: {error}")

        claims: tuple[DraftClaim, ...] = ()
        citations: list[Citation] = []
        claim_lines = []
        if evidence:
            draft = self.writer.write(evidence_query, evidence, route)
            if draft.abstain_reason:
                return self._abstain(route, draft.abstain_reason)
            if not draft.claims:
                return self._abstain(route, "the writer returned no supported claims")
            claims = draft.claims
            evidence_by_id = {item.id: item for item in evidence}
            resolver = self.retriever.citation_resolver(
                route.entities.protocol_version or "v2.0")
            citation_numbers = {}
            for claim in claims:
                if not claim.text.strip():
                    raise AnswerError("writer returned an empty claim")
                item = evidence_by_id.get(claim.evidence_id)
                if item is None:
                    raise AnswerError(
                        f"writer cited evidence not supplied: {claim.evidence_id}")
                if not claim.supporting_quote or claim.supporting_quote not in item.display_text:
                    raise AnswerError(
                        f"claim support is not an exact corpus substring: {item.id}")
                if item.id not in citation_numbers:
                    try:
                        citation = resolver.resolve(item, include_quote=True)
                    except CitationError as error:
                        raise AnswerError(str(error))
                    citations.append(citation)
                    citation_numbers[item.id] = len(citations)
                claim_lines.append(
                    f"{claim.text} [{citation_numbers[item.id]}]")

        sections = []
        if retrieval_response and retrieval_response.preamble:
            sections.append(retrieval_response.preamble)
        if route.mode == RouteMode.CORRECT:
            sections.append("Premise correction\n\n" + "\n\n".join(claim_lines))
        elif claim_lines:
            sections.append("Explanation\n\n" + "\n\n".join(claim_lines))
        if live_rendered:
            heading = ("Transaction history"
                       if live_rendered.operation == "history"
                       else "Current state")
            sections.append(heading + "\n\n" + live_rendered.text)
        if route.mode == RouteMode.PARTIAL:
            sections.append(
                "I can report public state, but I cannot infer or speak for a "
                "borrower's plans or intentions.")
        if citations:
            sources = [f"[{index}] {citation.label}: {citation.source_url}"
                       for index, citation in enumerate(citations, 1)]
            sections.append("Sources\n\n" + "\n".join(sources))
        return Answer(
            status="answered", mode=route.mode, text="\n\n".join(sections),
            route=route, citations=tuple(citations), claims=claims,
            live=live_rendered,
            corpus_release_id=(retrieval_response.release_id
                               if retrieval_response else None))

    def _read_live(self, route: Route):
        operation = route.live_operation
        entities = route.entities
        if operation == "registry":
            return self.live_client.registry()
        if operation == "borrower_markets":
            return self.live_client.borrower_markets(entities.borrower_address)
        if operation == "account":
            return self.live_client.account(
                entities.market_address, entities.account_address)
        if operation == "withdrawals":
            return self.live_client.withdrawals(entities.market_address)
        if operation == "history":
            return self.live_client.history(
                entities.market_address,
                limit=route.live_limit or DEFAULT_HISTORY_EVENTS,
                event_types=route.live_event_types)
        if operation == "market":
            return self.live_client.market(entities.market_address)
        raise AnswerError(f"unsupported live operation {operation!r}")

    @staticmethod
    def _missing_entity(route: Route) -> str | None:
        entities = route.entities
        if route.live_operation == "borrower_markets" and not entities.borrower_address:
            return "the borrower's Ethereum address"
        if (route.live_operation in ("market", "withdrawals", "history")
                and not entities.market_address):
            return "the market contract address"
        if route.live_operation == "account":
            if not entities.market_address:
                return "the market contract address"
            if not entities.account_address:
                return "the lender wallet address"
        return None

    @staticmethod
    def _refusal(route: Route, destination: str | None = None) -> Answer:
        text = "I can't help with that request."
        if route.refusal_reason == "advice_or_assessment":
            text = ("I can provide public protocol facts, but I can't recommend a "
                    "market or assess a borrower.")
        elif route.refusal_reason == "bulk_lender_disclosure":
            text = "I can't provide or compile lender address lists."
        elif route.refusal_reason == "inferred_intent":
            text = "I can't infer or speak for a borrower's plans or intentions."
        elif route.refusal_reason == "unsupported_chain":
            text = "This Aleph release supports Ethereum mainnet only."
        elif route.refusal_reason == "unsafe_or_abusive":
            text = ("I can't comply with hateful or self-harm coercion. If someone "
                    "may be in immediate danger, contact local emergency services.")
        elif route.refusal_reason == "malformed_address":
            text = "I can't use malformed address-like text as a market or account."
        elif route.refusal_reason == "outside_answer_boundary":
            text = "I can only answer questions within Aleph's Wildcat Protocol scope."
        if destination:
            text += f" The appropriate destination is {destination}."
        if (route.refusal_reason != "unsafe_or_abusive"
                and not (route.refusal_reason == "outside_answer_boundary"
                         and destination is None)):
            text += (" I can prepare a handoff if you choose; I will not contact "
                     "anyone automatically.")
        return Answer(status="refused", mode=route.mode, text=text, route=route,
                      refusal_reason=route.refusal_reason)

    @staticmethod
    def _triage(route: Route) -> Answer:
        fields = {
            "withdrawal_action": (
                "market_address", "wallet_address", "withdrawal_amount",
                "transaction_hash"),
            "technical_failure": (
                "page_or_action", "chain_id", "wallet_type", "exact_error",
                "transaction_hash", "screenshot"),
        }[route.triage_kind]
        payload = TriagePayload(route.triage_kind, fields, {})
        return Answer(
            status="needs_handoff", mode=route.mode,
            text=("I can't perform that action, but I can prepare a support "
                  "handoff. Please provide: " + ", ".join(fields) +
                  ". Nothing is sent until you explicitly confirm."),
            route=route, triage=payload)

    @staticmethod
    def _abstain(route: Route, reason: str) -> Answer:
        return Answer(
            status="unavailable", mode=route.mode,
            text=("I can't produce a supported answer right now. " + reason +
                  ". No fallback source was used."),
            route=route, refusal_reason=reason)
