# Android 应用内存分析工具集

[English Version](./README.md) | 中文版本

一个用于 Android 应用内存分析的综合工具集，提供 `smaps` 和 `hprof` 两种核心文件的分析功能。

## 核心功能

- **SMAPS 分析**: 解析 `/proc/pid/smaps` 文件，用于分析 Native 内存、系统内存和内存映射文件。支持从 Android 4.0 到 16+ 的所有版本，需要 Root 权限。
- **HPROF 分析**: 解析 Java 堆转储 (`.hprof`) 文件，用于分析 Java 对象、检测内存泄漏和识别大内存对象。此功能无需 Root 权限，兼容所有 Android 版本。

## 快速开始

本仓库经过简化，通过统一的 `analyze.py` Python 脚本提供一个清晰的、跨平台的分析入口。

### 环境要求

- Python 3.6+
- 已配置好 `adb` 的 Android SDK

### 使用方法

主脚本 `analyze.py` 提供 `hprof` 和 `smaps` 两个命令。

1.  **分析 HPROF 文件:**
    使用 `hprof` 命令并提供 `.hprof` 文件的路径。示例文件位于 `demo/hprof_sample` 目录中。
    ```bash
    python3 analyze.py hprof demo/hprof_sample/heapdump-20250921-122155.hprof
    ```

2.  **分析 smaps 文件:**
    使用 `smaps` 命令并提供 `smaps` 文件的路径。示例文件位于 `demo/smaps_sample` 目录中。
    ```bash
    python3 analyze.py smaps demo/smaps_sample/2056_smaps_file.txt
    ```

## 分析工具

本仓库包含位于 `tools/` 目录下的核心分析工具：

- `hprof_parser.py`: 用于 Java HPROF 文件的详细解析器。
- `smaps_parser.py`: 用于进程 `smaps` 文件的综合解析器。
- `memory_analyzer.py`: 一个可以结合 HPROF 和 smaps 进行分析的脚本，但现在推荐使用 `analyze.sh` 作为主入口。

在高级使用场景下，你也可以直接运行这些脚本。例如：
```bash
python3 tools/hprof_parser.py -f demo/hprof_sample/heapdump-20250921-122155.hprof
```

## 文档

如需深入了解内存分析的概念和工具输出，请参阅 `docs/` 目录中的文档。

- [英文文档](./docs/en/)
- [中文文档](./docs/zh/)

## 贡献

欢迎任何形式的贡献。您可以提交 Pull Request 或开启 Issue。
