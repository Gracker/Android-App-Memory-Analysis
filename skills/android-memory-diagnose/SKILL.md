---
name: android-memory-diagnose
description: Produce detailed, theory-grounded Android memory diagnoses from a validated evidence context or raw artifacts. Use for Java/ART leaks, native/Scudo/JNI growth, Graphics/WebView/DMA-BUF memory, PSS/RSS/SwapPss accounting, ZRAM/PSI/LMKD pressure, process kills, before/after regressions, and any request that needs facts, hypotheses, uncertainty, citations, and exact next evidence kept separate.
---

# Android Memory Diagnose

Explain Android memory behavior without collapsing different ledgers or converting incomplete evidence into certainty.

## Workflow

1. Start from an `android-memory-ai-context` JSON when available. If it contains multiple `evaluated_intents`, use the overall support level and inspect every `intent_coverage` entry; branch evidence does not prove a simultaneous growth/leak/pressure claim.
2. If only raw files exist, invoke `$android-memory-evidence` and use its bundled `scripts/build_context.py` before diagnosing. Do not assume the target project contains `analyze.py`.
3. Read [references/reasoning-protocol.md](references/reasoning-protocol.md) completely.
4. Read [references/accounting-domains.md](references/accounting-domains.md) whenever comparing memory values, percentages, or totals.
5. Read the matching branch in [references/intent-routing.md](references/intent-routing.md).
6. Confirm target package/PID/phase/device and resolve reported conflicts. Do not merge values across unresolved identities.
7. Build a claim ledger:
   - observed facts tied to artifact IDs;
   - derived values with formulas and accounting domains;
   - hypotheses with supporting and contradicting evidence;
   - missing evidence that would discriminate hypotheses;
   - recommendations only after ownership and mechanism are supported.
8. Use the selected knowledge records for definitions, proof boundaries, Android-version caveats, and official source URLs.
9. Explain current evidence even if coverage is insufficient. Narrow the scope and prioritize collection instead of guessing a root cause.
10. Hand a supported owner/mechanism finding to `$android-memory-remediate` only when code changes are requested.

## Non-Negotiable Boundaries

- Do not add or subtract values from different accounting domains without a cited formula.
- Do not call high PSS, retained size, object count, Native Heap, Graphics, Unknown, or SwapPss a leak by threshold alone.
- Do not infer a native allocation callsite from a VMA name.
- Do not infer a Java owner from a class histogram without lifecycle expectation and a root/owner path.
- Do not infer LMKD, OOM, memory limiter, freezer, or user kill from process disappearance alone.
- Do not present current Android 17 behavior as universal on older devices.
- Do not hide invalid, denied, stale, mixed, or missing artifacts.

## Response Shape

Lead with the strongest bounded conclusion. Then provide:

1. scope and evidence support level;
2. target identity and conflicts;
3. observed facts with artifact IDs;
4. accounting explanation with knowledge IDs and official sources;
5. ranked hypotheses, including evidence for and against each;
6. what the evidence cannot prove;
7. exact next evidence and why it distinguishes the alternatives;
8. remediation direction only when owner and mechanism are supported;
9. verification conditions.

Use concrete language: “artifact X shows Y in ledger Z” and “this does not prove Q.” Avoid confidence theater and generic optimization lists.
