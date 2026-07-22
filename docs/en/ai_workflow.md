# Android Memory AI Workflow

This workflow connects the repository's practical collectors/parsers with the proof boundaries maintained in the private `Gracker/android-memory` theory repository. It does not delegate truth to a model: the repository first creates a validated, provider-neutral context, then Codex, Claude, or another Skills-capable agent interprets that context.

## Architecture

<table><thead><tr><th>Layer</th><th>Components</th><th>Stable boundary</th></tr></thead><tbody><tr><td>User and AI project</td><td><code>android-memory-evidence</code><br><code>android-memory-diagnose</code><br><code>android-memory-remediate</code></td><td>User question, evidence state, separated facts/hypotheses/advice</td></tr><tr><td>AI protocol</td><td>bundled Skill runtime<br><code>analyze.py ai-context</code><br><code>android_memory_ai.context</code></td><td><code>android-memory-ai-context</code> schema 1.2 plus generator version</td></tr><tr><td>Evidence and knowledge</td><td>artifact validators<br>intent coverage<br>QA log/screenshot observations<br><code>android_memory_catalog.json</code></td><td>Hashes, provenance, accounting domains, versions, gaps, conflicts</td></tr><tr><td>Practical tools</td><td>meminfo/smaps/HPROF/gfxinfo/DMA-BUF/ZRAM/Perfetto/logcat/panorama/diff</td><td>Raw artifacts and backward-compatible derived reports</td></tr><tr><td>Android / Linux</td><td>ART, Scudo, memtrack, LMKD, PSI, ZRAM, VMAs, process exits</td><td>API/kernel/ROM/permission/device variance</td></tr></tbody></table>

Privacy, collection perturbation, package/PID/phase identity, Android version, accounting compatibility, and raw-versus-derived provenance cross every layer.

New live dumps also write `manifest.json` with per-artifact `ok`, `empty`, `permission_denied`, `not_supported`, `command_failed`, `skipped`, `not_applicable`, or `not_collected` state plus command, domain, perturbation, and reason. `not_collected` never means the memory category is absent.

## Create an AI context

The default input is the complete folder downloaded from QA plus the issue title or symptom. Do not require the user to classify or enumerate files first:

```bash
python3 analyze.py ai-context \
  -d ./qa-handoff/ANDROID-1234 \
  --question "Native memory keeps growing after the screen exits" \
  --format json \
  -o android-memory-context.json
```

Create a human-readable report:

```bash
python3 analyze.py ai-context \
  -d ./dumps/com.example.app_20260721_120000 \
  --intent native-memory \
  --format markdown \
  --lang en \
  -o android-memory-context.md
```

Artifact and subject overrides keep partial evidence useful:

```bash
python3 analyze.py ai-context \
  -d ./case \
  --meminfo /evidence/meminfo.txt \
  --smaps /evidence/smaps.txt \
  --analysis-report /evidence/panorama.json \
  --package com.example.app \
  --android-sdk 37 \
  --phase after-exit-30s \
  --question "Does this prove a JNI leak?"
```

Use `--strict` only for automation. An incomplete context is still written, but the command exits 2.

## Follow-up analysis and new evidence

Every follow-up starts by rescanning the complete current folder. If a prior `android-memory-ai-context` or recognizable analysis report is stored in that folder, the runtime indexes it as analysis history rather than treating it as new memory evidence. It compares the newest prior context snapshot with the current rescan and reports added, changed, missing-since-previous, and unchanged-by-fingerprint artifacts.

The usual interaction needs only the same folder and the user's new request:

```bash
python3 analyze.py ai-context \
  -d ./qa-handoff/ANDROID-1234 \
  --question "I disagree with the prior conclusion; QA added logs. Reanalyze the case." \
  --format json \
  -o android-memory-context-v2.json
```

If the old material lives outside the QA folder, pass repeatable explicit overrides:

```bash
python3 analyze.py ai-context \
  -d ./qa-handoff/ANDROID-1234 \
  --previous-context /reviews/android-memory-context-v1.json \
  --previous-analysis /reviews/android-memory-analysis-v1.md \
  --analysis-mode reanalysis-with-new-evidence \
  --question "Recheck the old owner conclusion against the new logs" \
  -o android-memory-context-v2.json
```

Keep `--analysis-mode auto` unless the user has explicitly selected the workflow. The runtime distinguishes:

- `initial`: no prior analysis applies;
- `reanalysis`: rebuild the current claim ledger independently because the old reasoning is challenged;
- `supplement`: preserve only still-valid claims and propagate new, changed, or missing evidence;
- `reanalysis-with-new-evidence`: perform both;
- `clarification-required`: prior analysis exists, the evidence is unchanged, and the request does not say whether to redo or extend. The folder may still be inventoried, but the agent must clarify the mode before presenting a final diagnosis.

The agent must also inspect the current conversation/task for the previous answer; a context JSON records the earlier evidence snapshot, not necessarily the earlier prose conclusion. Every material old claim must be marked `confirmed`, `revised`, `retracted`, or `unresolved`, with genuinely new claims listed separately. An unchanged hash does not prove that an old interpretation was correct, and a missing path is not proof of deletion when the scan was truncated or a file was renamed.

## QA logs and screenshots

The runtime recursively inventories the QA directory before building context. It does not rely on QA naming conventions: known names and extensions are discovery hints, while content signatures classify supported artifacts. Multiple files of the same type remain distinct. Every indexed regular file is represented either as a recognized artifact or `unclassified_file`; skipped symlinks, unreadable entries, index truncation, per-type overflow, and hash-budget omissions are explicit limitations. Recognized HPROF, high-specificity log signals, native profiles, and comparisons augment question-based intent routing; generic supporting artifacts do not open unrelated branches. `request.intent_source` records whether routing came from the question, evidence, both, or an explicit choice.

The directory may contain nested plain/gzip Android logs, bugreport ZIPs, targeted logcat/LeakCanary/bugreport/tombstone/ANR text, PNG/JPEG/WebP screenshots, dumps, traces, reports, or unrelated attachments. The default bounds are 2,048 indexed files, 64 processed artifacts per type, 32 MiB decoded per log/archive, 256 ZIP members, 512 MiB per-file hashing, and 1 GiB total hashing. Use repeatable overrides only for files outside the QA directory:

```bash
python3 analyze.py ai-context \
  -d ./case \
  --android-log /qa/logcat-main.log \
  --android-log /qa/system.log.gz \
  --qa-screenshot /qa/leakcanary.png \
  --qa-screenshot /qa/memory-chart.jpg \
  --question "QA saw a retained Activity and an OOM after five loops"
```

Each log or bugreport ZIP is scanned independently up to 32 MiB of decoded text; ZIP samples also bind the archive member and use a 256-member ceiling. `evidence.qa_observations` contains signal type/strength/count, one-based line numbers, SHA-256 for matched lines, available threadtime timestamps/tags, and scan truncation. It never contains raw lines. Signals cover complete LeakCanary-path candidates, Android component/StrictMode cleanup warnings, Java/native allocation failures, GC pressure, JNI reference overflow, Binder/database/graphics pressure, LMKD, and kernel OOM events.

A complete LeakCanary GC-root/reference path can satisfy the managed owner-path branch when the original report, target/build/phase, expected lifecycle, and suspect edge are verified. A notification screenshot, retained count, OOM throw site, GC line, or keyword match cannot. Growth/regression still requires comparable phases.

Screenshots are validated only for format, dimensions, size, and hash. No OCR or pixel content is placed in the context. The consuming AI must inspect the authorized image and bind every visible claim to its screenshot artifact ID and region, while recording cropped, hidden, unreadable, or inferred content.

Artifact paths are relative or redacted by default, which is appropriate for a context sent to an external AI. Add `--include-local-paths` only for an authorized AI running on the same machine; it adds the absolute evidence root and artifact paths so the agent can open raw evidence. Do not forward that context without a separate privacy review.

## Context contract

The schema records the request, subject candidates, recursive `folder_inventory`, validated artifacts, accounting domains, hashes, intent-specific coverage, QA observations, conflicts, bounded derived-report summaries, `evidence.analysis_history`, relevant knowledge records, analysis rules, privacy policy, limitations, and executable next-evidence guidance. `analysis_history` identifies prior contexts/reports, the selected mode, the bounded evidence delta, limitations, and the mandatory claim-review contract; it does not embed old report text. An automatic mixed question such as “Native memory keeps growing” evaluates both the native branch and regression claim; the overall support level is the weakest contract, while `primary_intent_support_level` preserves the branch-only result.

Support levels describe evidence-set coverage, not probability:

- `insufficient`: explain current evidence and collect discriminators; do not select a root cause or code fix;
- `limited`: identify direction while preserving alternatives;
- `supported`: core and some ownership/timeline evidence is available;
- `strong`: the intent-defined evidence set is complete, but every claim still needs artifact binding.

An artifact can be format-valid yet inadequate for the selected intent. In particular, a single live snapshot has a valid `phase`, but Java/native leak and regression claims still require timestamp, process role, user/profile, scenario, loops, cooldown, collection mode, perturbation, and comparable phases. Such artifacts appear in `evidence.coverage.inadequate` and remain in `next_evidence`.

## Install the public Skills

The public package contains three Skills and a self-contained stdlib-only evidence runtime. Context generation requires Python 3.8 or later, but it does not require cloning this repository or setting `ANDROID_MEMORY_ANALYSIS_ROOT`.

Install all three into the current project with the open Skills CLI (Node.js 18+):

```bash
npx skills add Gracker/Android-App-Memory-Analysis \
  --skill '*'
```

Project scope is recommended for a team because the generated `skills-lock.json` records the source and installed hashes. For a global Codex install:

```bash
npx skills add Gracker/Android-App-Memory-Analysis \
  --skill '*' \
  --agent codex \
  --global \
  --yes
```

Replace `codex` with the target agent identifier when needed, and restart or reload the agent after installation or update.

Refresh an existing global installation by rerunning the same source command; the CLI replaces the managed copies and refreshes their hashes:

```bash
npx skills add Gracker/Android-App-Memory-Analysis \
  --skill '*' \
  --agent codex \
  --global \
  --yes
```

Omit `--global` and the explicit agent for an interactive project-scoped refresh. The Evidence Skill's `runtime/runtime-manifest.json` pins the runtime, context schema, catalog version, and file hashes. Repository maintainers regenerate the bundle from canonical sources; users should not edit generated runtime files.

The full repository remains an optional enhancement for live capture, panorama, diff, and helper-driven Perfetto collection. Use `--repo /path/to/Android-App-Memory-Analysis` only when deliberately selecting such a checkout. Some generated advanced-collection commands use `ANDROID_MEMORY_ANALYSIS_ROOT` to reference that optional checkout, but the installed-Skill context runtime never discovers or depends on the variable.

Recommended sequence:

1. `$android-memory-evidence` validates partial/malformed inputs and creates the context.
2. `$android-memory-diagnose` combines artifact-bound facts with versioned theory and official sources.
3. `$android-memory-remediate` changes code only after ownership/mechanism evidence exists and then verifies the same scenario/domain.

## Incomplete or inaccurate user input

Do not ask vaguely for more logs. State what is observed, what it supports, what it cannot prove, remaining hypotheses, and the smallest artifact that distinguishes them. Include the exact command, placeholder substitutions, prerequisites, permissions, Android-version gate, perturbation, and expected discriminator. Preserve user/tool conflicts instead of silently choosing one source.

## Theory and publication boundary

[android_memory_catalog.json](../../knowledge/android_memory_catalog.json) contains original condensed operational knowledge, private source revision provenance, official public links, evidence requirements, non-claims, version scope, and practical tool mappings. It does not copy the private articles or treat review history as runtime truth.

Current audited theory revision: `2feca977830e99ddfb191022e9ba02409e7f0e19`.

## Privacy and cost

The context does not embed raw HPROF, trace, log lines, screenshot pixels, or arbitrary file bodies, and it redacts external absolute paths by default. Files up to 512 MiB are eligible for hashing within the default 1 GiB total budget; `--hash-large-files` opts into hashing larger files and removes the total budget. Review authorization, privacy, access control, processing location, and retention before sharing raw artifacts with an external model. Context generation never starts heavy HPROF or panorama analysis implicitly.

## Verification

The repository-defined gate for this AI/Skills surface is:

```bash
python3 scripts/sync_skill_runtime.py --write  # only after canonical runtime/catalog changes
./scripts/verify.sh
./scripts/verify_npx_skill_install.sh
```

Commit the regenerated runtime with its canonical source change. `verify.sh` never regenerates it: stale or missing bundle files fail the build. The gates run stdlib tests, bundle drift validation, isolated copied-Skill execution, catalog/Skills validation, a real demo CLI smoke test, strict incomplete-evidence exit-code checks, and cloned-git `npx skills` install/reinstall execution. Run Skill Creator `quick_validate.py` separately for every Skill.

The `AI Knowledge and Skills` GitHub Actions workflow runs the same gate on Python 3.8 and 3.12. A separate job installs and reinstalls all three Skills through a pinned real `npx skills` CLI into a clean project, removes repository/environment discovery, and proves the copied runtime can create a context both times. CI adds no hosted-model credentials and never uploads dump artifacts.
