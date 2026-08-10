# Answer path

`agent.py` is the current boundary between a user's question and Aleph's typed
evidence and live-state components. It is policy-first: routing and entity
extraction finish before retrieval, gateway access, or language generation can
run.

## Flow

```text
question
  -> extract chain, version and addresses
  -> choose reviewed handling mode
  -> retrieve corpus evidence and/or read pinned live state
  -> validate structured claims against corpus bytes
  -> append deterministic live rendering unchanged
  -> return answer, refusal, clarification, or unsent triage payload
```

No component silently falls back. Missing entities produce one targeted request;
missing evidence, an unhealthy gateway, a changed block, a citation mismatch, or
an unsupported scope produces no factual answer.

## Handling modes

| Mode | Inputs | Output |
|---|---|---|
| `corpus` | immutable release evidence | supported claims and commit-pinned citations |
| `live` | one health-checked gateway block | deterministic renderer output |
| `corpus+live` | both | separate explanation and current-state sections |
| `correct` | corpus evidence | an explicitly labelled premise correction |
| `partial` | allowed public live facts plus a disallowed intent question | public state followed by a deterministic intent refusal |
| `refuse` | policy only | refusal and optional user-controlled handoff offer |
| `refuse+point` | policy and destination map | refusal naming the correct owner or tool |
| `triage` | policy only | the minimum fields needed for a later human handoff |

`eval/golden-v1.yaml` is the reviewed routing contract. `test_agent.py` requires
all 125 questions to enter their expected mode. The rules describe the question
shapes rather than matching question IDs, so new wording still reaches the same
policy boundary.

## Claim contract

An `EvidenceWriter` receives only the question, the selected route, and quotable
`Evidence` objects. It returns `DraftClaim` objects containing:

- the proposed text;
- one evidence ID from the supplied set; and
- an exact supporting substring from that evidence's `display_text`.

The answer engine rejects an unknown evidence ID, an empty claim, a supporting
quote absent from the corpus, a synthesized retrieval aid, or a citation that
does not resolve against the loaded release. `ExtractiveWriter` is the safe
dependency-free implementation and emits corpus substrings directly. A language
writer cannot weaken the validation contract.

Stage 5 adds semantic claim-support evaluation. Structural attribution is
already enforced here; a writer that pairs a true quote with an unsupported
paraphrase must still fail the promotion evaluation.

## Live-state separation

The writer never receives numeric live payloads. `live.py` parses gateway values
into typed integer facts and renders them separately. `AnswerEngine` appends the
finished `RenderedLive.text` byte-for-byte, preserving its block number, pinned
gateway release, units, basis-point formatting, and state labels.

## Refusal and handoff boundary

Aleph does not recommend markets, assess borrowers, infer intentions, disclose
bulk lender addresses, expose system/private context, or answer for unsupported
chains. A refusal can name a destination and offer to prepare a handoff, but it
cannot contact anyone.

Triage requests only fields required by its category. A withdrawal action asks
for market, wallet, amount, and transaction hash. A technical failure asks for
the page or action, chain, wallet type, exact error, transaction hash, and an
optional screenshot. The returned payload is empty until the user supplies
those fields and remains unsent until they separately confirm.
