# Aleph corpus structural audit

Audit `af5810196db35a92` covers all 1,624 chunks 
in corpus payload `8acfa67138fd092240cae101f7f4718c7b2f639ccf09c2bcaf0d1adde747a851`.

## Dispositions

- **auto-pass**: 1,276
- **reviewed-pass**: 348

`auto-pass` means an explicit structural rule covers the chunk. 
`review-required` identifies material that needs a recorded 
classification. `reviewed-pass` is bound to the exact corpus and base 
audit by a disposition ledger. `blocked` is release-stopping.

## Findings

- **duplicate-content**: 18
- **legal**: 144
- **nested-strong-sections**: 15
- **oversized-review**: 57
- **synthesised**: 145

## Review queue

| Disposition | Model chars | Tier | Source | Findings |
| --- | ---: | --- | --- | --- |
| reviewed-pass | 9,524 | B | `wildcat-docs:legal/master-loan-agreement.md#id-1-definitions` | oversized-review, legal |
| reviewed-pass | 6,000 | B | `wildcat-docs:using-wildcat/day-to-day-usage/lenders.md#making-deposits` | oversized-review |
| reviewed-pass | 5,822 | A | `v2-protocol:docs/Scale Factor.md#wildcat-markets` | oversized-review, nested-strong-sections |
| reviewed-pass | 5,062 | A | `v2-protocol:src/types/HooksConfig.sol:LibHooksConfig` | oversized-review, synthesised |
| reviewed-pass | 4,637 | B | `wildcat-docs:legal/protocol-ui-privacy-policy.md#types-of-cookies` | oversized-review, legal |
| reviewed-pass | 4,296 | B | `wildcat-docs:using-wildcat/day-to-day-usage/lenders.md#expired-claims-and-the-withdrawal-queue` | oversized-review |
| reviewed-pass | 3,822 | B | `wildcat-docs:legal/master-loan-agreement.md#id-3-representations-warranties-and-covenants` | oversized-review, legal |
| reviewed-pass | 3,793 | B | `wildcat-docs:using-wildcat/day-to-day-usage/market-access-via-policies-hooks.md#market-access-via-policies-hooks` | oversized-review |
| reviewed-pass | 3,687 | A | `v2-protocol:src/market/WildcatMarket.sol:WildcatMarket#surface` | oversized-review, synthesised |
| reviewed-pass | 3,684 | B | `wildcat-docs:legal/master-loan-agreement.md#term-sheet` | oversized-review, legal |
| reviewed-pass | 3,636 | A | `v2-protocol:src/access/MarketConstraintHooks.sol:MarketConstraintHooks.onSetAnnualInterestAndReserveRatioBips(uint16,uint16,MarketState,bytes)` | oversized-review |
| reviewed-pass | 3,130 | A | `v2-protocol:src/HooksFactory.sol:HooksFactory._deployMarket(DeployMarketInputs,bytes,address,HooksTemplate,bytes32,address,uint256)` | oversized-review |
| reviewed-pass | 3,060 | B | `wildcat-docs:technical-overview/security-developer-dives/the-scale-factor.md#rebasing-with-interest` | oversized-review |
| reviewed-pass | 2,953 | A | `v2-protocol:src/access/FixedTermHooks.sol:FixedTermHooks._onCreateMarket(address,address,DeployMarketInputs,bytes)` | oversized-review |
| reviewed-pass | 2,927 | B | `wildcat-docs:using-wildcat/delinquency.md#unclaimed-pending-withdrawals-and-delinquency` | oversized-review |
| reviewed-pass | 2,910 | B | `wildcat-docs:legal/protocol-ui-privacy-policy.md#how-we-use-your-data` | oversized-review, legal |
| reviewed-pass | 2,876 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#index` | oversized-review, legal, synthesised |
| reviewed-pass | 2,835 | B | `wildcat-docs:technical-overview/security-developer-dives/hooks/access-control-hooks.md#tryvalidateaccess-address-lender-bytes-hooksdata` | oversized-review |
| reviewed-pass | 2,738 | A | `v2-protocol:src/market/WildcatMarket.sol:WildcatMarket.closeMarket()` | oversized-review |
| reviewed-pass | 2,706 | B | `wildcat-docs:using-wildcat/telegram-notification-bot.md#command-reference` | oversized-review |
| reviewed-pass | 2,702 | B | `wildcat-docs:legal/master-loan-agreement.md#id-6-limitations-on-liability` | oversized-review, legal |
| reviewed-pass | 2,673 | B | `wildcat-docs:legal/risk-disclosure-statement.md#iv.-security-risks` | oversized-review, legal |
| reviewed-pass | 2,623 | A | `v2-protocol:src/access/BaseAccessControls.sol:BaseAccessControls._tryValidateCredential(LenderStatus,address,bytes)` | oversized-review |
| reviewed-pass | 2,540 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-14.1-user-responsibility` | oversized-review, legal |
| reviewed-pass | 2,536 | B | `wildcat-docs:technical-overview/function-event-signatures/access/accesscontrolhooks.sol.md#functions` | oversized-review |
| reviewed-pass | 2,524 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-6.2-market-deployers-borrowers-responsibility-and-liability` | oversized-review, legal |
| reviewed-pass | 2,519 | A | `v2-protocol:src/access/FixedTermHooks.sol:FixedTermHooks#surface` | oversized-review, synthesised |
| reviewed-pass | 2,516 | A | `v2-protocol:docs/hooks/templates/Access Control Hooks.md#tryvalidateaccess-address-lender-bytes-hooksdata` | oversized-review |
| reviewed-pass | 2,423 | A | `v2-protocol:src/access/OpenTermHooks.sol:OpenTermHooks#surface` | oversized-review, synthesised |
| reviewed-pass | 2,414 | B | `wildcat-docs:using-wildcat/how-borrowers-are-onboarded.md#how-the-check-verifies-it` | oversized-review |
| reviewed-pass | 2,386 | B | `wildcat-docs:technical-overview/contract-deployments.md#sepolia-testnet-v1-components-of-pre-audited-v2` | oversized-review |
| reviewed-pass | 2,340 | A | `v2-protocol:src/market/WildcatMarketBase.sol:WildcatMarketBase._getUpdatedState()` | oversized-review |
| reviewed-pass | 2,330 | A | `v2-protocol:src/spherex/SphereXProtectedRegisteredBase.sol:SphereXProtectedRegisteredBase._getStorageSlotsAndPreparePostCalldata(int256)` | oversized-review |
| reviewed-pass | 2,329 | A | `v2-protocol:docs/CHANGELOG.md#market` | oversized-review, nested-strong-sections |
| reviewed-pass | 2,313 | A | `v2-protocol:src/types/HooksConfig.sol:LibHooksConfig.onSetAnnualInterestAndReserveRatioBips(HooksConfig,uint16,uint16,MarketState)` | oversized-review |
| reviewed-pass | 2,305 | A | `v2-protocol:src/market/WildcatMarketBase.sol:WildcatMarketBase._writeState(MarketState)` | oversized-review |
| reviewed-pass | 2,304 | A | `v2-protocol:docs/hooks/How Hooks Work.md#how-hooks-work` | oversized-review |
| reviewed-pass | 2,269 | A | `v2-protocol:EIP-4626_audit_scope.md#summary` | oversized-review |
| reviewed-pass | 2,251 | B | `wildcat-docs:using-wildcat/day-to-day-usage/borrowers.md#borrowing-from-a-market` | oversized-review |
| reviewed-pass | 2,244 | B | `wildcat-docs:using-wildcat/day-to-day-usage/borrowers.md#reducing-apr` | oversized-review |
| reviewed-pass | 2,242 | B | `wildcat-docs:using-wildcat/day-to-day-usage/lenders.md#making-withdrawals` | oversized-review |
| reviewed-pass | 2,235 | A | `v2-protocol:src/access/OpenTermHooks.sol:OpenTermHooks._onCreateMarket(address,address,DeployMarketInputs,bytes)` | oversized-review |
| reviewed-pass | 2,234 | B | `wildcat-docs:technical-overview/contract-deployments.md#mainnet` | oversized-review |
| reviewed-pass | 2,207 | A | `v2-protocol:src/market/WildcatMarketWithdrawals.sol:WildcatMarketWithdrawals#surface` | oversized-review, synthesised |
| reviewed-pass | 2,184 | A | `v2-protocol:src/WildcatArchController.sol:WildcatArchController#surface` | oversized-review, synthesised |
| reviewed-pass | 2,151 | B | `wildcat-docs:legal/master-loan-agreement.md#id-13-treatment-of-sanctioned-entities` | oversized-review, legal |
| reviewed-pass | 2,108 | B | `wildcat-docs:security-measures/spherex-protection.md#spherex-protection` | oversized-review |
| reviewed-pass | 2,104 | A | `v2-protocol:src/market/WildcatMarketConfig.sol:WildcatMarketConfig#surface` | oversized-review, synthesised |
| reviewed-pass | 2,098 | B | `wildcat-docs:legal/risk-disclosure-statement.md#vi.-protocol-specific-risks` | oversized-review, legal |
| reviewed-pass | 2,096 | B | `wildcat-docs:using-wildcat/day-to-day-usage/lenders.md#claiming` | oversized-review |
| reviewed-pass | 2,091 | B | `wildcat-docs:legal/risk-disclosure-statement.md#i.-introduction` | oversized-review, legal |
| reviewed-pass | 2,080 | A | `v2-protocol:src/market/WildcatMarketBase.sol:WildcatMarketBase._calculateCurrentState()` | oversized-review |
| reviewed-pass | 2,078 | A | `v2-protocol:src/lens/MarketData.sol:MarketDataLib.fillState(MarketData)` | oversized-review |
| reviewed-pass | 2,068 | B | `wildcat-docs:using-wildcat/day-to-day-usage/borrowers.md#confirmation` | oversized-review |
| reviewed-pass | 2,057 | B | `wildcat-docs:legal/master-loan-agreement.md#id-8-transfer-of-title` | oversized-review, legal |
| reviewed-pass | 2,026 | B | `wildcat-docs:legal/risk-disclosure-statement.md#ix.-user-responsibility` | oversized-review, legal |
| reviewed-pass | 2,012 | A | `v2-protocol:src/market/WildcatMarketToken.sol:WildcatMarketToken#surface` | oversized-review, synthesised |
| reviewed-pass | 1,851 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-13.1-general-limitation` | legal |
| reviewed-pass | 1,836 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-6.3-market-users-lenders-acknowledgment-of-risk-and-responsibility` | legal |
| reviewed-pass | 1,786 | A | `v2-protocol:src/HooksFactory.sol:HooksFactory#surface` | synthesised |
| reviewed-pass | 1,717 | B | `wildcat-docs:legal/master-loan-agreement.md#template-mla` | legal, nested-strong-sections |
| reviewed-pass | 1,716 | B | `wildcat-docs:legal/master-loan-agreement.md#id-11-governing-law-dispute-resolution` | legal |
| reviewed-pass | 1,702 | B | `wildcat-docs:legal/master-loan-agreement.md#id-4-default` | legal |
| reviewed-pass | 1,688 | B | `wildcat-docs:legal/master-loan-agreement.md#id-12-third-party-beneficiaries` | legal |
| reviewed-pass | 1,685 | B | `wildcat-docs:overview/introduction.md#for-borrowers` | nested-strong-sections |
| reviewed-pass | 1,660 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-15.2-arbitration` | legal |
| reviewed-pass | 1,655 | B | `wildcat-docs:overview/faqs.md#index` | synthesised |
| reviewed-pass | 1,584 | B | `wildcat-docs:legal/protocol-ui-privacy-policy.md#what-personal-data-we-collect` | legal |
| reviewed-pass | 1,573 | A | `v2-protocol:docs/EIP-4626.md#conversions-and-rounding` | nested-strong-sections |
| reviewed-pass | 1,504 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-13.3-no-liability-for-cyberattacks-or-third-party-malicious-activity` | legal |
| reviewed-pass | 1,484 | B | `wildcat-docs:overview/introduction.md#for-lenders` | nested-strong-sections |
| reviewed-pass | 1,407 | B | `wildcat-docs:legal/master-loan-agreement.md#h-termination-of-loan` | legal |
| reviewed-pass | 1,394 | B | `wildcat-docs:technical-overview/security-developer-dives/wildcat-4626-wrapper.md#preview-functions` | nested-strong-sections |
| reviewed-pass | 1,383 | A | `v2-protocol:src/lens/MarketLens.sol:MarketLens#surface` | synthesised |
| reviewed-pass | 1,354 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-7.6-sanctioned-persons` | legal |
| reviewed-pass | 1,331 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-7.4-geographic-restrictions` | legal |
| reviewed-pass | 1,313 | B | `wildcat-docs:technical-overview/function-event-signatures/market/wildcatmarketbase.sol.md#events` | duplicate-content |
| reviewed-pass | 1,313 | B | `wildcat-docs:technical-overview/function-event-signatures/market/wildcatmarketconfig.sol.md#events` | duplicate-content |
| reviewed-pass | 1,313 | B | `wildcat-docs:technical-overview/function-event-signatures/market/wildcatmarkettoken.sol.md#events` | duplicate-content |
| reviewed-pass | 1,313 | B | `wildcat-docs:technical-overview/function-event-signatures/market/wildcatmarketwithdrawals.sol.md#events` | duplicate-content |
| reviewed-pass | 1,284 | B | `wildcat-docs:legal/master-loan-agreement.md#index` | legal, synthesised |
| reviewed-pass | 1,223 | B | `wildcat-docs:technical-overview/protocol-structs.md#index` | synthesised |
| reviewed-pass | 1,188 | B | `wildcat-docs:legal/risk-disclosure-statement.md#v.-technical-risks` | legal |
| reviewed-pass | 1,184 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-17.1-termination-by-us` | legal |
| reviewed-pass | 1,145 | B | `wildcat-docs:legal/protocol-ui-privacy-policy.md#how-we-share-your-data` | legal |
| reviewed-pass | 1,114 | A | `v2-protocol:src/market/WildcatMarketBase.sol:WildcatMarketBase#surface` | synthesised |
| reviewed-pass | 1,098 | A | `v2-protocol:lib/solady/src/auth/Ownable.sol:Ownable` | synthesised |
| reviewed-pass | 1,062 | B | `wildcat-docs:technical-overview/security-developer-dives/wildcat-4626-wrapper.md#wildcat4626wrapper-1` | nested-strong-sections |
| reviewed-pass | 1,050 | B | `wildcat-docs:using-wildcat/terminology.md#index` | synthesised |
| reviewed-pass | 1,048 | A | `v2-protocol:docs/Scale Factor.md#typical-token-vaults` | duplicate-content |
| reviewed-pass | 1,048 | B | `wildcat-docs:technical-overview/security-developer-dives/the-scale-factor.md#typical-token-vaults` | duplicate-content |
| reviewed-pass | 1,019 | A | `v2-protocol:src/HooksFactory.sol:HooksFactory` | synthesised |
| reviewed-pass | 976 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-4.2-your-responsibility-to-understand-and-accept-risk-disclosures-policy` | legal |
| reviewed-pass | 967 | B | `wildcat-docs:legal/risk-disclosure-statement.md#xii.-assumption-of-risks-and-limitation-of-liability` | legal |
| reviewed-pass | 958 | A | `v2-protocol:src/access/FixedTermHooks.sol:FixedTermHooks` | synthesised |
| reviewed-pass | 953 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-13.2-maximum-liability` | legal |
| reviewed-pass | 915 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-16.2-no-guarantee-of-payment` | legal |
| reviewed-pass | 900 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-9.1-ownership-and-license` | legal |
| reviewed-pass | 898 | B | `wildcat-docs:legal/risk-disclosure-statement.md#iii.-general-risks` | legal |
| reviewed-pass | 891 | B | `wildcat-docs:legal/master-loan-agreement.md#id-17-single-agreement` | legal |
| reviewed-pass | 890 | A | `v2-protocol:docs/Terminology.md#index` | synthesised |
| reviewed-pass | 889 | B | `wildcat-docs:legal/protocol-ui-privacy-policy.md#international-data-transfers` | legal |
| reviewed-pass | 877 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-8.2-prohibited-activities` | legal |
| reviewed-pass | 858 | B | `wildcat-docs:legal/risk-disclosure-statement.md#xi.-no-professional-advice-or-fiduciary-duties` | legal |
| reviewed-pass | 847 | B | `wildcat-docs:legal/risk-disclosure-statement.md#x.-legal-uncertainty` | legal |
| reviewed-pass | 840 | B | `wildcat-docs:technical-overview/security-developer-dives/known-issues.md#index` | synthesised, nested-strong-sections |
| reviewed-pass | 831 | A | `v2-protocol:docs/CHANGELOG.md#market-deployment` | nested-strong-sections |
| reviewed-pass | 831 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-18.5-force-majeure` | legal |
| reviewed-pass | 828 | A | `v2-protocol:src/market/WildcatMarketBase.sol:WildcatMarketBase` | synthesised |
| reviewed-pass | 826 | B | `wildcat-docs:legal/risk-disclosure-statement.md#vii.-third-party-risks` | legal |
| reviewed-pass | 815 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-13.4-third-party-dependencies` | legal |
| reviewed-pass | 808 | A | `v2-protocol:src/spherex/SphereXProtectedRegisteredBase.sol:SphereXProtectedRegisteredBase` | synthesised |
| reviewed-pass | 804 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-1.3-incorporation-of-other-terms-and-policies` | legal |
| reviewed-pass | 801 | B | `wildcat-docs:using-wildcat/day-to-day-usage/borrowers.md#index` | synthesised |
| reviewed-pass | 796 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-5.1-obligations-to-your-users` | legal |
| reviewed-pass | 783 | B | `wildcat-docs:legal/protocol-ui-privacy-policy.md#introduction` | legal |
| reviewed-pass | 775 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-4.7-assumption-of-risk` | legal |
| reviewed-pass | 772 | A | `v2-protocol:src/access/OpenTermHooks.sol:OpenTermHooks` | synthesised |
| reviewed-pass | 772 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-12.2-blockchain-data` | legal |
| reviewed-pass | 763 | A | `v2-protocol:src/access/BaseAccessControls.sol:BaseAccessControls#surface` | synthesised |
| reviewed-pass | 763 | B | `wildcat-docs:legal/master-loan-agreement.md#wildcat-protocol-master-loan-agreement` | legal |
| reviewed-pass | 759 | B | `wildcat-docs:legal/protocol-ui-privacy-policy.md#links` | legal |
| reviewed-pass | 757 | A | `v2-protocol:src/libraries/LibERC20.sol:LibERC20` | synthesised |
| reviewed-pass | 752 | B | `wildcat-docs:using-wildcat/how-borrowers-are-onboarded.md#index` | synthesised |
| reviewed-pass | 746 | A | `v2-protocol:src/access/MarketConstraintHooks.sol:MarketConstraintHooks` | synthesised |
| reviewed-pass | 728 | B | `wildcat-docs:technical-overview/security-developer-dives/wildcat-4626-wrapper.md#mutating-functions` | nested-strong-sections |
| reviewed-pass | 726 | B | `wildcat-docs:technical-overview/security-developer-dives/wildcat-4626-wrapper.md#index` | synthesised |
| reviewed-pass | 697 | B | `wildcat-docs:legal/protocol-ui-privacy-policy.md#security` | legal |
| reviewed-pass | 689 | A | `v2-protocol:docs/EIP-4626.md#index` | synthesised |
| reviewed-pass | 688 | B | `wildcat-docs:legal/master-loan-agreement.md#id-7-alternative-arrangements-in-the-event-of-loss-of-wallet-address-access` | legal |
| reviewed-pass | 683 | B | `wildcat-docs:legal/master-loan-agreement.md#id-22-no-waiver` | legal |
| reviewed-pass | 644 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-4.1-products-overview` | legal |
| reviewed-pass | 644 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-4.5-no-warranties-on-products-or-protocol` | legal |
| reviewed-pass | 625 | B | `wildcat-docs:legal/risk-disclosure-statement.md#ii.-experimental-nature` | legal |
| reviewed-pass | 608 | B | `wildcat-docs:legal/master-loan-agreement.md#recitals` | legal |
| reviewed-pass | 605 | B | `wildcat-docs:legal/risk-disclosure-statement.md#viii.-open-source-and-experimental-technology` | legal |
| reviewed-pass | 597 | B | `wildcat-docs:using-wildcat/day-to-day-usage/wildcat-4626-wrapper.md#index` | synthesised |
| reviewed-pass | 592 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-4.6-experimental-technology` | legal |
| reviewed-pass | 591 | B | `wildcat-docs:technical-overview/security-developer-dives/wildcat-4626-wrapper.md#wildcat4626wrapperfactory` | nested-strong-sections |
| reviewed-pass | 586 | B | `wildcat-docs:legal/master-loan-agreement.md#id-9-rights-and-remedies-cumulative` | legal |
| reviewed-pass | 581 | B | `wildcat-docs:legal/risk-disclosure-statement.md#index` | legal, synthesised |
| reviewed-pass | 578 | B | `wildcat-docs:legal/master-loan-agreement.md#id-16-variation-assignment-successors-and-assigns` | legal |
| reviewed-pass | 577 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-6.4-no-control-or-warranties` | legal |
| reviewed-pass | 567 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-10.1-transaction-costs` | legal |
| reviewed-pass | 566 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-14.2-third-party-enforcement-rights` | legal |
| reviewed-pass | 562 | A | `v2-protocol:src/WildcatSanctionsSentinel.sol:WildcatSanctionsSentinel#surface` | synthesised |
| reviewed-pass | 559 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-17.2-survival-of-terms` | legal |
| reviewed-pass | 557 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-1.1-welcome-and-overview` | legal |
| reviewed-pass | 551 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-6.5-no-guarantee-of-performance-or-security` | legal |
| reviewed-pass | 548 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-6.1-markets-overview` | legal |
| reviewed-pass | 542 | B | `wildcat-docs:legal/master-loan-agreement.md#id-19-partial-invalidity` | legal |
| reviewed-pass | 539 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-5.2-indemnification` | legal |
| reviewed-pass | 535 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-9.4-responsibility-for-content` | legal |
| reviewed-pass | 529 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-10.2-irreversibility-of-transactions` | legal |
| reviewed-pass | 526 | A | `v2-protocol:src/spherex/SphereXConfig.sol:SphereXConfig` | synthesised |
| reviewed-pass | 518 | B | `wildcat-docs:legal/master-loan-agreement.md#a-general-loan-terms` | legal |
| reviewed-pass | 515 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-15.3-class-action-waiver` | legal |
| reviewed-pass | 514 | B | `wildcat-docs:legal/master-loan-agreement.md#g-closing-a-market` | legal |
| reviewed-pass | 510 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-15.5-limitation-on-time-to-file-claims` | legal |
| reviewed-pass | 506 | B | `wildcat-docs:legal/master-loan-agreement.md#id-5-remedies` | legal |
| reviewed-pass | 498 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-15.1-governing-law` | legal |
| reviewed-pass | 497 | A | `v2-protocol:src/ReentrancyGuard.sol:ReentrancyGuard` | synthesised |
| reviewed-pass | 496 | A | `v2-protocol:docs/hooks/templates/Access Control Hooks.md#access-control-hooks` | duplicate-content |
| reviewed-pass | 496 | B | `wildcat-docs:technical-overview/security-developer-dives/hooks/access-control-hooks.md#access-control-hooks` | duplicate-content |
| reviewed-pass | 494 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-6.6-indemnification` | legal |
| reviewed-pass | 491 | B | `wildcat-docs:technical-overview/security-developer-dives/v1-greater-than-v2-changelog.md#index` | synthesised |
| reviewed-pass | 487 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-2.1-right-to-modify` | legal |
| reviewed-pass | 486 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-16.1-independent-rules` | legal |
| reviewed-pass | 485 | A | `v2-protocol:src/WildcatSanctionsSentinel.sol:WildcatSanctionsSentinel` | synthesised |
| reviewed-pass | 485 | B | `wildcat-docs:technical-overview/security-developer-dives/core-behaviour.md#index` | synthesised |
| reviewed-pass | 481 | B | `wildcat-docs:technical-overview/function-event-signatures/interfaces/iwildcatsanctionssentinel.sol.md#functions` | duplicate-content |
| reviewed-pass | 481 | B | `wildcat-docs:technical-overview/function-event-signatures/wildcatsanctionssentinel.sol.md#functions` | duplicate-content |
| reviewed-pass | 476 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-15.4-jurisdiction-for-non-arbitrable-disputes` | legal |
| reviewed-pass | 476 | B | `wildcat-docs:using-wildcat/wildcat-market-csv-exporter.md#index` | synthesised |
| reviewed-pass | 472 | B | `wildcat-docs:legal/protocol-ui-privacy-policy.md#retention-of-personal-information` | legal |
| reviewed-pass | 472 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-18.2-severability` | legal |
| reviewed-pass | 466 | B | `wildcat-docs:security-measures/proving-you-are-an-affected-lender-in-a-default.md#index` | synthesised |
| reviewed-pass | 462 | B | `wildcat-docs:legal/master-loan-agreement.md#id-24-miscellaneous` | legal |
| reviewed-pass | 456 | B | `wildcat-docs:legal/protocol-ui-privacy-policy.md#how-we-use-cookies` | legal |
| reviewed-pass | 455 | B | `wildcat-docs:technical-overview/security-developer-dives/hooks/access-control-hooks.md#index` | synthesised |
| reviewed-pass | 440 | B | `wildcat-docs:legal/master-loan-agreement.md#f-withdrawals` | legal |
| reviewed-pass | 439 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-18.7-notices` | legal |
| reviewed-pass | 426 | A | `v2-protocol:docs/Scale Factor.md#scaled-tokens` | duplicate-content |
| reviewed-pass | 426 | B | `wildcat-docs:technical-overview/security-developer-dives/the-scale-factor.md#scaled-tokens` | duplicate-content |
| reviewed-pass | 425 | B | `wildcat-docs:legal/protocol-ui-privacy-policy.md#changes-to-the-policy` | legal |
| reviewed-pass | 420 | B | `wildcat-docs:legal/protocol-ui-privacy-policy.md#index` | legal, synthesised |
| reviewed-pass | 414 | B | `wildcat-docs:security-measures/code-security-reviews.md#index` | synthesised |
| reviewed-pass | 405 | B | `wildcat-docs:legal/risk-disclosure-statement.md#xiv.-mitigation-strategies` | legal |
| reviewed-pass | 402 | B | `wildcat-docs:technical-overview/security-developer-dives/the-scale-factor.md#index` | synthesised |
| reviewed-pass | 400 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-3.1-no-custodial-services` | legal |
| reviewed-pass | 398 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-7.3-no-access-from-restricted-jurisdiction` | legal |
| reviewed-pass | 386 | B | `wildcat-docs:legal/risk-disclosure-statement.md#xiii.-incident-reporting-and-transparency` | legal |
| reviewed-pass | 384 | A | `v2-protocol:src/access/BaseAccessControls.sol:BaseAccessControls` | synthesised |
| reviewed-pass | 376 | B | `wildcat-docs:legal/risk-disclosure-statement.md#acknowledgment-of-risks` | legal |
| reviewed-pass | 373 | B | `wildcat-docs:legal/master-loan-agreement.md#id-18-entire-agreement` | legal |
| reviewed-pass | 369 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-16.4-no-contractual-relationship` | legal |
| reviewed-pass | 369 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-18.6-language` | legal |
| reviewed-pass | 368 | A | `v2-protocol:docs/Known Issues.md#index` | synthesised |
| reviewed-pass | 368 | A | `v2-protocol:src/libraries/FunctionTypeCasts.sol:FunctionTypeCasts` | synthesised |
| reviewed-pass | 358 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-4.3-protocol-independence` | legal |
| reviewed-pass | 357 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-16.3-limitation-of-liability` | legal |
| reviewed-pass | 357 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-3.4-we-are-not-intermediaries` | legal |
| reviewed-pass | 355 | B | `wildcat-docs:technical-overview/security-developer-dives/wildcat-4626-wrapper.md#wildcat4626wrapperfactory-1` | nested-strong-sections |
| reviewed-pass | 346 | B | `wildcat-docs:legal/protocol-ui-privacy-policy.md#age-limitations` | legal |
| reviewed-pass | 335 | B | `wildcat-docs:technical-overview/contract-deployments.md#index` | synthesised |
| reviewed-pass | 333 | A | `v2-protocol:src/spherex/ISphereXEngine.sol:ISphereXEngine` | synthesised |
| reviewed-pass | 332 | B | `wildcat-docs:technical-overview/security-developer-dives/README.md#index` | synthesised |
| reviewed-pass | 315 | A | `v2-protocol:src/WildcatArchController.sol:WildcatArchController` | synthesised |
| reviewed-pass | 314 | B | `wildcat-docs:using-wildcat/day-to-day-usage/market-access-via-policies-hooks.md#index` | synthesised |
| reviewed-pass | 311 | B | `wildcat-docs:using-wildcat/telegram-notification-bot.md#index` | synthesised |
| reviewed-pass | 304 | B | `wildcat-docs:legal/master-loan-agreement.md#e-fixed-term-maturity-amendment` | legal |
| reviewed-pass | 304 | B | `wildcat-docs:technical-overview/security-developer-dives/hooks/how-hooks-work.md#index` | synthesised |
| reviewed-pass | 299 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-12.1-data-collection` | legal |
| reviewed-pass | 296 | B | `wildcat-docs:using-wildcat/day-to-day-usage/optional-collateral-contracts.md#index` | synthesised |
| reviewed-pass | 295 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-11.2-restrictions-on-use` | legal |
| reviewed-pass | 291 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-8.4-monitoring-and-reporting` | legal |
| reviewed-pass | 289 | B | `wildcat-docs:using-wildcat/day-to-day-usage/lenders.md#index` | synthesised |
| reviewed-pass | 287 | B | `wildcat-docs:legal/master-loan-agreement.md#id-14-third-party-rights` | legal |
| reviewed-pass | 286 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-4.4-user-responsibility` | legal |
| reviewed-pass | 286 | B | `wildcat-docs:technical-overview/security-developer-dives/hooks/README.md#index` | synthesised |
| reviewed-pass | 285 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-7.1-eligibility-requirements` | legal |
| reviewed-pass | 285 | B | `wildcat-docs:using-wildcat/onboarding.md#index` | synthesised |
| reviewed-pass | 284 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-18.1-entire-agreement` | legal |
| reviewed-pass | 284 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-19-contact-information` | legal |
| reviewed-pass | 284 | B | `wildcat-docs:technical-overview/function-event-signatures/spherex/ispherexprotectedregisteredbase.sol.md#index` | synthesised |
| reviewed-pass | 280 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-3.2-risks-of-digital-assets` | legal |
| reviewed-pass | 278 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-18.3-waiver` | legal |
| reviewed-pass | 277 | B | `wildcat-docs:technical-overview/function-event-signatures/market/wildcatmarketwithdrawals.sol.md#index` | synthesised |
| reviewed-pass | 274 | B | `wildcat-docs:technical-overview/security-developer-dives/hooks/fixed-term-loan-hooks.md#index` | synthesised |
| reviewed-pass | 272 | B | `wildcat-docs:technical-overview/function-event-signatures/interfaces/iwildcatsanctionssentinel.sol.md#index` | synthesised |
| reviewed-pass | 271 | B | `wildcat-docs:overview/for-ai-agents.md#index` | synthesised |
| reviewed-pass | 269 | B | `wildcat-docs:technical-overview/security-developer-dives/wildcat-4626-wrapper.md#sentinel` | nested-strong-sections |
| reviewed-pass | 268 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-1.2-binding-agreement` | legal |
| reviewed-pass | 268 | B | `wildcat-docs:technical-overview/function-event-signatures/access/marketconstrainthooks.sol.md#index` | synthesised |
| reviewed-pass | 266 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-8.5-cooperation-with-authorities` | legal |
| reviewed-pass | 266 | B | `wildcat-docs:technical-overview/function-event-signatures/interfaces/iwildcatsanctionsescrow.sol.md#index` | synthesised |
| reviewed-pass | 263 | B | `wildcat-docs:technical-overview/function-event-signatures/interfaces/iwildcatarchcontroller.sol.md#index` | synthesised |
| reviewed-pass | 262 | A | `v2-protocol:src/WildcatSanctionsEscrow.sol:WildcatSanctionsEscrow#surface` | synthesised |
| reviewed-pass | 262 | B | `wildcat-docs:technical-overview/function-event-signatures/market/wildcatmarketconfig.sol.md#index` | synthesised |
| reviewed-pass | 260 | B | `wildcat-docs:legal/master-loan-agreement.md#id-21-no-relationship` | legal |
| reviewed-pass | 260 | B | `wildcat-docs:technical-overview/function-event-signatures/wildcatsanctionssentinel.sol.md#index` | synthesised |
| reviewed-pass | 259 | B | `wildcat-docs:technical-overview/function-event-signatures/access/accesscontrolhooks.sol.md#index` | synthesised |
| reviewed-pass | 259 | B | `wildcat-docs:technical-overview/function-event-signatures/market/wildcatmarkettoken.sol.md#index` | synthesised |
| reviewed-pass | 258 | A | `v2-protocol:docs/Core Behavior.md#index` | synthesised |
| reviewed-pass | 256 | B | `wildcat-docs:technical-overview/function-event-signatures/interfaces/imarketeventsanderrors.sol.md#index` | synthesised |
| reviewed-pass | 256 | B | `wildcat-docs:technical-overview/function-event-signatures/market/wildcatmarketbase.sol.md#index` | synthesised |
| reviewed-pass | 254 | B | `wildcat-docs:technical-overview/function-event-signatures/wildcatsanctionsescrow.sol.md#index` | synthesised |
| reviewed-pass | 253 | B | `wildcat-docs:using-wildcat/delinquency.md#index` | synthesised |
| reviewed-pass | 252 | A | `v2-protocol:docs/hooks/templates/Access Control Hooks.md#index` | synthesised |
| reviewed-pass | 251 | B | `wildcat-docs:technical-overview/function-event-signatures/wildcatarchcontroller.sol.md#index` | synthesised |
| reviewed-pass | 250 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-7.2-duty-to-disclose` | legal |
| reviewed-pass | 246 | B | `wildcat-docs:legal/master-loan-agreement.md#b-base-apr-amendment` | legal |
| reviewed-pass | 246 | B | `wildcat-docs:technical-overview/function-event-signatures/spherex/spherexconfig.sol.md#index` | synthesised |
| reviewed-pass | 242 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#acknowledgment` | legal |
| reviewed-pass | 240 | B | `wildcat-docs:legal/master-loan-agreement.md#id-23-termination-of-agreement` | legal |
| reviewed-pass | 240 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-9.2-prohibited-content` | legal |
| reviewed-pass | 239 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-18.4-assignment` | legal |
| reviewed-pass | 235 | A | `v2-protocol:src/WildcatSanctionsEscrow.sol:WildcatSanctionsEscrow` | synthesised |
| reviewed-pass | 235 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-2.3-retroactive-application` | legal |
| reviewed-pass | 235 | B | `wildcat-docs:technical-overview/security-developer-dives/wildcat-4626-wrapper.md#metadata` | nested-strong-sections |
| reviewed-pass | 228 | B | `wildcat-docs:legal/master-loan-agreement.md#id-10-survival-of-rights-and-remedies` | legal |
| reviewed-pass | 227 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-7.5-sanctioned-jurisdictions` | legal |
| reviewed-pass | 226 | B | `wildcat-docs:legal/master-loan-agreement.md#id-15-notices` | legal |
| reviewed-pass | 225 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-11.1-ownership` | legal |
| reviewed-pass | 224 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-3.3-no-financial-advice` | legal |
| reviewed-pass | 224 | B | `wildcat-docs:overview/introduction.md#index` | synthesised |
| reviewed-pass | 224 | B | `wildcat-docs:technical-overview/function-event-signatures/hooksfactory.sol.md#index` | synthesised |
| reviewed-pass | 223 | B | `wildcat-docs:technical-overview/function-event-signatures/spherex/ispherexengine.sol.md#index` | synthesised |
| reviewed-pass | 218 | B | `wildcat-docs:technical-overview/function-event-signatures/access/iroleprovider.sol.md#index` | synthesised |
| reviewed-pass | 213 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#wildcat-terms-of-use` | legal |
| reviewed-pass | 211 | B | `wildcat-docs:technical-overview/function-event-signatures/ihooksfactory.sol.md#index` | synthesised |
| reviewed-pass | 208 | B | `wildcat-docs:technical-overview/function-event-signatures/spherex/README.md#index` | synthesised |
| reviewed-pass | 205 | B | `wildcat-docs:technical-overview/function-event-signatures/interfaces/ihooks.sol.md#index` | synthesised |
| reviewed-pass | 201 | B | `wildcat-docs:technical-overview/function-event-signatures/access/README.md#index` | synthesised |
| reviewed-pass | 199 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-2.2-continued-use` | legal |
| reviewed-pass | 198 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-9.3-no-endorsement` | legal |
| reviewed-pass | 198 | B | `wildcat-docs:using-wildcat/day-to-day-usage/the-sentinel.md#index` | synthesised |
| reviewed-pass | 195 | B | `wildcat-docs:legal/master-loan-agreement.md#id-20-intention-to-be-bound` | legal |
| reviewed-pass | 193 | B | `wildcat-docs:technical-overview/function-event-signatures/README.md#index` | synthesised |
| reviewed-pass | 193 | B | `wildcat-docs:technical-overview/function-event-signatures/interfaces/README.md#index` | synthesised |
| reviewed-pass | 193 | B | `wildcat-docs:technical-overview/function-event-signatures/market/README.md#index` | synthesised |
| reviewed-pass | 192 | B | `wildcat-docs:technical-overview/function-event-signatures/interfaces/iwildcatsanctionsescrow.sol.md#functions` | duplicate-content |
| reviewed-pass | 192 | B | `wildcat-docs:technical-overview/function-event-signatures/wildcatsanctionsescrow.sol.md#functions` | duplicate-content |
| reviewed-pass | 182 | B | `wildcat-docs:security-measures/spherex-protection.md#index` | synthesised |
| reviewed-pass | 181 | B | `wildcat-docs:legal/master-loan-agreement.md#c-amount-of-digital-asset-to-be-loaned-amendment` | legal |
| reviewed-pass | 181 | B | `wildcat-docs:legal/protocol-ui-privacy-policy.md#acknowledgment-of-risks` | legal |
| reviewed-pass | 173 | A | `v2-protocol:README.md#index` | synthesised |
| reviewed-pass | 172 | B | `wildcat-docs:overview/whitepaper.md#index` | synthesised |
| reviewed-pass | 169 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-8.3-consequences-of-prohibited-use` | legal |
| reviewed-pass | 167 | B | `wildcat-docs:using-wildcat/day-to-day-usage/README.md#index` | synthesised |
| reviewed-pass | 167 | B | `wildcat-docs:using-wildcat/protocol-usage-fees.md#index` | synthesised |
| reviewed-pass | 166 | B | `wildcat-docs:technical-overview/function-event-signatures/interfaces/iwildcatsanctionssentinel.sol.md#events` | duplicate-content |
| reviewed-pass | 166 | B | `wildcat-docs:technical-overview/function-event-signatures/wildcatsanctionssentinel.sol.md#events` | duplicate-content |
| reviewed-pass | 164 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-8.1-compliance-with-laws` | legal |
| reviewed-pass | 156 | B | `wildcat-docs:legal/protocol-ui-privacy-policy.md#contact-information` | legal |
| reviewed-pass | 154 | B | `wildcat-docs:security-measures/bug-bounty-program.md#index` | synthesised |
| reviewed-pass | 151 | B | `wildcat-docs:legal/master-loan-agreement.md#i-taxes-and-fees` | legal |
| reviewed-pass | 150 | B | `wildcat-docs:README.md#index` | synthesised |
| reviewed-pass | 146 | B | `wildcat-docs:legal/master-loan-agreement.md#d-minimum-deposit-amendment` | legal |
| reviewed-pass | 129 | A | `v2-protocol:docs/Scale Factor.md#index` | synthesised |
| reviewed-pass | 126 | A | `v2-protocol:src/lens/MarketLens.sol:MarketLens` | synthesised |
| reviewed-pass | 124 | A | `v2-protocol:docs/CHANGELOG.md#index` | synthesised |
| reviewed-pass | 120 | A | `v2-protocol:src/market/WildcatMarketToken.sol:WildcatMarketToken` | synthesised |
| reviewed-pass | 115 | A | `v2-protocol:src/market/WildcatMarket.sol:WildcatMarket` | synthesised |
| reviewed-pass | 78 | A | `v2-protocol:TESTS.md#index` | synthesised |
| reviewed-pass | 74 | A | `v2-protocol:EIP-4626_audit_scope.md#index` | synthesised |
| reviewed-pass | 74 | A | `v2-protocol:docs/hooks/Hooks.md#index` | synthesised |
| reviewed-pass | 74 | A | `v2-protocol:docs/hooks/How Hooks Work.md#index` | synthesised |
| reviewed-pass | 63 | B | `wildcat-docs:technical-overview/function-event-signatures/interfaces/iwildcatsanctionsescrow.sol.md#events` | duplicate-content |
| reviewed-pass | 63 | B | `wildcat-docs:technical-overview/function-event-signatures/wildcatsanctionsescrow.sol.md#events` | duplicate-content |
| reviewed-pass | 60 | A | `v2-protocol:src/IHooksFactory.sol:IHooksFactory` | synthesised |
| reviewed-pass | 59 | A | `v2-protocol:src/market/WildcatMarketWithdrawals.sol:WildcatMarketWithdrawals` | synthesised |
| reviewed-pass | 55 | A | `v2-protocol:src/access/IHooks.sol:IHooks` | synthesised |
| reviewed-pass | 54 | A | `v2-protocol:src/market/WildcatMarketConfig.sol:WildcatMarketConfig` | synthesised |
| reviewed-pass | 51 | A | `v2-protocol:docs/README.md#index` | synthesised |
| reviewed-pass | 46 | A | `v2-protocol:src/interfaces/ISphereXProtectedRegisteredBase.sol:ISphereXProtectedRegisteredBase` | synthesised |
| reviewed-pass | 44 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-15-governing-law-and-dispute-resolution` | legal |
| reviewed-pass | 43 | A | `v2-protocol:src/IHooksFactory.sol:IHooksFactoryEventsAndErrors` | synthesised |
| reviewed-pass | 42 | B | `wildcat-docs:legal/wildcat-terms-of-use.md#id-16-bug-bounties-and-security-contests` | legal |
| reviewed-pass | 40 | A | `v2-protocol:src/interfaces/IChainalysisSanctionsList.sol:IChainalysisSanctionsList` | synthesised |
| reviewed-pass | 40 | A | `v2-protocol:src/interfaces/IWildcatSanctionsSentinel.sol:IWildcatSanctionsSentinel` | synthesised |
| reviewed-pass | 38 | A | `v2-protocol:src/interfaces/IWildcatSanctionsEscrow.sol:IWildcatSanctionsEscrow` | synthesised |
| reviewed-pass | 37 | A | `v2-protocol:src/interfaces/IMarketEventsAndErrors.sol:IMarketEventsAndErrors` | synthesised |
| reviewed-pass | 37 | A | `v2-protocol:src/interfaces/IWildcatArchController.sol:IWildcatArchController` | synthesised |
| reviewed-pass | 36 | A | `v2-protocol:src/lens/HooksDataForBorrower.sol:HooksDataForBorrowerLib` | synthesised |
| reviewed-pass | 35 | A | `v2-protocol:src/access/IRoleProviderFactory.sol:IRoleProviderFactory` | synthesised |
| reviewed-pass | 35 | A | `v2-protocol:src/lens/WithdrawalBatchData.sol:WithdrawalBatchDataLib` | synthesised |
| reviewed-pass | 35 | A | `v2-protocol:src/types/TransientBytesArray.sol:LibTransientBytesArray` | synthesised |
| reviewed-pass | 33 | A | `v2-protocol:src/lens/HooksInstanceData.sol:HooksInstanceDataLib` | synthesised |
| reviewed-pass | 33 | A | `v2-protocol:src/lens/HooksTemplateData.sol:HooksTemplateDataLib` | synthesised |
| reviewed-pass | 33 | A | `v2-protocol:src/lens/LenderAccountData.sol:IVersionedContract` | synthesised |
| reviewed-pass | 33 | A | `v2-protocol:src/lens/LenderAccountData.sol:LenderAccountDataLib` | synthesised |
| reviewed-pass | 32 | A | `v2-protocol:src/lens/RoleProviderData.sol:RoleProviderDataLib` | synthesised |
| reviewed-pass | 31 | A | `v2-protocol:src/lens/HooksConfigData.sol:HooksConfigDataLib` | synthesised |
| reviewed-pass | 30 | A | `v2-protocol:src/libraries/LibStoredInitCode.sol:LibStoredInitCode` | synthesised |
| reviewed-pass | 29 | A | `v2-protocol:src/lens/TokenData.sol:TokenMetadataLib` | synthesised |
| reviewed-pass | 28 | A | `v2-protocol:src/access/IRoleProvider.sol:IRoleProvider` | synthesised |
| reviewed-pass | 28 | A | `v2-protocol:src/types/LenderStatus.sol:LibLenderStatus` | synthesised |
| reviewed-pass | 28 | A | `v2-protocol:src/types/RoleProvider.sol:LibRoleProvider` | synthesised |
| reviewed-pass | 27 | A | `v2-protocol:src/libraries/MarketState.sol:MarketStateLib` | synthesised |
| reviewed-pass | 26 | A | `v2-protocol:src/lens/MarketData.sol:MarketDataLib` | synthesised |
| reviewed-pass | 26 | A | `v2-protocol:src/libraries/Withdrawal.sol:WithdrawalLib` | synthesised |
| reviewed-pass | 25 | A | `v2-protocol:src/libraries/FIFOQueue.sol:FIFOQueueLib` | synthesised |
| reviewed-pass | 24 | A | `v2-protocol:src/libraries/SafeCastLib.sol:SafeCastLib` | synthesised |
| reviewed-pass | 22 | A | `v2-protocol:src/libraries/BoolUtils.sol:BoolUtils` | synthesised |
| reviewed-pass | 22 | A | `v2-protocol:src/libraries/MathUtils.sol:MathUtils` | synthesised |
| reviewed-pass | 21 | A | `v2-protocol:src/interfaces/IERC20.sol:IERC20` | synthesised |
| reviewed-pass | 20 | A | `v2-protocol:src/libraries/FeeMath.sol:FeeMath` | synthesised |

## Interpretation

This report inventories structure; it does not certify factual truth. 
Legal, synthesised, oversized, duplicate, and whole-document evidence 
stays visible for review even when it is structurally valid. Exact 
duplicates across different sources are reported rather than silently 
removed because authority and provenance differ.
