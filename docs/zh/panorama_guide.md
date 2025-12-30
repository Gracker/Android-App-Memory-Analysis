# Android 内存全景分析指南

## 概述

全景分析（Panorama Analysis）是本工具集的核心功能，通过关联多个数据源来提供对 Android 应用内存使用的深度洞察。与传统的单一数据源分析不同，全景分析能够：

1. **关联 Java 和 Native 内存**：例如，将 Java Bitmap 对象与其 Native 像素内存关联
2. **追踪 Native 内存分配**：区分可追踪和未追踪的 Native 内存
3. **整合 GPU/图形内存**：包括 GraphicBuffer 和 GPU 缓存
4. **系统内存上下文**：分析系统内存压力和 Swap/zRAM 使用情况
5. **DMA-BUF 分析**：追踪 GPU、Camera、Display 等硬件缓冲区内存
6. **检测潜在问题**：自动发现内存异常并给出优化建议
7. **阈值告警**：支持自定义阈值，CI/CD 集成

## 数据源

全景分析整合以下数据源：

| 数据源 | 获取命令 | 关键信息 | 是否必需 |
|--------|----------|----------|----------|
| **meminfo** | `dumpsys meminfo <pkg>` | 内存汇总、Native Allocations（精确 Bitmap 统计） | 推荐 |
| **gfxinfo** | `dumpsys gfxinfo <pkg>` | GPU 缓存、GraphicBuffer、帧率统计 | 推荐 |
| **hprof** | `am dumpheap <pkg> <path>` | Java 堆对象、引用链 | 可选 |
| **smaps** | `cat /proc/<pid>/smaps` | 详细内存映射（需要 Root） | 可选 |
| **proc_meminfo** | `cat /proc/meminfo` | 系统内存状态、内存压力 | 可选 |
| **dmabuf** | `cat /sys/kernel/debug/dma_buf/bufinfo` | DMA-BUF 硬件缓冲区（需要 Root） | 可选 |
| **zram_swap** | `/proc/swaps` + `/sys/block/zram*/mm_stat` | zRAM 压缩、Swap 使用情况 | 可选 |

### 关键发现：Native Allocations

`dumpsys meminfo` 中的 **Native Allocations** 部分提供了精确的 Bitmap 统计：

```
Native Allocations
   Bitmap (malloced):       27                           6939
   Bitmap (nonmalloced):     8                          11873
```

这是关联 Java Bitmap 对象和 Native 内存的关键桥梁！

- **malloced**: 通过 malloc 分配的 Bitmap 像素内存
- **nonmalloced**: 直接分配（如 ashmem）的 Bitmap 像素内存

## 使用方法

### 一键 Dump 并分析

```bash
# 列出正在运行的应用
python3 analyze.py live --list

# 完整分析（包括 hprof）
python3 analyze.py live --package com.example.app

# 快速分析（跳过耗时的 hprof）
python3 analyze.py live --package com.example.app --skip-hprof

# 只 Dump 不分析
python3 analyze.py live --package com.example.app --dump-only -o ./dumps
```

**一键 Dump 会自动采集**：
- `meminfo.txt` - dumpsys meminfo 输出
- `gfxinfo.txt` - dumpsys gfxinfo 输出
- `smaps.txt` - /proc/pid/smaps（需要 Root）
- `proc_meminfo.txt` - /proc/meminfo 系统内存
- `zram_swap.txt` - zRAM/Swap 信息
- `heap.hprof` - Java 堆快照（可跳过）

### 分析已有数据

```bash
# 分析 dump 目录（自动读取所有文件）
python3 analyze.py panorama -d ./dumps/com.example.app_20231225_120000

# 分析单独文件
python3 analyze.py panorama -m meminfo.txt -g gfxinfo.txt

# 完整分析（包括所有数据源）
python3 analyze.py panorama -m meminfo.txt -g gfxinfo.txt -H app.hprof -S smaps.txt \
    -P proc_meminfo.txt -D dmabuf_debug.txt -Z zram_swap.txt
```

### 输出格式

```bash
# 默认终端输出
python3 analyze.py panorama -d ./dump

# 输出 JSON 格式（便于自动化处理）
python3 analyze.py panorama -d ./dump --json -o result.json

# 输出 Markdown 报告
python3 analyze.py panorama -d ./dump --markdown -o report.md
```

### 阈值告警（CI/CD 集成）

```bash
# 设置内存阈值
python3 tools/panorama_analyzer.py -d ./dump \
    --threshold-pss 300 \
    --threshold-java-heap 100 \
    --threshold-native-heap 80 \
    --threshold-views 500

# Exit code: 0=正常, 1=WARNING, 2=ERROR
```

**可用的阈值参数**：
| 参数 | 说明 | 单位 |
|------|------|------|
| `--threshold-pss` | Total PSS 阈值 | MB |
| `--threshold-java-heap` | Java Heap 阈值 | MB |
| `--threshold-native-heap` | Native Heap 阈值 | MB |
| `--threshold-graphics` | Graphics 阈值 | MB |
| `--threshold-native-untracked` | Native 未追踪比例阈值 | % |
| `--threshold-janky` | 卡顿率阈值 | % |
| `--threshold-views` | View 数量阈值 | 个 |
| `--threshold-activities` | Activity 数量阈值 | 个 |
| `--threshold-bitmaps` | Bitmap 数量阈值 | 个 |
| `--threshold-bitmap-size` | Bitmap 总大小阈值 | MB |

## 报告解读

### 内存概览

```
📊 内存概览:
------------------------------
  Total PSS:        245.67 MB
  Java Heap:        89.34 MB
  Native Heap:      34.21 MB
  Graphics:         45.67 MB
  Code:             23.78 MB
  Stack:            1.23 MB
```

| 指标 | 说明 | 关注点 |
|------|------|--------|
| **Total PSS** | 进程实际占用的物理内存 | 整体内存使用情况 |
| **Java Heap** | Dalvik/ART 堆内存 | Java 对象、泄漏检测 |
| **Native Heap** | C/C++ 堆内存 | Native 代码、JNI |
| **Graphics** | 图形相关内存 | Bitmap、GPU 资源 |
| **Code** | 代码段内存 | DEX、SO 库 |
| **Stack** | 线程栈内存 | 线程数量 |

### 系统内存上下文

```
────────────────────────────────────────
[ 系统内存上下文 ]
────────────────────────────────────────
系统总内存: 3579 MB (3.50 GB)
系统可用:   2099 MB (58.6%)
内存压力:   🟢 低 (LOW)
Swap 使用:  256 / 2048 MB (12.5%)
ION 内存:   169 MB
```

| 指标 | 说明 | 关注点 |
|------|------|--------|
| **系统总内存** | 设备物理内存总量 | 设备规格参考 |
| **系统可用** | 当前可分配给应用的内存 | <20% 需要关注 |
| **内存压力** | LOW/MEDIUM/HIGH/CRITICAL | HIGH 以上影响性能 |
| **Swap 使用** | zRAM/Swap 使用情况 | 使用率高表示内存紧张 |
| **ION 内存** | GPU/Camera 硬件内存 | 与 Graphics 相关 |

### zRAM/Swap 分析

```
────────────────────────────────────────
[ zRAM/Swap 分析 ]
────────────────────────────────────────
Swap 总量:       2048.0 MB (1 个设备)
Swap 已用:        512.0 MB (25.0%)
zRAM 磁盘:       2048.0 MB (1 个设备)
原始数据:        1200.0 MB
压缩后数据:       280.5 MB
实际内存占用:     300.2 MB
压缩率:            4.28x
节省空间:          76.6%
节省内存:         899.8 MB
```

| 指标 | 说明 | 关注点 |
|------|------|--------|
| **Swap 使用率** | Swap 空间已用比例 | >50% 需要关注，>80% 系统内存紧张 |
| **压缩率** | 原始数据/压缩后数据 | >2x 为正常，<1.5x 数据不太可压缩 |
| **节省内存** | 通过压缩实际节省的内存 | zRAM 的实际效益 |

### DMA-BUF 分析

```
────────────────────────────────────────
[ DMA-BUF 分析 ]
────────────────────────────────────────
总 DMA-BUF: 156.7 MB (89 buffers)
  GPU 图形:   120.45 MB (56 buffers)
  显示:        24.00 MB (12 buffers)
  相机:         8.25 MB (15 buffers)
  视频:         4.00 MB (6 buffers)
```

DMA-BUF 是 Linux 内核的跨设备内存共享机制，在 Android 中用于：
- **GPU**: 纹理、渲染缓冲区
- **Display**: SurfaceFlinger 合成缓冲区
- **Camera**: 相机预览和拍照缓冲区
- **Video**: 视频解码/编码缓冲区

### Bitmap 深度分析

```
🖼️ Bitmap 深度分析:
------------------------------
  Bitmap (malloced):     27 个    6.78 MB
  Bitmap (nonmalloced):   8 个   11.59 MB
  GPU Cache:             15.34 MB
  GraphicBuffer:         12.45 MB
```

#### Bitmap 类型

1. **malloced Bitmap**
   - 通过 `malloc()` 分配的像素内存
   - 计入 Native Heap
   - 可通过 `Bitmap.recycle()` 释放

2. **nonmalloced Bitmap**
   - 通过 ashmem 或其他机制直接分配
   - 不计入 Native Heap
   - 通常是硬件加速 Bitmap

#### 图形内存

1. **GPU Cache**
   - GPU 着色器缓存
   - 纹理缓存
   - 字体缓存

2. **GraphicBuffer**
   - Surface 相关的图形缓冲区
   - 视频/相机预览缓冲区
   - 硬件加速渲染缓冲区

### Native 内存追踪

```
📈 Native 内存追踪:
------------------------------
  可追踪 Native:        28.45 MB (83.2%)
  未追踪 Native:         5.76 MB (16.8%)
```

#### 可追踪 Native 内存

包括：
- Bitmap (malloced + nonmalloced)
- Other malloced allocations
- Other nonmalloced allocations

这些内存可以在 `dumpsys meminfo` 的 Native Allocations 部分看到。

#### 未追踪 Native 内存

计算公式：`未追踪 = Native Heap - 可追踪部分`

可能来源：
- 第三方 Native 库
- JNI 代码中的直接分配
- 系统库分配
- 内存泄漏

**重要警告**：如果未追踪的 Native 内存占比过高（>30%），需要重点关注！

### UI 资源统计

```
🎨 UI 资源统计:
------------------------------
  Views: 1,234
  ViewRootImpl: 3
  Activities: 5
  WebViews: 0
```

| 指标 | 正常范围 | 异常情况 |
|------|----------|----------|
| Views | <5000 | 过多可能导致 UI 卡顿 |
| ViewRootImpl | 1-3 | >5 可能存在窗口泄漏 |
| Activities | 1-5 | >10 可能存在 Activity 泄漏 |
| WebViews | 0-2 | 每个 WebView 消耗大量内存 |

### 帧率统计

```
📈 帧率统计:
------------------------------
  Janky frames: 12.5%
  P50: 8ms
  P90: 16ms
  P95: 24ms
  P99: 48ms
```

| 指标 | 良好 | 需要优化 |
|------|------|----------|
| Janky frames | <10% | >20% |
| P50 | <10ms | >16ms |
| P90 | <16ms | >32ms |
| P95 | <24ms | >48ms |

## 异常检测

全景分析会自动检测以下异常：

### 1. Native 内存异常

```
⚠️ 未追踪的 Native 内存较大 (5.76 MB, 16.8%)
   可能原因:
   - 第三方 Native 库分配
   - JNI 直接分配
   - 内存泄漏
   建议: 使用 Native 内存分析工具（如 AddressSanitizer）进行排查
```

### 2. UI 资源异常

```
⚠️ Activity 数量异常 (15 个)
   正常情况下运行中的 Activity 数量应该 < 5
   可能存在 Activity 泄漏
   建议: 检查 Activity 生命周期管理
```

### 3. 帧率异常

```
⚠️ 卡顿帧比例过高 (25%)
   用户体验可能受到影响
   建议: 使用 Systrace/Perfetto 进行帧率分析
```

## 优化建议

### Bitmap 优化

1. **及时回收不用的 Bitmap**
   ```java
   if (bitmap != null && !bitmap.isRecycled()) {
       bitmap.recycle();
       bitmap = null;
   }
   ```

2. **使用合适的 Bitmap 配置**
   ```java
   BitmapFactory.Options options = new BitmapFactory.Options();
   options.inSampleSize = 2;  // 缩放
   options.inPreferredConfig = Bitmap.Config.RGB_565;  // 减少内存
   ```

3. **使用图片加载库的内存管理**
   ```java
   Glide.with(context)
       .load(url)
       .override(targetWidth, targetHeight)
       .format(DecodeFormat.PREFER_RGB_565)
       .into(imageView);
   ```

### Native 内存优化

1. **检查 JNI 代码中的内存分配**
2. **使用 AddressSanitizer 检测泄漏**
3. **审查第三方 Native 库**

### UI 优化

1. **减少 View 层级**
2. **使用 ViewStub 延迟加载**
3. **正确管理 Activity 生命周期**

## 与其他工具配合

| 场景 | 推荐工具 |
|------|----------|
| Java 内存泄漏 | LeakCanary + MAT |
| Native 内存泄漏 | AddressSanitizer |
| 帧率优化 | Perfetto / Systrace |
| GPU 分析 | RenderDoc / Mali Graphics Debugger |

## 常见问题

### Q: 为什么 smaps 需要 Root？

A: `/proc/<pid>/smaps` 文件需要特权权限才能读取。但即使没有 smaps，meminfo + gfxinfo 仍然能提供足够的信息进行有效分析。

### Q: hprof dump 失败怎么办？

A: 确保应用是 debuggable 的，或者设备已 Root。也可以使用 `--skip-hprof` 跳过 hprof dump，使用快速模式分析。

### Q: 如何解读"未追踪 Native 内存"？

A: 未追踪的 Native 内存是指在 meminfo 的 Native Allocations 中没有记录的部分。通常来自：
- 第三方库
- 直接使用 mmap 分配的内存
- 系统分配

如果这部分内存持续增长，可能存在 Native 内存泄漏。

## 对比分析

全景分析还支持两次 Dump 的对比分析，帮助发现内存增长问题：

```bash
# 对比两个 dump 目录
python3 analyze.py diff -b ./dump_before -a ./dump_after

# 或对比单独的 meminfo 文件
python3 analyze.py diff --before-meminfo m1.txt --after-meminfo m2.txt
```

对比分析会显示：
- 各类内存的增减变化
- View/Activity 数量变化
- 帧率变化
- 高亮显示增长超过阈值的项目

## 版本兼容性

| Android 版本 | 支持状态 | 备注 |
|--------------|----------|------|
| Android 4.0-7.x | ✅ 完全支持 | 部分数据源可能不可用 |
| Android 8.0-10 | ✅ 完全支持 | - |
| Android 11-13 | ✅ 完全支持 | Scudo 分配器 |
| Android 14+ | ✅ 完全支持 | 支持 16KB 页面 |

## 参考资料

- [Android Memory Management](https://developer.android.com/topic/performance/memory)
- [dumpsys meminfo 源码分析](https://cs.android.com/android/platform/superproject/+/master:frameworks/base/core/jni/android_os_Debug.cpp)
- [Bitmap 内存管理](https://developer.android.com/topic/performance/graphics)
- [DMA-BUF 文档](https://www.kernel.org/doc/html/latest/driver-api/dma-buf.html)
- [zRAM 文档](https://www.kernel.org/doc/html/latest/admin-guide/blockdev/zram.html)
