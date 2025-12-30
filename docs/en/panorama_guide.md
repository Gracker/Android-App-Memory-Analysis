# Android Memory Panorama Analysis Guide

## Overview

Panorama Analysis is the core feature of this toolkit, providing deep insights into Android application memory usage by correlating multiple data sources. Unlike traditional single-source analysis, panorama analysis can:

1. **Correlate Java and Native memory**: e.g., link Java Bitmap objects to their Native pixel memory
2. **Track Native memory allocations**: Distinguish between tracked and untracked Native memory
3. **Integrate GPU/Graphics memory**: Including GraphicBuffer and GPU cache
4. **System memory context**: Analyze system memory pressure and Swap/zRAM usage
5. **DMA-BUF analysis**: Track hardware buffer memory for GPU, Camera, Display, etc.
6. **Detect potential issues**: Automatically discover memory anomalies and provide optimization suggestions
7. **Threshold alerts**: Support custom thresholds for CI/CD integration

## Data Sources

Panorama analysis integrates the following data sources:

| Data Source | Command | Key Information | Required |
|-------------|---------|-----------------|----------|
| **meminfo** | `dumpsys meminfo <pkg>` | Memory summary, Native Allocations (precise Bitmap stats) | Recommended |
| **gfxinfo** | `dumpsys gfxinfo <pkg>` | GPU cache, GraphicBuffer, frame stats | Recommended |
| **hprof** | `am dumpheap <pkg> <path>` | Java heap objects, reference chains | Optional |
| **smaps** | `cat /proc/<pid>/smaps` | Detailed memory mapping (requires Root) | Optional |
| **proc_meminfo** | `cat /proc/meminfo` | System memory status, memory pressure | Optional |
| **dmabuf** | `cat /sys/kernel/debug/dma_buf/bufinfo` | DMA-BUF hardware buffers (requires Root) | Optional |
| **zram_swap** | `/proc/swaps` + `/sys/block/zram*/mm_stat` | zRAM compression, Swap usage | Optional |

### Key Discovery: Native Allocations

The **Native Allocations** section in `dumpsys meminfo` provides precise Bitmap statistics:

```
Native Allocations
   Bitmap (malloced):       27                           6939
   Bitmap (nonmalloced):     8                          11873
```

This is the key bridge for correlating Java Bitmap objects with Native memory!

- **malloced**: Bitmap pixel memory allocated via malloc
- **nonmalloced**: Directly allocated Bitmap pixel memory (e.g., ashmem)

## Usage

### One-Click Dump and Analysis

```bash
# List running applications
python3 analyze.py live --list

# Full analysis (including hprof)
python3 analyze.py live --package com.example.app

# Quick analysis (skip time-consuming hprof)
python3 analyze.py live --package com.example.app --skip-hprof

# Dump only, no analysis
python3 analyze.py live --package com.example.app --dump-only -o ./dumps
```

**One-click dump automatically collects**:
- `meminfo.txt` - dumpsys meminfo output
- `gfxinfo.txt` - dumpsys gfxinfo output
- `smaps.txt` - /proc/pid/smaps (requires Root)
- `proc_meminfo.txt` - /proc/meminfo system memory
- `zram_swap.txt` - zRAM/Swap information
- `heap.hprof` - Java heap snapshot (can be skipped)

### Analyze Existing Data

```bash
# Analyze dump directory (auto-reads all files)
python3 analyze.py panorama -d ./dumps/com.example.app_20231225_120000

# Analyze individual files
python3 analyze.py panorama -m meminfo.txt -g gfxinfo.txt

# Full analysis (including all data sources)
python3 analyze.py panorama -m meminfo.txt -g gfxinfo.txt -H app.hprof -S smaps.txt \
    -P proc_meminfo.txt -D dmabuf_debug.txt -Z zram_swap.txt
```

### Output Formats

```bash
# Default terminal output
python3 analyze.py panorama -d ./dump

# JSON output (for automation)
python3 analyze.py panorama -d ./dump --json -o result.json

# Markdown report
python3 analyze.py panorama -d ./dump --markdown -o report.md
```

### Threshold Alerts (CI/CD Integration)

```bash
# Set memory thresholds
python3 tools/panorama_analyzer.py -d ./dump \
    --threshold-pss 300 \
    --threshold-java-heap 100 \
    --threshold-native-heap 80 \
    --threshold-views 500

# Exit code: 0=OK, 1=WARNING, 2=ERROR
```

**Available threshold parameters**:
| Parameter | Description | Unit |
|-----------|-------------|------|
| `--threshold-pss` | Total PSS threshold | MB |
| `--threshold-java-heap` | Java Heap threshold | MB |
| `--threshold-native-heap` | Native Heap threshold | MB |
| `--threshold-graphics` | Graphics threshold | MB |
| `--threshold-native-untracked` | Native untracked ratio threshold | % |
| `--threshold-janky` | Jank rate threshold | % |
| `--threshold-views` | View count threshold | count |
| `--threshold-activities` | Activity count threshold | count |
| `--threshold-bitmaps` | Bitmap count threshold | count |
| `--threshold-bitmap-size` | Bitmap total size threshold | MB |

## Report Interpretation

### Memory Overview

```
────────────────────────────────────────
[ Memory Overview ]
────────────────────────────────────────
Total PSS:                   142.08 MB
Java Heap:                   31.85 MB
Native Heap:                 44.76 MB
Graphics:                    29.27 MB
Code:                        15.29 MB
Stack:                        1.11 MB
```

| Metric | Description | Focus Points |
|--------|-------------|--------------|
| **Total PSS** | Actual physical memory occupied by process | Overall memory usage |
| **Java Heap** | Dalvik/ART heap memory | Java objects, leak detection |
| **Native Heap** | C/C++ heap memory | Native code, JNI |
| **Graphics** | Graphics-related memory | Bitmap, GPU resources |
| **Code** | Code segment memory | DEX, SO libraries |
| **Stack** | Thread stack memory | Thread count |

### System Memory Context

```
────────────────────────────────────────
[ System Memory Context ]
────────────────────────────────────────
System Total: 3579 MB (3.50 GB)
Available:    2099 MB (58.6%)
Pressure:     🟢 LOW
Swap Usage:   256 / 2048 MB (12.5%)
ION Memory:   169 MB
```

| Metric | Description | Focus Points |
|--------|-------------|--------------|
| **System Total** | Device physical memory total | Device specifications |
| **Available** | Memory available for allocation | <20% needs attention |
| **Pressure** | LOW/MEDIUM/HIGH/CRITICAL | HIGH+ affects performance |
| **Swap Usage** | zRAM/Swap usage | High usage indicates memory pressure |
| **ION Memory** | GPU/Camera hardware memory | Related to Graphics |

### zRAM/Swap Analysis

```
────────────────────────────────────────
[ zRAM/Swap Analysis ]
────────────────────────────────────────
Swap Total:       2048.0 MB (1 device)
Swap Used:         512.0 MB (25.0%)
zRAM Disk:        2048.0 MB (1 device)
Original Data:    1200.0 MB
Compressed Data:   280.5 MB
Actual Mem Used:   300.2 MB
Compression Ratio:   4.28x
Space Saved:        76.6%
Memory Saved:      899.8 MB
```

| Metric | Description | Focus Points |
|--------|-------------|--------------|
| **Swap Usage** | Swap space used ratio | >50% needs attention, >80% memory pressure |
| **Compression Ratio** | Original/Compressed | >2x is normal, <1.5x data not very compressible |
| **Memory Saved** | Actual memory saved by compression | zRAM effectiveness |

### DMA-BUF Analysis

```
────────────────────────────────────────
[ DMA-BUF Analysis ]
────────────────────────────────────────
Total DMA-BUF: 156.7 MB (89 buffers)
  GPU Graphics:   120.45 MB (56 buffers)
  Display:         24.00 MB (12 buffers)
  Camera:           8.25 MB (15 buffers)
  Video:            4.00 MB (6 buffers)
```

DMA-BUF is a Linux kernel mechanism for cross-device memory sharing, used in Android for:
- **GPU**: Textures, render buffers
- **Display**: SurfaceFlinger composition buffers
- **Camera**: Camera preview and capture buffers
- **Video**: Video decode/encode buffers

### Bitmap Deep Analysis

```
────────────────────────────────────────
[ Bitmap Deep Analysis ]
────────────────────────────────────────
Bitmap Total: 35 objects (18.37 MB)
  - malloced (Java managed): 27 / 6.78 MB
  - nonmalloced (Native):     8 / 11.59 MB
GPU Cache: 15.34 MB
GraphicBuffer: 12 / 12.45 MB
```

#### Bitmap Types

1. **malloced Bitmap**
   - Pixel memory allocated via `malloc()`
   - Counted in Native Heap
   - Can be freed via `Bitmap.recycle()`

2. **nonmalloced Bitmap**
   - Directly allocated via ashmem or other mechanisms
   - Not counted in Native Heap
   - Usually hardware-accelerated Bitmaps

#### Graphics Memory

1. **GPU Cache**
   - GPU shader cache
   - Texture cache
   - Font cache

2. **GraphicBuffer**
   - Surface-related graphics buffers
   - Video/camera preview buffers
   - Hardware-accelerated rendering buffers

### Native Memory Tracking

```
────────────────────────────────────────
[ Native Memory Tracking ]
────────────────────────────────────────
Native Heap PSS: 44.76 MB
  - Tracked: 39.00 MB (87.1%)
    - Bitmap: 18.37 MB
    - Other malloced: 15.43 MB
    - Other nonmalloced: 5.20 MB
  - Untracked: 5.76 MB (12.9%)
```

#### Tracked Native Memory

Includes:
- Bitmap (malloced + nonmalloced)
- Other malloced allocations
- Other nonmalloced allocations

This memory can be seen in the Native Allocations section of `dumpsys meminfo`.

#### Untracked Native Memory

Formula: `Untracked = Native Heap - Tracked portion`

Possible sources:
- Third-party Native libraries
- Direct allocations in JNI code
- System library allocations
- Memory leaks

**Important Warning**: If untracked Native memory is too high (>30%), it needs attention!

### UI Resource Statistics

```
────────────────────────────────────────
[ UI Resources ]
────────────────────────────────────────
Views: 863 | Activities: 1 | ViewRootImpl: 6 | WebViews: 0
```

| Metric | Normal Range | Abnormal |
|--------|--------------|----------|
| Views | <5000 | Too many may cause UI lag |
| ViewRootImpl | 1-3 | >5 may indicate window leak |
| Activities | 1-5 | >10 may indicate Activity leak |
| WebViews | 0-2 | Each WebView consumes significant memory |

### Frame Statistics

```
────────────────────────────────────────
[ Frame Statistics ]
────────────────────────────────────────
Jank Rate: 12.5%
Frame Latency: p50=8ms | p90=16ms
```

| Metric | Good | Needs Optimization |
|--------|------|-------------------|
| Jank frames | <10% | >20% |
| P50 | <10ms | >16ms |
| P90 | <16ms | >32ms |

## Anomaly Detection

Panorama analysis automatically detects the following anomalies:

### 1. Native Memory Anomaly

```
[!!] UNTRACKED_NATIVE: 44.8 MB untracked Native memory
    -> Use malloc_debug or ASan to detect Native memory allocations
```

### 2. UI Resource Anomaly

```
[!] TOO_MANY_VIEWS: View count 863 is high
    -> Consider using RecyclerView, ViewStub or simplifying layouts
```

### 3. Frame Rate Anomaly

```
[!] HIGH_JANK: Jank rate 39.9% is high
    -> Use Perfetto or Systrace to analyze jank causes
```

## Diff Analysis

Panorama analysis also supports comparing two dumps to find memory growth issues:

```bash
# Compare two dump directories
python3 analyze.py diff -b ./dump_before -a ./dump_after

# Or compare individual meminfo files
python3 analyze.py diff --before-meminfo m1.txt --after-meminfo m2.txt
```

Diff analysis shows:
- Memory changes by category
- View/Activity count changes
- Frame rate changes
- Highlighted items exceeding thresholds

## Optimization Recommendations

### Bitmap Optimization

1. **Recycle unused Bitmaps promptly**
   ```java
   if (bitmap != null && !bitmap.isRecycled()) {
       bitmap.recycle();
       bitmap = null;
   }
   ```

2. **Use appropriate Bitmap configuration**
   ```java
   BitmapFactory.Options options = new BitmapFactory.Options();
   options.inSampleSize = 2;  // Scale down
   options.inPreferredConfig = Bitmap.Config.RGB_565;  // Reduce memory
   ```

3. **Use image loading library's memory management**
   ```java
   Glide.with(context)
       .load(url)
       .override(targetWidth, targetHeight)
       .format(DecodeFormat.PREFER_RGB_565)
       .into(imageView);
   ```

### Native Memory Optimization

1. **Review memory allocations in JNI code**
2. **Use AddressSanitizer to detect leaks**
3. **Audit third-party Native libraries**

### UI Optimization

1. **Reduce View hierarchy depth**
2. **Use ViewStub for lazy loading**
3. **Properly manage Activity lifecycle**

## Integration with Other Tools

| Scenario | Recommended Tool |
|----------|-----------------|
| Java memory leaks | LeakCanary + MAT |
| Native memory leaks | AddressSanitizer |
| Frame rate optimization | Perfetto / Systrace |
| GPU analysis | RenderDoc / Mali Graphics Debugger |

## Version Compatibility

| Android Version | Support Status | Notes |
|-----------------|----------------|-------|
| Android 4.0-7.x | ✅ Fully supported | Some data sources may be unavailable |
| Android 8.0-10 | ✅ Fully supported | - |
| Android 11-13 | ✅ Fully supported | Scudo allocator |
| Android 14+ | ✅ Fully supported | 16KB page support |

## FAQ

### Q: Why does smaps require Root?

A: The `/proc/<pid>/smaps` file requires privileged permissions to read. However, even without smaps, meminfo + gfxinfo can still provide sufficient information for effective analysis.

### Q: What if hprof dump fails?

A: Ensure the application is debuggable or the device is rooted. You can also use `--skip-hprof` to skip hprof dump and use quick mode analysis.

### Q: How to interpret "untracked Native memory"?

A: Untracked Native memory refers to the portion not recorded in meminfo's Native Allocations. It usually comes from:
- Third-party libraries
- Memory allocated directly using mmap
- System allocations

If this portion keeps growing, there may be a Native memory leak.

## References

- [Android Memory Management](https://developer.android.com/topic/performance/memory)
- [dumpsys meminfo Source Code](https://cs.android.com/android/platform/superproject/+/master:frameworks/base/core/jni/android_os_Debug.cpp)
- [Bitmap Memory Management](https://developer.android.com/topic/performance/graphics)
- [DMA-BUF Documentation](https://www.kernel.org/doc/html/latest/driver-api/dma-buf.html)
- [zRAM Documentation](https://www.kernel.org/doc/html/latest/admin-guide/blockdev/zram.html)
