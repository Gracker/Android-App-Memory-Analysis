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

- Python 3.6+
- ADB (Android Debug Bridge) in your PATH or in `tools/` folder
- Connected Android device with USB debugging enabled

### Installation

```bash
git clone https://github.com/aspect-apps/Android-App-Memory-Analysis.git
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
```

#### Individual File Analysis

```bash
# Analyze Java heap (HPROF)
python3 analyze.py hprof demo/hprof_sample/heapdump_latest.hprof

# Analyze native memory (smaps)
python3 analyze.py smaps demo/smaps_sample/smaps

# Analyze meminfo
python3 analyze.py meminfo dump/meminfo.txt

# Analyze gfxinfo
python3 analyze.py gfxinfo dump/gfxinfo.txt

# Traditional combined analysis (HPROF + smaps)
python3 analyze.py combined -H demo/hprof_sample/heapdump_latest.hprof -S demo/smaps_sample/smaps

# Enhanced combined analysis (meminfo-aware, mtrack included)
python3 analyze.py combined --modern --hprof demo/hprof_sample/heapdump_latest.hprof --smaps demo/smaps_sample/smaps --meminfo demo/smaps_sample/meminfo.txt --json-output report.json

# One-command demo shortcut (built-in hprof+smaps+meminfo)
python3 analyze.py combined --demo --json-output demo_report.json
```

Notes:
- `combined` defaults to legacy mode (`combined_analyzer.py`) unless `--modern`, `--meminfo`, `--pid`, `--json-output`, or `--demo` is provided.
- In modern mode with `-p/--pid`, the tool auto-collects `smaps` and tries to collect `dumpsys meminfo -d`.
- The bundled demo HPROF is committed as `heapdump_latest.hprof.gz` to avoid large-file push limits. Extract once before running `.hprof` sample commands: `gzip -dk demo/hprof_sample/heapdump_latest.hprof.gz`.

## What Gets Analyzed?

### Panorama Analysis Output

The panorama analysis provides a comprehensive view of memory usage:

```
================================================================================
                     Android 内存全景分析报告
================================================================================

📊 Memory Overview:
------------------------------
  Total PSS:        245.67 MB
  Java Heap:        89.34 MB
  Native Heap:      34.21 MB
  Graphics:         45.67 MB
  Code:             23.78 MB
  Stack:            1.23 MB

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

1. **Bitmap Correlation**: Links Java Bitmap objects to Native pixel memory
2. **Native Memory Tracking**: Identifies tracked vs untracked Native allocations
3. **GPU Memory Analysis**: GraphicBuffer and GPU cache usage
4. **UI Resource Counting**: View hierarchy and Activity leak detection
5. **Anomaly Detection**: Automatic warnings for potential issues

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

- [English Documentation](./docs/en/)
  - [Analysis Results Guide](./docs/en/analysis_results_interpretation_guide.md)
  - [Meminfo Interpretation](./docs/en/meminfo_interpretation_guide.md)
  - [SMAPS Interpretation](./docs/en/smaps_interpretation_guide.md)

- [Chinese Documentation](./docs/zh/)
  - [分析结果解读指南](./docs/zh/analysis_results_interpretation_guide.md)
- [meminfo 解读](./docs/zh/meminfo_interpretation_guide.md)
- [smaps 解读](./docs/zh/smaps_interpretation_guide.md)
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

This project is open source. See LICENSE file for details.
