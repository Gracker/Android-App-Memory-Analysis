# Android Memory Panorama Analysis Guide

## Overview

Panorama Analysis is the core feature of this toolkit, providing deep insights into Android application memory usage by correlating multiple data sources. Unlike traditional single-source analysis, panorama analysis can:

1. **Correlate Java and Native memory**: e.g., link Java Bitmap objects to their Native pixel memory
2. **Track Native memory allocations**: Distinguish between tracked and untracked Native memory
3. **Integrate GPU/Graphics memory**: Including GraphicBuffer and GPU cache
4. **Detect potential issues**: Automatically discover memory anomalies and provide optimization suggestions

## Data Sources

Panorama analysis integrates the following data sources:

| Data Source | Command | Key Information |
|-------------|---------|-----------------|
| **meminfo** | `dumpsys meminfo <pkg>` | Memory summary, Native Allocations (precise Bitmap stats) |
| **gfxinfo** | `dumpsys gfxinfo <pkg>` | GPU cache, GraphicBuffer, frame stats |
| **hprof** | `am dumpheap <pkg> <path>` | Java heap objects, reference chains |
| **smaps** | `cat /proc/<pid>/smaps` | Detailed memory mapping (requires Root) |

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

### Analyze Existing Data

```bash
# Analyze dump directory
python3 analyze.py panorama -d ./dumps/com.example.app_20231225_120000

# Analyze individual files
python3 analyze.py panorama -m meminfo.txt -g gfxinfo.txt

# Full analysis (including hprof and smaps)
python3 analyze.py panorama -m meminfo.txt -g gfxinfo.txt -H app.hprof -S smaps.txt
```

## Report Interpretation

### Memory Overview

```
📊 Memory Overview:
------------------------------
  Total PSS:        245.67 MB
  Java Heap:        89.34 MB
  Native Heap:      34.21 MB
  Graphics:         45.67 MB
  Code:             23.78 MB
  Stack:            1.23 MB
```

| Metric | Description | Focus Points |
|--------|-------------|--------------|
| **Total PSS** | Actual physical memory occupied by process | Overall memory usage |
| **Java Heap** | Dalvik/ART heap memory | Java objects, leak detection |
| **Native Heap** | C/C++ heap memory | Native code, JNI |
| **Graphics** | Graphics-related memory | Bitmap, GPU resources |
| **Code** | Code segment memory | DEX, SO libraries |
| **Stack** | Thread stack memory | Thread count |

### Bitmap Deep Analysis

```
🖼️ Bitmap Deep Analysis:
------------------------------
  Bitmap (malloced):     27 objects    6.78 MB
  Bitmap (nonmalloced):   8 objects   11.59 MB
  GPU Cache:             15.34 MB
  GraphicBuffer:         12.45 MB
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
📈 Native Memory Tracking:
------------------------------
  Tracked Native:        28.45 MB (83.2%)
  Untracked Native:       5.76 MB (16.8%)
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
🎨 UI Resources:
------------------------------
  Views: 1,234
  ViewRootImpl: 3
  Activities: 5
  WebViews: 0
```

| Metric | Normal Range | Abnormal |
|--------|--------------|----------|
| Views | <5000 | Too many may cause UI lag |
| ViewRootImpl | 1-3 | >5 may indicate window leak |
| Activities | 1-5 | >10 may indicate Activity leak |
| WebViews | 0-2 | Each WebView consumes significant memory |

### Frame Statistics

```
📈 Frame Statistics:
------------------------------
  Janky frames: 12.5%
  P50: 8ms
  P90: 16ms
  P95: 24ms
  P99: 48ms
```

| Metric | Good | Needs Optimization |
|--------|------|-------------------|
| Janky frames | <10% | >20% |
| P50 | <10ms | >16ms |
| P90 | <16ms | >32ms |
| P95 | <24ms | >48ms |

## Anomaly Detection

Panorama analysis automatically detects the following anomalies:

### 1. Native Memory Anomaly

```
⚠️ Large untracked Native memory (5.76 MB, 16.8%)
   Possible causes:
   - Third-party Native library allocations
   - Direct JNI allocations
   - Memory leaks
   Recommendation: Use Native memory analysis tools (e.g., AddressSanitizer)
```

### 2. UI Resource Anomaly

```
⚠️ Abnormal Activity count (15)
   Normal running Activity count should be < 5
   Possible Activity leak
   Recommendation: Check Activity lifecycle management
```

### 3. Frame Rate Anomaly

```
⚠️ High janky frame ratio (25%)
   User experience may be affected
   Recommendation: Use Systrace/Perfetto for frame analysis
```

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
