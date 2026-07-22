---
name: android-memory-remediate
description: Plan, implement, review, and verify Android memory code or configuration changes after evidence identifies an owner and mechanism. Use for fixing Java lifecycle leaks, caches, native/JNI allocations, DirectByteBuffer ownership, Bitmap/Surface/WebView resources, background work, memory budgets, or memory-related regressions while preserving architecture, unrelated worktree changes, and project-specific validation rules.
---

# Android Memory Remediate

Turn a supported Android memory diagnosis into the smallest architecture-correct change and prove its effect in the same scenario.

## Entry Gate

1. Require a diagnosis with artifact IDs, accounting domain, owner, mechanism, and residual alternatives.
2. If the diagnosis revises a prior analysis, use only the current `confirmed` or newly supported owner/mechanism as the entry gate. A retracted, unresolved, or merely inherited prior claim cannot authorize a code change.
3. Treat QA logs and screenshots as admissible evidence only when the diagnosis binds the exact line/hash or visible region to the matching target/build/phase. An OOM line, keyword match, notification, or chart screenshot alone does not open the code-change gate.
4. If evidence support is `insufficient` or the owner is unresolved, invoke `$android-memory-evidence` and `$android-memory-diagnose` first.
5. Permit a collection/instrumentation change without a root cause when its explicit purpose is to obtain the missing discriminator.
6. Never implement a generic memory tip merely because a threshold fired.
7. Confirm the target source root, module, revision, and build variant. When a workspace contains both an analyzer and a demo/test fixture, do not infer the edit target from package name alone.

## Workflow

1. Read the target project's instructions, source, tests, architecture, current branch, and worktree before editing.
2. Read [references/change-protocol.md](references/change-protocol.md) completely.
3. Read the relevant rows in [references/verification-matrix.md](references/verification-matrix.md).
4. Write the change contract:
   - observed evidence and accounting domain;
   - owner and mechanism;
   - exact files/components;
   - expected same-domain metric or lifecycle change;
   - functional/performance risks;
   - before/after/cooldown scenario;
   - rollback condition.
5. Prefer ownership and lifecycle corrections over forced cleanup, global GC, arbitrary thresholds, or broad cache removal.
6. Preserve existing public behavior and unrelated dirty worktree changes unless the user explicitly broadens scope.
7. Add or update focused tests for the mechanism when the project provides a test surface.
8. Run only the target project's documented, executable validation commands.
9. Recollect matching evidence. Compare the same device bucket, process role, scenario, phase, collection mode, and accounting domain.
10. Report code validation and memory evidence validation separately. Do not call the fix proven if only one side passed.

## Architecture Review

- Confirm the change repairs the responsible owner instead of hiding its accounting.
- Confirm cleanup occurs at the correct lifecycle boundary and is idempotent.
- Confirm thread, process, JNI, Binder, buffer, and callback ownership remains valid.
- Confirm cache changes preserve hit rate, latency, network/storage cost, and product behavior.
- Confirm native changes preserve allocator/symbolization/sanitizer compatibility.
- Confirm graphics changes preserve rendering correctness and release ordering.
- Confirm device/API/vendor branches are capability-gated rather than model-name hardcoded.
- Confirm observability distinguishes unsupported, permission denied, empty, and true absence.

## Handoff

Return:

1. evidence-backed root cause or instrumentation purpose;
2. changed files and architecture rationale;
3. tests and project validation results;
4. before/after memory evidence with matching accounting domain;
5. product/performance regressions checked;
6. residual uncertainty and missing device validation;
7. rollback condition.

If the Entry Gate fails, return a blocked handoff instead: facts currently supported, unresolved owner/mechanism or target-project fields, the smallest discriminator and its prerequisites, code and files deliberately left unchanged, and the condition that would permit implementation. Do not make the user infer that stopping was intentional.
