# Local Ouroboros control plane

`ouroboros.py` lets a local Claude session or deterministic daemon direct the
same Aleph–Null cycle without becoming a second source of truth. It stores the
cycle position, emits one bounded action, and accepts one attributable receipt.
It does not hold Telegram, GitHub, Gateway, corpus, signing, deployment, or
production credentials and never executes those mutations itself.

The local system has three named parts:

- **Ouroboros** is the complete improvement cycle;
- **Mephistopheles** is Aleph's optional local inference daemon; and
- `ouroboros.py` is the deterministic controller shared by interactive and
  unattended executors.

The controller reproduces ordering, identities, stop conditions, review
counts, candidate-drain requirements, release gates, handoff, and resume. It
does not reproduce human factual review, repository approval, release approval,
production access, Telegram delivery, or external service availability. Those
remain external actions proven by receipts.

## State and trust boundary

The state directory contains `cycle.json`, `cycle.lock`, and optional advisory
model proposals. Keep it outside the repository; the default
`state/ouroboros` is ignored by Git. State is atomically written with mode
`0600`; its receipt ledger is hash-chained and covered by the state hash. This
detects damage and partial or unsophisticated edits inside the protected state
directory. It is not a signature: someone able to replace the complete state
and controller code can construct a new chain. Filesystem access control,
attributable external artefacts, Git history, and existing release approvals
remain the trust anchors.

An operating-system lock excludes simultaneous controller processes. The
durable lease excludes sequential control by different people. One Wildcat
identity holds it. Normal handoff uses `release` then `acquire`; emergency
`takeover` requires a new identity and reason and advances the lease epoch. A
takeover does not revoke the droplet tunnel or Telegram access—follow the
separate revocation steps in [`../OUROBOROS.MD`](../OUROBOROS.MD).

The controller records state assertions, not secrets or conversation content:

- Aleph source revision, release, evolution/generation and activation sequence;
- Null source revision, run, pause/mode, exact unreviewed and candidate counts,
  and coverage identity;
- action/receipt IDs, actors, timestamps and validation outcomes; and
- Mephistopheles mode, alias, pinned ID and identity result at preflight.

Never put questions, answers, feedback notes, Telegram identifiers, addresses,
tokens, environment values, generated prose, or model reasoning in controller
state. External audit and immutable candidate systems retain their existing
records.

## Collect an initial identity

Collect fresh outputs while Null is paused:

1. run Aleph's production `monitor.py` as `aleph-query` and save its JSON;
2. run Null's `snapshot.py` through its production one-shot wrapper and save
   its canonical JSON; and
3. obtain the exact deployed Aleph source revision from the deployment record.

Do not scrape `/ping` or `/status` prose. Do not give the local controller SSH,
bot, Gateway, GitHub, or database credentials. Copy only the two scrubbed JSON
outputs through the approved operator channel.

Build the init identity:

```bash
python3 ouroboros.py snapshot \
  --aleph-monitor /secure/handoff/aleph-monitor.json \
  --null-snapshot /secure/handoff/null-snapshot.json \
  --aleph-source-revision <deployed-commit> \
  > /secure/handoff/identity.json
```

The command verifies every Aleph monitor check, Null's snapshot hash, and exact
release/evolution/generation agreement. Any lag or malformed input is a stop.

## Start and inspect a cycle

```bash
python3 ouroboros.py --state-dir /secure/ouroboros init \
  --actor operator@wildcat.finance \
  --identity /secure/handoff/identity.json

python3 ouroboros.py --state-dir /secure/ouroboros status
python3 ouroboros.py --state-dir /secure/ouroboros plan
python3 ouroboros.py --state-dir /secure/ouroboros receipt-template
```

`plan` is the only action a daemon should schedule. It includes the action ID,
phase, input identity, plain-language instruction, exact result fields, and the
statement that execution authority is external. `receipt-template` makes the
corresponding envelope. Fill every result field from actual command output; do
not ask a model to invent receipt values.

Validate a receipt without changing state:

```bash
python3 ouroboros.py --state-dir /secure/ouroboros --dry-run record \
  --controller-actor operator@wildcat.finance \
  --receipt /secure/handoff/receipt.json
```

Record it only after the preview succeeds:

```bash
python3 ouroboros.py --state-dir /secure/ouroboros record \
  --controller-actor operator@wildcat.finance \
  --receipt /secure/handoff/receipt.json
```

The next `plan` returns the same pending action across restarts until one valid
receipt advances it. Replaying an earlier receipt fails because its action ID is
no longer pending.

## Phase contract

| Phase | External executor proves | Blocking rule |
|---|---|---|
| `preflight` | both monitors, Null paused, Mephistopheles status and pin | disabled has no model pin; shadow requires an observed matching pin |
| `wave` | requested, delivered and correlated counts plus boundary | all counts match and Null is paused again |
| `review` | feedback and finalisation counts | no malformed or unexplained result; reviewer decides another wave |
| `candidate_drain` | complete export/disposition report and zero pile | no unresolved candidate remains |
| `implementation` | issue, PR, reviewed source IDs and source revision | issue-first provenance exists; model proposals are not evidence |
| `evaluation` | passing evaluation, exact source/candidate/evaluation IDs | prior release remains available |
| `activation` | human approver, reason and prior candidate/evaluation IDs | only this phase may advance Aleph runtime identity |
| `verification` | monitors, canary, applied report and zero pile | may only synchronise Null coverage to activated Aleph identity |

If candidate disposition requires no source or code change, the controller
skips directly from `candidate_drain` to `verification`. If review explicitly
requests more coverage, it returns to `wave`. These branches are receipt facts,
not model choices.

## Interactive Claude or plugin operation

An interactive `/ouroboros` skill should be a presenter and receipt helper over
this CLI:

1. call `status` and `plan`;
2. explain the pending external action;
3. optionally ask a local model for an advisory proposal;
4. show the proposal to the operator without executing it;
5. collect actual external results;
6. fill a receipt template;
7. run `--dry-run record`; and
8. ask for the authority required by the external action before it occurs.

The session must not summarize away codes, counts, IDs, approval names, or stop
conditions. A later session resumes from state instead of relying on chat
history. The plugin may choose local Mephistopheles once per operator preference
or use hosted inference, but both produce the same advisory schema and neither
changes execution authority.

## Unattended daemon operation

A daemon uses the same commands and state. It may automatically perform only
pre-authorized deterministic reads and local validation. It should:

1. invoke one controller command at a time;
2. read `plan`;
3. dispatch the phase to a fixed allowlisted adapter;
4. store the adapter's original scrubbed output outside controller state;
5. build the exact receipt;
6. preview with `--dry-run record`;
7. record only if the phase is in its configured authority set; and
8. stop and notify on any nonzero exit.

Recommended automatic authority is limited to monitors, snapshots, local build
and evaluation in an isolated workspace. Telegram waves, feedback,
finalisation, GitHub writes, source review, promotion, activation, deployment,
rollback, lease takeover, and candidate acknowledgement remain human-gated
unless a separate policy explicitly grants that exact action. Never implement
“continue on error.”

## Advisory local-model proposals

Mephistopheles or another local model can propose three bounded objects:

```bash
python3 ouroboros.py --state-dir /secure/ouroboros propose \
  --actor operator@wildcat.finance --kind wave_plan \
  --input /secure/handoff/model-proposal.json
```

The kinds are `wave_plan`, `feedback`, and `next_action`. The validator limits
counts and fields, rejects reasoning keys, and stores accepted objects as
`advisory_only`. Proposal text is never copied into a receipt. The model cannot
advance state, send a probe, classify a result authoritatively, create an issue,
write corpus content, approve an evaluation, or activate a release.

## Recovery and handoff

After a process or machine restart, rerun `status`. Valid state replays its
receipt chain and returns the exact pending action. If verification fails, keep
the directory unchanged for investigation; never delete a receipt or rebuild
state by hand. Recover from the last trusted backup of the complete directory,
then compare its cycle and chain-head IDs with the prior handoff.

Normal operator handoff:

```bash
python3 ouroboros.py --state-dir /secure/ouroboros handoff \
  > /secure/handoff/ouroboros-handoff.json
python3 ouroboros.py --state-dir /secure/ouroboros release \
  --actor outgoing@wildcat.finance
python3 ouroboros.py --state-dir /secure/ouroboros acquire \
  --actor incoming@wildcat.finance
```

The handoff is scrubbed and contains cycle identity, phase, chain head and next
action, not receipts or proposals. The new operator independently re-collects
Aleph and Null state before the next external action. If that state differs from
the pending action identity, stop and reconcile rather than issuing a receipt.

Emergency takeover is explicit and forensic:

```bash
python3 ouroboros.py --state-dir /secure/ouroboros takeover \
  --actor incident-operator@wildcat.finance \
  --reason <incident-or-handoff-reference>
```

## Local fidelity boundary

Faithfully reproduced locally:

- evolution/generation and release/run identity binding;
- one-operator control, exact phase ordering and restart-safe resume;
- wave/review count reconciliation and candidate-pile completion;
- model proposal schemas and fail-closed reasoning exclusion;
- corpus/evaluation/activation checkpoint semantics;
- atomic, attributable, hash-chained receipts in a protected state directory; and
- the same state surface for Claude guidance and deterministic daemons.

Still requires a person or external system:

- Telegram delivery and visual answer review;
- deciding whether a factual proposal is correct and locating canonical proof;
- GitHub issue, PR and required human review policy;
- deciding to change the evolution contract;
- corpus diff approval, release approval and production activation authority;
- production credentials, host access and incident response; and
- judgment when an unexpected result is not represented by the current schema.

Equal fidelity means these external decisions are preserved and evidenced. It
does not mean replacing them with a local model.
