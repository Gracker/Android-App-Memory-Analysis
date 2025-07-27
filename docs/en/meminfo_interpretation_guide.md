# Android dumpsys meminfo Output Interpretation Guide

## 📋 Overview

`dumpsys meminfo` is an application-level memory analysis tool provided by Android system, displaying detailed memory usage of specific applications. Unlike system-level `/proc/meminfo`, this command focuses on single application memory breakdown and is a core tool for application memory optimization.

---

## 🔍 Methods to Get dumpsys meminfo

```bash
# Method 1: Analyze specific application (recommended)
adb shell "dumpsys meminfo <package_name>"

# Method 2: Analyze by PID
adb shell "dumpsys meminfo <pid>"

# Method 3: Detailed mode (with more details)
adb shell "dumpsys meminfo -d <package_name>"

# Method 4: All applications overview
adb shell "dumpsys meminfo -a"

# Method 5: Save to file for analysis
adb shell "dumpsys meminfo <package_name>" > meminfo.txt
```

---

## 📊 dumpsys meminfo Output Structure Analysis

### Header Information

```
$ mem -a -d com.android.launcher3
Applications Memory Usage (in Kilobytes):
Uptime: 277172845 Realtime: 423847246

** MEMINFO in pid 21936 [com.android.launcher3] **
```

#### Basic Information Explanation
- **Applications Memory Usage**: Application memory usage report
- **Uptime**: System uptime (milliseconds)
- **Realtime**: System actual runtime (milliseconds)
- **pid 21936**: Application process ID
- **[com.android.launcher3]**: Application package name

### Main Memory Classification Table

```
                   Pss      Pss   Shared  Private   Shared  Private     Swap      Rss     Heap     Heap     Heap
                 Total    Clean    Dirty    Dirty    Clean    Clean    Dirty    Total     Size    Alloc     Free
                ------   ------   ------   ------   ------   ------   ------   ------   ------   ------   ------
  Native Heap    24482        0     2692    24380        0        0        0    27072    39580    24489    11037
  Dalvik Heap     3783        0     4596     3588        0        0        0     8184    28651     4075    24576
 Dalvik Other     1755        0     1532     1376        0        0        0     2908
        Stack      976        0       12      976        0        0        0      988
       Ashmem        2        0        4        0       16        0        0       20
      Gfx dev     5884        0        0     5884        0        0        0     5884
    Other dev      136        0      216        0        0      136        0      352
     .so mmap     3294      168     4280      228    22656      168        0    27332
    .jar mmap     1084        8        0        0    11616        8        0    11624
    .apk mmap     3048      448        0        0    15468      448        0    15916
    .ttf mmap       39        0        0        0      200        0        0      200
    .dex mmap       54        0       12        4      128        0        0      144
    .oat mmap     1169        4       64        0     9040        4        0     9108
    .art mmap     2732        4    16136     2012      156        4        0    18308
   Other mmap      490        0       36        8     1776       80        0     1900
   EGL mtrack    51348        0        0    51348        0        0        0    51348
    GL mtrack     4460        0        0     4460        0        0        0     4460
      Unknown      793        0      520      784        0        0        0     1304
        TOTAL   105529      632    30100    95048    61056      848        0   187052    68231    28564    35613
```

## 📈 Field Meaning Analysis

### Core Memory Metrics

#### Pss Total (Proportional Set Size Total)
- **Meaning**: 🔴 **Most Important Metric** - Application's actual contribution to system memory
- **Calculation**: Private + Shared/Number of sharing processes
- **Usage**: Key data for memory budget allocation and performance evaluation
- **Example**: Native Heap 24482 kB
  - This application's Native memory contributes 24.5MB to system memory pressure

#### Pss Clean (Proportional Set Size Clean)
- **Meaning**: Shared memory portion that can be reclaimed by system
- **Characteristics**: Can be discarded under memory pressure, reloaded when needed
- **Example**: .so mmap 168 kB
  - Reclaimable code segments in shared libraries

#### Shared Dirty (Shared Dirty Pages)
- **Meaning**: Memory shared by multiple processes and modified
- **Characteristics**: Cannot be simply reclaimed, needs to be written back to storage
- **Problem Diagnosis**: Excessively large values may indicate shared memory usage issues

#### Private Dirty (Private Dirty Pages)
- **Meaning**: 🔴 **Key Metric** - Application-exclusive and non-reclaimable memory
- **Importance**: The portion that truly consumes system memory
- **Optimization Priority**: Reducing Private Dirty is the core goal of memory optimization

#### Shared Clean (Shared Clean Pages)
- **Meaning**: 🟢 **Best Memory** - Multi-process shared and reclaimable
- **Advantages**: No additional memory usage, highest efficiency
- **Sources**: System libraries, APK files, and other read-only resources

#### Private Clean (Private Clean Pages)
- **Meaning**: Application-private but reclaimable memory
- **Characteristics**: Can be discarded under memory pressure, reloaded from files

#### Swap Dirty (Swap Dirty Pages)
- **Meaning**: Memory swapped out to storage devices
- **Android Characteristics**: Most devices show 0 (no traditional swap)
- **Performance Impact**: Non-zero values indicate high memory pressure, affecting performance

#### Rss Total (Resident Set Size Total)
- **Meaning**: All physical memory currently occupied by the application
- **Comparison**: Usually larger than Pss Total (includes complete shared memory)

#### Heap Size/Alloc/Free (Heap Memory Only)
- **Heap Size**: Total virtual size of heap
- **Heap Alloc**: Allocated heap memory
- **Heap Free**: Available heap space

---

## 🧩 Detailed Memory Category Analysis

### 1. Native Heap

```
  Native Heap    24482        0     2692    24380        0        0        0    27072    39580    24489    11037
```

#### Detailed Analysis
- **Pss Total (24482 kB)**: Native memory contribution to system
  - **Evaluation Standards**:
    - Lightweight apps: <20MB
    - Regular apps: 20-50MB
    - Heavy apps: 50-100MB
    - Abnormal: >100MB

- **Private Dirty (24380 kB)**: True Native memory consumption
  - **Source**: C/C++ malloc/new allocations
  - **Problem Diagnosis**: Close to Pss Total indicates mostly private memory

- **Heap Size (39580 kB)**: Total Native heap space
  - **Comparison**: Size > Alloc indicates reserved space
  - **Efficiency**: Alloc/Size ratio reflects heap utilization

- **Heap Alloc (24489 kB)**: Actually allocated Native memory
- **Heap Free (11037 kB)**: Available Native heap space

#### Problem Diagnosis and Optimization
```bash
# Check Native memory leaks
# 1. Compare Native Heap changes before/after operations
adb shell "dumpsys meminfo <package>" | grep "Native Heap"

# 2. Use detailed mode to view Native categories
adb shell "dumpsys meminfo -d <package>"

# 3. Native memory debugging tools
# - AddressSanitizer (ASan)
# - Malloc debug hooks
# - Valgrind (emulator)
```

**Optimization Suggestions**:
- Check memory allocation and deallocation in JNI code
- Review third-party Native library memory usage
- Use object pools to reduce frequent malloc/free

### 2. Dalvik Heap (Java Virtual Machine Heap)

```
  Dalvik Heap     3783        0     4596     3588        0        0        0     8184    28651     4075    24576
```

#### Detailed Analysis
- **Pss Total (3783 kB)**: Java heap memory contribution
  - **Evaluation Standards**:
    - Lightweight apps: <30MB
    - Regular apps: 30-80MB
    - Heavy apps: 80-200MB
    - Abnormal: >200MB

- **Shared Dirty (4596 kB)**: Shared Java heap memory
  - **Source**: System classes shared from Zygote process
  - **Characteristics**: Larger than Private Dirty indicates effective sharing

- **Private Dirty (3588 kB)**: Application-exclusive Java objects
  - **Importance**: True Java memory usage
  - **Optimization Priority**: Reduce object creation and memory leaks

- **Heap Size (28651 kB)**: Maximum available Java heap space
- **Heap Alloc (4075 kB)**: Currently allocated Java memory
- **Heap Free (24576 kB)**: Available Java heap space

#### Health Assessment
```bash
# Java heap utilization
heap_utilization = Heap Alloc / Heap Size * 100%
# Example: 4075 / 28651 * 100% = 14.2%

# Evaluation standards:
# - <30%: Sufficient heap space
# - 30-70%: Normal usage
# - 70-90%: Memory pressure, frequent GC possible
# - >90%: Insufficient memory, performance affected
```

#### Next Step Tools
```bash
# 1. HPROF analysis of Java objects
python3 tools/hprof_dumper.py -pkg <package>
python3 tools/hprof_parser.py -f <hprof_file>

# 2. GC monitoring
adb shell "dumpsys gfxinfo <package>"

# 3. Memory leak detection
# - LeakCanary automatic detection
# - MAT (Memory Analyzer Tool) analysis
```

### 3. Graphics Memory

```
      Gfx dev     5884        0        0     5884        0        0        0     5884
   EGL mtrack    51348        0        0    51348        0        0        0    51348
    GL mtrack     4460        0        0     4460        0        0        0     4460
```

#### Graphics Memory Analysis
- **Gfx dev (5884 kB)**: GPU device direct memory
- **EGL mtrack (51348 kB)**: EGL graphics memory tracking
- **GL mtrack (4460 kB)**: OpenGL memory tracking

#### Total Graphics Memory
```bash
Total Graphics = Gfx dev + EGL mtrack + GL mtrack
              = 5884 + 51348 + 4460 = 61692 kB (about 60MB)
```

#### Evaluation Standards
- Regular apps: <30MB
- Graphics-intensive: 30-100MB
- Game apps: 100-300MB
- Abnormal: >300MB

#### Optimization Suggestions
```java
// 1. Bitmap optimization
BitmapFactory.Options options = new BitmapFactory.Options();
options.inPreferredConfig = Bitmap.Config.RGB_565; // Reduce memory
options.inSampleSize = 2; // Scale down

// 2. Timely recycle
if (bitmap != null && !bitmap.isRecycled()) {
    bitmap.recycle();
}

// 3. GPU resource management
// Timely release textures, buffers and other GPU resources
```

### 4. File Mapping Memory

#### Shared Library Mapping
```
     .so mmap     3294      168     4280      228    22656      168        0    27332
```
- **High Shared Clean (22656 kB)**: System libraries shared by multiple processes
- **Low Pss (3294 kB)**: Efficient memory sharing
- **Optimization**: Demonstrates shared library memory efficiency

#### APK File Mapping
```
    .apk mmap     3048      448        0        0    15468      448        0    15916
```
- **Shared Clean (15468 kB)**: APK code shared by multiple components
- **Private Clean (448 kB)**: Application-specific APK portion

#### ART File Mapping
```
    .art mmap     2732        4    16136     2012      156        4        0    18308
```
- **High Shared Dirty (16136 kB)**: Sharing of ART compiled code
- **Performance Optimization**: Precompiled code improves execution efficiency

---

## 📋 App Summary Section Analysis

```
 App Summary
                       Pss(KB)                        Rss(KB)
                        ------                         ------
           Java Heap:     5604                          26492
         Native Heap:    24380                          27072
                Code:      880                          65056
               Stack:      976                            988
            Graphics:    61692                          61692
       Private Other:     2364
              System:     9633
             Unknown:                                    5752

           TOTAL PSS:   105529            TOTAL RSS:   187052      TOTAL SWAP (KB):        0
```

### Summary Metrics Interpretation

#### Java Heap (5604 kB)
- **Calculation**: Dalvik Heap + part of Dalvik Other
- **Percentage**: 5604/105529 = 5.3%
- **Evaluation**: Low Java memory percentage, app may lean towards Native or graphics

#### Native Heap (24380 kB)
- **Percentage**: 24380/105529 = 23.1%
- **Comparison**: About 4:1 ratio with Java Heap
- **Analysis**: High Native memory usage, need to focus on C/C++ code

#### Graphics (61692 kB)
- **Percentage**: 61692/105529 = 58.5%
- **Analysis**: Graphics memory over half, optimization priority
- **Problem**: Possibly large number of bitmaps or GPU resources

#### Memory Distribution Health
```bash
# Ideal memory distribution (reference)
Java Heap:    30-50%  (Current: 5.3%)
Native Heap:  20-30%  (Current: 23.1%)
Graphics:     10-30%  (Current: 58.5%)
Code:         5-15%   (Current: 0.8%)
Other:        5-20%   (Current: 12.3%)
```

#### Evaluation Conclusion
- 🔴 **Graphics memory too high**: Needs priority optimization
- 🟡 **Java memory low**: May over-rely on Native
- 🟢 **Code memory reasonable**: High sharing efficiency

---

## 🧮 Objects Section Analysis

```
 Objects
               Views:      114         ViewRootImpl:        1
         AppContexts:        9           Activities:        1
              Assets:        7        AssetManagers:        0
       Local Binders:       39        Proxy Binders:       41
       Parcel memory:       17         Parcel count:       75
    Death Recipients:        1      OpenSSL Sockets:        0
            WebViews:        0
```

### Object Statistics Analysis

#### UI Objects
- **Views (114)**: Number of View objects
  - **Evaluation**: Reasonable count, large interfaces may have more
  - **Optimization**: Reduce unnecessary View hierarchy
- **ViewRootImpl (1)**: Root view implementation
  - **Normal**: Usually corresponds to Activity count

#### Application Context
- **AppContexts (9)**: Number of application contexts
  - **Source**: Application, Service, Activity, etc.
  - **Problem**: Too many may indicate Context leaks
- **Activities (1)**: Activity instance count
  - **Normal**: Corresponds to currently active Activities

#### Inter-Process Communication
- **Local Binders (39)**: Local Binder objects
- **Proxy Binders (41)**: Proxy Binder objects
- **Parcel (17/75)**: Serialized object memory/count

### Object Leak Detection
```bash
# Monitor object count changes
# 1. Get baseline data
adb shell "dumpsys meminfo <package>" | grep -A 15 "Objects"

# 2. Detect again after operations
# 3. Compare object count changes

# Focus on:
# - Activities > 2: Possible Activity leaks  
# - Views continuously growing: Possible View leaks
# - AppContexts abnormally high: Context leaks
```

---

## 🚨 Abnormal Pattern Recognition and Diagnosis

### 1. Memory Leak Patterns

#### Java Memory Leaks
```bash
# Symptoms: Dalvik Heap continuously growing
# Before: Dalvik Heap    3783 kB
# After: Dalvik Heap    8756 kB (growth 4973 kB)

# Diagnosis process:
# 1. Compare meminfo before/after operations
# 2. Check Heap Alloc and Objects count changes
# 3. Use HPROF to analyze specific objects
```

#### Graphics Memory Leaks
```bash
# Symptoms: Graphics memory abnormal growth
# EGL mtrack    51348 kB → 85672 kB

# Common causes:
# - Bitmaps not timely recycled
# - GPU resources not released
# - Texture memory accumulation
```

### 2. Memory Distribution Abnormalities

#### Graphics Memory Overload (current example)
```bash
Graphics: 61692 kB (58.5% of total)
# Problem: Graphics memory percentage too high
# Normal: Should be 10-30%
```

#### Java Memory Percentage Abnormally Low (current 5.3%)
```bash
# Possible reasons:
# - Main application logic in Native layer
# - Over-reliance on C/C++ implementation
# - Graphics rendering dominates

# Evaluation:
# - Check if architecture design is reasonable
# - Consider Java/Native balance
```

---

## 📊 Memory Health Assessment Standards

### Overall Memory Evaluation

#### Excellent (Green)
- **Total PSS**: <80MB
- **Java Heap**: 20-40% of total memory
- **Native Heap**: 20-40% of total memory
- **Graphics**: <20% of total memory
- **Heap Utilization**: 30-70%

#### Good (Yellow)  
- **Total PSS**: 80-150MB
- **Graphics**: 20-40% of total memory
- **Object Count**: Within reasonable range
- **No obvious memory leaks**

#### Warning (Orange)
- **Total PSS**: 150-250MB
- **Graphics**: 40-60% of total memory
- **Heap Utilization**: >80%
- **Object Count**: Somewhat high

#### Dangerous (Red)
- **Total PSS**: >250MB
- **Graphics**: >60% of total memory
- **Obvious Memory Leaks**: Abnormal Activity/View counts
- **Frequent OOM**: Out of memory

---

## 🔗 Related Tools and Resource Links

### Basic Analysis Tools
- **System Level**: [/proc/meminfo Interpretation Guide](./proc_meminfo_interpretation_guide.md)
- **Process Level**: [showmap Interpretation Guide](./showmap_interpretation_guide.md)
- **Detailed Mapping**: [smaps Interpretation Guide](./smaps_interpretation_guide.md)
- **Analysis Results**: [Results Interpretation Guide](./analysis_results_interpretation_guide.md)

### Android Memory Tools
- **HPROF Analysis**: `python3 tools/hprof_dumper.py` / `python3 tools/hprof_parser.py`
- **SMAPS Parsing**: `python3 tools/smaps_parser.py`
- **Comprehensive Analysis**: `python3 tools/memory_analyzer.py`

### Official Tools
- **Android Studio Profiler**: Real-time memory monitoring
- **MAT (Memory Analyzer Tool)**: Java heap analysis
- **LeakCanary**: Automatic memory leak detection

---

## 💡 Best Practice Recommendations

### 1. Regular Monitoring
```bash
# Establish memory monitoring baseline
./scripts/meminfo_monitor.sh com.example.app

# Key checkpoint detection
# - After app startup
# - After main feature usage  
# - After long-term running
# - Before/after memory-sensitive operations
```

### 2. Problem Diagnosis Process
1. **Quick Assessment**: Check App Summary memory distribution
2. **Anomaly Identification**: Focus on memory types with high percentages
3. **Detailed Analysis**: Use corresponding tools for in-depth analysis
4. **Trend Monitoring**: Compare data across multiple time points

### 3. Optimization Priority
1. **Graphics Memory**: If percentage >40%, prioritize bitmap and GPU usage optimization
2. **Java Heap**: If continuously growing, focus on HPROF analysis
3. **Native Heap**: If oversized, check C/C++ code and third-party libraries
4. **Object Leaks**: Abnormal Activity/View counts need immediate handling

### 4. Preventive Measures
- Establish memory usage standards and Code Review checkpoints
- Integrate automated memory detection tools
- Regularly conduct memory stress testing
- Establish memory usage monitoring and alerting mechanisms

Through deep understanding of every item in `dumpsys meminfo` output, you can accurately diagnose application memory issues and develop targeted optimization strategies to significantly improve application memory performance.