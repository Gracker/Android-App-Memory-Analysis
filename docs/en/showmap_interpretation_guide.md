# Android Showmap Output Interpretation Guide

## 📋 Overview

`showmap` is an Android memory mapping analysis tool that displays memory mapping details for specified processes. It provides more memory usage statistics than `/proc/pid/maps`, making it an important tool for process-level memory analysis.

---

## 🔍 Methods to Get Showmap

```bash
# Method 1: Direct use of showmap command
adb shell "showmap <pid>"

# Method 2: Get PID by package name then analyze
adb shell "showmap $(pidof <package_name>)"

# Method 3: Save to file for analysis
adb shell "showmap <pid>" > showmap_output.txt

# Method 4: Get showmap for multiple processes
adb shell "ps | grep <app_name> | awk '{print \$2}' | xargs showmap"
```

---

## 📊 Showmap Output Format Analysis

### Output Header Information

```
  virtual                     shared   shared  private  private
     size      RSS      PSS    clean    dirty    clean    dirty     swap  swapPSS
--------  --------  --------  -------  -------  -------  -------  -------  -------
```

#### Field Meaning Details

| Field | Full Name | Chinese Meaning | Calculation Method | Importance |
|-------|-----------|-----------------|-------------------|------------|
| **virtual** | Virtual Size | Virtual memory size | Process address space mapping size | 🔵 Reference |
| **RSS** | Resident Set Size | Resident memory size | Actual physical memory occupied | 🟡 Important |
| **PSS** | Proportional Set Size | Proportional allocation memory | RSS + (shared memory/sharing processes) | 🔴 Critical |
| **shared clean** | Shared Clean Pages | Shared read-only pages | Multi-process shared read-only memory | 🟢 Optimization |
| **shared dirty** | Shared Dirty Pages | Shared writable pages | Multi-process shared writable memory | 🟡 Monitor |
| **private clean** | Private Clean Pages | Private read-only pages | Process-exclusive read-only memory | 🟢 Normal |
| **private dirty** | Private Dirty Pages | Private writable pages | Process-exclusive writable memory | 🔴 Critical |
| **swap** | Swap Size | Swap space size | Memory swapped out to storage | 🟡 Performance |
| **swapPSS** | Swap PSS | Swap space PSS | Proportionally allocated swap memory | 🟡 Performance |

---

## 📖 Typical Output Example Analysis

### 1. Dalvik Heap Memory

```
[anon:dalvik-main space (region space)]
    49152     2500     2500        0        0        0     2500        0        0
```

**Detailed Explanation**:
- **virtual (49152 kB)**: Virtual address space reserved by Dalvik for main heap
  - **Source**: Continuous address space allocated by ART virtual machine
  - **Characteristics**: Usually much larger than actual usage, reserved for heap expansion
  - **Problem Diagnosis**: Excessive size may affect address space utilization

- **RSS (2500 kB)**: Actual physical memory occupied
  - **Source**: Java objects actually allocated and used by the application
  - **Importance**: Directly affects system memory pressure
  - **Problem Diagnosis**: Continuous growth indicates possible memory leaks

- **PSS (2500 kB)**: Proportional allocation memory (equal to RSS means no sharing)
  - **Source**: This memory area is completely private to the current process
  - **Importance**: Most accurately reflects process contribution to system memory
  - **Next Step Tools**: Use HPROF to analyze specific object usage

- **private dirty (2500 kB)**: Private dirty pages
  - **Meaning**: Modified private memory pages
  - **Characteristics**: Cannot be shared with other processes, cannot be swapped out
  - **Optimization Suggestion**: Monitor growth trends, avoid unnecessary object creation

### 2. Native Heap Memory

```
[anon:scudo:primary]
    16384    16000    16000        0        0        0    16000        0        0
```

**Detailed Explanation**:
- **scudo:primary**: Android's new memory allocator
  - **Source**: C/C++ code malloc/new allocations
  - **Characteristics**: Provides memory safety protection mechanisms
  - **Version**: Default enabled on Android 11+

- **High private dirty (16000 kB)**: 
  - **Meaning**: Heavy memory allocation by Native code
  - **Problem Diagnosis**: Check JNI calls, third-party libraries, NDK code
  - **Next Step Tools**: 
    ```bash
    # Analyze Native memory details
    adb shell "dumpsys meminfo <package> -d"
    # View call stacks
    adb shell "debuggerd -b <pid>"
    ```

### 3. Graphics Memory

```
/dev/kgsl-3d0
     6016     6016     6016        0        0        0     6016        0        0
```

**Detailed Explanation**:
- **kgsl-3d0**: GPU graphics memory device
  - **Source**: OpenGL/Vulkan textures, buffers, shaders
  - **Characteristics**: Direct GPU memory mapping, cannot be swapped out
  - **Importance**: Affects graphics performance and memory usage

- **High PSS value**: Graphics memory intensive usage
  - **Problem Diagnosis**: Check texture sizes, buffer quantities
  - **Optimization Suggestions**: 
    - Use compressed texture formats
    - Timely release unused graphics resources
    - Use object pools to reduce frequent allocations

- **Next Step Tools**:
  ```bash
  # GPU memory details
  adb shell "cat /d/kgsl/proc/<pid>/mem"
  # Graphics performance analysis
  adb shell "dumpsys gfxinfo <package>"
  ```

### 4. Shared Library Memory

```
/vendor/lib64/libllvm-glnext.so
     3568      859      215      644        0        0        0        0        0
```

**Detailed Explanation**:
- **virtual vs RSS**: Large virtual space but small actual usage
  - **Reason**: On-demand loading mechanism, only loads used code segments
  - **Optimization**: Indicates efficient system memory management

- **High shared clean (644 kB)**:
  - **Meaning**: Multi-process shared read-only code segments
  - **Advantage**: Saves system memory, one copy used by multiple processes
  - **Calculation**: PSS = private + shared/sharing processes

- **Low PSS (215 kB)**:
  - **Meaning**: Although library is large, memory allocated to process is small
  - **Importance**: Demonstrates efficiency of shared memory

### 5. APK File Mapping

```
/system_ext/priv-app/Launcher3QuickStep/Launcher3QuickStep.apk
     2560     2480      620     1860        0        0        0        0        0
```

**Detailed Explanation**:
- **APK memory mapping**: Application package directly mapped to memory
  - **Contains**: DEX code, resource files, Native libraries
  - **Characteristics**: Read-only mapping, can be reclaimed and reloaded by system

- **High shared clean (1860 kB)**:
  - **Advantage**: Multiple components of the same APK can share the same code
  - **Source**: System maps APK as shared read-only memory

- **PSS calculation example**:
  ```
  PSS = private clean + shared clean / sharing processes
  620 = 0 + 1860 / 3 (assuming 3 processes sharing)
  ```

---

## 🔍 Memory Classification Statistics

### Typical showmap Summary Section

```
   -------- -------- -------- ------- ------- ------- ------- ------- -------
    332928    50816    49702   24056    2100       48   24612       0       0 TOTAL
```

#### Total Line Interpretation

- **virtual (332928 kB)**: Total virtual address space
  - **32-bit processes**: Theoretical maximum 4GB, actual usable ~3GB
  - **64-bit processes**: Theoretical maximum very large, actually limited by system configuration
  - **Problem**: Excessive size may cause address space fragmentation

- **RSS (50816 kB)**: Total physical memory usage
  - **System Impact**: Directly affects available memory
  - **Comparison**: Corresponds to VSZ/RSS in `ps` command
  - **Monitoring**: Continuous growth needs attention

- **PSS (49702 kB)**: Actual memory contribution
  - **Most Important Metric**: Process's real contribution to system memory pressure
  - **Calculation**: Considers shared memory allocation
  - **Optimization Target**: Primary optimization goal

- **shared clean (24056 kB)**: Shared read-only memory
  - **Advantage**: No additional memory usage, shared by multiple processes
  - **Source**: System libraries, APK files, read-only data

- **private dirty (24612 kB)**: Private dirty pages
  - **Key Metric**: Portion that truly consumes system memory
  - **Cannot be reclaimed**: This memory cannot be reclaimed by the system
  - **Optimization Focus**: Reducing this type of memory is optimization priority

---

## 🚨 Problem Diagnosis Patterns

### 1. Memory Leak Detection

#### Symptom Identification
```bash
# First measurement
adb shell "showmap <pid>" > showmap_1.txt

# Perform potentially leaking operations
# ... user operations ...

# Second measurement
adb shell "showmap <pid>" > showmap_2.txt

# Comparative analysis
diff showmap_1.txt showmap_2.txt
```

#### Key Metric Changes
- **PSS continuous growth**: Overall memory leak
- **private dirty growth**: Heap memory leak
- **Specific mapping area growth**: Targeted analysis

#### Diagnosis Process
1. **Java heap leak**:
   ```bash
   # Check if Dalvik-related lines are growing
   grep "dalvik" showmap_output.txt
   # Further HPROF analysis
   python3 tools/hprof_dumper.py -pkg <package>
   # Or use one-click analysis
   python3 analyze.py live --package <package>
   ```

2. **Native memory leak**:
   ```bash
   # Check anon anonymous memory growth
   grep "anon:" showmap_output.txt
   # Analyze Native memory details
   adb shell "dumpsys meminfo <package> -d"
   ```

3. **File descriptor leak**:
   ```bash
   # Check number of mapped files
   adb shell "ls -la /proc/<pid>/fd | wc -l"
   # View open files
   adb shell "ls -la /proc/<pid>/fd"
   ```

### 2. Memory Usage Pattern Analysis

#### Healthy Memory Pattern
```
- Large shared clean (shared libraries, APK)
- Moderate private dirty (application data)
- Less private clean (temporary data)
- Minimal or no swap
```

#### Abnormal Pattern Recognition

**Pattern 1: Graphics Memory Overload**
```
/dev/kgsl-3d0        High memory usage
/dev/mali0           Excessive GPU device usage
```
- **Problem**: Poor texture and buffer management
- **Next Step**: Use GPU analysis tools

**Pattern 2: Excessive Library Loading**
```
Multiple .so files    Many library mappings
virtual >> RSS        Libraries loaded but unused
```
- **Problem**: Unnecessary library loading
- **Next Step**: Analyze application dependencies, lazy loading

**Pattern 3: Excessive Data Cache**
```
private dirty continuous growth
[anon:...] type growth
```
- **Problem**: Poor cache strategy
- **Next Step**: Check cache implementation and cleanup mechanisms

### 3. Performance Impact Assessment

#### Memory Efficiency Metrics

**Sharing Efficiency**:
```bash
Sharing efficiency = shared memory / (shared + private) * 100%
Efficient: >40%
Average: 20-40%  
Inefficient: <20%
```

**Memory Density**:
```bash
Memory density = RSS / virtual * 100%
High density: >30% (full memory utilization)
Low density: <10% (possible memory waste)
```

**Dirty Page Ratio**:
```bash
Dirty page ratio = private dirty / RSS * 100%
Normal: <70%
Abnormal: >90% (large amount of non-reclaimable memory)
```

---

## 📊 Data Comparison with Other Tools

### Comparison with `/proc/pid/status`

```bash
# showmap total
PSS: 49702 kB

# /proc/pid/status
VmRSS: 50816 kB    # Corresponds to showmap RSS
VmSize: 332928 kB  # Corresponds to showmap virtual
```

### Comparison with `dumpsys meminfo`

```bash
# PSS total in dumpsys meminfo should be close to showmap PSS
# But classification methods differ:
# dumpsys: Classified by function (Dalvik, Native, Graphics...)
# showmap: Classified by memory mapping (file mapping, anonymous mapping...)
```

### Data Consistency Check

```bash
#!/bin/bash
PID=$1

echo "=== Data Consistency Check ==="
echo "showmap PSS:"
adb shell "showmap $PID" | tail -1 | awk '{print $3}'

echo "dumpsys PSS:"
adb shell "dumpsys meminfo $PID" | grep "TOTAL PSS:" | awk '{print $3}'

echo "status VmRSS:"
adb shell "cat /proc/$PID/status" | grep VmRSS | awk '{print $2}'
```

---

## 🔧 Advanced Analysis Techniques

### 1. Automated Monitoring Script

```bash
#!/bin/bash
# showmap_monitor.sh

PID=$1
INTERVAL=${2:-60}  # Default 60 second interval
LOG_FILE="showmap_monitor_$(date +%Y%m%d_%H%M%S).log"

echo "Starting monitoring process $PID, interval $INTERVAL seconds"
echo "Timestamp,Virtual,RSS,PSS,SharedClean,SharedDirty,PrivateClean,PrivateDirty" > $LOG_FILE

while true; do
    TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
    SHOWMAP_OUTPUT=$(adb shell "showmap $PID" 2>/dev/null | tail -1)
    
    if [ $? -eq 0 ]; then
        echo "$TIMESTAMP,$SHOWMAP_OUTPUT" >> $LOG_FILE
        echo "[$TIMESTAMP] PSS: $(echo $SHOWMAP_OUTPUT | awk '{print $3}') kB"
    else
        echo "[$TIMESTAMP] Process may have exited"
        break
    fi
    
    sleep $INTERVAL
done
```

### 2. Memory Hotspot Analysis

```bash
#!/bin/bash
# memory_hotspot.sh

PID=$1

echo "=== Memory Hotspot Analysis ==="
echo "1. Largest memory mapping areas:"
adb shell "showmap $PID" | grep -v "TOTAL" | sort -k3 -nr | head -5

echo ""
echo "2. Areas with most private dirty pages:"
adb shell "showmap $PID" | grep -v "TOTAL" | sort -k8 -nr | head -5

echo ""
echo "3. Possible memory leak points:"
adb shell "showmap $PID" | grep -E "(anon:|dalvik)" | sort -k3 -nr
```

### 3. Memory Baseline Comparison

```bash
#!/bin/bash
# memory_baseline.sh

PACKAGE=$1
OPERATION=$2

echo "=== Memory Baseline Test ==="

# Get PID
PID=$(adb shell "pidof $PACKAGE")
if [ -z "$PID" ]; then
    echo "Application not running: $PACKAGE"
    exit 1
fi

# Baseline state
echo "Recording baseline state..."
adb shell "showmap $PID" > baseline_showmap.txt
BASELINE_PSS=$(tail -1 baseline_showmap.txt | awk '{print $3}')

echo "Baseline PSS: $BASELINE_PSS kB"
echo "Executing operation: $OPERATION"
echo "Press Enter to continue..."
read

# Post-operation state
echo "Recording post-operation state..."
adb shell "showmap $PID" > after_showmap.txt
AFTER_PSS=$(tail -1 after_showmap.txt | awk '{print $3}')

# Calculate difference
DIFF_PSS=$((AFTER_PSS - BASELINE_PSS))
echo ""
echo "=== Result Analysis ==="
echo "Baseline PSS: $BASELINE_PSS kB"
echo "Post-operation PSS: $AFTER_PSS kB"
echo "PSS change: $DIFF_PSS kB"

if [ $DIFF_PSS -gt 1000 ]; then
    echo "⚠️  Memory growth over 1MB, recommend checking for memory leaks"
elif [ $DIFF_PSS -gt 500 ]; then
    echo "⚠️  Large memory growth, needs attention"
else
    echo "✅ Memory growth within normal range"
fi

# Detailed comparison
echo ""
echo "=== Detailed Comparison ==="
diff -u baseline_showmap.txt after_showmap.txt
```

---

## 🔗 Related Tool Links

- **Application Level Analysis**: [dumpsys meminfo Interpretation Guide](./meminfo_interpretation_guide.md)
- **System Level Analysis**: [/proc/meminfo Interpretation Guide](./proc_meminfo_interpretation_guide.md)
- **Process Detailed Analysis**: [smaps Interpretation Guide](./smaps_interpretation_guide.md)  
- **Application Memory Analysis**: [Analysis Results Guide](./analysis_results_interpretation_guide.md)

---

## 💡 Best Practice Recommendations

### 1. Daily Monitoring
- Establish application memory baseline data
- Regularly use showmap to check memory trends
- Cross-validate with dumpsys meminfo

### 2. Problem Diagnosis
- Use differential comparison to detect memory leaks
- Focus on private dirty growth trends
- Analyze PSS values rather than virtual sizes

### 3. Performance Optimization
- Prioritize reducing private dirty memory
- Fully utilize shared memory (shared clean)
- Avoid unnecessary large file mappings

### 4. Tool Combination
- showmap provides overview, HPROF provides details
- Combine GPU profiler for graphics memory analysis
- Use Native memory tools for C/C++ memory analysis

Through deep understanding of each field in showmap output and memory mapping patterns, you can quickly identify memory usage anomalies and provide directional guidance for in-depth memory optimization.