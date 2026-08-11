# Telegram adapter

`telegram.py` is a transport over `AnswerEngine`. It does not route questions,
retrieve evidence, query live state, rewrite answers, or decide refusals. The
adapter selects relevant Telegram messages, passes their text to the engine, and
delivers eligible human-facing answers as native Rich Messages with an exact
plain-message fallback.

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
Human-facing engine answers of at most 32,768 characters first use
`sendRichMessage`. The adapter maps only Aleph's reviewed `Explanation`,
`Premise correction`, `Current state`, and `Sources` labels to native headings;
the answer remains held separately as the unchanged fallback payload and source
URLs are copied byte-for-byte.

Set `ALEPH_TELEGRAM_RICH_MESSAGES=false` to disable rich delivery immediately on
the next service restart. The default is `true`. If Telegram refuses or does not
support `sendRichMessage`, the adapter sends the original answer without a parse
mode, disables link previews, and splits it at stable boundaries under the
4,096-character limit. Joining those chunks recreates the exact engine output.
Answers above the rich limit use this fallback directly, so a partially sent
rich answer can never be duplicated by a later fallback.

Only a definite Bot API refusal triggers fallback. A timeout, lost response, or
other ambiguous transport failure does not send a second representation; it
leaves the update uncheckpointed for retry. This distinction prevents a rich
answer accepted by Telegram from being duplicated by a speculative plain send.

Commands, handoff previews, and answers to approved peer bots always stay on the
plain-text contract. The peer rule preserves Project Null's end-to-end outcome
capture, which currently observes Telegram text replies. Rich drafts are not
sent: `sendRichMessageDraft` creates an ephemeral 30-second preview and Aleph has
no streaming answer path that could justify that additional lifecycle yet.

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
[`sendMessage`](https://core.telegram.org/bots/api#sendmessage), and
[`sendRichMessage`](https://core.telegram.org/bots/api#sendrichmessage),
[`InputRichMessage`](https://core.telegram.org/bots/api#inputrichmessage), and
[`ReplyParameters`](https://core.telegram.org/bots/api#replyparameters). Group
delivery assumptions follow Telegram's
[`Privacy Mode`](https://core.telegram.org/bots/features#privacy-mode) rules.
The narrow peer-bot path follows Telegram's
[`Bot-to-Bot Communication`](https://core.telegram.org/bots/features#bot-to-bot-communication)
delivery and loop-prevention rules.

`serve.py` supplies production composition, restart signaling, scrubbed audit
logging, and environment-only secret delivery. `monitor.py` supplies dependency
checks for the supervisor timer. A concrete human handoff sink remains disabled
until an operator names its owner and destination.
