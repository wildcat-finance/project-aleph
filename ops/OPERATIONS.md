# Production operations

This runbook operates already-built Aleph artifacts. The query service never
builds a corpus, changes an index, approves an evaluation, watches a signing key,
or edits its active pointer.

## Process and credential separation

Use distinct operating-system identities and storage permissions:

| Identity | May read | May write | Credentials |
|---|---|---|---|
| `aleph-build` | manifest and pinned public sources | candidate corpus/index/release store | source-fetch access only |
| `aleph-embed` | candidate corpus | candidate index/release store | model runtime only |
| `aleph-operator` | approved artifact store | activation records and active pointer | none |
| `aleph-query` | active artifacts and pointer | Telegram offset and scrubbed audit directory | gateway, Telegram, audit HMAC |
| offline reviewer | corpus diff and evaluation | signed review/approval input | any future signing authority |

Do not install a source-tag signing secret on the build, embedding, query, or
Telegram host. `sdk-watch.py` is an alarm and has no write path into artifacts.

## Build and approve

Build main and v2.5 releases through `release.py`. The main release must use
`--fetch-sdk`, and a changed corpus must name its reviewer:

```bash
python3 release.py --manifest manifest.yaml \
  --solc ingest/solc-container --fetch-sdk \
  --against artifacts/corpus/<previous>/chunks.jsonl \
  --diff-reviewed-by <reviewer> --artifacts artifacts

python3 release.py --manifest manifest.yaml --prerelease \
  --solc ingest/solc-container --artifacts artifacts
```

Evaluate the exact artifacts and bind the passing record:

```bash
python3 eval/product_eval.py --manifest manifest.yaml \
  --release artifacts/releases/<candidate>/release.json \
  --prerelease artifacts/releases/<v25>/release.json \
  --embedder ollama:bge-m3 --artifacts artifacts

python3 promotion.py \
  --release artifacts/releases/<candidate>/release.json \
  --evaluation artifacts/evaluations/<evaluation>/evaluation.json
```

`promotion.py` emits a new release ID. That evaluated child—not the raw
candidate—is eligible for activation.

## Activate

Copy the immutable artifact tree to the query host without changing paths inside
the tree. As `aleph-operator`, use compare-and-swap when replacing an existing
release:

```bash
python3 activation.py --manifest /opt/aleph/manifest.yaml \
  --artifacts /srv/aleph/artifacts \
  --pointer /srv/aleph/active-release.json activate <approved-release-id> \
  --actor <operator> --reason <change-ticket> \
  --expected-active <current-release-id>
```

The command re-verifies the manifest, corpus, index, evaluation, required gates,
and release identity under an exclusive lock. It publishes an immutable
activation record before atomically replacing the pointer. A crash before the
pointer replacement leaves the prior release active.

Restart the query unit after the pointer changes, then run `monitor.py`. The
service loads and verifies the pointer before it creates network clients.

Before an active release or Telegram credential exists, verify the dedicated
Data Gateway credential independently from the repository root:

```bash
python3 gateway_smoke.py --manifest manifest.yaml
```

The command performs one authenticated registry query after the normal health
gate, pins it to the checked block, and prints only release, block, head, and
sample-count metadata. It never prints the credential or response contents.

## Roll back

Rollback does not rebuild and does not delete the rejected release:

```bash
python3 activation.py --manifest /opt/aleph/manifest.yaml \
  --artifacts /srv/aleph/artifacts \
  --pointer /srv/aleph/active-release.json rollback \
  --actor <operator> --reason <incident-ticket>

systemctl restart aleph.service
```

By default the target is the active activation record's predecessor. Use
`--to-release <approved-release-id>` only for an intentionally selected older
artifact. Rollback creates another immutable activation generation, preserving
the complete sequence.

## Query service

Supply three independent secrets through root-owned environment files:

- `ALEPH_GATEWAY_TOKEN` for authenticated live GraphQL reads;
- `ALEPH_TELEGRAM_TOKEN` for the Bot API; and
- `ALEPH_AUDIT_HMAC_KEY`, at least 32 random bytes, for non-reversible question
  fingerprints.

`ALEPH_PEER_BOT_IDS` is not a secret. Leave it unset by default. When an approved
peer bot must ask Aleph questions, set it in `/etc/aleph/telegram.env` to that
bot's numeric Telegram ID (or a comma-separated allowlist), verify Bot-to-Bot
Communication Mode, and restart the query service. An allowlisted peer still has
access only to explicitly targeted `/ask@AlephBot` commands.

The audit log contains route and evidence provenance, not raw question text,
answer text, user IDs, wallet/market/borrower addresses, or exception messages.
Daily files are mode `0600`; `serve.py` removes days older than the configured
retention at startup. Thirty days is the default and should not be raised without
a documented need.

Keep `/srv/aleph/artifacts` and `/srv/aleph/active-release.json` read-only to
`aleph-query`. Its only writable paths are `/var/lib/aleph-query` for the
Telegram offset and `/var/log/aleph` for scrubbed audits. This prevents the
network-facing process from selecting its own evidence release.

Archive transfers may preserve restrictive build-host modes. After copying,
make the immutable tree service-readable without making it writable:

```bash
chown -R root:root /srv/aleph/artifacts
chmod -R a+rX /srv/aleph/artifacts
chmod -R a-w /srv/aleph/artifacts
```

Run `monitor.py` as `aleph-query` before enabling polling; this catches a
permission error at the same boundary production uses.

The Telegram bot must retain Group Privacy mode, must not be a group admin, and
must have no webhook. A human handoff sink is disabled until an owner and
idempotent destination are explicitly configured.

## Monitoring

`monitor.py` exits nonzero unless all of the following agree:

- active pointer, immutable activation, promotable release, and evaluation;
- active index identity and the running embedding model artifact;
- pinned gateway release health, integrity, circuit state, and zero lag; and
- Telegram authentication, privacy mode, and absent webhook.

The supplied timer runs this check every five minutes. Alert on any nonzero
exit. The service manager separately alerts on query-process restarts.

`aleph-sdk-watch.timer` runs daily. Exit `1` means mainnet addresses changed and
is an incident; exit `2` means a newer package exists with unchanged addresses
and is a review notification; exit `3` is an operational failure. It never
updates the manifest or rebuilds Aleph.

## Incident decisions

| Condition | Response |
|---|---|
| Gateway lag, open circuit, or wrong block | Do not fall back. Keep corpus-only/refusal behavior and investigate the pinned release. |
| Model identity mismatch | Stop query service. Restore the pinned artifact or build and evaluate a new release. |
| SDK address drift | Treat live address resolution as stale. Reconcile the SDK change before editing the manifest. |
| Failed evaluation or corpus review | Leave the current pointer unchanged. Read per-ID regressions and corpus diff. |
| Bad active answers | Roll back the pointer, restart query service, retain artifacts and audit provenance. |
| Telegram privacy disabled or webhook present | Stop polling; correct BotFather/webhook state before restart. |
| Suspected credential exposure | Stop the affected process, rotate only that credential, and do not place replacements in the repository. |
