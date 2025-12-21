# Android App Memory Analysis

[中文版本](./README_zh.md) | English Version

A toolkit for comprehensive Android application memory analysis, featuring two primary analysis tools for `smaps` and `hprof` files.

## Core Features

- **SMAPS Analysis**: Parses `/proc/pid/smaps` files to analyze native memory, system memory, and memory-mapped files. It supports all Android versions from 4.0 to 16+ and requires root access.
- **HPROF Analysis**: Parses Java heap dump (`.hprof`) files to analyze Java objects, detect memory leaks, and identify large memory consumers. It works on all Android versions without requiring root access.

## Quick Start

This repository has been simplified to provide a clear, cross-platform entry point through a single Python script: `analyze.py`.

### Prerequisites

- Python 3.6+
- Android SDK with `adb` in your PATH

### Usage

The main script `analyze.py` provides two commands: `hprof` and `smaps`.

1.  **Analyze an HPROF file:**
    Use the `hprof` command and provide the path to your `.hprof` file. Sample files are in the `demo/hprof_sample` directory.
    ```bash
    python3 analyze.py hprof demo/hprof_sample/heapdump-20250921-122155.hprof
    ```

2.  **Analyze a smaps file:**
    Use the `smaps` command and provide the path to your `smaps` file. Sample files are in the `demo/smaps_sample` directory.
    ```bash
    python3 analyze.py smaps demo/smaps_sample/smaps
    ```

## Analysis Tools

This repository contains the following core analysis tools located in the `tools/` directory:

- `hprof_parser.py`: A detailed parser for Java HPROF files.
- `smaps_parser.py`: A comprehensive parser for process `smaps` files.
- `memory_analyzer.py`: A script that can combine analysis from both HPROF and smaps, though the primary entry point is now `analyze.sh`.

For advanced use cases, you can run these scripts directly. For example:
```bash
python3 tools/hprof_parser.py -f demo/hprof_sample/heapdump-20250921-122155.hprof
```

## Documentation

For a deeper understanding of memory analysis concepts and tool outputs, please refer to the documentation in the `docs/` directory.

- [English Documentation](./docs/en/)
- [Chinese Documentation](./docs/zh/)

## Contributing

Contributions are welcome. Please feel free to submit pull requests or open issues.
