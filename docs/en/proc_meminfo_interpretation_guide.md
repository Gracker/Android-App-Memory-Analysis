# Android /proc/meminfo Output Interpretation Guide

## 📋 Overview

The `/proc/meminfo` file provides system-level memory usage statistics. This is the foundation of Android system memory analysis, and understanding the meaning of each item is crucial for memory optimization.

---

## 🔍 Methods to Get /proc/meminfo

```bash
# Method 1: Direct view via ADB
adb shell "cat /proc/meminfo"

# Method 2: Using dumpsys tools
adb shell "dumpsys meminfo"

# Method 3: Save to file for analysis
adb shell "cat /proc/meminfo" > meminfo.txt
```

---

## 📊 Detailed /proc/meminfo Output Explanation

### Basic Memory Information

#### MemTotal (Total Memory)
```
MemTotal:        3951616 kB
```
- **Meaning**: Total amount of physical memory on the device
- **Source**: System hardware configuration, minus kernel reserved portions
- **Problem Diagnosis**: If application memory usage approaches this value, indicates high memory pressure
- **Next Step Tools**: 
  - Use `free -m` to view memory usage details
  - Analyze specific application memory usage: `dumpsys meminfo <package_name>`

#### MemFree (Free Memory)
```
MemFree:          234567 kB
```
- **Meaning**: Currently completely unused physical memory
- **Source**: Kernel memory management statistics
- **Normal Range**: Usually 5%-20% of total memory
- **Problem Diagnosis**: 
  - Too low (<5%): High system memory pressure, possible OOM
  - Too high (>50%): Low application utilization or just restarted
- **Next Step Tools**:
  - Low memory: Use `dumpsys procstats` to analyze process statistics
  - Memory leaks: Use HPROF to analyze heap memory

#### MemAvailable (Available Memory)
```
MemAvailable:     1234567 kB
```
- **Meaning**: Memory that the system can allocate to new applications (including reclaimable cache)
- **Source**: Kernel calculation of MemFree + reclaimable cache + swappable memory
- **Importance**: More accurately reflects actual available memory than MemFree
- **Problem Diagnosis**: 
  - <100MB: Severe memory shortage, system may kill applications
  - 100-300MB: Memory tension, needs optimization
  - >500MB: Sufficient memory
- **Next Step Tools**:
  - Analyze high memory consumers: `dumpsys meminfo -a`
  - Monitor memory trends: `watch -n 5 'cat /proc/meminfo | head -10'`

### Buffers and Cache

#### Buffers (Buffer Cache)
```
Buffers:          45678 kB
```
- **Meaning**: File system metadata cache (directory info, inodes, etc.)
- **Source**: Kernel caching to accelerate file system access
- **Normal Range**: Usually tens of MB, grows with file operations
- **Problem Diagnosis**: 
  - Abnormal growth: Possible heavy file operations or file system issues
- **Next Step Tools**:
  - Check file system usage: `df -h`
  - Monitor I/O: `iostat 1`

#### Cached (Page Cache)
```
Cached:           891234 kB
```
- **Meaning**: File content cache used to accelerate file reading
- **Source**: Kernel caching of read file contents
- **Characteristics**: Can be reclaimed when memory is insufficient
- **Problem Diagnosis**: 
  - Too large and continuously growing: Possible memory leak or cache strategy issues
  - Too small: File access performance may be affected
- **Next Step Tools**:
  - Test cache cleanup: `echo 3 > /proc/sys/vm/drop_caches`
  - Analyze cache content: `cat /proc/meminfo | grep -E "(Cached|SReclaimable)"`

#### SwapCached (Swap Cache)
```
SwapCached:       12345 kB
```
- **Meaning**: Pages that have been read back from swap but still remain in swap
- **Source**: Swap mechanism optimization to avoid duplicate writes
- **Android Characteristics**: Many Android devices don't enable traditional swap
- **Problem Diagnosis**: 
  - Has value and continuously growing: Memory pressure causing frequent swapping
- **Next Step Tools**:
  - Check swap usage: `cat /proc/swaps`
  - Analyze swap activity: `vmstat 1`

### Active and Inactive Memory

#### Active (Active Memory)
```
Active:           1234567 kB
```
- **Meaning**: Memory pages that have been recently accessed
- **Source**: Kernel LRU (Least Recently Used) algorithm tracking
- **Classification**: Includes active portions of application memory and file cache
- **Problem Diagnosis**: 
  - Too high percentage (>70%): Intense memory competition, may affect performance
- **Next Step Tools**:
  - View detailed classification: `cat /proc/meminfo | grep -E "(Active|Inactive)"`
  - Analyze application activity: `dumpsys activity`

#### Inactive (Inactive Memory)
```
Inactive:         567890 kB
```
- **Meaning**: Memory pages that haven't been accessed for a longer time
- **Source**: Candidate reclaim memory identified by LRU algorithm
- **Reclaim Priority**: This memory is prioritized for reclaim when memory is insufficient
- **Problem Diagnosis**: 
  - Imbalanced ratio: Abnormal Active/Inactive ratio may affect performance
- **Next Step Tools**:
  - Force memory reclaim test: `echo 1 > /proc/sys/vm/drop_caches`

### Specific Memory Types

#### Slab (Kernel Object Cache)
```
Slab:             123456 kB
```
- **Meaning**: Cache for dynamically allocated kernel data structures
- **Source**: Kernel slab allocator statistics
- **Contains**: inode cache, dentry cache, network buffers, etc.
- **Problem Diagnosis**: 
  - Abnormal growth: Possible kernel memory leak or massive object allocation
  - Normal range: Usually tens to hundreds of MB
- **Next Step Tools**:
  - Detailed slab info: `cat /proc/slabinfo`
  - View specific categories: `slabtop` (if available)

#### SReclaimable (Reclaimable Slab)
```
SReclaimable:     45678 kB
```
- **Meaning**: Kernel cache that can be reclaimed under memory pressure
- **Source**: Reclaimable portion in slab allocator
- **Characteristics**: Mainly directory entry cache and inode cache
- **Problem Diagnosis**: 
  - Evaluate total reclaimable memory together with Cached
- **Next Step Tools**:
  - Force reclaim: `echo 2 > /proc/sys/vm/drop_caches`

#### SUnreclaim (Unreclaimable Slab)
```
SUnreclaim:       78901 kB
```
- **Meaning**: Kernel memory that cannot be reclaimed
- **Source**: Critical kernel data structures
- **Characteristics**: This memory cannot be freed
- **Problem Diagnosis**: 
  - Abnormal growth: Possible kernel memory leak, may need restart
- **Next Step Tools**:
  - Analyze kernel modules: `lsmod`
  - Check kernel logs: `dmesg | grep -i memory`

### Android-Specific Memory Types

#### Mapped (Mapped Memory)
```
Mapped:           234567 kB
```
- **Meaning**: Memory mapped to process address space through mmap
- **Source**: File mappings, shared libraries, anonymous mappings, etc.
- **Android Characteristics**: Includes APK, SO file, ART file mappings
- **Problem Diagnosis**: 
  - Too large: Possible excessive file mappings or memory-mapped files
- **Next Step Tools**:
  - Analyze process mappings: `cat /proc/<pid>/maps`
  - Use SMAPS analysis: `python3 smaps_parser.py -p <pid>`

#### AnonPages (Anonymous Pages)
```
AnonPages:        345678 kB
```
- **Meaning**: Memory pages not associated with files
- **Source**: Heap memory, stack memory, anonymous mmap
- **Android Characteristics**: Includes Dalvik heap, Native heap, etc.
- **Problem Diagnosis**: 
  - Continuous growth: Possible memory leak
  - Sudden increase: Application allocated large amount of memory
- **Next Step Tools**:
  - HPROF analysis for Java heap: `python3 hprof_dumper.py`
  - Analyze Native memory: `dumpsys meminfo <package> -d`

### Memory Reclaim Related

#### Unevictable (Non-evictable Memory)
```
Unevictable:      12345 kB
```
- **Meaning**: Pages locked in memory that cannot be swapped out
- **Source**: Memory locked by mlock(), critical kernel pages
- **Android Characteristics**: Usually includes some critical system services
- **Problem Diagnosis**: 
  - Abnormal growth: Possible incorrect mlock usage by applications
- **Next Step Tools**:
  - View locked memory details: `cat /proc/*/status | grep VmLck`

#### Mlocked (Locked Memory)
```
Mlocked:          6789 kB
```
- **Meaning**: Memory locked through mlock() system calls
- **Source**: Applications or system services actively locking
- **Problem Diagnosis**: 
  - Large value: Check if applications are abusing memory locking
- **Next Step Tools**:
  - Find processes with locked memory: `grep -r VmLck /proc/*/status`

---

## 🚨 Common Problem Diagnosis Procedures

### 1. Out of Memory (OOM) Diagnosis

**Symptoms**: 
```
MemAvailable:     45678 kB    # < 100MB
MemFree:          12345 kB    # Very low
```

**Diagnosis Steps**:
1. Check total memory usage rate: `(MemTotal - MemAvailable) / MemTotal * 100%`
2. Analyze high memory consumers: `dumpsys meminfo -a | head -20`
3. Check OOM logs: `dmesg | grep -i "killed process"`
4. Use HPROF to analyze application memory

**Recommended Tools**:
```bash
# 1. System memory overview
adb shell "dumpsys meminfo"

# 2. Application detailed analysis
adb shell "dumpsys meminfo <package_name>"

# 3. Get HPROF analysis
python3 hprof_dumper.py -pkg <package_name>
```

### 2. Memory Leak Detection

**Symptoms**:
```
AnonPages:        Continuous growth
Cached:           Normal or declining
SwapCached:       Possible growth
```

**Diagnosis Steps**:
1. Monitor memory trends: `watch -n 10 'cat /proc/meminfo | head -10'`
2. Compare memory before and after application restart
3. Check if memory is freed after GC execution
4. Use HPROF comparative analysis

**Recommended Tools**:
```bash
# 1. Scheduled monitoring
while true; do 
    echo "$(date): $(cat /proc/meminfo | grep MemAvailable)"
    sleep 60
done

# 2. Application memory tracking
adb shell "am start -a android.intent.action.MAIN -c android.intent.category.LAUNCHER <package_name>"
# Wait for application startup
python3 hprof_dumper.py -pkg <package_name> -o before/
# Perform operations
python3 hprof_dumper.py -pkg <package_name> -o after/
```

### 3. Cache Efficiency Analysis

**Symptoms**:
```
Cached:           Abnormally large or small
Buffers:          Abnormal changes
SReclaimable:     Abnormal values
```

**Diagnosis Steps**:
1. Calculate cache hit rate related metrics
2. Analyze file access patterns
3. Test impact of cache cleanup on performance

**Recommended Tools**:
```bash
# 1. Cache statistics
echo "Total cache: $(($(grep 'Cached:' /proc/meminfo | awk '{print $2}') + $(grep 'Buffers:' /proc/meminfo | awk '{print $2}'))) kB"

# 2. Cache cleanup test
echo 3 > /proc/sys/vm/drop_caches
# Monitor memory changes and performance impact after cleanup
```

---

## 📈 Memory Health Assessment Standards

### Excellent (Green)
- MemAvailable > 500MB
- MemFree > 200MB  
- Active/Inactive ratio 1:1 to 2:1
- Slab < 100MB
- No continuously growing AnonPages

### Good (Yellow)
- MemAvailable 200-500MB
- MemFree 50-200MB
- Cached accounts for 20-40% of total memory
- Slight memory pressure indicators

### Warning (Orange)
- MemAvailable 100-200MB
- MemFree < 50MB
- Frequent memory reclaim activity
- Abnormal Unevictable memory

### Dangerous (Red)
- MemAvailable < 100MB
- Frequent OOM process kills
- SwapCached continuous growth
- SUnreclaim abnormal growth

---

## 🔗 Related Tool Links

- **Application Level Analysis**: [dumpsys meminfo Interpretation Guide](./meminfo_interpretation_guide.md)
- **Process Level Analysis**: [showmap Interpretation Guide](./showmap_interpretation_guide.md)
- **Detailed Mapping Analysis**: [smaps Interpretation Guide](./smaps_interpretation_guide.md)  
- **Analysis Results Understanding**: [Analysis Results Guide](./analysis_results_interpretation_guide.md)

---

## 💡 Best Practice Recommendations

1. **Regular Monitoring**: Establish memory monitoring scripts to regularly collect meminfo data
2. **Baseline Comparison**: Save normal state meminfo as comparison baseline
3. **Trend Analysis**: Focus on memory usage trends rather than single-point data
4. **Combine Other Tools**: meminfo is just the starting point, needs to be combined with SMAPS, HPROF, etc. for in-depth analysis
5. **Documentation**: Record abnormal situations and solutions, build problem database

Through deep understanding of each meminfo indicator, you can quickly locate the direction of memory problems and lay the foundation for further detailed analysis.