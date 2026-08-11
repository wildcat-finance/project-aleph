# Telegram adapter

`telegram.py` is a transport over `AnswerEngine`. It does not route questions,
retrieve evidence, query live state, rewrite answers, or decide refusals. The
adapter selects relevant Telegram messages, passes their text to the engine, and
delivers the returned text — rendered with cosmetic Telegram markup for humans,
byte-exact plain text for peer bots.

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

Answers with the engine's section structure are rendered for human askers with
Telegram HTML: section headings are bold, inline `[n]` citation markers link to
their sources, full-length hex values become tap-to-copy `code` spans, and the
trailing Sources section collapses into an expandable quotation. Inside it each
URL is tucked behind a shortened label — the file name and the breadcrumb's
most specific segment — while the plain fallback keeps the full citation line.
The first two sources also repeat as URL buttons under the final message, so
the primary evidence is one tap away without expanding the quotation. The
visible text is otherwise the answer's own bytes — markup is added only after
every byte is HTML-escaped, so answer text can never be reinterpreted. The
renderer verifies that the plain fallback of its chunks reconstructs the exact
engine output and refuses to send otherwise.

Rendering is cosmetic and never load-bearing: if Telegram refuses a rendered
chunk, the adapter resends that chunk's exact plain bytes without buttons.
Unstructured replies (commands, refusals, rate-limit notices) are sent without
a parse mode, as are all replies to peer bots, which consume answer bytes
rather than markup. A best-effort `typing` chat action precedes engine answers
for human askers and is renewed about every five seconds until the answer is
ready; its failure never blocks an answer. Link previews are disabled. Responses longer
than Telegram's 4,096-character limit are split at stable text boundaries —
plain chunks join to recreate the exact engine output, and rendered chunks are
bounded by visible length with headroom for Telegram's double-width counting of
astral characters.

## Delivery and load boundaries

`OffsetStore` persists only the next Telegram update ID, never message text. The
checkpoint is atomically replaced after an ignored update or after every reply
has succeeded. A failed send leaves the update unconfirmed for retry.

Admission is limited per chat and user before the answer engine runs. The worker
pool has a configured upper bound; sends and checkpoints remain ordered. An
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
