# Corpus diff review: `30809abeed344694`

This review compares the `wildcat-docs@aleph-v0.4` candidate corpus
`30809abeed344694` with the v0.3 corpus `0e693cdec06e5992`. It reviews source,
structure, and provenance; production activation remains a separate operation.

## Outcome

- The corpus grows from **1,616** to **1,624** chunks: **9 added, 1 removed,
  and 3 changed-text records**.
- Every content change comes from
  `using-wildcat/wildcat-market-csv-exporter.md` at commit
  `dced3f3843258aa063fb6d6369cf434d5dfa4957`.
- All four watched legal documents are byte-identical to their pinned digests.
- All 64 documentation files remain placed in the `SUMMARY.md` hierarchy.
- Base audit `d317fe51f1763779` has zero blockers; reviewed audit
  `af5810196db35a92` has zero unreviewed chunks after the corpus-bound
  structural ledger is applied.
- Product evaluation `3c05737ba7da9b922db5` passes all **143** cases and all
  **26** retrieval labels.
- Promotable release `841be8286322cd7605ea` binds this corpus, its embedding
  index, the v2.5 isolation release, the evaluation, and the evaluated runtime
  tool inventory.

## Added evidence

The nine new heading-bounded sections document:

1. the archive-node, Etherscan transaction, and Etherscan transfer inputs;
2. exact snapshot-block reconciliation and fail-closed export conditions;
3. the distinction between contract facts and FIFO, LIFO, or pro-rata
   accounting conventions;
4. a worked allocation example;
5. funded and unfunded queued-withdrawal treatment;
6. lender-to-lender transfer basis;
7. realised and unrealised interest fields;
8. raw-unit position invariants; and
9. the limits on using the resulting files for formal accounting or tax work.

All nine are ordinary source headings with no structural warning. They contain
no prompt-like instructions, hidden model text, new legal terms, addresses, or
claims that the accounting convention is an on-chain fact.

## Removed and changed evidence

The old `#using-the-csvs` section is replaced by the more precise
`#using-the-files` section. The page title, requirements, and deterministic page
index change to reflect ChatGPT support, the fixed snapshot, additional output
files, and the expanded heading structure. No other corpus text changes.

## Structural ledger

The candidate has the same 348 warning-bearing logical IDs and the same
per-warning ID-set digests as the reviewed v0.3 corpus. The changed page index
retains its existing ID and deterministic-index classification; the nine new
sections are auto-pass records. The ledger therefore rebinds the previously
reviewed structural classes to the new corpus and audit identities without
silently admitting a new warning-bearing unit.

## Behavioural boundary

Aleph may explain what the downloadable exporter builds and verifies from the
pinned documentation. It still does not generate a full CSV or financial
statement itself. Its typed live-history operation remains a separate,
explicitly addressed, one-to-ten-event read.
