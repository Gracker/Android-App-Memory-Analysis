# Changelog

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
