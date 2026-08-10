# Telegram adapter

`telegram.py` is a transport over `AnswerEngine`. It does not route questions,
retrieve evidence, query live state, rewrite answers, or decide refusals. The
adapter selects relevant Telegram messages, passes their text to the engine, and
delivers the returned text as plain messages.

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
- a leading `@AlephBot` mention; and
- a direct reply to an Aleph message.

Ambient group text, commands addressed to another bot, channel posts, service
updates, non-text messages, and messages from bots are ignored. Polling requests
only the `message` update type.

Replies preserve the originating forum topic and use `reply_parameters`. Answer
text is sent without a Telegram parse mode, so citations and punctuation cannot
be reinterpreted as markup. Link previews are disabled. Responses longer than
Telegram's 4,096-character limit are split at stable text boundaries; joining
the chunks recreates the exact engine output.

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
[`ReplyParameters`](https://core.telegram.org/bots/api#replyparameters). Group
delivery assumptions follow Telegram's
[`Privacy Mode`](https://core.telegram.org/bots/features#privacy-mode) rules.

Production composition, restart/backoff policy, metrics, audit logging, secret
delivery, and a concrete human handoff sink belong to stage 7.
