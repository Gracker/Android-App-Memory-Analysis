# Android Application Memory Debugging Complete Guide

> **Version**: 2.0  
> **Updated**: 2025-01  
> **Scope**: Android 4.0 - Android 15+

## Table of Contents

1. [Overview](#1-overview)
2. [Android Memory Architecture](#2-android-memory-architecture)
3. [Memory Metrics](#3-memory-metrics)
4. [smaps Mechanism](#4-smaps-mechanism)
5. [Memory Type Classification](#5-memory-type-classification)
6. [Memory Analysis Tools](#6-memory-analysis-tools)
7. [Common Issue Diagnosis](#7-common-issue-diagnosis)
8. [Optimization Strategies](#8-optimization-strategies)
9. [Modern Android Features](#9-modern-android-features)
10. [References](#10-references)

---

## 1. Overview

### 1.1 Why Memory Management Matters

Android runs on resource-constrained mobile devices. Poor memory management leads to:

- **Performance degradation**: Increased GC frequency, main thread blocking
- **System intervention**: LowMemoryKiller terminates app processes
- **User experience**: App stuttering, crashes, data loss
- **Device heating**: Frequent memory operations increase CPU load

### 1.2 Device Memory Variations

Android device memory limits vary significantly:

```java
ActivityManager am = (ActivityManager) getSystemService(Context.ACTIVITY_SERVICE);
int memoryClass = am.getMemoryClass();        // Normal app memory limit (MB)
int largeMemoryClass = am.getLargeMemoryClass(); // Limit when largeHeap=true

// Typical device memory limits:
// Entry-level: 64-128 MB
// Mid-range: 192-256 MB
// Flagship: 512 MB+
```

### 1.3 Typical Memory Problem Symptoms

| Symptom | Possible Cause | Diagnosis Direction |
|---------|----------------|---------------------|
| App gradually slows after launch | Memory leak | Activity/Fragment reference check |
| Memory spikes after image loading | Unoptimized Bitmap | Image caching strategy |
| Background app frequently killed | High memory usage | PSS analysis |
| Native crash | C/C++ memory error | AddressSanitizer |

---

## 2. Android Memory Architecture

### 2.1 System Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     User Space                               │
├─────────────────────────────────────────────────────────────┤
│  Application Layer                                           │
│  ├── ART Runtime                                            │
│  │   ├── Young Generation                                   │
│  │   ├── Old Generation                                     │
│  │   └── Large Object Space                                 │
│  ├── Native Layer                                           │
│  │   ├── Scudo/jemalloc Allocator                          │
│  │   ├── JNI References                                     │
│  │   └── Shared Libraries (.so)                            │
│  └── Graphics Layer                                         │
│      ├── Surface/GraphicBuffer                              │
│      └── GPU Memory                                         │
├─────────────────────────────────────────────────────────────┤
│                     Kernel Space                             │
├─────────────────────────────────────────────────────────────┤
│  ├── Page Table Management (4KB/16KB)                       │
│  ├── Virtual Memory Subsystem                               │
│  ├── Memory Reclaim (LRU, Compaction)                       │
│  └── Memory Protection (ASLR, DEP)                          │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Java Heap Structure

ART (Android Runtime) uses generational garbage collection:

#### Young Generation
- **Contents**: Newly created objects
- **GC Strategy**: Frequent Minor GC, fast
- **Typical Objects**: Temporary variables, method-local objects

```java
public void processData() {
    // These objects are allocated in Young Generation
    String temp = "temporary";
    List<String> localList = new ArrayList<>();
    Intent intent = new Intent();
}
```

#### Old Generation
- **Contents**: Long-lived objects
- **GC Strategy**: Less frequent Major GC, takes longer
- **Typical Objects**: Singletons, caches, Application-level objects

```java
public class AppCache {
    private static AppCache instance; // Old generation
    private Map<String, Object> cache = new HashMap<>(); // Old generation
}
```

#### Large Object Space
- **Contents**: Objects larger than 12KB (Android 8.0+) or 32KB
- **Typical Objects**: Bitmap, large arrays

```java
// Directly allocated to Large Object Space
Bitmap bitmap = Bitmap.createBitmap(2048, 2048, Bitmap.Config.ARGB_8888);
// Calculation: 2048 × 2048 × 4 = 16 MB
```

### 2.3 Native Heap Structure

Native memory is directly managed by C/C++ code:

```cpp
// Native memory allocation
void* buffer = malloc(1024 * 1024); // Allocate 1MB

// Must be manually freed
free(buffer);
buffer = nullptr;
```

**Characteristics**:
- Not limited by Java Heap size
- Requires manual lifecycle management
- Memory leaks won't trigger Java OOM, but cause system memory shortage

### 2.4 Graphics Memory

Graphics memory includes:
- **Surface**: UI rendering buffers
- **GraphicBuffer**: Cross-process graphics data sharing
- **GPU Textures**: OpenGL/Vulkan texture data

```java
// Memory usage for different Bitmap formats (1920×1080)
// ARGB_8888: 1920 × 1080 × 4 = 8.29 MB
// RGB_565:   1920 × 1080 × 2 = 4.15 MB
// ALPHA_8:   1920 × 1080 × 1 = 2.07 MB
```

---

## 3. Memory Metrics

### 3.1 Core Metric Definitions

| Metric | Full Name | Definition | Usage |
|--------|-----------|------------|-------|
| **VSS** | Virtual Set Size | Process virtual address space size | Low reference value |
| **RSS** | Resident Set Size | Actual physical memory occupied | Includes shared memory, double-counted |
| **PSS** | Proportional Set Size | Proportionally allocated memory | **Most important metric** |
| **USS** | Unique Set Size | Process-exclusive memory | Memory freed when process exits |

### 3.2 PSS Calculation Method

PSS solves the shared memory double-counting problem:

```
PSS = Private Memory + (Shared Memory / Number of Sharing Processes)
```

**Calculation Example**:
```
Process A memory composition:
- Private memory: 50 MB
- Shared library libc.so: 2 MB (shared by 10 processes)
- Shared library liblog.so: 1 MB (shared by 5 processes)

PSS = 50 + (2/10) + (1/5) = 50.4 MB
```

### 3.3 Metric Relationships

```
USS ≤ PSS ≤ RSS ≤ VSS
```

- **USS**: Memory that can be freed when process is killed
- **PSS**: Process's true contribution to system memory
- **RSS**: Physical memory currently used by process (including shared)
- **VSS**: Virtual address space accessible by process

### 3.4 Obtaining Memory Metrics

```bash
# Method 1: dumpsys meminfo
adb shell dumpsys meminfo <package_name>

# Method 2: /proc/pid/smaps (requires root)
adb shell "su -c 'cat /proc/<pid>/smaps'"

# Method 3: /proc/pid/statm
adb shell cat /proc/<pid>/statm
```

---

## 4. smaps Mechanism

### 4.1 smaps Overview

`/proc/pid/smaps` is a virtual file provided by the Linux kernel containing detailed information about process memory mappings. It is the lowest-level and most accurate data source for Android memory analysis.

### 4.2 smaps Data Structure

Format for each memory region entry:

```
12c00000-13000000 rw-p 00000000 00:00 0    [anon:dalvik-main space]
Size:               4096 kB
Rss:                2048 kB
Pss:                2048 kB
Shared_Clean:          0 kB
Shared_Dirty:          0 kB
Private_Clean:         0 kB
Private_Dirty:      2048 kB
Referenced:         2048 kB
Anonymous:          2048 kB
LazyFree:              0 kB
AnonHugePages:         0 kB
ShmemPmdMapped:        0 kB
Shared_Hugetlb:        0 kB
Private_Hugetlb:       0 kB
Swap:                  0 kB
SwapPss:               0 kB
Locked:                0 kB
```

### 4.3 Field Explanations

| Field | Description |
|-------|-------------|
| **Address Range** | `12c00000-13000000` virtual address start-end |
| **Permissions** | `rw-p` (r=read, w=write, x=execute, p=private, s=shared) |
| **Size** | Virtual memory size |
| **Rss** | Actual physical memory usage |
| **Pss** | Proportionally allocated physical memory |
| **Private_Dirty** | Private dirty pages (modified private memory) |
| **Shared_Dirty** | Shared dirty pages (modified shared memory) |
| **Swap** | Memory swapped to disk |
| **Anonymous** | Anonymous memory (non-file mapped) |

### 4.4 Obtaining smaps Data

```bash
# Get complete smaps
adb shell "su -c 'cat /proc/<pid>/smaps'" > smaps.txt

# Get summary data (Android 9+)
adb shell "su -c 'cat /proc/<pid>/smaps_rollup'"

# Analyze with project tools
python3 tools/smaps_parser.py -f smaps.txt
```

---

## 5. Memory Type Classification

### 5.1 Android Memory Region Identifiers

Memory region names in smaps reflect memory purposes:

#### Java Heap Related
```bash
[anon:dalvik-main space]              # Main heap space
[anon:dalvik-large object space]      # Large object space
[anon:dalvik-zygote space]            # Zygote shared space
[anon:dalvik-non moving space]        # Non-moving object space
```

#### Native Heap Related
```bash
[anon:libc_malloc]                    # Standard C library allocation
[anon:scudo:primary]                  # Scudo primary allocator (Android 11+)
[anon:scudo:secondary]                # Scudo large object allocator
[anon:GWP-ASan]                       # Memory error detection (Android 11+)
```

#### Code and Libraries
```bash
/data/app/.../base.apk                # APK file mapping
/system/lib64/libc.so                 # System library
/apex/com.android.art/lib64/libart.so # APEX module
*.oat                                  # Pre-compiled code
*.art                                  # ART runtime image
*.vdex                                 # Verified DEX file
```

#### Graphics Related
```bash
/dev/kgsl-3d0                         # Qualcomm GPU
/dev/mali0                            # ARM Mali GPU
/dev/dma_heap/system                  # DMA buffer
```

#### Others
```bash
[stack]                               # Main thread stack
[anon:stack_and_tls:<tid>]            # Worker thread stack
[anon:thread signal stack]            # Signal handling stack
```

### 5.2 Memory Type Classification Table

| Type ID | Name | Description | Typical Size |
|---------|------|-------------|--------------|
| 0 | HEAP_UNKNOWN | Unclassified memory | Few MB |
| 1 | HEAP_DALVIK | Java heap | 20-200 MB |
| 2 | HEAP_NATIVE | Native heap | 10-150 MB |
| 4 | HEAP_STACK | Thread stacks | 5-50 MB |
| 6 | HEAP_ASHMEM | Anonymous shared memory | Varies |
| 7 | HEAP_GL_DEV | GPU device memory | 20-100 MB |
| 9 | HEAP_SO | Dynamic libraries | 20-100 MB |
| 11 | HEAP_APK | APK mapping | 10-50 MB |
| 17 | HEAP_GRAPHICS | Graphics memory | 20-150 MB |
| 40 | HEAP_SCUDO | Scudo allocator | 10-100 MB |
| 41 | HEAP_GWP_ASAN | GWP-ASan | Few MB |
| 43 | HEAP_APEX | APEX modules | 10-50 MB |

---

## 6. Memory Analysis Tools

### 6.1 Tool Comparison

| Tool | Use Case | Advantages | Limitations |
|------|----------|------------|-------------|
| **Android Studio Memory Profiler** | Development debugging | Real-time monitoring, visualization | Requires USB connection |
| **LeakCanary** | Leak detection | Automatic detection, detailed reports | Java leaks only |
| **KOOM** | OOM prevention | Production-ready, AI-driven | Complex configuration |
| **MAT** | Heap analysis | Deep analysis, powerful queries | Steep learning curve |
| **dumpsys meminfo** | Quick check | Always available | Limited information |
| **smaps analysis tools** | Deep analysis | Most detailed, offline analysis | Requires root |
| **This project's tools** | Panorama analysis | Multi-source integration, auto diagnosis | - |

### 6.2 Android Studio Memory Profiler

**Features**:
- Real-time memory usage charts
- Heap Dump analysis
- Memory allocation tracking
- Object reference chain viewing

**Usage**:
1. Connect device and run app
2. View → Tool Windows → Profiler
3. Select Memory module
4. Click "Capture heap dump" to get heap snapshot

**Analysis Tips**:
```java
// Force GC before capturing at key points
System.gc();
System.runFinalization();
System.gc();
// Then click "Capture heap dump" in Profiler
```

### 6.3 dumpsys meminfo

```bash
# Basic information
adb shell dumpsys meminfo <package>

# Detailed information
adb shell dumpsys meminfo -d <package>

# System overview
adb shell dumpsys meminfo
```

**Output Interpretation**:
```
                   Pss      Pss   Shared  Private   Shared  Private     Heap
                 Total    Clean    Dirty    Dirty    Clean    Clean     Size
                ------   ------   ------   ------   ------   ------   ------
  Native Heap    24482        0     2692    24380        0        0    39580
  Dalvik Heap     3783        0     4596     3588        0        0    28651
 Dalvik Other     1755        0     1532     1376        0        0
        Stack      976        0       12      976        0        0
       Ashmem        2        0        4        0       16        0
      Gfx dev     5884        0        0     5884        0        0
    Other dev      136        0      216        0        0      136
     .so mmap     3294      168     4280      228    22656      168
    .apk mmap     3048      448        0        0    15468      448
    .art mmap     2732        4    16136     2012      156        4
      Unknown      793        0      520      784        0        0
        TOTAL   105529      632    30100    95048    61056      848
```

### 6.4 Using This Project's Tools

#### One-Click Dump Analysis
```bash
# List running applications
python3 analyze.py live --list

# Full analysis
python3 analyze.py live --package com.example.app

# Quick analysis (skip HPROF)
python3 analyze.py live --package com.example.app --skip-hprof

# Dump only, no analysis
python3 analyze.py live --package com.example.app --dump-only -o ./dumps
```

#### Analyzing Existing Data
```bash
# Analyze dump directory
python3 analyze.py panorama -d ./dumps/com.example.app_20250101_120000

# Analyze individual files
python3 analyze.py panorama -m meminfo.txt -g gfxinfo.txt -S smaps.txt

# Output JSON/Markdown
python3 analyze.py panorama -d ./dump --json -o result.json
python3 analyze.py panorama -d ./dump --markdown -o report.md
```

#### Standalone smaps Analysis
```bash
python3 tools/smaps_parser.py -p <pid>
python3 tools/smaps_parser.py -f smaps.txt -o analysis.txt
```

---

## 7. Common Issue Diagnosis

### 7.1 Activity Memory Leak

**Symptoms**:
- Memory continues to grow after multiple screen rotations
- Multiple Activity instances in Heap Dump

**Common Causes**:

```java
// ❌ Wrong: Static variable holds Activity reference
public class Utils {
    private static Context sContext;
    public static void init(Context context) {
        sContext = context; // Activity cannot be recycled
    }
}

// ❌ Wrong: Non-static inner class Handler
public class LeakyActivity extends Activity {
    private Handler mHandler = new Handler() {
        @Override
        public void handleMessage(Message msg) {
            // Implicitly holds Activity reference
        }
    };
}
```

**Fixes**:

```java
// ✅ Correct: Use ApplicationContext
public class Utils {
    private static Context sAppContext;
    public static void init(Context context) {
        sAppContext = context.getApplicationContext();
    }
}

// ✅ Correct: Static inner class + WeakReference
public class FixedActivity extends Activity {
    private static class SafeHandler extends Handler {
        private final WeakReference<FixedActivity> mActivityRef;
        
        SafeHandler(FixedActivity activity) {
            mActivityRef = new WeakReference<>(activity);
        }
        
        @Override
        public void handleMessage(Message msg) {
            FixedActivity activity = mActivityRef.get();
            if (activity != null && !activity.isFinishing()) {
                // Safe to process
            }
        }
    }
}
```

### 7.2 Bitmap Memory Issues

**Symptoms**:
- Memory spikes dramatically after image loading
- Large Object Space over-occupied
- Frequent OOM

**Optimization Strategies**:

```java
// 1. Sample load large images
BitmapFactory.Options options = new BitmapFactory.Options();
options.inJustDecodeBounds = true;
BitmapFactory.decodeFile(path, options);

options.inSampleSize = calculateInSampleSize(options, reqWidth, reqHeight);
options.inJustDecodeBounds = false;
Bitmap bitmap = BitmapFactory.decodeFile(path, options);

// 2. Use more memory-efficient format
options.inPreferredConfig = Bitmap.Config.RGB_565; // Save 50% memory

// 3. Use Bitmap reuse (Android 4.4+)
options.inBitmap = getReusableBitmap();
options.inMutable = true;

// 4. Recycle promptly
if (bitmap != null && !bitmap.isRecycled()) {
    bitmap.recycle();
    bitmap = null;
}

// 5. Use image loading libraries
Glide.with(context)
    .load(url)
    .override(targetWidth, targetHeight)
    .format(DecodeFormat.PREFER_RGB_565)
    .diskCacheStrategy(DiskCacheStrategy.ALL)
    .into(imageView);
```

### 7.3 Native Memory Leak

**Symptoms**:
- Native Heap continuously growing
- `[anon:scudo:*]` or `[anon:libc_malloc]` too large in smaps
- Non-Java OOM crashes

**Diagnostic Tools**:

```bash
# AddressSanitizer (enable at compile time)
# Add in CMakeLists.txt:
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -fsanitize=address")

# Use malloc_debug
adb shell setprop libc.debug.malloc.program <package>
adb shell setprop libc.debug.malloc.options "backtrace leak_track"
```

**Fixes**:

```cpp
// ❌ Wrong: Forgot to free
void processData() {
    char* buffer = (char*)malloc(1024);
    // ... process data
    // Forgot free(buffer)
}

// ✅ Correct: Use RAII
void processData() {
    std::unique_ptr<char[]> buffer(new char[1024]);
    // Automatically freed
}

// ✅ Correct: Ensure paired calls
void processData() {
    char* buffer = (char*)malloc(1024);
    try {
        // ... process data
    } finally {
        free(buffer);
    }
}
```

### 7.4 Graphics Memory Overload

**Symptoms**:
- High Graphics/Gfx dev memory
- UI rendering stuttering
- GPU-related crashes

**Diagnostic Methods**:

```bash
# Check graphics memory
adb shell dumpsys gfxinfo <package>

# Check GPU memory details
adb shell cat /d/kgsl/proc/<pid>/mem
```

**Optimization Strategies**:

```java
// 1. Reduce overdraw
// Remove unnecessary backgrounds
android:background="@null"

// 2. Use hardware layers carefully
view.setLayerType(View.LAYER_TYPE_HARDWARE, null);
// Disable after use
view.setLayerType(View.LAYER_TYPE_NONE, null);

// 3. Release OpenGL resources promptly
GLES20.glDeleteTextures(1, textureIds, 0);
GLES20.glDeleteBuffers(1, bufferIds, 0);
```

---

## 8. Optimization Strategies

### 8.1 Memory Optimization Checklist

#### Development Phase
- [ ] Integrate LeakCanary for memory leak detection
- [ ] Avoid static variables holding Context/View
- [ ] Use WeakReference for callbacks
- [ ] Unregister listeners in onDestroy

#### Image Processing
- [ ] Use sampling for large images
- [ ] Choose appropriate Bitmap format
- [ ] Implement three-level caching strategy
- [ ] Recycle unused Bitmaps promptly

#### Native Code
- [ ] Use smart pointers for memory management
- [ ] Check malloc/free pairing
- [ ] Enable AddressSanitizer for testing

#### Pre-Release
- [ ] Stress test memory behavior
- [ ] Establish memory baseline
- [ ] Configure memory monitoring alerts

### 8.2 Memory Monitoring Script

```bash
#!/bin/bash
# memory_monitor.sh

PACKAGE=$1
INTERVAL=${2:-60}
LOG_DIR="./memory_logs"

mkdir -p $LOG_DIR

while true; do
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    PID=$(adb shell pidof $PACKAGE 2>/dev/null)
    
    if [ -n "$PID" ]; then
        # Get memory info
        adb shell dumpsys meminfo $PACKAGE > "$LOG_DIR/meminfo_$TIMESTAMP.txt"
        
        # Extract PSS
        PSS=$(grep "TOTAL PSS" "$LOG_DIR/meminfo_$TIMESTAMP.txt" | awk '{print $3}')
        echo "$TIMESTAMP: PSS = $PSS KB"
        
        # Check threshold
        if [ "$PSS" -gt 300000 ]; then
            echo "⚠️ WARNING: Memory exceeds 300MB!"
        fi
    else
        echo "$TIMESTAMP: App not running"
    fi
    
    sleep $INTERVAL
done
```

### 8.3 CI/CD Integration

```bash
# Set threshold checks
python3 tools/panorama_analyzer.py -d ./dump \
    --threshold-pss 200 \
    --threshold-java-heap 80 \
    --threshold-native-heap 60 \
    --threshold-views 500

# Check exit code
# 0 = OK
# 1 = WARNING
# 2 = ERROR
```

---

## 9. Modern Android Features

### 9.1 Scudo Security Allocator (Android 11+)

Scudo is a security memory allocator introduced in Android 11, providing:

- **Buffer overflow detection**: Detects heap buffer out-of-bounds writes
- **Use-after-free detection**: Detects usage after freeing
- **Double-free detection**: Detects duplicate freeing
- **Memory layout randomization**: Increases attack difficulty

**smaps Identifiers**:
```bash
[anon:scudo:primary]     # Primary allocation pool (<256KB)
[anon:scudo:secondary]   # Large object allocation pool (>=256KB)
```

**Performance Impact**:
- Allocation speed decreased 5-15%
- Memory overhead increased ~5%
- Security significantly improved

### 9.2 GWP-ASan (Android 11+)

GWP-ASan (Google-Wide Profiling ASan) is a production memory error detection tool:

- **Sampling detection**: Low overhead, randomly monitors some allocations
- **Precise location**: Provides detailed error location and call stack
- **Production-ready**: Performance impact <1%

**Enabling**:
```xml
<!-- AndroidManifest.xml -->
<application android:gwpAsanMode="always">
```

### 9.3 16KB Page Support (Android 15+)

Android 15 supports 16KB memory pages on ARM64 devices:

**Advantages**:
- TLB cache hit rate improved 4x
- Memory fragmentation reduced 75%
- Large memory allocation efficiency improved

**Compatibility Requirements**:
- Native code needs 16KB page alignment
- Some third-party libraries may need updates

### 9.4 APEX Modules (Android 10+)

APEX is a modular system component format:

```bash
/apex/com.android.art/        # ART runtime
/apex/com.android.media/      # Media framework
/apex/com.android.wifi/       # WiFi system
```

**Features**:
- Independent updates without system upgrade
- Security isolation
- Precise fixes

---

## 10. References

### Official Documentation
- [Android Memory Management](https://developer.android.com/topic/performance/memory)
- [Memory Profiler](https://developer.android.com/studio/profile/memory-profiler)
- [Manage your app's memory](https://developer.android.com/topic/performance/memory-overview)

### Kernel Documentation
- [/proc/pid/smaps](https://www.kernel.org/doc/Documentation/filesystems/proc.txt)
- [Linux Memory Management](https://www.kernel.org/doc/html/latest/admin-guide/mm/index.html)

### Tool Resources
- [LeakCanary](https://square.github.io/leakcanary/)
- [KOOM](https://github.com/AKB48Team/KOOM)
- [MAT (Memory Analyzer Tool)](https://eclipse.org/mat/)

### This Project
- [GitHub Repository](https://github.com/aspect-ratio-pro/Android-App-Memory-Analysis)
- [Panorama Analysis Guide](./panorama_guide.md)
- [dumpsys meminfo Interpretation](./meminfo_interpretation_guide.md)
- [smaps Interpretation](./smaps_interpretation_guide.md)

---

> **Version History**
> - v2.0 (2025-01): Merged optimized version, updated modern Android features
> - v1.0 (2024): Initial version

