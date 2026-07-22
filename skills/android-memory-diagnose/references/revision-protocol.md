# Revision Protocol

Use this protocol for every second analysis, dissatisfied-user follow-up, continued analysis, or evidence update.

## Prevent conclusion anchoring

Read the old conclusion so its claims can be audited, but do not start by editing its prose. First build a current claim ledger from the current folder snapshot, original authorized artifacts, target identity, accounting domains, and current proof boundaries. Compare the two ledgers only after the independent pass.

An old context records evidence provenance and earlier support state. It does not contain the full assistant reasoning unless a separate report or conversation does. An old report is derived evidence, never a substitute for the raw artifact it cites.

## Revision procedure

1. State the selected analysis mode and the exact baseline context/report or conversation response.
2. Start with `evidence.analysis_history.case_identity`, then verify that old and current package, process role, build, device bucket, scenario, phase, clock, and collection mode are comparable. Runtime identity comparison is a warning surface, not a substitute for this review.
3. Review every added, changed, missing, and unchanged-by-fingerprint artifact. Read delta limitations before treating absence as deletion or sameness as proof.
4. Build the current observed/derived/hypothesis/recommendation ledger independently.
5. Map every material old claim to the current ledger.
6. Assign exactly one status: `confirmed`, `revised`, `retracted`, or `unresolved`.
7. List new current claims separately.
8. Explain the conclusion delta independently from the file delta. A new file may change no conclusion; unchanged files may still produce a corrected conclusion after better reasoning.

For `reanalysis`, explicitly identify any old inference that was invalid, unsupported, overly broad, or still sound. For `supplement`, preserve only claims whose identity and evidence bindings remain valid, then show how new/changed/missing evidence affects them. For `reanalysis-with-new-evidence`, do both.

## Required follow-up table

| Prior claim | Status | Old binding | Current binding | Reason |
|-------------|--------|-------------|-----------------|--------|
| ... | confirmed/revised/retracted/unresolved | artifact/section or unavailable | artifact/section or missing | proof-boundary explanation |

Do not use confidence percentages. Do not mark a claim confirmed because the old report said it, because a file is unchanged, or because a new log contains a matching keyword.

## Missing baseline

If the user requests a comparison but the old conclusion is unavailable, do not fabricate the prior claim ledger. Provide the fresh bounded analysis if useful, label conclusion comparison as blocked, and request the missing prior response/report. If `request.analysis_mode` is `clarification-required`, ask whether the user wants a from-scratch reanalysis or an extension before issuing the final diagnosis.
