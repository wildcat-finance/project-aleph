# Corpus diff review: `0e693cdec06e5992`

This review compares candidate corpus `0e693cdec06e5992` with active corpus
`1a78817a47146c00`. It reviews structure and provenance; it does not promote or
activate the candidate and does not replace product evaluation or human release
approval.

## Outcome

- Chunk count remains **1,616**.
- The diff is **6 added, 6 removed, and 1 changed-text index**.
- No pinned source text, source ref, tier, legal metadata, or live-state policy
  changed.
- The candidate has zero structural blockers and zero unreviewed chunks under
  audit `9277b8dfab51384e`.
- The candidate release is `53eeccf8f3604247b1dd` and remains non-promotable
  until evaluation and human release review are recorded.

## Known Issues reconciliation

There are **10 distinct known issues** in the pinned `wildcat-docs` page at
`aleph-v0.3`. All ten already have separate Tier B issue-level chunks.

The separately pinned `v2-protocol` file at `aleph-v2.1.0` contains only the
first **6** of those issues. In the active corpus those six were collapsed into
one 3,799-character Tier A chunk. The candidate splits that Tier A copy into six
issue-level chunks. This produces ten distinct issues overall, with six present
under both protocol-source and user-documentation provenance.

| Distinct issue | Tier A `v2-protocol` | Tier B `wildcat-docs` |
| --- | --- | --- |
| Avoiding delinquency fees | yes | yes |
| Malicious or delinquent borrowers can lead to loss of funds | yes | yes |
| Newer withdrawals lose accrued interest to previous withdrawals in the same batch | yes | yes |
| Bad hook implementations | yes | yes |
| Sanctioned-account handling with withdrawal restrictions | yes | yes |
| Hooks lack some specificity | yes | yes |
| Scaled/normalised conversion rounding | no | yes |
| Assembly blocks can leave dirty memory bits | no | yes |
| Markets can prevent anyone requesting a withdrawal | no | yes |
| Reliance on Chainalysis | no | yes |

The six duplicates are retained deliberately: they bind identical or
substantially equivalent statements to separate pinned authorities. Answer
assembly deduplicates identical quoted claims, so the duplicate lineage does
not require duplicate answer prose.

## Added chunks

All additions come from `v2-protocol:docs/Known Issues.md` and preserve the
source bytes of one strong-titled issue each:

1. `#avoiding-delinquency-fees`
2. `#malicious-or-delinquent-borrowers-can-lead-to-loss-of-funds`
3. `#newer-withdrawals-lose-some-of-their-accrued-interest-to-previous-withdrawals-in-the-same-batch`
4. `#bad-hooks-implementations`
5. `#sanctioned-account-handling-can-lead-to-unexpected-behavior-on-markets-with-withdrawal-restrictions`
6. `#hooks-lack-some-specificity`

These logical chunk IDs intentionally do not invent GitBook fragments: the
source uses strong paragraphs rather than rendered headings. Citations continue
to resolve to the pinned file while breadcrumbs expose the issue title.

## Removed chunks

- `v2-protocol:docs/Known Issues.md#intro` — replaced by the six coherent Tier A
  issue chunks above.
- Five `#document` chunks whose entire evidence was a heading such as
  `# /access`, `# /market`, or `# Day-To-Day Usage` — removed as retrieval
  noise. Their synthesized document indexes and useful frontmatter descriptions
  remain in the corpus, so navigation coverage is preserved.

## Changed text

`v2-protocol:docs/Known Issues.md#index` now lists the six logical issue titles.
No factual issue prose changed.

## Review limits

The structural ledger records 348 coherent warning-bearing units and explicitly
binds every rule to the candidate corpus hash, base audit ID, exact match count,
and sorted-ID digest. Legal sections, deterministic indexes and Solidity
surfaces, provenance-distinct duplicates, subordinate strong labels, and
heading/symbol-bounded size exceptions remain visible in the final inventory.
Any future corpus or audit-rule change invalidates the ledger instead of silently
inheriting these dispositions.

## Behavioural evaluation status

Candidate evaluation `e119ef83e84fe8c6f7b5` and active-baseline evaluation
`9f61f171944ba7883c37` produce the same result: 133/134 product cases and 24/25
retrieval labels pass. The candidate therefore introduces no measured
behavioural regression, but it does **not** satisfy the promotion gate.

The two baseline gaps are tracked separately in issue #45: the `n05` APR-owner
premise correction needs a grounded evidence-query expansion, and retrieval
label `a08` needs the reviewed withdrawal-batch wording restored to the ranked
evidence set. Thresholds remain unchanged and this candidate must not be
promoted until the complete evaluation passes.
