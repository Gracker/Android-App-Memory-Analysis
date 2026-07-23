---
name: android-memory-diagnose
description: Produce detailed, theory-grounded Android memory diagnoses from validated QA evidence, including reanalysis and supplementation of a prior conclusion. Use for Java/ART leaks, OOM/GC/resource warnings, native/Scudo/JNI growth, graphics/DMA-BUF memory, PSS/RSS/SwapPss accounting, system pressure, regressions, user dissatisfaction with an earlier analysis, changed or newly supplied artifacts, and requests that need facts, hypotheses, uncertainty, citations, and exact next evidence kept separate.
---

# Android Memory Diagnose

Explain Android memory behavior without collapsing different ledgers or converting incomplete evidence into certainty.

## Workflow

1. Start from an `android-memory-ai-context` JSON when available. If it contains multiple `evaluated_intents`, use the overall support level and inspect every `intent_coverage` entry; branch evidence does not prove a simultaneous growth/leak/pressure claim.
2. If only raw files exist, invoke `$android-memory-evidence` and use its bundled `scripts/build_context.py` before diagnosing. Do not assume the target project contains `analyze.py`.
3. If `evidence.analysis_history.has_prior_analysis` is true or the user refers to an earlier conclusion, read [references/revision-protocol.md](references/revision-protocol.md) completely. Unless the selected mode is explicit `initial`, read the prior conclusion from the current conversation/task and listed report artifacts before writing the follow-up result. If the old conclusion is unavailable, state that blocker rather than inventing a comparison. In explicit `initial` mode, do not apply discovered history as a baseline.
4. Read [references/reasoning-protocol.md](references/reasoning-protocol.md) completely.
5. Read [references/accounting-domains.md](references/accounting-domains.md) whenever comparing memory values, percentages, or totals.
6. When meminfo is available, read [references/meminfo-smaps-ledger.md](references/meminfo-smaps-ledger.md) completely. Treat `evidence.accounting_ledger` as the quantitative navigation contract: preserve every meminfo row in source order and attach same-phase smaps evidence per row. Do not replace it with only overview totals or smaps TOP lists.
7. Read the matching branch in [references/intent-routing.md](references/intent-routing.md).
8. When `qa_observations` or attached QA artifacts exist, read [references/qa-signal-interpretation.md](references/qa-signal-interpretation.md) completely. Inspect the original authorized log context and each relevant screenshot; do not diagnose from the pattern inventory or image filename alone.
9. Confirm target package/PID/phase/device/build and resolve reported conflicts. Do not merge values across unresolved identities or clocks.
10. Build the current claim ledger independently from the current evidence before comparing it with any old conclusion:
   - observed facts tied to artifact IDs;
   - derived values with formulas and accounting domains;
   - hypotheses with supporting and contradicting evidence;
   - missing evidence that would discriminate hypotheses;
   - recommendations only after ownership and mechanism are supported.
11. For a follow-up, classify every material prior claim as `confirmed`, `revised`, `retracted`, or `unresolved`; list genuinely new claims separately. Explain both the evidence delta and the conclusion delta.
12. Use the selected knowledge records for definitions, proof boundaries, Android-version caveats, and official source URLs.
13. Explain current evidence even if coverage is insufficient. Narrow the scope and prioritize collection instead of guessing a root cause.
14. Hand a supported owner/mechanism finding to `$android-memory-remediate` only when code changes are requested.

## Non-Negotiable Boundaries

- Do not add or subtract values from different accounting domains without a cited formula.
- Do not call high PSS, retained size, object count, Native Heap, Graphics, Unknown, or SwapPss a leak by threshold alone.
- Do not infer a native allocation callsite from a VMA name.
- Do not infer a Java owner from a class histogram without lifecycle expectation and a root/owner path.
- Do not infer LMKD, OOM, memory limiter, freezer, or user kill from process disappearance alone.
- Do not treat an OOM throw site, isolated LeakCanary notification, log keyword, screenshot filename, cropped chart, or single visible value as a proven leak owner or trend.
- Do not present current Android 17 behavior as universal on older devices.
- Do not hide invalid, denied, stale, mixed, or missing artifacts.

## Response Shape

Lead with the strongest bounded conclusion. Then provide:

1. analysis mode, baseline used, and evidence support level;
2. evidence delta: added, changed, missing, and unchanged-by-fingerprint artifacts;
3. prior-claim revision table for follow-ups: old claim, status, old binding, current binding, and reason;
4. target identity and conflicts;
5. the complete meminfo main table in source order when present, with row-level smaps PSS/SwapPss/mapping supplements, comparison status, and explicit non-comparable rows;
6. Dalvik Details and the explicit total-reconciliation formula when present;
7. observed facts with artifact IDs;
8. QA observations with screenshot region or log line/hash binding;
9. accounting explanation with knowledge IDs and official sources;
10. ranked hypotheses, including evidence for and against each;
11. new claims and the conclusion delta;
12. what the evidence cannot prove;
13. exact next evidence and why it distinguishes the alternatives;
14. remediation direction only when owner and mechanism are supported;
15. verification conditions.

Use concrete language: “artifact X shows Y in ledger Z” and “this does not prove Q.” Avoid confidence theater and generic optimization lists.
