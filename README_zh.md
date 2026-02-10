# Android 应用内存分析工具

[English Version](./README.md) | 中文版本

一套完整的 Android 应用内存分析工具集，支持**一键 Dump**连接设备的内存数据，并进行**多数据源关联分析**以深入洞察内存问题。

## 功能特性

### 核心能力

| 功能 | 说明 | 是否需要 Root |
|------|------|--------------|
| **一键 Dump** | 从连接的设备一键采集所有内存数据 | 部分需要（见下表） |
| **全景分析** | 多数据源关联分析（meminfo + gfxinfo + hprof + smaps） | 否 |
| **HPROF 分析** | Java 堆分析、泄漏检测、大对象追踪 | 否 |
| **SMAPS 分析** | Native 内存映射、详细内存分类 | 是 |
| **Meminfo 分析** | 解析 `dumpsys meminfo`，包括 Native Allocations | 否 |
| **Gfxinfo 分析** | 解析 `dumpsys gfxinfo`，获取 GPU/图形统计 | 否 |

### Root 权限需求

| 数据源 | 无 Root | 有 Root |
|--------|---------|---------|
| dumpsys meminfo | ✅ 完整数据 | ✅ 完整数据 |
| dumpsys gfxinfo | ✅ 完整数据 | ✅ 完整数据 |
| hprof dump | ⚠️ 仅 debuggable 应用 | ✅ 所有应用 |
| smaps | ❌ 权限拒绝 | ✅ 完整数据 |

## 快速开始

### 环境要求

- Python 3.6+
- ADB（Android Debug Bridge）在 PATH 中或放在 `tools/` 目录
- 已连接的 Android 设备并开启 USB 调试

### 安装

```bash
git clone https://github.com/aspect-apps/Android-App-Memory-Analysis.git
cd Android-App-Memory-Analysis
```

### 使用方法

#### 一键 Dump 并分析（推荐）

```bash
# 列出设备上正在运行的应用
python3 analyze.py live --list

# Dump 并分析指定应用
python3 analyze.py live --package com.example.app

# 快速模式（跳过 hprof 以加快速度）
python3 analyze.py live --package com.example.app --skip-hprof

# 仅 Dump 不分析
python3 analyze.py live --package com.example.app --dump-only -o ./dumps
```

#### 全景分析（多数据源关联）

```bash
# 分析已有的 dump 目录
python3 analyze.py panorama -d ./dumps/com.example.app_20231225_120000

# 分析单独的文件
python3 analyze.py panorama -m meminfo.txt -g gfxinfo.txt -H app.hprof -S smaps.txt
```

#### 单独文件分析

```bash
# 分析 Java 堆（HPROF）
python3 analyze.py hprof demo/hprof_sample/heapdump.hprof

# 分析 Native 内存（smaps）
python3 analyze.py smaps demo/smaps_sample/smaps

# 分析 meminfo
python3 analyze.py meminfo dump/meminfo.txt

# 分析 gfxinfo
python3 analyze.py gfxinfo dump/gfxinfo.txt

# 传统联合分析（HPROF + smaps）
python3 analyze.py combined -H demo/hprof.hprof -S demo/smaps.txt

# 增强联合分析（支持 meminfo 口径，包含 mtrack）
python3 analyze.py combined --modern --hprof demo/hprof_sample/heapdump-20250921-122155.hprof --smaps demo/smaps_sample/smaps --meminfo demo/smaps_sample/meminfo.txt --json-output report.json

# 一键运行内置 demo（自动使用 hprof+smaps+meminfo）
python3 analyze.py combined --demo --json-output demo_report.json
```

说明：
- `combined` 默认是传统模式（`combined_analyzer.py`）；当提供 `--modern`、`--meminfo`、`--pid`、`--json-output` 或 `--demo` 时，自动切换增强模式。
- 增强模式下使用 `-p/--pid` 会自动抓取 `smaps`，并尝试抓取 `dumpsys meminfo -d`。

## 分析内容

### 全景分析报告

全景分析提供全面的内存使用视图：

```
================================================================================
                     Android 内存全景分析报告
================================================================================

📊 内存概览:
------------------------------
  Total PSS:        245.67 MB
  Java Heap:        89.34 MB
  Native Heap:      34.21 MB
  Graphics:         45.67 MB
  Code:             23.78 MB
  Stack:            1.23 MB

🖼️ Bitmap 深度分析:
------------------------------
  Bitmap (malloced):     27 个    6.78 MB
  Bitmap (nonmalloced):   8 个   11.59 MB
  GPU Cache:             15.34 MB
  GraphicBuffer:         12.45 MB

📈 Native 内存追踪:
------------------------------
  可追踪 Native:        28.45 MB (83.2%)
  未追踪 Native:         5.76 MB (16.8%)

  ⚠️ 警告: 存在较大的未追踪 Native 内存

🎨 UI 资源统计:
------------------------------
  Views: 1,234
  ViewRootImpl: 3
  Activities: 5
  WebViews: 0
```

### 核心分析特性

1. **Bitmap 关联分析**：将 Java Bitmap 对象与 Native 像素内存关联
2. **Native 内存追踪**：识别可追踪 vs 未追踪的 Native 分配
3. **GPU 内存分析**：GraphicBuffer 和 GPU 缓存使用情况
4. **UI 资源统计**：View 层级和 Activity 泄漏检测
5. **异常检测**：自动检测潜在问题并发出警告

## 项目结构

```
Android-App-Memory-Analysis/
├── analyze.py              # 主入口
├── tools/
│   ├── hprof_parser.py     # HPROF 文件解析器
│   ├── smaps_parser.py     # smaps 文件解析器
│   ├── meminfo_parser.py   # dumpsys meminfo 解析器
│   ├── gfxinfo_parser.py   # dumpsys gfxinfo 解析器
│   ├── panorama_analyzer.py # 多数据源关联分析器
│   ├── combined_analyzer.py # HPROF + smaps 联合分析器
│   ├── memory_analyzer.py  # 增强联合分析器（meminfo/mtrack 关联）
│   ├── live_dumper.py      # 设备实时 Dump
│   ├── hprof_dumper.py     # HPROF Dump 工具
│   └── adb                 # ADB 二进制文件（可选）
├── demo/
│   ├── hprof_sample/       # 示例 HPROF 文件
│   └── smaps_sample/       # 示例 smaps 文件
├── docs/
│   ├── en/                 # 英文文档
│   └── zh/                 # 中文文档
└── pic/                    # 文档图片
```

## 文档

详细的分析结果解读指南：

- [中文文档](./docs/zh/)
  - [分析结果解读指南](./docs/zh/analysis_results_interpretation_guide.md)
  - [meminfo 解读](./docs/zh/meminfo_interpretation_guide.md)
  - [smaps 解读](./docs/zh/smaps_interpretation_guide.md)

- [英文文档](./docs/en/)
  - [Analysis Results Guide](./docs/en/analysis_results_interpretation_guide.md)
  - [Meminfo Interpretation](./docs/en/meminfo_interpretation_guide.md)
  - [SMAPS Interpretation](./docs/en/smaps_interpretation_guide.md)

## 数据源说明

| 数据源 | 命令 | 提供的信息 |
|--------|------|-----------|
| smaps | `cat /proc/<pid>/smaps` | 详细内存映射 |
| hprof | `am dumpheap <pkg> <path>` | Java 堆对象和引用链 |
| meminfo | `dumpsys meminfo <pkg>` | 汇总 + Native Allocations（Bitmap 精确统计） |
| gfxinfo | `dumpsys gfxinfo <pkg>` | GPU 缓存、GraphicBuffer、帧率统计 |

## 相关工具

本工具集可与以下 Android 内存分析工具配合使用：

- **Android Studio Profiler**: 实时内存监控
- **LeakCanary**: 自动内存泄漏检测
- **MAT (Memory Analyzer Tool)**: 深度 HPROF 分析
- **Perfetto**: 系统级追踪

## 贡献

欢迎贡献代码！请随时提交 Pull Request 或开启 Issue。

## 许可证

本项目开源，详见 LICENSE 文件。
