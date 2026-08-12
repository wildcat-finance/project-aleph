# Telegram adapter

`telegram.py` is a transport over `AnswerEngine`. It does not route questions,
retrieve evidence, query live state, rewrite answers, or decide refusals. The
adapter selects relevant Telegram messages, passes their text to the engine, and
delivers the returned text: native Rich Messages where eligible, cosmetic
entity rendering as the universal fallback, and byte-exact plain text for peer
bots, commands, and the final fallback rung.

`/ping` (or `/ping@<AlephBot>` in a group) is a read-only polling command. A
live process replies with `Pong!`, monotonic process uptime, activation
generation, release/corpus/index/evaluation identities, prerelease and Gateway
pins, embedding identity, manifest hash, and abbreviated pinned source commits.
It does not run retrieval or generation, consume the question rate limit, read
live user state, or expose credentials. Missing optional metadata is omitted;
if no runtime identity was supplied at composition, the reply says so.

## Startup boundary

The adapter uses the HTTPS Bot API directly and reads its credential only from
`ALEPH_TELEGRAM_TOKEN`. It runs `getMe` and `getWebhookInfo` before polling and
refuses to start when:

- the credential does not identify a bot with a username;
- `can_read_all_group_messages` says group privacy mode is disabled; or
- an outgoing webhook is configured.

The adapter never deletes a webhook automatically. Telegram does not allow
`getUpdates` while a webhook is active, and silently changing an existing bot's
delivery mode would discard an operator decision. Remove the webhook explicitly
before starting this service.

After the checks pass, startup registers the `/ask`, `/ping`, `/help`, and `/privacy`
command menu via `setMyCommands` so commands are discoverable from Telegram's
command button. Registration is best-effort and never blocks startup; the
contextual handoff commands stay out of the menu and are introduced by the
triage answer that needs them.

Keep the bot's Group Privacy setting enabled in BotFather and do not make Aleph a
group administrator. Telegram administrators receive the whole group stream
regardless of the ordinary privacy-mode setting.

## Accepted messages

Private chats accept `/ask <question>` and plain text. Groups and supergroups
accept:

- `/ask@AlephBot <question>` or a delivered `/ask <question>` command;
- a direct reply to an Aleph message.

The adapter can parse a leading `@AlephBot` mention if Telegram delivers it,
but that is not a reliable summon while Group Privacy is enabled. Telegram's
[privacy-mode FAQ](https://core.telegram.org/bots/faq#what-messages-will-my-bot-get)
guarantees commands explicitly addressed to the bot and replies; use those in
groups. Do not disable privacy or grant administrator access merely to make a
plain mention work.

Ambient group text, commands addressed to another bot, channel posts, service
updates, and non-text messages are ignored. Polling requests only the `message`
update type.

Bot-authored messages are ignored by default. A bot whose numeric Telegram ID is
listed in the comma-separated `ALEPH_PEER_BOT_IDS` environment variable may send
only `/ask@AlephBot <question>` in a shared group. Peer bots cannot use ambient
text, replies, untargeted commands, or any handoff command. Aleph refuses to
start if its own ID appears in the allowlist. Keep the allowlist empty unless an
operator has identified a specific peer and enabled Telegram's
[Bot-to-Bot Communication Mode](https://core.telegram.org/api/bots%2Fbot-to-bot)
for one of the participating bots.

Replies preserve the originating forum topic and use `reply_parameters`.

## Rendering

Human-facing engine answers descend a three-rung delivery ladder — native rich
message, entity-rendered HTML, exact plain text. Each rung falls through to the
next only on a definite Bot API refusal; a timeout, lost response, or other
ambiguous transport failure never sends a second representation and instead
leaves the update uncheckpointed for retry. This distinction prevents an answer
accepted by Telegram from being duplicated by a speculative resend.

Answers of at most 32,768 characters first use `sendRichMessage`. Only
adapter-generated constructs carry markup: Aleph's reviewed `Explanation`,
`Premise correction`, `Current state`, and `Sources` labels map to native
headings, the source list becomes numbered links with compact labels, and
inline `[n]` citation markers link to their sources. Every other byte is
backslash-escaped, so corpus text containing markdown or template syntax
renders as literal text and can never be reinterpreted as markup. The answer
remains held separately as the unchanged fallback payload. Set
`ALEPH_TELEGRAM_RICH_MESSAGES=false` to disable rich delivery immediately on
the next service restart; the default is `true`. Answers above the rich limit
skip this rung, so a partially sent rich answer can never be duplicated by a
later fallback.

On both rendered rungs a lone `Explanation` heading is dropped from the
displayed message — the body speaks for itself and `Sources` still anchors the
layout — while answers with several sections keep every heading. The plain
fallback always keeps the heading's bytes.

`Current state` sections render as a stat card on both rungs: one field per
line, bold `Label:` prefixes, and hex values in tap-to-copy code spans. The
rich dialect soft-wraps single newlines into spaces — production collapsed a
live market reading into one run-on paragraph — so the rich renderer ends
consecutive content lines with an explicit hard break. Labels are bolded only
under a `Current state` heading; claim prose with a colon never changes.

When rich delivery is refused, unsupported, disabled, or oversized, answers
with the engine's section structure are rendered with classic Telegram HTML
entities, which every client can display — including clients too old to render
rich messages at all: section headings are bold, inline `[n]` citation markers
link to their sources, full-length hex values become tap-to-copy `code` spans,
and the trailing Sources section collapses into an expandable quotation.
Inside it each URL is tucked behind the same compact label the rich rung uses —
the file name and the breadcrumb's most specific segment — while the plain
fallback keeps the full citation line. The first two sources also repeat as
URL buttons under the final message, so the primary evidence is one tap away
without expanding the quotation. The visible text is otherwise the answer's
own bytes — markup is added only after every byte is HTML-escaped, so answer
text can never be reinterpreted. The renderer verifies that the plain fallback
of its chunks reconstructs the exact engine output and refuses to send
otherwise. If Telegram definitively refuses a rendered chunk, the adapter
resends that chunk's exact plain bytes without buttons.

Commands, handoff previews, refusals, rate-limit notices, and answers to
approved peer bots always stay on the plain-text contract with no parse mode.
The peer rule preserves Project Null's end-to-end outcome capture, which
currently observes Telegram text replies. Rich drafts are not sent:
`sendRichMessageDraft` creates an ephemeral 30-second preview and Aleph has no
streaming answer path that could justify that additional lifecycle yet.

A best-effort `typing` chat action precedes engine answers for human askers
and is renewed about every five seconds until the answer is ready; its failure
never blocks an answer. Link previews are disabled on every rung. Responses
longer than Telegram's 4,096-character limit are split at stable text
boundaries — plain chunks join to recreate the exact engine output, and
rendered chunks are bounded by visible length with headroom for Telegram's
double-width counting of astral characters.

## Delivery and load boundaries

`OffsetStore` persists only the next Telegram update ID, never message text. The
checkpoint is atomically replaced after an ignored update or after every reply
has succeeded. A failed send leaves the update unconfirmed for retry.

Admission is limited per chat and user before the answer engine runs. Human
askers receive the default five-question budget per 60 seconds. An allowlisted
peer bot has a separate ten-question budget over the same window, matching one
complete bounded Project Null burst without increasing the human allowance.
The eleventh peer question is rejected before the answer engine. The worker pool
has a configured upper bound; sends and checkpoints remain ordered. An
unexpected engine exception produces a fixed user-facing failure and exposes no
exception text.

## Handoffs

A triage answer prepares an in-memory draft for the same chat and user. It does
not invoke a handoff destination. The user must then:

1. supply allowlisted fields with `/handoff field=value; field=value`;
2. review the returned preview; and
3. issue a separate `/confirm_handoff` command.

`/cancel_handoff` discards the draft. Transaction hashes and screenshots are
optional; the other fields selected by `AnswerEngine` are required. Unknown,
duplicate, empty, or oversized fields are refused.

The configured `HandoffSink` receives a deterministic `handoff_id` and must use
it as an idempotency key. With the default disabled sink, confirmation reports
that no destination is configured and sends nothing.

## Official protocol fit

The implementation follows the current Telegram Bot API contracts for
[`getUpdates`](https://core.telegram.org/bots/api#getupdates),
[`sendMessage`](https://core.telegram.org/bots/api#sendmessage),
[`sendRichMessage`](https://core.telegram.org/bots/api#sendrichmessage),
[`InputRichMessage`](https://core.telegram.org/bots/api#inputrichmessage),
[`ReplyParameters`](https://core.telegram.org/bots/api#replyparameters),
[`sendChatAction`](https://core.telegram.org/bots/api#sendchataction),
[`InlineKeyboardMarkup`](https://core.telegram.org/bots/api#inlinekeyboardmarkup)
restricted to stateless `url` buttons, and the
[HTML formatting style](https://core.telegram.org/bots/api#html-style),
restricted to `b`, `a`, `code`, and `blockquote expandable` — entity types
stable since Bot API 7.3 (May 2024). Group
delivery assumptions follow Telegram's
[`Privacy Mode`](https://core.telegram.org/bots/features#privacy-mode) rules.
The narrow peer-bot path follows Telegram's
[`Bot-to-Bot Communication`](https://core.telegram.org/bots/features#bot-to-bot-communication)
delivery and loop-prevention rules.

`serve.py` supplies production composition, restart signaling, scrubbed audit
logging, and environment-only secret delivery. `monitor.py` supplies dependency
checks for the supervisor timer. A concrete human handoff sink remains disabled
until an operator names its owner and destination.
