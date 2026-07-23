# Android App Memory Analysis

[中文版本](./README_zh.md) | English Version

A comprehensive toolkit for Android application memory analysis, featuring **one-click live dump** from connected devices and **multi-source correlation analysis** for deep memory insights.

## Features

### Core Capabilities

| Feature | Description | Root Required |
|---------|-------------|---------------|
| **Live Dump** | One-click dump all memory data from connected device | Partial (see below) |
| **Panorama Analysis** | Multi-source correlation (meminfo + gfxinfo + hprof + smaps) | No |
| **HPROF Analysis** | Java heap analysis, leak detection, large object tracking | No |
| **SMAPS Analysis** | Native memory mapping, detailed memory classification | Yes |
| **Meminfo Analysis** | Parse `dumpsys meminfo` including Native Allocations | No |
| **Gfxinfo Analysis** | Parse `dumpsys gfxinfo` for GPU/Graphics stats | No |

### Root Permission Requirements

| Data Source | Without Root | With Root |
|-------------|--------------|-----------|
| dumpsys meminfo | ✅ Full data | ✅ Full data |
| dumpsys gfxinfo | ✅ Full data | ✅ Full data |
| hprof dump | ⚠️ Debuggable apps only | ✅ All apps |
| smaps | ❌ Permission denied | ✅ Full data |

## Quick Start

### Prerequisites

- Python 3.8+
- ADB (Android Debug Bridge) in your PATH or in `tools/` folder
- Connected Android device with USB debugging enabled

### Android 17 / API 37 Compatibility Notes

- The Demo APK now uses `compileSdk = 37`, `targetSdk = 37`, and demo version `1.1.0`, while keeping Android 16 edge-to-edge handling and 16 KB page-size alignment for native `.so` output.
- The toolkit supports Android 4.0 through Android 17+ input formats; parsing logic includes newer allocator and mapping names such as Scudo, GWP-ASan, DMA-BUF, stack/TLS, and JIT caches.
- Panorama analysis now treats `dumpsys meminfo` as the primary row ledger and attaches same-category `smaps` PSS/SwapPSS and mapping evidence to every comparable row. Memtrack rows remain explicitly non-comparable, while smaps-only input still reports native allocator, graphics, DMA-BUF, code, stack, and top mappings.
- Android 17 app memory limits are an Android 17 all-app runtime behavior on supported devices. Live dump now archives `exit_info.txt`, `memory_limiter_status.txt`, package UID, process lists, Android release/sdk, build fingerprint, and page size before requiring PID-dependent artifacts.
- For `smaps` collection, use fallback order for better device compatibility:
  1) `adb shell cat /proc/<pid>/smaps`
  2) `adb shell su -c "cat /proc/<pid>/smaps"`
  3) `adb shell su 0 cat /proc/<pid>/smaps`
- `pidof` is preferred for PID lookup, and `ps -A` parsing is used as fallback.
- See [Android 17 / API 37 Adaptation Review](./docs/en/android_17_adaptation_review.md) for the Android 17 build, memory-limiter, runtime, and evidence checklist.
- See [Android 16 / API 36 Adaptation Review](./docs/en/android_16_adaptation_review.md) for the Android 16 and 16 KB page-size baseline.

### Installation

```bash
git clone https://github.com/Gracker/Android-App-Memory-Analysis.git
cd Android-App-Memory-Analysis
```

### Usage

#### One-Click Live Dump & Analysis (Recommended)

```bash
# List running apps on connected device
python3 analyze.py live --list

# Dump and analyze a specific app
python3 analyze.py live --package com.example.app

# Quick mode (skip hprof for faster results)
python3 analyze.py live --package com.example.app --skip-hprof

# Dump only (no analysis)
python3 analyze.py live --package com.example.app --dump-only -o ./dumps
```

#### Panorama Analysis (Multi-Source Correlation)

```bash
# Analyze existing dump directory
python3 analyze.py panorama -d ./dumps/com.example.app_20231225_120000

# Analyze individual files
python3 analyze.py panorama -m meminfo.txt -g gfxinfo.txt -H app.hprof -S smaps.txt

# Analyze privileged process mappings only
python3 analyze.py panorama -S smaps.txt --json -o smaps_panorama.json
```

#### Individual File Analysis

```bash
# Analyze Java heap (HPROF)
python3 analyze.py hprof demo/hprof_sample/heapdump_latest.hprof.gz

# Analyze native memory (smaps)
python3 analyze.py smaps demo/smaps_sample/smaps

# Analyze meminfo
python3 analyze.py meminfo dump/meminfo.txt

# Analyze gfxinfo
python3 analyze.py gfxinfo dump/gfxinfo.txt

# Traditional combined analysis (HPROF + smaps)
python3 analyze.py combined -H demo/hprof_sample/heapdump_latest.hprof.gz -S demo/smaps_sample/smaps

# Enhanced combined analysis (meminfo-aware, mtrack included)
python3 analyze.py combined --modern --hprof demo/hprof_sample/heapdump_latest.hprof.gz --smaps demo/smaps_sample/smaps --meminfo demo/smaps_sample/meminfo.txt --json-output report.json

# One-command demo shortcut (built-in hprof+smaps+meminfo)
python3 analyze.py combined --demo --json-output demo_report.json
```

Notes:
- `combined` defaults to legacy mode (`combined_analyzer.py`) unless `--modern`, `--meminfo`, `--pid`, `--json-output`, or `--demo` is provided.
- In modern mode with `-p/--pid`, the tool auto-collects `smaps` and tries to collect `dumpsys meminfo -d`.
- The bundled demo HPROF is committed as `heapdump_latest.hprof.gz` to avoid large-file push limits. The unified `analyze.py` entry point reads `.hprof.gz` directly. If an old sample path ending in `.hprof` is missing but a sibling `.hprof.gz` exists, it automatically falls back to the packaged sample.

## AI Evidence Context and Skills

The provider-neutral `ai-context` protocol validates artifacts, separates accounting domains, exposes missing/conflicting input, and selects versioned theory records with official sources before any AI interprets the case. It never uploads artifacts or calls an external model.

New live dumps include a structured `manifest.json`, so skipped, unsupported, permission-denied, failed, and genuinely collected states remain distinguishable instead of becoming a generic “missing” file.

The normal RD workflow is folder-first: download the complete QA handoff into one directory, then provide that directory plus the issue title or symptom. The context recursively inventories every regular file, treats names as hints rather than truth, classifies supported evidence by content, preserves multiple artifacts, and reports unclassified files and scan limits instead of silently ignoring them. Recognized evidence also augments intent routing, so a vague “memory increased” issue can evaluate the Java, native, graphics, or system-pressure branch actually present in the folder. It recognizes Android/logcat logs (plain text or gzip) and PNG/JPEG/WebP screenshots alongside dumps and reports.

Plain, gzip, and bugreport ZIP logs receive a bounded scan for LeakCanary, resource-leak, OOM, GC, JNI, graphics/database/Binder, LMKD, and kernel-OOM signals, but no raw log lines or screenshot pixels are embedded. Signals carry line numbers/hashes (and ZIP member binding); screenshots carry dimensions/hashes and must be visually inspected before use.

```bash
python3 analyze.py ai-context \
  -d ./qa-handoff/ANDROID-1234 \
  --question "Native memory keeps growing after the screen exits" \
  --format json \
  -o android-memory-context.json
```

Importable Skills live under `skills/`:

- `android-memory-evidence` validates partial or inaccurate inputs and gives exact capture guidance;
- `android-memory-diagnose` combines artifact-bound facts with versioned theory;
- `android-memory-remediate` changes code only after ownership and mechanism are supported, then verifies the matching scenario.

Install the complete public package into the current AI project (Node.js 18+ and Python 3.8+):

```bash
npx skills add Gracker/Android-App-Memory-Analysis \
  --skill '*'
```

For a global Codex install, add `--agent codex --global`. The Evidence Skill includes its validated runtime and knowledge catalog, so installed copies can create contexts without cloning this repository or setting `ANDROID_MEMORY_ANALYSIS_ROOT`. The full analyzer checkout is only an optional enhancement for live capture, panorama, diff, and helper-driven Perfetto workflows.

For a second pass, point the Skill at the same complete QA folder and describe whether the prior result should be challenged or extended. It rescans the whole tree, recognizes prior contexts/reports, compares added/changed/missing/unchanged evidence, and requires every material old claim to be confirmed, revised, retracted, or left unresolved. Prior material outside the folder can be supplied with repeatable `--previous-context` and `--previous-analysis` options.

See [Android Memory AI Workflow](./docs/en/ai_workflow.md) for architecture, schema, installation, refresh, privacy boundaries, and verification.

## What Gets Analyzed?

### Panorama Analysis Output

The panorama analysis starts from the familiar `dumpsys meminfo` table, preserves
every row in source order, and uses `smaps` as drill-down evidence rather than a
separate replacement summary:

```
[ meminfo Primary Ledger + smaps Row Evidence ]
Category          Mem PSS  PrivDirty  SwapPss  smaps PSS  Delta  Status
Native Heap          80860      80824        25      80860     +0  aligned
Dalvik Heap          59439      59420        69      59439     +0  aligned
EGL mtrack           54432      54432         0          -      -  not-comparable
...
TOTAL               337790     293788       162          -      -  see-total

Row interpretation:
- Native Heap: smaps identifies Scudo primary/secondary mappings without
  overwriting the meminfo Native Heap value.
- EGL mtrack: driver/HAL attribution is preserved and is not subtracted from
  `/proc/<pid>/smaps`.

🖼️ Bitmap Deep Analysis:
------------------------------
  Bitmap (malloced):     27 objects    6.78 MB
  Bitmap (nonmalloced):   8 objects   11.59 MB
  GPU Cache:             15.34 MB
  GraphicBuffer:         12.45 MB

📈 Native Memory Tracking:
------------------------------
  Tracked Native:        28.45 MB (83.2%)
  Untracked Native:       5.76 MB (16.8%)

  ⚠️ Warning: Significant untracked Native memory detected

🎨 UI Resources:
------------------------------
  Views: 1,234
  ViewRootImpl: 3
  Activities: 5
  WebViews: 0
```

### Key Analysis Features

1. **meminfo-first row ledger**: Preserves every familiar meminfo category and field
2. **smaps row supplements**: Adds category PSS/SwapPSS, allocator subtypes, mappings, and explicit reconciliation
3. **Bitmap Correlation**: Links Java Bitmap objects to Native pixel memory
4. **Native Memory Tracking**: Identifies tracked vs untracked Native allocations
5. **GPU Memory Analysis**: GraphicBuffer and GPU cache usage
6. **UI Resource Counting**: View hierarchy and Activity leak detection
7. **Anomaly Detection**: Automatic warnings for potential issues

## Project Structure

```
Android-App-Memory-Analysis/
├── analyze.py              # Main entry point
├── tools/
│   ├── hprof_parser.py     # HPROF file parser
│   ├── smaps_parser.py     # smaps file parser
│   ├── meminfo_parser.py   # dumpsys meminfo parser
│   ├── gfxinfo_parser.py   # dumpsys gfxinfo parser
│   ├── panorama_analyzer.py # Multi-source correlation analyzer
│   ├── combined_analyzer.py # HPROF + smaps combined analyzer
│   ├── memory_analyzer.py  # Enhanced combined analyzer with meminfo/mtrack correlation
│   ├── live_dumper.py      # Live dump from device
│   ├── hprof_dumper.py     # HPROF dump utility
│   └── adb                 # ADB binary (optional)
├── demo/
│   ├── hprof_sample/       # Latest sample HPROF + analysis output
│   ├── smaps_sample/       # Latest sample smaps/meminfo/showmap/gfxinfo + reports
│   └── memory-lab/         # Demo APK project used to regenerate sample datasets
├── docs/
│   ├── en/                 # English documentation
│   └── zh/                 # Chinese documentation
└── pic/                    # Images for documentation
```

## Documentation

For detailed guides on interpreting analysis results:

- [English Learning Path](./docs/en/README.md)
  - [Analysis Results Guide](./docs/en/analysis_results_interpretation_guide.md)
  - [Meminfo Interpretation](./docs/en/meminfo_interpretation_guide.md)
  - [SMAPS Interpretation](./docs/en/smaps_interpretation_guide.md)
  - [Android 17 / API 37 Adaptation Review](./docs/en/android_17_adaptation_review.md)
  - [Android 16 / API 36 Adaptation Review](./docs/en/android_16_adaptation_review.md)
  - [Teaching Playbook](./docs/en/teaching_playbook.md)

- [Chinese Learning Path](./docs/zh/README.md)
  - [分析结果解读指南](./docs/zh/analysis_results_interpretation_guide.md)
  - [meminfo 解读](./docs/zh/meminfo_interpretation_guide.md)
  - [smaps 解读](./docs/zh/smaps_interpretation_guide.md)
  - [Android 17 / API 37 适配 Review](./docs/zh/android_17_adaptation_review.md)
  - [教学实践手册](./docs/zh/teaching_playbook.md)
  - [Demo APK case study (Chinese)](./docs/zh/memory_lab_demo_case_study.md)

## Data Sources

| Data Source | Command | Information Provided |
|-------------|---------|---------------------|
| smaps | `cat /proc/<pid>/smaps` | Detailed memory mapping |
| hprof | `am dumpheap <pkg> <path>` | Java heap objects and references |
| meminfo | `dumpsys meminfo <pkg>` | Summary + Native Allocations (Bitmap stats) |
| gfxinfo | `dumpsys gfxinfo <pkg>` | GPU cache, GraphicBuffer, frame stats |

## Related Tools

This toolkit complements these Android memory analysis tools:

- **Android Studio Profiler**: Real-time memory monitoring
- **LeakCanary**: Automatic memory leak detection
- **MAT (Memory Analyzer Tool)**: Deep HPROF analysis
- **Perfetto**: System-wide tracing

## Contributing

Contributions are welcome! Please feel free to submit pull requests or open issues.

## License

Licensed under the [Apache License 2.0](./LICENSE). Each independently installed Skill includes the same license text.
