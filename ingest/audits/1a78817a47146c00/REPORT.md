# Aleph corpus structural audit

Audit `9dd946a8f8ddb216` covers all 1,616 chunks 
in corpus payload `bb9072aac79c87a140c6fb7fd4a0b25d736810d9982b123aa5650f6afcca4953`.

## Dispositions

- **auto-pass**: 1,262
- **blocked**: 1
- **review-required**: 353

`auto-pass` means an explicit structural rule covers the chunk. 
`review-required` identifies material that needs a recorded human 
classification. `blocked` is a release-stopping structural defect.

## Findings

- **duplicate-content**: 18
- **legal**: 144
- **multiple-strong-sections**: 1
- **nested-strong-sections**: 15
- **oversized-review**: 58
- **synthesised**: 145
- **whole-document**: 5

## Review queue

| Disposition | Model chars | Tier | Source | Findings |
| --- | ---: | --- | --- | --- |
| blocked | 3,799 | A | `v2-protocol:docs/Known Issues.md#intro` | multiple-strong-sections, oversized-review |
| review-required | 9,524 | B | `wildcat-docs:legal/master-loan-agreement.md#id-1-definitions` | oversized-review, legal |
| review-required | 6,000 | B | `wildcat-docs:using-wildcat/day-to-day-usage/lenders.md#making-deposits` | oversized-review |
| review-required | 5,822 | A | `v2-protocol:docs/Scale Factor.md#wildcat-markets` | oversized-review, nested-strong-sections |
| review-required | 5,062 | A | `v2-protocol:src/types/HooksConfig.sol:LibHooksConfig` | oversized-review, synthesised |
| review-required | 4,637 | B | `wildcat-docs:legal/protocol-ui-privacy-policy.md#types-of-cookies` | oversized-review, legal |
| review-required | 4,296 | B | `wildcat-docs:using-wildcat/day-to-day-usage/lenders.md#expired-claims-and-the-withdrawal-queue` | oversized-review |
| review-required | 3,822 | B | `wildcat-docs:legal/master-loan-agreement.md#id-3-representations-warranties-and-covenants` | oversized-review, legal |
| review-required | 3,793 | B | `wildcat-docs:using-wildcat/day-to-day-usage/market-access-via-policies-hooks.md#market-access-via-policies-hooks` | oversized-review |
| review-required | 3,687 | A | `v2-protocol:src/market/WildcatMarket.sol:WildcatMarket#surface` | oversized-review, synthesised |
| review-required | 3,684 | B | `wildcat-docs:legal/master-loan-agreement.md#term-sheet` | oversized-review, legal |
| review-required | 3,636 | A | `v2-protocol:src/access/MarketConstraintHooks.sol:MarketConstraintHooks.onSetAnnualInterestAndReserveRatioBips(uint16,uint16,MarketState,bytes)` | oversized-review |
| review-required | 3,130 | A | `v2-protocol:src/HooksFactory.sol:HooksFactory._deployMarket(DeployMarketInputs,bytes,address,HooksTemplate,bytes32,address,uint256)` | oversized-review |
| review-required | 3,060 | B | `wildcat-docs:technical-overview/security-developer-dives/the-scale-factor.md#rebasing-with-interest` | oversized-review |
| review-required | 2,953 | A | `v2-protocol:src/access/FixedTermHooks.sol:FixedTermHooks._onCreateMarket(address,address,DeployMarketInputs,bytes)` | oversized-review |
| review-required | 2,927 | B | `wildcat-docs:using-wildcat/delinquency.md#unclaimed-pending-withdrawals-and-delinquency` | oversized-review |
| review-required | 2,910 | B | `wildcat-docs:legal/protocol-ui-privacy-policy.md#how-we-use-your-data` | oversized-review, legal |
| review-required | 2,876 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#index` | oversized-review, legal, synthesised |
| review-required | 2,835 | B | `wildcat-docs:technical-overview/security-developer-dives/hooks/access-control-hooks.md#tryvalidateaccess-address-lender-bytes-hooksdata` | oversized-review |
| review-required | 2,738 | A | `v2-protocol:src/market/WildcatMarket.sol:WildcatMarket.closeMarket()` | oversized-review |
| review-required | 2,706 | B | `wildcat-docs:using-wildcat/telegram-notification-bot.md#command-reference` | oversized-review |
| review-required | 2,702 | B | `wildcat-docs:legal/master-loan-agreement.md#id-6-limitations-on-liability` | oversized-review, legal |
| review-required | 2,673 | B | `wildcat-docs:legal/risk-disclosure-statement.md#iv.-security-risks` | oversized-review, legal |
| review-required | 2,623 | A | `v2-protocol:src/access/BaseAccessControls.sol:BaseAccessControls._tryValidateCredential(LenderStatus,address,bytes)` | oversized-review |
| review-required | 2,540 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-14.1-user-responsibility` | oversized-review, legal |
| review-required | 2,536 | B | `wildcat-docs:technical-overview/function-event-signatures/access/accesscontrolhooks.sol.md#functions` | oversized-review |
| review-required | 2,524 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-6.2-market-deployers-borrowers-responsibility-and-liability` | oversized-review, legal |
| review-required | 2,519 | A | `v2-protocol:src/access/FixedTermHooks.sol:FixedTermHooks#surface` | oversized-review, synthesised |
| review-required | 2,516 | A | `v2-protocol:docs/hooks/templates/Access Control Hooks.md#tryvalidateaccess-address-lender-bytes-hooksdata` | oversized-review |
| review-required | 2,450 | B | `wildcat-docs:using-wildcat/how-borrowers-are-onboarded.md#how-the-check-verifies-it` | oversized-review |
| review-required | 2,423 | A | `v2-protocol:src/access/OpenTermHooks.sol:OpenTermHooks#surface` | oversized-review, synthesised |
| review-required | 2,386 | B | `wildcat-docs:technical-overview/contract-deployments.md#sepolia-testnet-v1-components-of-pre-audited-v2` | oversized-review |
| review-required | 2,340 | A | `v2-protocol:src/market/WildcatMarketBase.sol:WildcatMarketBase._getUpdatedState()` | oversized-review |
| review-required | 2,330 | A | `v2-protocol:src/spherex/SphereXProtectedRegisteredBase.sol:SphereXProtectedRegisteredBase._getStorageSlotsAndPreparePostCalldata(int256)` | oversized-review |
| review-required | 2,329 | A | `v2-protocol:docs/CHANGELOG.md#market` | oversized-review, nested-strong-sections |
| review-required | 2,313 | A | `v2-protocol:src/types/HooksConfig.sol:LibHooksConfig.onSetAnnualInterestAndReserveRatioBips(HooksConfig,uint16,uint16,MarketState)` | oversized-review |
| review-required | 2,305 | A | `v2-protocol:src/market/WildcatMarketBase.sol:WildcatMarketBase._writeState(MarketState)` | oversized-review |
| review-required | 2,304 | A | `v2-protocol:docs/hooks/How Hooks Work.md#how-hooks-work` | oversized-review |
| review-required | 2,269 | A | `v2-protocol:EIP-4626_audit_scope.md#summary` | oversized-review |
| review-required | 2,251 | B | `wildcat-docs:using-wildcat/day-to-day-usage/borrowers.md#borrowing-from-a-market` | oversized-review |
| review-required | 2,244 | B | `wildcat-docs:using-wildcat/day-to-day-usage/borrowers.md#reducing-apr` | oversized-review |
| review-required | 2,242 | B | `wildcat-docs:using-wildcat/day-to-day-usage/lenders.md#making-withdrawals` | oversized-review |
| review-required | 2,235 | A | `v2-protocol:src/access/OpenTermHooks.sol:OpenTermHooks._onCreateMarket(address,address,DeployMarketInputs,bytes)` | oversized-review |
| review-required | 2,234 | B | `wildcat-docs:technical-overview/contract-deployments.md#mainnet` | oversized-review |
| review-required | 2,207 | A | `v2-protocol:src/market/WildcatMarketWithdrawals.sol:WildcatMarketWithdrawals#surface` | oversized-review, synthesised |
| review-required | 2,184 | A | `v2-protocol:src/WildcatArchController.sol:WildcatArchController#surface` | oversized-review, synthesised |
| review-required | 2,151 | B | `wildcat-docs:legal/master-loan-agreement.md#id-13-treatment-of-sanctioned-entities` | oversized-review, legal |
| review-required | 2,108 | B | `wildcat-docs:security-measures/spherex-protection.md#spherex-protection` | oversized-review |
| review-required | 2,104 | A | `v2-protocol:src/market/WildcatMarketConfig.sol:WildcatMarketConfig#surface` | oversized-review, synthesised |
| review-required | 2,098 | B | `wildcat-docs:legal/risk-disclosure-statement.md#vi.-protocol-specific-risks` | oversized-review, legal |
| review-required | 2,096 | B | `wildcat-docs:using-wildcat/day-to-day-usage/lenders.md#claiming` | oversized-review |
| review-required | 2,091 | B | `wildcat-docs:legal/risk-disclosure-statement.md#i.-introduction` | oversized-review, legal |
| review-required | 2,080 | A | `v2-protocol:src/market/WildcatMarketBase.sol:WildcatMarketBase._calculateCurrentState()` | oversized-review |
| review-required | 2,078 | A | `v2-protocol:src/lens/MarketData.sol:MarketDataLib.fillState(MarketData)` | oversized-review |
| review-required | 2,068 | B | `wildcat-docs:using-wildcat/day-to-day-usage/borrowers.md#confirmation` | oversized-review |
| review-required | 2,057 | B | `wildcat-docs:legal/master-loan-agreement.md#id-8-transfer-of-title` | oversized-review, legal |
| review-required | 2,026 | B | `wildcat-docs:legal/risk-disclosure-statement.md#ix.-user-responsibility` | oversized-review, legal |
| review-required | 2,012 | A | `v2-protocol:src/market/WildcatMarketToken.sol:WildcatMarketToken#surface` | oversized-review, synthesised |
| review-required | 1,851 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-13.1-general-limitation` | legal |
| review-required | 1,836 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-6.3-market-users-lenders-acknowledgment-of-risk-and-responsibility` | legal |
| review-required | 1,786 | A | `v2-protocol:src/HooksFactory.sol:HooksFactory#surface` | synthesised |
| review-required | 1,717 | B | `wildcat-docs:legal/master-loan-agreement.md#template-mla` | legal, nested-strong-sections |
| review-required | 1,716 | B | `wildcat-docs:legal/master-loan-agreement.md#id-11-governing-law-dispute-resolution` | legal |
| review-required | 1,702 | B | `wildcat-docs:legal/master-loan-agreement.md#id-4-default` | legal |
| review-required | 1,688 | B | `wildcat-docs:legal/master-loan-agreement.md#id-12-third-party-beneficiaries` | legal |
| review-required | 1,685 | B | `wildcat-docs:overview/introduction.md#for-borrowers` | nested-strong-sections |
| review-required | 1,660 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-15.2-arbitration` | legal |
| review-required | 1,655 | B | `wildcat-docs:overview/faqs.md#index` | synthesised |
| review-required | 1,584 | B | `wildcat-docs:legal/protocol-ui-privacy-policy.md#what-personal-data-we-collect` | legal |
| review-required | 1,573 | A | `v2-protocol:docs/EIP-4626.md#conversions-and-rounding` | nested-strong-sections |
| review-required | 1,504 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-13.3-no-liability-for-cyberattacks-or-third-party-malicious-activity` | legal |
| review-required | 1,484 | B | `wildcat-docs:overview/introduction.md#for-lenders` | nested-strong-sections |
| review-required | 1,407 | B | `wildcat-docs:legal/master-loan-agreement.md#h-termination-of-loan` | legal |
| review-required | 1,394 | B | `wildcat-docs:technical-overview/security-developer-dives/wildcat-4626-wrapper.md#preview-functions` | nested-strong-sections |
| review-required | 1,383 | A | `v2-protocol:src/lens/MarketLens.sol:MarketLens#surface` | synthesised |
| review-required | 1,354 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-7.6-sanctioned-persons` | legal |
| review-required | 1,331 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-7.4-geographic-restrictions` | legal |
| review-required | 1,313 | B | `wildcat-docs:technical-overview/function-event-signatures/market/wildcatmarketbase.sol.md#events` | duplicate-content |
| review-required | 1,313 | B | `wildcat-docs:technical-overview/function-event-signatures/market/wildcatmarketconfig.sol.md#events` | duplicate-content |
| review-required | 1,313 | B | `wildcat-docs:technical-overview/function-event-signatures/market/wildcatmarkettoken.sol.md#events` | duplicate-content |
| review-required | 1,313 | B | `wildcat-docs:technical-overview/function-event-signatures/market/wildcatmarketwithdrawals.sol.md#events` | duplicate-content |
| review-required | 1,284 | B | `wildcat-docs:legal/master-loan-agreement.md#index` | legal, synthesised |
| review-required | 1,223 | B | `wildcat-docs:technical-overview/protocol-structs.md#index` | synthesised |
| review-required | 1,188 | B | `wildcat-docs:legal/risk-disclosure-statement.md#v.-technical-risks` | legal |
| review-required | 1,184 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-17.1-termination-by-us` | legal |
| review-required | 1,145 | B | `wildcat-docs:legal/protocol-ui-privacy-policy.md#how-we-share-your-data` | legal |
| review-required | 1,114 | A | `v2-protocol:src/market/WildcatMarketBase.sol:WildcatMarketBase#surface` | synthesised |
| review-required | 1,098 | A | `v2-protocol:lib/solady/src/auth/Ownable.sol:Ownable` | synthesised |
| review-required | 1,062 | B | `wildcat-docs:technical-overview/security-developer-dives/wildcat-4626-wrapper.md#wildcat4626wrapper-1` | nested-strong-sections |
| review-required | 1,050 | B | `wildcat-docs:using-wildcat/terminology.md#index` | synthesised |
| review-required | 1,048 | A | `v2-protocol:docs/Scale Factor.md#typical-token-vaults` | duplicate-content |
| review-required | 1,048 | B | `wildcat-docs:technical-overview/security-developer-dives/the-scale-factor.md#typical-token-vaults` | duplicate-content |
| review-required | 1,019 | A | `v2-protocol:src/HooksFactory.sol:HooksFactory` | synthesised |
| review-required | 976 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-4.2-your-responsibility-to-understand-and-accept-risk-disclosures-policy` | legal |
| review-required | 967 | B | `wildcat-docs:legal/risk-disclosure-statement.md#xii.-assumption-of-risks-and-limitation-of-liability` | legal |
| review-required | 958 | A | `v2-protocol:src/access/FixedTermHooks.sol:FixedTermHooks` | synthesised |
| review-required | 953 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-13.2-maximum-liability` | legal |
| review-required | 915 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-16.2-no-guarantee-of-payment` | legal |
| review-required | 900 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-9.1-ownership-and-license` | legal |
| review-required | 898 | B | `wildcat-docs:legal/risk-disclosure-statement.md#iii.-general-risks` | legal |
| review-required | 891 | B | `wildcat-docs:legal/master-loan-agreement.md#id-17-single-agreement` | legal |
| review-required | 890 | A | `v2-protocol:docs/Terminology.md#index` | synthesised |
| review-required | 889 | B | `wildcat-docs:legal/protocol-ui-privacy-policy.md#international-data-transfers` | legal |
| review-required | 877 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-8.2-prohibited-activities` | legal |
| review-required | 858 | B | `wildcat-docs:legal/risk-disclosure-statement.md#xi.-no-professional-advice-or-fiduciary-duties` | legal |
| review-required | 847 | B | `wildcat-docs:legal/risk-disclosure-statement.md#x.-legal-uncertainty` | legal |
| review-required | 840 | B | `wildcat-docs:technical-overview/security-developer-dives/known-issues.md#index` | synthesised, nested-strong-sections |
| review-required | 831 | A | `v2-protocol:docs/CHANGELOG.md#market-deployment` | nested-strong-sections |
| review-required | 831 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-18.5-force-majeure` | legal |
| review-required | 828 | A | `v2-protocol:src/market/WildcatMarketBase.sol:WildcatMarketBase` | synthesised |
| review-required | 826 | B | `wildcat-docs:legal/risk-disclosure-statement.md#vii.-third-party-risks` | legal |
| review-required | 815 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-13.4-third-party-dependencies` | legal |
| review-required | 808 | A | `v2-protocol:src/spherex/SphereXProtectedRegisteredBase.sol:SphereXProtectedRegisteredBase` | synthesised |
| review-required | 804 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-1.3-incorporation-of-other-terms-and-policies` | legal |
| review-required | 801 | B | `wildcat-docs:using-wildcat/day-to-day-usage/borrowers.md#index` | synthesised |
| review-required | 796 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-5.1-obligations-to-your-users` | legal |
| review-required | 783 | B | `wildcat-docs:legal/protocol-ui-privacy-policy.md#introduction` | legal |
| review-required | 775 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-4.7-assumption-of-risk` | legal |
| review-required | 772 | A | `v2-protocol:src/access/OpenTermHooks.sol:OpenTermHooks` | synthesised |
| review-required | 772 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-12.2-blockchain-data` | legal |
| review-required | 763 | A | `v2-protocol:src/access/BaseAccessControls.sol:BaseAccessControls#surface` | synthesised |
| review-required | 763 | B | `wildcat-docs:legal/master-loan-agreement.md#wildcat-protocol-master-loan-agreement` | legal |
| review-required | 759 | B | `wildcat-docs:legal/protocol-ui-privacy-policy.md#links` | legal |
| review-required | 757 | A | `v2-protocol:src/libraries/LibERC20.sol:LibERC20` | synthesised |
| review-required | 752 | B | `wildcat-docs:using-wildcat/how-borrowers-are-onboarded.md#index` | synthesised |
| review-required | 746 | A | `v2-protocol:src/access/MarketConstraintHooks.sol:MarketConstraintHooks` | synthesised |
| review-required | 728 | B | `wildcat-docs:technical-overview/security-developer-dives/wildcat-4626-wrapper.md#mutating-functions` | nested-strong-sections |
| review-required | 726 | B | `wildcat-docs:technical-overview/security-developer-dives/wildcat-4626-wrapper.md#index` | synthesised |
| review-required | 697 | B | `wildcat-docs:legal/protocol-ui-privacy-policy.md#security` | legal |
| review-required | 689 | A | `v2-protocol:docs/EIP-4626.md#index` | synthesised |
| review-required | 688 | B | `wildcat-docs:legal/master-loan-agreement.md#id-7-alternative-arrangements-in-the-event-of-loss-of-wallet-address-access` | legal |
| review-required | 683 | B | `wildcat-docs:legal/master-loan-agreement.md#id-22-no-waiver` | legal |
| review-required | 644 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-4.1-products-overview` | legal |
| review-required | 644 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-4.5-no-warranties-on-products-or-protocol` | legal |
| review-required | 625 | B | `wildcat-docs:legal/risk-disclosure-statement.md#ii.-experimental-nature` | legal |
| review-required | 608 | B | `wildcat-docs:legal/master-loan-agreement.md#recitals` | legal |
| review-required | 605 | B | `wildcat-docs:legal/risk-disclosure-statement.md#viii.-open-source-and-experimental-technology` | legal |
| review-required | 597 | B | `wildcat-docs:using-wildcat/day-to-day-usage/wildcat-4626-wrapper.md#index` | synthesised |
| review-required | 592 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-4.6-experimental-technology` | legal |
| review-required | 591 | B | `wildcat-docs:technical-overview/security-developer-dives/wildcat-4626-wrapper.md#wildcat4626wrapperfactory` | nested-strong-sections |
| review-required | 586 | B | `wildcat-docs:legal/master-loan-agreement.md#id-9-rights-and-remedies-cumulative` | legal |
| review-required | 581 | B | `wildcat-docs:legal/risk-disclosure-statement.md#index` | legal, synthesised |
| review-required | 578 | B | `wildcat-docs:legal/master-loan-agreement.md#id-16-variation-assignment-successors-and-assigns` | legal |
| review-required | 577 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-6.4-no-control-or-warranties` | legal |
| review-required | 567 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-10.1-transaction-costs` | legal |
| review-required | 566 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-14.2-third-party-enforcement-rights` | legal |
| review-required | 562 | A | `v2-protocol:src/WildcatSanctionsSentinel.sol:WildcatSanctionsSentinel#surface` | synthesised |
| review-required | 559 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-17.2-survival-of-terms` | legal |
| review-required | 557 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-1.1-welcome-and-overview` | legal |
| review-required | 551 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-6.5-no-guarantee-of-performance-or-security` | legal |
| review-required | 548 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-6.1-markets-overview` | legal |
| review-required | 542 | B | `wildcat-docs:legal/master-loan-agreement.md#id-19-partial-invalidity` | legal |
| review-required | 539 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-5.2-indemnification` | legal |
| review-required | 535 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-9.4-responsibility-for-content` | legal |
| review-required | 529 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-10.2-irreversibility-of-transactions` | legal |
| review-required | 526 | A | `v2-protocol:src/spherex/SphereXConfig.sol:SphereXConfig` | synthesised |
| review-required | 518 | B | `wildcat-docs:legal/master-loan-agreement.md#a-general-loan-terms` | legal |
| review-required | 515 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-15.3-class-action-waiver` | legal |
| review-required | 514 | B | `wildcat-docs:legal/master-loan-agreement.md#g-closing-a-market` | legal |
| review-required | 510 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-15.5-limitation-on-time-to-file-claims` | legal |
| review-required | 506 | B | `wildcat-docs:legal/master-loan-agreement.md#id-5-remedies` | legal |
| review-required | 498 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-15.1-governing-law` | legal |
| review-required | 497 | A | `v2-protocol:src/ReentrancyGuard.sol:ReentrancyGuard` | synthesised |
| review-required | 496 | A | `v2-protocol:docs/hooks/templates/Access Control Hooks.md#access-control-hooks` | duplicate-content |
| review-required | 496 | B | `wildcat-docs:technical-overview/security-developer-dives/hooks/access-control-hooks.md#access-control-hooks` | duplicate-content |
| review-required | 494 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-6.6-indemnification` | legal |
| review-required | 491 | B | `wildcat-docs:technical-overview/security-developer-dives/v1-greater-than-v2-changelog.md#index` | synthesised |
| review-required | 487 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-2.1-right-to-modify` | legal |
| review-required | 486 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-16.1-independent-rules` | legal |
| review-required | 485 | A | `v2-protocol:src/WildcatSanctionsSentinel.sol:WildcatSanctionsSentinel` | synthesised |
| review-required | 485 | B | `wildcat-docs:technical-overview/security-developer-dives/core-behaviour.md#index` | synthesised |
| review-required | 481 | B | `wildcat-docs:technical-overview/function-event-signatures/interfaces/iwildcatsanctionssentinel.sol.md#functions` | duplicate-content |
| review-required | 481 | B | `wildcat-docs:technical-overview/function-event-signatures/wildcatsanctionssentinel.sol.md#functions` | duplicate-content |
| review-required | 476 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-15.4-jurisdiction-for-non-arbitrable-disputes` | legal |
| review-required | 472 | B | `wildcat-docs:legal/protocol-ui-privacy-policy.md#retention-of-personal-information` | legal |
| review-required | 472 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-18.2-severability` | legal |
| review-required | 466 | B | `wildcat-docs:security-measures/proving-you-are-an-affected-lender-in-a-default.md#index` | synthesised |
| review-required | 462 | B | `wildcat-docs:legal/master-loan-agreement.md#id-24-miscellaneous` | legal |
| review-required | 456 | B | `wildcat-docs:legal/protocol-ui-privacy-policy.md#how-we-use-cookies` | legal |
| review-required | 455 | B | `wildcat-docs:technical-overview/security-developer-dives/hooks/access-control-hooks.md#index` | synthesised |
| review-required | 440 | B | `wildcat-docs:legal/master-loan-agreement.md#f-withdrawals` | legal |
| review-required | 439 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-18.7-notices` | legal |
| review-required | 426 | A | `v2-protocol:docs/Scale Factor.md#scaled-tokens` | duplicate-content |
| review-required | 426 | B | `wildcat-docs:technical-overview/security-developer-dives/the-scale-factor.md#scaled-tokens` | duplicate-content |
| review-required | 425 | B | `wildcat-docs:legal/protocol-ui-privacy-policy.md#changes-to-the-policy` | legal |
| review-required | 420 | B | `wildcat-docs:legal/protocol-ui-privacy-policy.md#index` | legal, synthesised |
| review-required | 414 | B | `wildcat-docs:security-measures/code-security-reviews.md#index` | synthesised |
| review-required | 405 | B | `wildcat-docs:legal/risk-disclosure-statement.md#xiv.-mitigation-strategies` | legal |
| review-required | 402 | B | `wildcat-docs:technical-overview/security-developer-dives/the-scale-factor.md#index` | synthesised |
| review-required | 400 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-3.1-no-custodial-services` | legal |
| review-required | 398 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-7.3-no-access-from-restricted-jurisdiction` | legal |
| review-required | 386 | B | `wildcat-docs:legal/risk-disclosure-statement.md#xiii.-incident-reporting-and-transparency` | legal |
| review-required | 384 | A | `v2-protocol:src/access/BaseAccessControls.sol:BaseAccessControls` | synthesised |
| review-required | 376 | B | `wildcat-docs:legal/risk-disclosure-statement.md#acknowledgment-of-risks` | legal |
| review-required | 373 | B | `wildcat-docs:legal/master-loan-agreement.md#id-18-entire-agreement` | legal |
| review-required | 369 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-16.4-no-contractual-relationship` | legal |
| review-required | 369 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-18.6-language` | legal |
| review-required | 368 | A | `v2-protocol:src/libraries/FunctionTypeCasts.sol:FunctionTypeCasts` | synthesised |
| review-required | 358 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-4.3-protocol-independence` | legal |
| review-required | 357 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-16.3-limitation-of-liability` | legal |
| review-required | 357 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-3.4-we-are-not-intermediaries` | legal |
| review-required | 355 | B | `wildcat-docs:technical-overview/security-developer-dives/wildcat-4626-wrapper.md#wildcat4626wrapperfactory-1` | nested-strong-sections |
| review-required | 346 | B | `wildcat-docs:legal/protocol-ui-privacy-policy.md#age-limitations` | legal |
| review-required | 335 | B | `wildcat-docs:technical-overview/contract-deployments.md#index` | synthesised |
| review-required | 333 | A | `v2-protocol:src/spherex/ISphereXEngine.sol:ISphereXEngine` | synthesised |
| review-required | 332 | B | `wildcat-docs:technical-overview/security-developer-dives/README.md#index` | synthesised |
| review-required | 315 | A | `v2-protocol:src/WildcatArchController.sol:WildcatArchController` | synthesised |
| review-required | 314 | B | `wildcat-docs:using-wildcat/day-to-day-usage/market-access-via-policies-hooks.md#index` | synthesised |
| review-required | 311 | B | `wildcat-docs:using-wildcat/telegram-notification-bot.md#index` | synthesised |
| review-required | 304 | B | `wildcat-docs:legal/master-loan-agreement.md#e-fixed-term-maturity-amendment` | legal |
| review-required | 304 | B | `wildcat-docs:technical-overview/security-developer-dives/hooks/how-hooks-work.md#index` | synthesised |
| review-required | 299 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-12.1-data-collection` | legal |
| review-required | 296 | B | `wildcat-docs:using-wildcat/day-to-day-usage/optional-collateral-contracts.md#index` | synthesised |
| review-required | 295 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-11.2-restrictions-on-use` | legal |
| review-required | 291 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-8.4-monitoring-and-reporting` | legal |
| review-required | 289 | B | `wildcat-docs:using-wildcat/day-to-day-usage/lenders.md#index` | synthesised |
| review-required | 287 | B | `wildcat-docs:legal/master-loan-agreement.md#id-14-third-party-rights` | legal |
| review-required | 286 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-4.4-user-responsibility` | legal |
| review-required | 286 | B | `wildcat-docs:technical-overview/security-developer-dives/hooks/README.md#index` | synthesised |
| review-required | 285 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-7.1-eligibility-requirements` | legal |
| review-required | 285 | B | `wildcat-docs:using-wildcat/onboarding.md#index` | synthesised |
| review-required | 284 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-18.1-entire-agreement` | legal |
| review-required | 284 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-19-contact-information` | legal |
| review-required | 284 | B | `wildcat-docs:technical-overview/function-event-signatures/spherex/ispherexprotectedregisteredbase.sol.md#index` | synthesised |
| review-required | 280 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-3.2-risks-of-digital-assets` | legal |
| review-required | 278 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-18.3-waiver` | legal |
| review-required | 277 | B | `wildcat-docs:technical-overview/function-event-signatures/market/wildcatmarketwithdrawals.sol.md#index` | synthesised |
| review-required | 274 | B | `wildcat-docs:technical-overview/security-developer-dives/hooks/fixed-term-loan-hooks.md#index` | synthesised |
| review-required | 272 | B | `wildcat-docs:technical-overview/function-event-signatures/interfaces/iwildcatsanctionssentinel.sol.md#index` | synthesised |
| review-required | 271 | B | `wildcat-docs:overview/for-ai-agents.md#index` | synthesised |
| review-required | 269 | B | `wildcat-docs:technical-overview/security-developer-dives/wildcat-4626-wrapper.md#sentinel` | nested-strong-sections |
| review-required | 268 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-1.2-binding-agreement` | legal |
| review-required | 268 | B | `wildcat-docs:technical-overview/function-event-signatures/access/marketconstrainthooks.sol.md#index` | synthesised |
| review-required | 266 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-8.5-cooperation-with-authorities` | legal |
| review-required | 266 | B | `wildcat-docs:technical-overview/function-event-signatures/interfaces/iwildcatsanctionsescrow.sol.md#index` | synthesised |
| review-required | 263 | B | `wildcat-docs:technical-overview/function-event-signatures/interfaces/iwildcatarchcontroller.sol.md#index` | synthesised |
| review-required | 262 | A | `v2-protocol:src/WildcatSanctionsEscrow.sol:WildcatSanctionsEscrow#surface` | synthesised |
| review-required | 262 | B | `wildcat-docs:technical-overview/function-event-signatures/market/wildcatmarketconfig.sol.md#index` | synthesised |
| review-required | 260 | B | `wildcat-docs:legal/master-loan-agreement.md#id-21-no-relationship` | legal |
| review-required | 260 | B | `wildcat-docs:technical-overview/function-event-signatures/wildcatsanctionssentinel.sol.md#index` | synthesised |
| review-required | 259 | B | `wildcat-docs:technical-overview/function-event-signatures/access/accesscontrolhooks.sol.md#index` | synthesised |
| review-required | 259 | B | `wildcat-docs:technical-overview/function-event-signatures/market/wildcatmarkettoken.sol.md#index` | synthesised |
| review-required | 258 | A | `v2-protocol:docs/Core Behavior.md#index` | synthesised |
| review-required | 256 | B | `wildcat-docs:technical-overview/function-event-signatures/interfaces/imarketeventsanderrors.sol.md#index` | synthesised |
| review-required | 256 | B | `wildcat-docs:technical-overview/function-event-signatures/market/wildcatmarketbase.sol.md#index` | synthesised |
| review-required | 254 | B | `wildcat-docs:technical-overview/function-event-signatures/wildcatsanctionsescrow.sol.md#index` | synthesised |
| review-required | 253 | B | `wildcat-docs:using-wildcat/delinquency.md#index` | synthesised |
| review-required | 252 | A | `v2-protocol:docs/hooks/templates/Access Control Hooks.md#index` | synthesised |
| review-required | 251 | B | `wildcat-docs:technical-overview/function-event-signatures/wildcatarchcontroller.sol.md#index` | synthesised |
| review-required | 250 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-7.2-duty-to-disclose` | legal |
| review-required | 246 | B | `wildcat-docs:legal/master-loan-agreement.md#b-base-apr-amendment` | legal |
| review-required | 246 | B | `wildcat-docs:technical-overview/function-event-signatures/spherex/spherexconfig.sol.md#index` | synthesised |
| review-required | 243 | B | `wildcat-docs:using-wildcat/wildcat-market-csv-exporter.md#index` | synthesised |
| review-required | 242 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#acknowledgment` | legal |
| review-required | 240 | B | `wildcat-docs:legal/master-loan-agreement.md#id-23-termination-of-agreement` | legal |
| review-required | 240 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-9.2-prohibited-content` | legal |
| review-required | 239 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-18.4-assignment` | legal |
| review-required | 235 | A | `v2-protocol:src/WildcatSanctionsEscrow.sol:WildcatSanctionsEscrow` | synthesised |
| review-required | 235 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-2.3-retroactive-application` | legal |
| review-required | 235 | B | `wildcat-docs:technical-overview/security-developer-dives/wildcat-4626-wrapper.md#metadata` | nested-strong-sections |
| review-required | 228 | B | `wildcat-docs:legal/master-loan-agreement.md#id-10-survival-of-rights-and-remedies` | legal |
| review-required | 227 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-7.5-sanctioned-jurisdictions` | legal |
| review-required | 226 | B | `wildcat-docs:legal/master-loan-agreement.md#id-15-notices` | legal |
| review-required | 225 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-11.1-ownership` | legal |
| review-required | 224 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-3.3-no-financial-advice` | legal |
| review-required | 224 | B | `wildcat-docs:overview/introduction.md#index` | synthesised |
| review-required | 224 | B | `wildcat-docs:technical-overview/function-event-signatures/hooksfactory.sol.md#index` | synthesised |
| review-required | 223 | B | `wildcat-docs:technical-overview/function-event-signatures/spherex/ispherexengine.sol.md#index` | synthesised |
| review-required | 218 | B | `wildcat-docs:technical-overview/function-event-signatures/access/iroleprovider.sol.md#index` | synthesised |
| review-required | 213 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#wildcat-terms-of-use` | legal |
| review-required | 211 | B | `wildcat-docs:technical-overview/function-event-signatures/ihooksfactory.sol.md#index` | synthesised |
| review-required | 208 | B | `wildcat-docs:technical-overview/function-event-signatures/spherex/README.md#index` | synthesised |
| review-required | 205 | B | `wildcat-docs:technical-overview/function-event-signatures/interfaces/ihooks.sol.md#index` | synthesised |
| review-required | 201 | B | `wildcat-docs:technical-overview/function-event-signatures/access/README.md#index` | synthesised |
| review-required | 199 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-2.2-continued-use` | legal |
| review-required | 198 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-9.3-no-endorsement` | legal |
| review-required | 198 | B | `wildcat-docs:using-wildcat/day-to-day-usage/the-sentinel.md#index` | synthesised |
| review-required | 195 | B | `wildcat-docs:legal/master-loan-agreement.md#id-20-intention-to-be-bound` | legal |
| review-required | 193 | B | `wildcat-docs:technical-overview/function-event-signatures/README.md#index` | synthesised |
| review-required | 193 | B | `wildcat-docs:technical-overview/function-event-signatures/interfaces/README.md#index` | synthesised |
| review-required | 193 | B | `wildcat-docs:technical-overview/function-event-signatures/market/README.md#index` | synthesised |
| review-required | 192 | B | `wildcat-docs:technical-overview/function-event-signatures/interfaces/iwildcatsanctionsescrow.sol.md#functions` | duplicate-content |
| review-required | 192 | B | `wildcat-docs:technical-overview/function-event-signatures/wildcatsanctionsescrow.sol.md#functions` | duplicate-content |
| review-required | 182 | B | `wildcat-docs:security-measures/spherex-protection.md#index` | synthesised |
| review-required | 181 | B | `wildcat-docs:legal/master-loan-agreement.md#c-amount-of-digital-asset-to-be-loaned-amendment` | legal |
| review-required | 181 | B | `wildcat-docs:legal/protocol-ui-privacy-policy.md#acknowledgment-of-risks` | legal |
| review-required | 173 | A | `v2-protocol:README.md#index` | synthesised |
| review-required | 172 | B | `wildcat-docs:overview/whitepaper.md#index` | synthesised |
| review-required | 169 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-8.3-consequences-of-prohibited-use` | legal |
| review-required | 167 | B | `wildcat-docs:using-wildcat/day-to-day-usage/README.md#index` | synthesised |
| review-required | 167 | B | `wildcat-docs:using-wildcat/protocol-usage-fees.md#index` | synthesised |
| review-required | 166 | B | `wildcat-docs:technical-overview/function-event-signatures/interfaces/iwildcatsanctionssentinel.sol.md#events` | duplicate-content |
| review-required | 166 | B | `wildcat-docs:technical-overview/function-event-signatures/wildcatsanctionssentinel.sol.md#events` | duplicate-content |
| review-required | 164 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-8.1-compliance-with-laws` | legal |
| review-required | 156 | B | `wildcat-docs:legal/protocol-ui-privacy-policy.md#contact-information` | legal |
| review-required | 154 | B | `wildcat-docs:security-measures/bug-bounty-program.md#index` | synthesised |
| review-required | 151 | B | `wildcat-docs:legal/master-loan-agreement.md#i-taxes-and-fees` | legal |
| review-required | 150 | B | `wildcat-docs:README.md#index` | synthesised |
| review-required | 146 | B | `wildcat-docs:legal/master-loan-agreement.md#d-minimum-deposit-amendment` | legal |
| review-required | 129 | A | `v2-protocol:docs/Scale Factor.md#index` | synthesised |
| review-required | 126 | A | `v2-protocol:src/lens/MarketLens.sol:MarketLens` | synthesised |
| review-required | 124 | A | `v2-protocol:docs/CHANGELOG.md#index` | synthesised |
| review-required | 120 | A | `v2-protocol:src/market/WildcatMarketToken.sol:WildcatMarketToken` | synthesised |
| review-required | 115 | A | `v2-protocol:src/market/WildcatMarket.sol:WildcatMarket` | synthesised |
| review-required | 78 | A | `v2-protocol:TESTS.md#index` | synthesised |
| review-required | 74 | A | `v2-protocol:EIP-4626_audit_scope.md#index` | synthesised |
| review-required | 74 | A | `v2-protocol:docs/hooks/Hooks.md#index` | synthesised |
| review-required | 74 | A | `v2-protocol:docs/hooks/How Hooks Work.md#index` | synthesised |
| review-required | 63 | B | `wildcat-docs:technical-overview/function-event-signatures/interfaces/iwildcatsanctionsescrow.sol.md#events` | duplicate-content |
| review-required | 63 | B | `wildcat-docs:technical-overview/function-event-signatures/wildcatsanctionsescrow.sol.md#events` | duplicate-content |
| review-required | 60 | A | `v2-protocol:src/IHooksFactory.sol:IHooksFactory` | synthesised |
| review-required | 59 | A | `v2-protocol:src/market/WildcatMarketWithdrawals.sol:WildcatMarketWithdrawals` | synthesised |
| review-required | 55 | A | `v2-protocol:src/access/IHooks.sol:IHooks` | synthesised |
| review-required | 54 | A | `v2-protocol:src/market/WildcatMarketConfig.sol:WildcatMarketConfig` | synthesised |
| review-required | 51 | A | `v2-protocol:docs/README.md#index` | synthesised |
| review-required | 46 | A | `v2-protocol:src/interfaces/ISphereXProtectedRegisteredBase.sol:ISphereXProtectedRegisteredBase` | synthesised |
| review-required | 44 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-15-governing-law-and-dispute-resolution` | legal |
| review-required | 43 | A | `v2-protocol:src/IHooksFactory.sol:IHooksFactoryEventsAndErrors` | synthesised |
| review-required | 42 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-16-bug-bounties-and-security-contests` | legal |
| review-required | 40 | A | `v2-protocol:src/interfaces/IChainalysisSanctionsList.sol:IChainalysisSanctionsList` | synthesised |
| review-required | 40 | A | `v2-protocol:src/interfaces/IWildcatSanctionsSentinel.sol:IWildcatSanctionsSentinel` | synthesised |
| review-required | 38 | A | `v2-protocol:src/interfaces/IWildcatSanctionsEscrow.sol:IWildcatSanctionsEscrow` | synthesised |
| review-required | 37 | A | `v2-protocol:src/interfaces/IMarketEventsAndErrors.sol:IMarketEventsAndErrors` | synthesised |
| review-required | 37 | A | `v2-protocol:src/interfaces/IWildcatArchController.sol:IWildcatArchController` | synthesised |
| review-required | 36 | A | `v2-protocol:src/lens/HooksDataForBorrower.sol:HooksDataForBorrowerLib` | synthesised |
| review-required | 35 | A | `v2-protocol:src/access/IRoleProviderFactory.sol:IRoleProviderFactory` | synthesised |
| review-required | 35 | A | `v2-protocol:src/lens/WithdrawalBatchData.sol:WithdrawalBatchDataLib` | synthesised |
| review-required | 35 | A | `v2-protocol:src/types/TransientBytesArray.sol:LibTransientBytesArray` | synthesised |
| review-required | 33 | A | `v2-protocol:docs/Known Issues.md#index` | synthesised |
| review-required | 33 | A | `v2-protocol:src/lens/HooksInstanceData.sol:HooksInstanceDataLib` | synthesised |
| review-required | 33 | A | `v2-protocol:src/lens/HooksTemplateData.sol:HooksTemplateDataLib` | synthesised |
| review-required | 33 | A | `v2-protocol:src/lens/LenderAccountData.sol:IVersionedContract` | synthesised |
| review-required | 33 | A | `v2-protocol:src/lens/LenderAccountData.sol:LenderAccountDataLib` | synthesised |
| review-required | 32 | A | `v2-protocol:src/lens/RoleProviderData.sol:RoleProviderDataLib` | synthesised |
| review-required | 31 | A | `v2-protocol:src/lens/HooksConfigData.sol:HooksConfigDataLib` | synthesised |
| review-required | 30 | A | `v2-protocol:src/libraries/LibStoredInitCode.sol:LibStoredInitCode` | synthesised |
| review-required | 29 | A | `v2-protocol:src/lens/TokenData.sol:TokenMetadataLib` | synthesised |
| review-required | 28 | A | `v2-protocol:src/access/IRoleProvider.sol:IRoleProvider` | synthesised |
| review-required | 28 | A | `v2-protocol:src/types/LenderStatus.sol:LibLenderStatus` | synthesised |
| review-required | 28 | A | `v2-protocol:src/types/RoleProvider.sol:LibRoleProvider` | synthesised |
| review-required | 27 | A | `v2-protocol:src/libraries/MarketState.sol:MarketStateLib` | synthesised |
| review-required | 26 | A | `v2-protocol:src/lens/MarketData.sol:MarketDataLib` | synthesised |
| review-required | 26 | A | `v2-protocol:src/libraries/Withdrawal.sol:WithdrawalLib` | synthesised |
| review-required | 25 | A | `v2-protocol:src/libraries/FIFOQueue.sol:FIFOQueueLib` | synthesised |
| review-required | 24 | A | `v2-protocol:src/libraries/SafeCastLib.sol:SafeCastLib` | synthesised |
| review-required | 22 | A | `v2-protocol:src/libraries/BoolUtils.sol:BoolUtils` | synthesised |
| review-required | 22 | A | `v2-protocol:src/libraries/MathUtils.sol:MathUtils` | synthesised |
| review-required | 21 | A | `v2-protocol:src/interfaces/IERC20.sol:IERC20` | synthesised |
| review-required | 21 | B | `wildcat-docs:using-wildcat/day-to-day-usage/README.md#document` | whole-document |
| review-required | 20 | A | `v2-protocol:src/libraries/FeeMath.sol:FeeMath` | synthesised |
| review-required | 16 | B | `wildcat-docs:technical-overview/function-event-signatures/interfaces/README.md#document` | whole-document |
| review-required | 13 | B | `wildcat-docs:technical-overview/function-event-signatures/spherex/README.md#document` | whole-document |
| review-required | 12 | B | `wildcat-docs:technical-overview/function-event-signatures/access/README.md#document` | whole-document |
| review-required | 12 | B | `wildcat-docs:technical-overview/function-event-signatures/market/README.md#document` | whole-document |

## Interpretation

This report inventories structure; it does not certify factual truth. 
Legal, synthesised, oversized, duplicate, and whole-document evidence 
stays visible for review even when it is structurally valid. Exact 
duplicates across different sources are reported rather than silently 
removed because authority and provenance differ.
