---
name: android-memory-evidence
description: Validate, inventory, and complete Android memory evidence before diagnosis. Use for dumpsys meminfo, smaps/showmap, HPROF, gfxinfo, DMA-BUF, ZRAM/swap, PSI, Perfetto, ApplicationExitInfo, panorama/combined reports, dump directories, missing or contradictory user details, permission failures, and requests asking what to collect next.
---

# Android Memory Evidence

Build a trustworthy evidence boundary before interpreting memory values. Accept partial inputs, explain what they support now, and give exact collection guidance for what remains unknown.

## Workflow

1. Preserve the supplied files. Never rewrite, rename, decompress, upload, or delete raw artifacts without explicit authorization.
2. Identify the user's question, target package/process, device/API, scenario, phase, and whether the problem is Java, native, graphics, system pressure, or regression oriented.
3. Run this Skill's [scripts/build_context.py](scripts/build_context.py) with the evidence directory and the user's question. It uses the bundled, versioned runtime and knowledge catalog, so a copied or package-manager-installed Skill does not require a separate repository checkout. Prefer JSON for another AI and Markdown for a human.
4. Use `--repo` only when intentionally testing a source checkout. Do not make a checkout or environment variable a prerequisite for normal context generation. If an optional collection command needs the full analyzer repository, identify that dependency separately from the bundled context runtime.
5. Read the resulting primary coverage, every entry in `intent_coverage`, conflicts, invalid artifacts, limitations, and `next_evidence` before drawing any conclusion. A mixed question must satisfy every evaluated claim contract.
6. Classify current statements as observed, derived, hypothesis, or recommendation. Bind observations to `artifact_id`.
7. Continue with a bounded explanation even when evidence is incomplete. Do not turn missing evidence into a guessed fact.
8. Give missing-evidence commands in priority order. Preserve prerequisites, permission boundaries, Android-version gates, and perturbation level.
9. Hand a valid context to `$android-memory-diagnose` for theory-grounded interpretation.

## Build Context

Run from any AI project when this Skill and the analysis repository are both available:

```bash
python3 .agents/skills/android-memory-evidence/scripts/build_context.py \
  --dump-dir /path/to/evidence \
  --question "Native memory grows after five loops" \
  --format json \
  --output android-memory-context.json
```

If the target agent uses another Skills root, replace `.agents/skills` with that installation path; do not assume `scripts/build_context.py` exists at the AI project root. The installed Skill contains `runtime/runtime-manifest.json`; generated contexts identify their `generator.name` and `generator.version` for compatibility checks.

Use `--repo /path/to/Android-App-Memory-Analysis` only to exercise a specific source checkout. An invalid explicit checkout is an error and must not silently fall back to the bundled release.

Use `--intent` only when the user has already chosen a branch. Keep `auto` when the symptom is ambiguous. Use `--strict` only for automation gates; interactive work should still produce a partial context.

Paths are redacted by default. Add `--include-local-paths` only when the consuming AI runs on the same authorized machine and needs to open the raw artifacts. Never use it for a context that may leave that boundary without a separate privacy review.

The helper forwards additional `ai-context` options such as `--meminfo`, `--phase-metadata`, `--device-context`, `--package`, or `--android-sdk` to the repository CLI. Unknown or misspelled options fail in that canonical parser instead of being silently ignored.

## Interpret Status Correctly

- Treat `ok` as format/content recognition, not as proof that the artifact captured the intended phase.
- Treat `invalid`, `empty`, `permission_denied`, `command_failed`, and `unreadable` as unavailable evidence.
- Treat a filename as a hint only. Validate the contents.
- Treat `insufficient` as permission to explain limits and collect evidence, not permission to diagnose a root cause.
- Treat `limited`, `supported`, and `strong` as evidence-set coverage, not calibrated probabilities.
- Resolve package, PID, phase, or device conflicts before merging values.

## Required References

- Read [references/evidence-protocol.md](references/evidence-protocol.md) when inventorying files, assessing coverage, or writing capture commands.
- Read [references/safety-and-privacy.md](references/safety-and-privacy.md) before handling HPROF, traces, production artifacts, or external AI uploads.

## Output Contract

Return:

1. target and question;
2. available artifacts with status and accounting domain;
3. conflicts and invalid inputs;
4. what can be explained now;
5. what cannot be proved now;
6. prioritized collection commands with prerequisites and perturbation;
7. privacy or production-safety constraints;
8. path to the generated context, when created.
