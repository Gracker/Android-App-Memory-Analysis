# Android SMAPS Output Interpretation Guide

## 📋 Overview

The `/proc/pid/smaps` file provides the most detailed information about process memory mappings and is the core data source for Android memory analysis. Each memory mapping region has complete statistics including physical memory usage, sharing status, swap information, etc.

---

## 🔍 Methods to Get SMAPS

```bash
# Method 1: Direct read (requires Root permission)
adb shell "su -c 'cat /proc/<pid>/smaps'"

# Method 2: Save to file for analysis
adb shell "su -c 'cat /proc/<pid>/smaps'" > smaps_file.txt

# Method 3: Use project tools
python3 smaps_parser.py -p <pid>
python3 smaps_parser.py -f smaps_file.txt

# Method 4: Monitor real-time changes
watch -n 5 "adb shell 'su -c \"cat /proc/<pid>/smaps\" | tail -20'"
```

---

## 📊 SMAPS File Structure Analysis

### Basic Format

Each memory mapping region contains two parts:
1. **Mapping line**: Address range and basic attributes
2. **Statistics lines**: Detailed memory usage statistics

```
12c00000-32c00000 rw-p 00000000 00:00 0    [anon:dalvik-main space (region space)]
Name:           [anon:dalvik-main space (region space)]
Size:             524288 kB
KernelPageSize:        4 kB
MMUPageSize:           4 kB
Rss:                2500 kB
Pss:                2500 kB
Shared_Clean:          0 kB
Shared_Dirty:          0 kB
Private_Clean:         0 kB
Private_Dirty:      2500 kB
Referenced:         2500 kB
Anonymous:          2500 kB
AnonHugePages:         0 kB
ShmemPmdMapped:        0 kB
Shared_Hugetlb:        0 kB
Private_Hugetlb:       0 kB
Swap:                  0 kB
SwapPss:               0 kB
Locked:                0 kB
VmFlags: rd wr mr mw me ac
```

---

## 🗺️ Mapping Line Analysis

### Address and Permission Information

```
12c00000-32c00000 rw-p 00000000 00:00 0    [anon:dalvik-main space (region space)]
```

#### Field Meanings

| Field | Example | Meaning | Analysis Points |
|-------|---------|---------|----------------|
| **Start Address** | 12c00000 | Virtual memory start address | Address space distribution |
| **End Address** | 32c00000 | Virtual memory end address | Mapping region size |
| **Permissions** | rw-p | Memory access permissions | Security and usage |
| **Offset** | 00000000 | File offset | File mapping start point |
| **Device** | 00:00 | Device number | 0:0 indicates anonymous mapping |
| **inode** | 0 | File inode number | 0 indicates anonymous memory |
| **Path/Name** | [anon:...] | Mapping name or file path | Memory type identification |

#### Permission Flag Analysis

| Flag | Meaning | Description | Security Impact |
|------|---------|-------------|----------------|
| **r** | read | Readable | Normal data access |
| **w** | write | Writable | Data can be modified |
| **x** | execute | Executable | Code segment characteristic |
| **p** | private | Private mapping | Modifications don't affect other processes |
| **s** | shared | Shared mapping | Modifications affect other processes |

#### Common Permission Combinations

- **r--p**: Read-only private (constants, read-only files)
- **r-xp**: Read-execute (code segments, shared libraries)
- **rw-p**: Read-write private (heap memory, private data)
- **rw-s**: Read-write shared (shared memory, device mappings)

---

## 📈 Memory Statistics Field Analysis

### Basic Size Information

#### Size (Mapping Size)
```
Size:             524288 kB
```
- **Meaning**: Total size of this mapping in virtual address space
- **Source**: End address - Start address
- **Characteristics**: May be much larger than actual physical memory used
- **Problem Diagnosis**: 
  - Excessive Size may cause address space fragmentation
  - Size >> RSS indicates large pre-allocation but unused
- **Next Step Tools**: Check application memory allocation strategy

#### KernelPageSize (Kernel Page Size)
```
KernelPageSize:        4 kB
```
- **Meaning**: Page size used by kernel
- **Common Values**: 4KB (ARMv7/ARMv8), 16KB (ARMv8 optional)
- **Impact**: Affects memory allocation granularity and efficiency
- **Android 16+**: Supports 16KB page optimization

#### MMUPageSize (MMU Page Size)
```
MMUPageSize:           4 kB
```
- **Meaning**: Page size used by Memory Management Unit
- **Purpose**: Hardware-level memory management
- **Optimization**: Page size affects TLB hit rate and memory efficiency

### Physical Memory Usage

#### RSS (Resident Set Size)
```
Rss:                2500 kB
```
- **Meaning**: Currently actually occupied physical memory
- **Importance**: 🔴 **Critical Metric** - Directly affects system memory pressure
- **Characteristics**: Changes in real-time, reflects current memory usage
- **Problem Diagnosis**:
  - RSS continuous growth: Possible memory leak
  - RSS sudden increase: Application loaded large amount of data
  - RSS = 0: Pages swapped out or not yet accessed
- **Optimization Target**: Reduce unnecessary RSS usage
- **Next Step Tools**:
  ```bash
  # Monitor RSS changes
  watch -n 2 "cat /proc/<pid>/smaps | grep Rss: | awk '{sum+=\$2} END {print sum\" kB\"}'"
  
  # Find mappings with largest RSS
  cat /proc/<pid>/smaps | grep -A 12 "^[0-9a-f]" | grep -B 12 "Rss:" | sort -k2 -nr
  ```

#### PSS (Proportional Set Size)
```
Pss:                2500 kB
```
- **Meaning**: Most accurate memory usage metric
- **Calculation**: PSS = Private + Shared/number of sharing processes
- **Importance**: 🔴 **Most Critical Metric** - Used for memory optimization decisions
- **Advantage**: Considers fair allocation of shared memory
- **Application Scenarios**: 
  - System memory budget allocation
  - Application memory limit setting
  - Memory optimization effect evaluation
- **Problem Diagnosis**:
  - PSS equals RSS: Completely private memory, no sharing
  - PSS much smaller than RSS: Large shared memory, high efficiency
  - PSS continuous growth: Real memory leak
- **Next Step Tools**:
  ```bash
  # PSS total
  cat /proc/<pid>/smaps | awk '/Pss:/ {sum+=$2} END {print "Total PSS: " sum " kB"}'
  
  # PSS distribution by memory type
  python3 smaps_parser.py -p <pid>
  ```

### Shared Memory Status

#### Shared_Clean (Shared Read-only Memory)
```
Shared_Clean:          0 kB
```
- **Meaning**: Memory pages shared with other processes and not modified
- **Characteristics**: 
  - Highest memory efficiency
  - Can be safely reclaimed by system
  - Not counted in process memory usage
- **Sources**: 
  - Shared library code segments
  - Read-only resource files
  - System cache data
- **Optimization Value**: 🟢 **Excellent** - No additional memory consumption
- **Problem Diagnosis**: 
  - Value is 0 but should have sharing: Possible library loading issue
  - Abnormally large value: Possible large file being accessed by multiple processes
- **Next Step Tools**:
  ```bash
  # View most shared libraries
  cat /proc/<pid>/smaps | grep -B 1 "Shared_Clean" | grep "\.so" | sort -k2 -nr
  ```

#### Shared_Dirty (Shared Modified Memory)
```
Shared_Dirty:          0 kB
```
- **Meaning**: Memory pages shared with other processes and modified
- **Characteristics**: 
  - Cannot be simply reclaimed
  - Needs to be written back to storage or swap
  - Modifications affect all sharing processes
- **Sources**: 
  - Shared memory objects
  - Writable memory-mapped files
  - Inter-process communication buffers
- **Problem Diagnosis**: 
  - Abnormal growth: Possible shared memory leak
  - Unexpected large value: Check if shared memory is misused
- **Security Consideration**: Shared dirty pages may be modified by other processes
- **Next Step Tools**:
  ```bash
  # Find shared dirty page sources
  cat /proc/<pid>/smaps | grep -B 1 -A 1 "Shared_Dirty:" | grep -v "0 kB"
  ```

### Private Memory Status

#### Private_Clean (Private Read-only Memory)
```
Private_Clean:         0 kB
```
- **Meaning**: Process-private memory pages that are not modified
- **Characteristics**: 
  - Can be discarded under memory pressure
  - Can be reloaded from files when needed
  - Does not affect other processes
- **Sources**: 
  - Privately mapped read-only files
  - Code segments (if not shared)
  - Initialized but unmodified data
- **Optimization Value**: 🟡 **Good** - Reclaimable but needs reloading
- **Problem Diagnosis**: 
  - Continuous growth: Possible large file mappings
  - Abnormally large value: Check for unnecessary private mappings
- **Next Step Tools**:
  ```bash
  # View private read-only memory sources
  cat /proc/<pid>/smaps | grep -B 12 "Private_Clean:" | grep -E "(r-x|r--)"
  ```

#### Private_Dirty (Private Modified Memory)
```
Private_Dirty:      2500 kB
```
- **Meaning**: Process-private memory pages that have been modified
- **Importance**: 🔴 **Critical** - Truly non-reclaimable memory consumption
- **Characteristics**: 
  - Cannot be shared with other processes
  - Cannot be reclaimed by system
  - Can only be swapped to storage under memory pressure
- **Sources**: 
  - Heap memory allocation
  - Stack memory
  - Global variable modifications
  - Buffer data
- **Optimization Priority**: 🔴 **Most Important** - Primary optimization target
- **Problem Diagnosis**:
  - Continuous rapid growth: Clear signal of memory leak
  - Sudden increase: Large data loading or caching
  - Abnormal distribution: Check memory allocation patterns
- **Next Step Tools**:
  ```bash
  # Monitor private dirty page growth
  while true; do 
    echo "$(date): $(cat /proc/<pid>/smaps | awk '/Private_Dirty/ {sum+=$2} END {print sum}')"
    sleep 10
  done
  
  # Find regions with most private dirty pages
  cat /proc/<pid>/smaps | grep -B 12 "Private_Dirty:" | grep -E "^[0-9a-f]" | sort -k2 -nr
  ```

### Advanced Memory Information

#### Referenced (Recently Referenced Memory)
```
Referenced:         2500 kB
```
- **Meaning**: Memory pages that have been recently accessed
- **Purpose**: Reference for kernel LRU algorithm
- **Characteristics**: Reflects memory activity level
- **Optimization Significance**: Helps identify memory hotspots

#### Anonymous (Anonymous Memory)
```
Anonymous:          2500 kB
```
- **Meaning**: Memory pages not associated with files
- **Contains**: 
  - Heap memory (malloc/new)
  - Stack memory
  - Anonymous mmap
- **Characteristics**: Cannot be recovered from files, can only be swapped
- **Problem Diagnosis**: 
  - Anonymous = Private_Dirty: Typical anonymous private memory
  - Abnormal growth: Heap memory leak or large allocations

#### AnonHugePages (Anonymous Huge Pages)
```
AnonHugePages:         0 kB
```
- **Meaning**: Anonymous memory using huge pages (2MB/1GB)
- **Advantage**: Reduces TLB misses, improves performance
- **Android**: Usually not used, value is 0
- **Problem**: Huge pages may cause memory waste

### Swap Related

#### Swap (Swap Space)
```
Swap:                  0 kB
```
- **Meaning**: Memory size swapped out to storage devices
- **Android Characteristics**: Many devices don't enable traditional swap
- **Performance Impact**: Swapped out pages need to be loaded from storage when accessed
- **Problem Diagnosis**: 
  - Has swap value: Memory pressure caused page swapping
  - Continuous growth: Insufficient memory, performance degradation
- **Next Step Tools**:
  ```bash
  # Check system swap configuration
  cat /proc/swaps
  
  # Monitor swap activity
  vmstat 1
  ```

#### SwapPss (Swap PSS)
```
SwapPss:               0 kB
```
- **Meaning**: Proportionally allocated swap space
- **Calculation**: Considers allocation of shared swap pages
- **Importance**: More accurate swap memory metric than Swap
- **Problem Diagnosis**: 
  - Has value indicates severe memory pressure
  - Need to check memory usage and optimization

### Memory Locking

#### Locked (Locked Memory)
```
Locked:                0 kB
```
- **Meaning**: Pages locked in memory by mlock()
- **Characteristics**: 
  - Cannot be swapped out
  - Cannot be reclaimed
  - Affects system memory availability
- **Purpose**: Critical data, security-sensitive information
- **Problem Diagnosis**: 
  - Abnormally large value: Possible memory locking abuse
  - Check if application correctly uses mlock

### Virtual Memory Flags

#### VmFlags (Virtual Memory Flags)
```
VmFlags: rd wr mr mw me ac
```

| Flag | Meaning | Description |
|------|---------|-------------|
| **rd** | readable | Readable |
| **wr** | writable | Writable |
| **ex** | executable | Executable |
| **sh** | shared | Shared |
| **mr** | may read | May read |
| **mw** | may write | May write |
| **me** | may execute | May execute |
| **ms** | may share | May share |
| **gd** | grows down | Grows down (stack) |
| **pf** | pure PFN range | Pure PFN range |
| **dw** | disabled write | Disabled write |
| **lo** | locked | Locked |
| **io** | I/O mapping | I/O mapping |
| **sr** | sequential read | Sequential read |
| **rr** | random read | Random read |
| **dc** | do not copy | Do not copy |
| **de** | do not expand | Do not expand |
| **ac** | account | Account |
| **nr** | no reserve | No reserve |
| **ht** | huge TLB | Huge TLB |
| **ar** | architecture specific | Architecture specific |
| **dd** | do not dump | Do not dump |
| **sd** | soft dirty | Soft dirty |
| **mm** | mixed map | Mixed map |
| **hg** | huge page | Huge page |
| **nh** | no huge page | No huge page |
| **mg** | mergeable | Mergeable |

---

## 🔍 Android-Specific Memory Type Analysis

### Dalvik Virtual Machine Memory

#### Main Space
```
[anon:dalvik-main space (region space)]
Size:             524288 kB
Rss:                2500 kB
Pss:                2500 kB
Private_Dirty:      2500 kB
```

**Meaning**: Dalvik/ART main heap space
- **Purpose**: Java object instance storage
- **Characteristics**: Large virtual space, physical memory allocated on demand
- **Problem Diagnosis**: Private_Dirty growth indicates Java memory leak
- **Next Step**: Use HPROF to analyze specific objects

#### Large Object Space
```
[anon:dalvik-large object space]
Size:              65536 kB
Rss:                327 kB
Private_Dirty:      327 kB
```

**Meaning**: Dedicated space for large objects (>12KB objects)
- **Purpose**: Store large arrays, bitmaps, etc.
- **Problem**: Large objects easily cause memory fragmentation
- **Optimization**: Avoid creating too many large objects

#### Non-Moving Space
```
[anon:dalvik-non moving space]
Size:               8192 kB
Rss:                300 kB
Private_Dirty:      300 kB
```

**Meaning**: Non-movable object space
- **Purpose**: Class objects, method metadata
- **Characteristics**: These objects are not moved during GC
- **Normal**: Relatively stable, slow growth

#### Zygote Space
```
[anon:dalvik-zygote space]
Size:               4096 kB
Rss:                656 kB
Shared_Clean:       656 kB
```

**Meaning**: Space shared by Zygote process
- **Purpose**: System classes and preloaded resources
- **Advantage**: Shared by multiple processes, saves memory
- **Characteristics**: Usually Shared_Clean

### Dalvik Auxiliary Memory

#### LinearAlloc
```
[anon:dalvik-LinearAlloc]
Size:               8192 kB
Rss:               1145 kB
Private_Dirty:     1145 kB
```

**Meaning**: Linear allocator for classes and methods
- **Purpose**: Store auxiliary data during class loading
- **Android Version**: Mainly in older versions, less in newer versions
- **Problem**: Too much class loading will increase this area

#### Indirect Reference Table
```
[anon:dalvik-indirect ref table]
Size:               1024 kB
Rss:                100 kB
Private_Dirty:      100 kB
```

**Meaning**: JNI reference management table
- **Purpose**: JNI global references and weak references
- **Problem**: JNI reference leaks will increase this area
- **Next Step**: Check reference management in JNI code

### Native Memory

#### Scudo Allocator (Android 11+)
```
[anon:scudo:primary]
Size:              16384 kB
Rss:              16491 kB
Private_Dirty:    16491 kB
```

**Meaning**: New secure memory allocator
- **Advantage**: Provides memory safety protection
- **Purpose**: C/C++ malloc/new allocations
- **Problem**: High Private_Dirty indicates heavy Native memory usage
- **Next Step**: Analyze Native code memory allocation

#### Traditional Heap Memory
```
[heap]
Size:               8192 kB
Rss:               1234 kB
Private_Dirty:     1234 kB
```

**Meaning**: Traditional process heap memory
- **Purpose**: C/C++ dynamic memory allocation
- **Characteristics**: Pure private memory, cannot be shared
- **Optimization**: Check memory allocation and deallocation pairing

### Stack Memory

#### Main Thread Stack
```
[stack]
Size:               8192 kB
Rss:                 60 kB
Private_Dirty:       60 kB
```

**Meaning**: Main thread stack space
- **Purpose**: Function calls, local variables
- **Normal Size**: Usually tens of KB to a few MB
- **Problem**: Excessive size may indicate recursive calls

#### Worker Thread Stack
```
[anon:stack_and_tls:22379]
Size:               1024 kB
Rss:                100 kB
Private_Dirty:      100 kB
```

**Meaning**: Worker thread stack and TLS
- **Contains**: Stack memory + Thread Local Storage
- **Quantity**: One per thread
- **Problem**: Too many threads will increase memory usage

### Graphics and GPU Memory

#### GPU Device Memory
```
/dev/kgsl-3d0
Size:               6016 kB
Rss:               5884 kB
Pss:               5884 kB
Private_Dirty:     5884 kB
```

**Meaning**: GPU graphics memory device
- **Purpose**: Textures, vertex buffers, shaders
- **Characteristics**: Cannot be swapped out, directly uses video memory
- **Problem**: Excessive size affects graphics performance and system memory
- **Next Step**: 
  ```bash
  # GPU memory details
  cat /d/kgsl/proc/<pid>/mem
  # Graphics performance analysis
  dumpsys gfxinfo <package>
  ```

#### Shared Memory
```
/dev/ashmem/GFXStats-21936 (deleted)
Size:                 4 kB
Rss:                  2 kB
Pss:                  1 kB
Shared_Clean:         2 kB
```

**Meaning**: Graphics statistics shared memory
- **Purpose**: System graphics performance statistics
- **Characteristics**: Shared by multiple processes
- **Status**: (deleted) indicates file is deleted but memory still in use

### File Mappings

#### Shared Libraries
```
/vendor/lib64/libllvm-glnext.so
Size:               3568 kB
Rss:                859 kB
Pss:                215 kB
Shared_Clean:       644 kB
Private_Clean:      215 kB
```

**Detailed Analysis**:
- **Efficient Sharing**: Shared_Clean indicates code segments shared by multiple processes
- **On-Demand Loading**: Size >> RSS means only needed parts are loaded
- **Low PSS**: Sharing reduces single process memory contribution

**Optimization Value**: 
- ✅ High sharing efficiency
- ✅ Reasonable memory usage
- ✅ Effective on-demand loading

#### APK File Mapping
```
/system_ext/priv-app/Launcher3QuickStep/Launcher3QuickStep.apk
Size:               2560 kB
Rss:               2480 kB
Pss:                620 kB
Shared_Clean:      1860 kB
```

**Analysis Points**:
- **APK Code Sharing**: Shared_Clean indicates DEX code is shared
- **PSS Calculation**: 620 = 620(Private) + 1860/3(assuming 3 processes sharing)
- **Memory Efficiency**: One APK, shared by multiple components

#### Font Files
```
/system/fonts/Roboto-Regular.ttf
Size:                128 kB
Rss:                 15 kB
Pss:                  3 kB
Shared_Clean:        15 kB
```

**Optimization Characteristics**:
- **Complete Sharing**: System fonts shared by all applications
- **Extremely Low PSS**: Single application bears almost no font memory cost
- **On-Demand Loading**: Only loads used characters

### ART Runtime

#### Boot ART Files
```
[anon:dalvik-/system/framework/boot-framework.art]
Size:               4096 kB
Rss:               1537 kB
Pss:                384 kB
Shared_Clean:      1153 kB
Private_Clean:      384 kB
```

**Meaning**: System framework ART files
- **Sharing**: Framework code shared by multiple applications
- **Pre-compiled**: AOT compiled native code
- **Efficiency**: Fast startup, high runtime efficiency

#### App ART Files
```
[anon:dalvik-/data/dalvik-cache/arm64/app.art]
Size:               1024 kB
Rss:                344 kB
Pss:                344 kB
Private_Clean:      344 kB
```

**Meaning**: Application-specific ART files
- **Private**: Each application has its own
- **Pre-compiled**: Native compiled version of application code
- **Performance**: Improves application execution performance

### JIT Compilation Cache

#### JIT Cache
```
/memfd:jit-cache (deleted)
Size:                512 kB
Rss:                368 kB
Pss:                368 kB
Private_Dirty:      368 kB
```

**Meaning**: Just-in-time compilation code cache
- **Dynamic**: Runtime hotspot code compilation
- **Memory File**: Stored in memory file system
- **Private**: Each process has its own compilation cache
- **Optimization**: Improves hotspot code execution efficiency

---

## 🚨 Problem Pattern Recognition

### 1. Java Memory Leaks

#### Typical Symptoms
```bash
# Dalvik-related areas continuously growing
[anon:dalvik-main space]         - Private_Dirty growth
[anon:dalvik-large object space] - Private_Dirty growth
[anon:dalvik-non moving space]   - Slow growth is normal
```

#### Diagnosis Process
```bash
# 1. Monitor Dalvik memory trends
grep -A 10 "dalvik-main space" /proc/<pid>/smaps | grep Private_Dirty

# 2. Compare before and after GC
adb shell "am broadcast -a com.android.internal.intent.action.REQUEST_GC"
sleep 5
grep -A 10 "dalvik" /proc/<pid>/smaps

# 3. In-depth HPROF analysis
python3 hprof_dumper.py -pkg <package>
python3 hprof_parser.py -f <hprof_file>
```

#### Next Step Tools
- **HPROF Analysis**: Specific objects and reference chains
- **MAT Tool**: Eclipse Memory Analyzer
- **LeakCanary**: Automatic memory leak detection

### 2. Native Memory Leaks

#### Typical Symptoms
```bash
# Native memory areas growing
[heap]                 - Private_Dirty growth
[anon:scudo:primary]   - Private_Dirty growth  
[anon:libc_malloc]     - Private_Dirty growth
```

#### Diagnosis Process
```bash
# 1. Count total Native memory
cat /proc/<pid>/smaps | grep -E "(heap|scudo|malloc)" -A 10 | grep Private_Dirty | awk '{sum+=$2} END {print sum " kB"}'

# 2. Detailed Native memory analysis
adb shell "dumpsys meminfo <package> -d"

# 3. Native memory tools
# AddressSanitizer, Valgrind, etc.
```

#### Next Step Tools
- **ASan**: AddressSanitizer memory error detection
- **Valgrind**: Linux memory analysis tool
- **Malloc Debug**: Android Native memory debugging

### 3. Graphics Memory Overuse

#### Typical Symptoms
```bash
# GPU memory usage too high
/dev/kgsl-3d0          - Large Private_Dirty
/dev/mali0             - GPU device memory growth
[anon:graphics]        - Graphics-related anonymous memory
```

#### Problem Analysis
- **Texture Memory**: Bitmap and texture usage
- **Buffers**: Vertex, index buffers
- **Render Targets**: FBO, RenderBuffer

#### Next Step Tools
```bash
# GPU memory details (if supported)
cat /sys/kernel/debug/kgsl/proc/<pid>/mem

# Graphics performance analysis
adb shell "dumpsys gfxinfo <package> framestats"

# GPU debugging tools
# RenderDoc, Mali Graphics Debugger
```

### 4. File Mapping Anomalies

#### Typical Symptoms
```bash
# Large number of file mappings
Many .so files          - Too many libraries loaded
Many .apk mappings     - Abnormal resource loading
Unusual file paths     - Temporary files not cleaned
```

#### Diagnosis Methods
```bash
# 1. Count mapped file types
cat /proc/<pid>/smaps | grep "^/" | cut -d' ' -f6 | sort | uniq -c | sort -nr

# 2. Find large memory mappings
cat /proc/<pid>/smaps | grep -B 12 "Size:" | grep "^/" | sort -k2 -nr

# 3. Check temporary files
cat /proc/<pid>/smaps | grep "/tmp\|/cache\|deleted"
```

### 5. Too Many Threads Problem

#### Typical Symptoms
```bash
# Large number of thread stacks
[anon:stack_and_tls:xxxxx]  - Multiple thread stack mappings
[stack]                     - Main thread stack abnormally large
```

#### Analysis Methods
```bash
# 1. Count number of threads
cat /proc/<pid>/smaps | grep "stack_and_tls" | wc -l

# 2. View thread information
cat /proc/<pid>/status | grep Threads
ls /proc/<pid>/task/ | wc -l

# 3. Thread stack size analysis
cat /proc/<pid>/smaps | grep -A 10 "stack_and_tls" | grep Size
```

---

## 📊 Memory Health Assessment

### Assessment Metrics

#### 1. Memory Efficiency Metrics

**Shared Memory Ratio**:
```bash
shared_ratio = (Shared_Clean + Shared_Dirty) / RSS * 100%
```
- Excellent: >30%
- Good: 20-30%
- Average: 10-20%
- Poor: <10%

**Private Dirty Page Ratio**:
```bash
dirty_ratio = Private_Dirty / RSS * 100%
```
- Excellent: <50%
- Good: 50-70%
- Average: 70-85%
- Poor: >85%

#### 2. Memory Distribution Health

**Dalvik Memory Ratio**:
```bash
dalvik_ratio = Dalvik_RSS / Total_RSS * 100%
```
- Normal: 30-60%
- Warning: >70%
- Dangerous: >85%

**Native Memory Ratio**:
```bash
native_ratio = Native_RSS / Total_RSS * 100%
```
- Normal: <40%
- Warning: 40-60%
- Dangerous: >60%

#### 3. Memory Growth Trends

**Growth Rate Monitoring**:
```bash
# Memory growth rate per minute
growth_rate = (Current_PSS - Previous_PSS) / Previous_PSS * 100%
```
- Normal: <5%/minute
- Warning: 5-10%/minute
- Dangerous: >10%/minute

### Automated Assessment Script

```bash
#!/bin/bash
# smaps_health_check.sh

PID=$1
OUTPUT_FILE="smaps_health_$(date +%Y%m%d_%H%M%S).txt"

echo "=== SMAPS Memory Health Check ===" > $OUTPUT_FILE
echo "PID: $PID" >> $OUTPUT_FILE
echo "Time: $(date)" >> $OUTPUT_FILE
echo "" >> $OUTPUT_FILE

# Basic statistics
TOTAL_RSS=$(cat /proc/$PID/smaps | awk '/^Rss:/ {sum+=$2} END {print sum}')
TOTAL_PSS=$(cat /proc/$PID/smaps | awk '/^Pss:/ {sum+=$2} END {print sum}')
SHARED_CLEAN=$(cat /proc/$PID/smaps | awk '/^Shared_Clean:/ {sum+=$2} END {print sum}')
SHARED_DIRTY=$(cat /proc/$PID/smaps | awk '/^Shared_Dirty:/ {sum+=$2} END {print sum}')
PRIVATE_CLEAN=$(cat /proc/$PID/smaps | awk '/^Private_Clean:/ {sum+=$2} END {print sum}')
PRIVATE_DIRTY=$(cat /proc/$PID/smaps | awk '/^Private_Dirty:/ {sum+=$2} END {print sum}')

echo "Basic Memory Statistics:" >> $OUTPUT_FILE
echo "  Total RSS: $TOTAL_RSS kB" >> $OUTPUT_FILE
echo "  Total PSS: $TOTAL_PSS kB" >> $OUTPUT_FILE
echo "  Shared Clean: $SHARED_CLEAN kB" >> $OUTPUT_FILE
echo "  Shared Dirty: $SHARED_DIRTY kB" >> $OUTPUT_FILE
echo "  Private Clean: $PRIVATE_CLEAN kB" >> $OUTPUT_FILE
echo "  Private Dirty: $PRIVATE_DIRTY kB" >> $OUTPUT_FILE
echo "" >> $OUTPUT_FILE

# Calculate ratios
SHARED_RATIO=$((($SHARED_CLEAN + $SHARED_DIRTY) * 100 / $TOTAL_RSS))
DIRTY_RATIO=$(($PRIVATE_DIRTY * 100 / $TOTAL_RSS))

echo "Memory Efficiency Metrics:" >> $OUTPUT_FILE
echo "  Shared Memory Ratio: $SHARED_RATIO%" >> $OUTPUT_FILE
echo "  Private Dirty Ratio: $DIRTY_RATIO%" >> $OUTPUT_FILE

# Assessment levels
if [ $SHARED_RATIO -gt 30 ]; then
    echo "  Sharing Efficiency: Excellent ✅" >> $OUTPUT_FILE
elif [ $SHARED_RATIO -gt 20 ]; then
    echo "  Sharing Efficiency: Good 🟡" >> $OUTPUT_FILE
else
    echo "  Sharing Efficiency: Needs Improvement ⚠️" >> $OUTPUT_FILE
fi

if [ $DIRTY_RATIO -lt 50 ]; then
    echo "  Dirty Page Ratio: Excellent ✅" >> $OUTPUT_FILE
elif [ $DIRTY_RATIO -lt 70 ]; then
    echo "  Dirty Page Ratio: Good 🟡" >> $OUTPUT_FILE
else
    echo "  Dirty Page Ratio: High ⚠️" >> $OUTPUT_FILE
fi

echo "" >> $OUTPUT_FILE

# Dalvik memory analysis
DALVIK_RSS=$(cat /proc/$PID/smaps | grep -A 10 "dalvik" | awk '/^Rss:/ {sum+=$2} END {print sum}')
DALVIK_RATIO=$(($DALVIK_RSS * 100 / $TOTAL_RSS))

echo "Memory Distribution Analysis:" >> $OUTPUT_FILE
echo "  Dalvik Memory: $DALVIK_RSS kB ($DALVIK_RATIO%)" >> $OUTPUT_FILE

if [ $DALVIK_RATIO -lt 60 ]; then
    echo "  Dalvik Ratio: Normal ✅" >> $OUTPUT_FILE
elif [ $DALVIK_RATIO -lt 70 ]; then
    echo "  Dalvik Ratio: High 🟡" >> $OUTPUT_FILE
else
    echo "  Dalvik Ratio: Too High, Check Memory Leaks ⚠️" >> $OUTPUT_FILE
fi

# TOP memory areas
echo "" >> $OUTPUT_FILE
echo "TOP 10 Memory Usage Areas:" >> $OUTPUT_FILE
cat /proc/$PID/smaps | grep -B 12 "^Pss:" | grep -E "^[0-9a-f]" | sort -k3 -nr | head -10 >> $OUTPUT_FILE

echo "" >> $OUTPUT_FILE
echo "Analysis completed, detailed report saved to: $OUTPUT_FILE"
```

---

## 🔗 Related Tool Links

- **Application Level Analysis**: [dumpsys meminfo Interpretation Guide](./meminfo_interpretation_guide.md)
- **System Level Analysis**: [/proc/meminfo Interpretation Guide](./proc_meminfo_interpretation_guide.md)
- **Process Level Overview**: [showmap Interpretation Guide](./showmap_interpretation_guide.md)  
- **Analysis Results Understanding**: [Analysis Results Guide](./analysis_results_interpretation_guide.md)

---

## 💡 Best Practice Recommendations

### 1. Daily Monitoring
- Establish memory baseline data, compare regularly
- Focus on Private_Dirty growth trends
- Monitor shared memory efficiency and PSS changes

### 2. Problem Localization
- Prioritize analyzing areas with largest Private_Dirty
- Combine application behavior with memory change patterns
- Use HPROF and Native tools for in-depth analysis

### 3. Performance Optimization
- Reduce unnecessary Private_Dirty memory
- Improve shared memory usage efficiency
- Optimize large object and file mapping management

### 4. Tool Coordination
- SMAPS provides detailed data, showmap provides overview
- Combine HPROF for Java heap analysis
- Use Native tools for C/C++ memory analysis

Through deep understanding of each SMAPS field and memory mapping patterns, you can precisely locate the root cause of memory problems and develop effective optimization strategies. SMAPS is the most important data source for Android memory analysis, and mastering its interpretation is crucial for memory optimization.