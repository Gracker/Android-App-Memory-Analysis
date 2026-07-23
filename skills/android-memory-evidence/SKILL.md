---
name: android-memory-evidence
description: Validate, inventory, compare, and complete Android memory evidence before diagnosis. Use for a complete QA handoff folder, QA screenshots, Android logs, LeakCanary output, dumps and reports, missing or contradictory details, permission failures, requests asking what to collect next, and follow-up work where the user is dissatisfied with a prior analysis, requests a reanalysis or supplement, or adds, changes, or removes evidence.
---

# Android Memory Evidence

Build a trustworthy evidence boundary before interpreting memory values. Accept partial inputs, explain what they support now, and give exact collection guidance for what remains unknown.

## Workflow

1. Preserve the supplied files. Never rewrite, rename, decompress, upload, or delete raw artifacts without explicit authorization.
2. Accept the normal RD intake as one QA handoff directory plus the issue title or symptom. Do not ask the user to classify, rename, or enumerate its files first. Record any supplied target package/process, device/API, scenario, phase, and whether the symptom appears Java, native, graphics, system-pressure, or regression oriented.
3. On every run, rescan the complete handoff directory. Never restrict a follow-up pass to the files the user says are new: unchanged, changed, missing, renamed, unclassified, and newly added artifacts all affect the evidence boundary.
4. Run this Skill's [scripts/build_context.py](scripts/build_context.py) against the directory and question. It recursively inventories the tree, validates supported artifacts by content, preserves multiple logs/screenshots/dumps, reports unclassified or skipped files, and augments vague question routing with evidence signals. Check `request.intent_source` and every `evaluated_intent`. The bundled versioned runtime and knowledge catalog require no separate repository checkout. Prefer JSON for another AI and Markdown for a human.
5. If the request mentions a prior analysis, dissatisfaction, continued analysis, or new evidence, or if `evidence.analysis_history.has_prior_analysis` is true, read [references/analysis-iteration.md](references/analysis-iteration.md) completely. For every mode except explicit `initial`, inspect both the current conversation/task history and every listed prior-analysis artifact. Do not assume the folder contains the previous assistant response; in explicit `initial` mode, retain old material as inventory without applying it as a baseline.
6. Check `request.analysis_mode`, `request.analysis_mode_source`, `evidence.analysis_history.baseline_applied`, and `evidence.analysis_history.evidence_delta`. A `clarification-required` mode permits inventory and context construction, but requires the user to choose full reanalysis or supplementation before a final diagnosis is presented.
7. Use `--repo` only when intentionally testing a source checkout. Do not make a checkout or environment variable a prerequisite for normal context generation. If an optional collection command needs the full analyzer repository, identify that dependency separately from the bundled context runtime.
8. Read the resulting primary coverage, every entry in `intent_coverage`, `qa_observations`, conflicts, invalid artifacts, limitations, and `next_evidence` before drawing any conclusion. A mixed question must satisfy every evaluated claim contract.
9. When QA logs or screenshots exist, read [references/qa-artifacts.md](references/qa-artifacts.md) completely. Use log signals only to navigate the original authorized lines and inspect each relevant screenshot; zero matches do not make a log irrelevant. The runtime deliberately performs no OCR and embeds no raw log lines or pixels.
10. Classify current statements as observed, derived, hypothesis, or recommendation. Bind observations to `artifact_id`; bind logs to line/hash and screenshots to a visible region.
11. Continue with a bounded explanation even when evidence is incomplete. Do not turn missing evidence into a guessed fact.
12. Give missing-evidence commands in priority order. Preserve prerequisites, permission boundaries, Android-version gates, and perturbation level.
13. Hand a valid context to `$android-memory-diagnose` for theory-grounded interpretation.

## Build Context

Run from any AI project where this Skill is installed:

```bash
python3 .agents/skills/android-memory-evidence/scripts/build_context.py \
  --dump-dir /path/to/qa-handoff \
  --question "Native memory grows after five loops" \
  --format json \
  --output android-memory-context.json
```

If the target agent uses another Skills root, replace `.agents/skills` with that installation path; do not assume `scripts/build_context.py` exists at the AI project root. The installed Skill contains `runtime/runtime-manifest.json`; generated contexts identify their `generator.name` and `generator.version` for compatibility checks.

Use `--repo /path/to/Android-App-Memory-Analysis` only to exercise a specific source checkout. An invalid explicit checkout is an error and must not silently fall back to the bundled release.

Use `--intent` only when the user has already chosen a branch. Keep `auto` when the symptom is ambiguous. Use `--analysis-mode` only when the user has explicitly chosen `initial`, `reanalysis`, `supplement`, or `reanalysis-with-new-evidence`; otherwise keep `auto`. Use `--strict` only for automation gates; interactive work should still produce a partial context.

Paths are redacted by default. Add `--include-local-paths` only when the consuming AI runs on the same authorized machine and needs to open the raw artifacts. Never use it for a context that may leave that boundary without a separate privacy review.

The helper forwards additional `ai-context` options such as `--meminfo`, `--phase-metadata`, `--device-context`, `--android-log`, `--qa-screenshot`, `--previous-context`, `--previous-analysis`, `--package`, or `--android-sdk` to the repository CLI. Prior contexts and reports inside the handoff directory are discovered automatically; the repeatable history overrides are only for material stored elsewhere. Other overrides are exceptional: use them for files outside the handoff directory or explicit subject facts, not to make the user pre-classify the folder. Unknown or misspelled options fail in that canonical parser instead of being silently ignored.

## Interpret Status Correctly

- Treat `ok` as format/content recognition, not as proof that the artifact captured the intended phase.
- Treat `invalid`, `empty`, `permission_denied`, `command_failed`, and `unreadable` as unavailable evidence.
- Treat a filename as a hint only. Validate the contents.
- Treat every `unclassified_file`, scan truncation, skipped symlink, per-type overflow, and hash omission as visible inventory state; never imply the whole folder was analyzed when a bound was reached.
- Treat `insufficient` as permission to explain limits and collect evidence, not permission to diagnose a root cause.
- Treat `limited`, `supported`, and `strong` as evidence-set coverage, not calibrated probabilities.
- Resolve package, PID, phase, or device conflicts before merging values.

## Required References

- Read [references/evidence-protocol.md](references/evidence-protocol.md) when inventorying files, assessing coverage, or writing capture commands.
- Read [references/qa-artifacts.md](references/qa-artifacts.md) whenever QA supplies screenshots, logcat, LeakCanary output, crash/ANR/bugreport text, or other Android logs.
- Read [references/analysis-iteration.md](references/analysis-iteration.md) for every reanalysis, supplemental analysis, dissatisfied-user follow-up, or run containing prior contexts/reports.
- Read [references/safety-and-privacy.md](references/safety-and-privacy.md) before handling HPROF, traces, production artifacts, or external AI uploads.

## Output Contract

Return:

1. target and question;
2. available artifacts with status and accounting domain;
3. QA screenshot observations and log signals with artifact/region or line/hash binding;
4. analysis mode, prior-analysis sources, and added/changed/missing/unchanged evidence delta when this is a follow-up;
5. conflicts and invalid inputs;
6. what can be explained now;
7. what cannot be proved now;
8. prioritized collection commands with prerequisites and perturbation;
9. privacy or production-safety constraints;
10. the `evidence.accounting_ledger` status; when available, preserve the complete meminfo row order and its row-level smaps supplements for diagnosis instead of reducing it to overview totals;
11. path to the generated context, when created.
