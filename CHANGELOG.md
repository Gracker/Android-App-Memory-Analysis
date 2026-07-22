# Changelog

## Unreleased

### Fixed
- Restored `[anon:native]` classification in the shared smaps parser so Native PSS and SwapPSS remain visible, and added regression coverage for deep HPROF dominator trees that exceed Python's recursion limit.

## v1.3.0 - 2026-07-22

### Added
- Added folder-first QA intake: recursively inventory the complete handoff directory, classify supported evidence by content rather than filenames alone, preserve multiple artifacts, and surface unclassified files, symlinks, truncation, per-type limits, and hash-budget gaps.
- Added multi-file QA evidence support for nested Android/logcat/gzip logs, bounded in-place bugreport ZIP scanning, and PNG/JPEG/WebP screenshots, including repeatable CLI overrides.
- Added bounded privacy-safe log signal extraction for LeakCanary paths, Android component/resource leaks, Java/native allocation failures, GC pressure, JNI reference overflow, graphics/database/Binder pressure, LMKD, and kernel OOM events.
- Added screenshot format/dimension/hash validation, explicit visual-review requirements, QA evidence Skill protocols, and bilingual workflow guidance.
- Added iterative-analysis history: automatic prior context/report discovery, bounded evidence deltas, explicit reanalysis/supplement modes, and mandatory confirmed/revised/retracted/unresolved review of prior claims.
- Added repeatable `--previous-context` and `--previous-analysis` overrides plus bilingual second-analysis protocols for material stored outside the QA folder.

### Changed
- The AI context schema is now 1.2 and the bundled runtime is 1.2.0; `qa_observations` keeps log signals and screenshot metadata separate from raw content and from proven root causes, while `analysis_history` tracks bounded prior-context and evidence-delta state.
- The default workflow now needs only the QA folder and issue background; explicit artifact flags are reserved for files outside that directory or deliberate overrides.
- Evidence-derived branches now augment vague issue-title routing, with an auditable `intent_source` distinguishing question, folder evidence, both, and explicit selection.
- A complete LeakCanary GC-root/reference-path log can satisfy the managed owner-path branch, while notification screenshots, OOM lines, retained counts, and isolated keywords remain insufficient.

## v1.2.0 - 2026-07-21

### Added
- Added the provider-neutral `ai-context` schema and CLI for validated artifacts, mixed-intent coverage, accounting domains, provenance, conflicts, privacy-safe paths, bounded report summaries, and executable missing-evidence guidance.
- Added a versioned operational knowledge catalog derived from the private theory source with public first-party citations and explicit non-claims.
- Added importable `android-memory-evidence`, `android-memory-diagnose`, and `android-memory-remediate` Skills, bilingual workflow documentation, a repository verification gate, and Python 3.8/3.12 CI.
- Added live-capture manifests that preserve per-artifact success, skipped, unsupported, permission, command-failure, and not-collected states with failure hashes.
- Added a self-contained, versioned runtime and knowledge bundle to `android-memory-evidence`, enabling public `npx skills add` installs without a repository clone or environment variable.
- Added deterministic runtime synchronization, isolated copied-Skill tests, a pinned real `npx skills` installation smoke test, and a dedicated public-install CI job.
- Added Apache-2.0 licensing to the repository and every independently installed Skill package.

### Changed
- Live collection now archives command failures instead of collapsing permission, support, and empty-output cases into a generic absence.
- The AI context CLI now has one canonical package implementation shared by the repository wrapper and generated Skill runtime, and every context records its generator version.

### Fixed
- Prevented a single snapshot or mapping name from satisfying regression/leak or native-callsite proof requirements.
- Prevented external absolute paths and unbounded legacy report bodies from entering AI context by default.

## v1.1.0 - 2026-06-05

### Added
- Added Android 17 / API 37 smaps context to panorama reports, including PSS, SwapPSS, native allocator, Scudo, DMA-BUF, graphics, code, stack, and top mapping evidence.
- Added smaps-only panorama analysis for privileged process-mapping investigations.
- Added a structured smaps summary API for parser reuse without polluting JSON stdout.

### Changed
- Updated the Memory Lab demo app to version `1.1.0` with `versionCode = 2`.
- Documented Android 17 memory-limiter evidence boundaries and current release baseline.
- The unified CLI now reads the bundled `.hprof.gz` sample directly and falls back from a missing sibling `.hprof` path to `.hprof.gz`.

### Fixed
- Fixed panorama analysis ignoring `--smaps` despite CLI and documentation support.
- Fixed fresh-checkout HPROF sample commands failing because only the compressed sample is committed.
- Fixed the demo ashmem scenario so mapped buffers remain alive until cleanup and are explicitly unmapped.
