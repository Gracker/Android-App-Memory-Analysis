# Android-App-Memory-Analysis

[中文版本](./README_zh.md) | English Version

Android application memory analysis toolkit providing SMAPS and HPROF core functionality to help developers deeply analyze application memory usage.

## 📊 Core Features Overview

### 🗺️ SMAPS Memory Mapping Analysis
- **Function**: Analyze Android application `/proc/pid/smaps` files
- **Usage**: Native memory, system memory, mapped file analysis
- **Support**: Android 4.0 - Android 16+ (full version compatibility)
- **Permission**: Requires Root access

### ☕ HPROF Java Heap Analysis  
- **Function**: Dump and parse Android application Java heap memory
- **Usage**: Java object analysis, memory leak detection
- **Support**: All Android versions
- **Permission**: No Root required

### 📈 Comprehensive Memory Analysis
- **Function**: Combine SMAPS and HPROF data for complete analysis
- **Usage**: Complete memory performance evaluation and optimization recommendations
- **Output**: Structured reports and JSON data

---

## 🚀 Quick Start

### Automated Analysis Script (Recommended)

```bash
# 1. List running applications
./scripts/analyze_memory.sh --list

# 2. Complete memory analysis (SMAPS + HPROF + comprehensive analysis)
./scripts/analyze_memory.sh --full -pkg com.example.app

# 3. Java heap memory analysis only
./scripts/analyze_memory.sh --hprof-only -pkg com.example.app

# 4. System memory mapping analysis only  
./scripts/analyze_memory.sh --smaps-only -p 12345

# 5. Specify output directory
./scripts/analyze_memory.sh --full -pkg com.example.app -o /path/to/output
```

---

## 🗺️ SMAPS Memory Mapping Analysis

### Feature Introduction

SMAPS (System Memory Maps) analysis tool parses `/proc/pid/smaps` files, providing detailed process memory mapping information.

**Supported Memory Types (Android Version Adaptive)**:
- **Basic Types** (Android 4.0+): Dalvik, Native, Stack, Graphics
- **Extended Types** (Android 5.0+): Dalvik subtypes, DEX/VDEX, ART
- **Modern Types** (Android 15+): Native Heap, DMA-BUF, JIT Cache  
- **Latest Types** (Android 16+): Scudo allocator, GWP-ASan, 16KB page optimization

### Basic Usage

```bash
# Direct analysis by process PID (requires Root permission)
python3 tools/smaps_parser.py -p 12345

# Analyze existing smaps file
python3 tools/smaps_parser.py -f /path/to/smaps_file

# Filter specific memory types
python3 tools/smaps_parser.py -p 12345 -t "Native"

# Specify output file
python3 tools/smaps_parser.py -p 12345 -o detailed_analysis.txt

# Simple output mode
python3 tools/smaps_parser.py -p 12345 -s
```

### Advanced Usage

```bash
# Analyze specific memory types
python3 tools/smaps_parser.py -p 12345 -t "Dalvik"          # Dalvik memory only
python3 tools/smaps_parser.py -p 12345 -t "graphics"        # Graphics memory only
python3 tools/smaps_parser.py -p 12345 -t ".so mmap"        # Dynamic library memory only

# Batch analyze multiple processes
for pid in 1234 5678 9012; do
    python3 tools/smaps_parser.py -p $pid -o "analysis_$pid.txt"
done
```

### Getting smaps Files

If you want to manually obtain smaps files:

```bash
# Method 1: Direct pull (requires Root)
adb shell "su -c 'cat /proc/PID/smaps'" > smaps_file.txt

# Method 2: Copy then pull  
adb shell "su -c 'cp /proc/PID/smaps /data/local/tmp/'"
adb pull /data/local/tmp/smaps ./
```

### SMAPS Output Description

```
Android App Memory Analysis Report
========================================

Memory Overview:
Total Memory Usage: 245.67 MB
Total Swap Memory: 12.34 MB

Dalvik (Dalvik Virtual Machine Runtime Memory) : 89.234 MB
    PSS: 87.123 MB
    SwapPSS: 2.111 MB
        [anon:dalvik-main space] : 45123 kB
        [anon:dalvik-large object space] : 32456 kB

Native (Native C/C++ Code Memory) : 56.789 MB
    PSS: 54.321 MB  
    SwapPSS: 2.468 MB
        libc.so : 12345 kB
        libandroid_runtime.so : 8765 kB

graphics (Graphics Related Memory) : 34.567 MB
    PSS: 34.567 MB
    SwapPSS: 0.000 MB

⚠️ Anomaly Detection:
  • [HIGH] Dalvik heap memory too high: 89.2MB, possible Java memory leak
    Recommendation: Check object references, static variable holding, listener unregistration etc.
```

### Supported Parameters

| Parameter | Description | Example |
|-----------|-------------|---------|
| `-p, --pid` | Target process PID | `-p 12345` |
| `-f, --filename` | smaps file path | `-f ./smaps` |
| `-t, --type` | Memory type filter | `-t "Dalvik"` |
| `-o, --output` | Output file path | `-o report.txt` |
| `-s, --simple` | Simple output mode | `-s` |
| `--version` | Show version info | `--version` |

### Common Issues

**Q: Cannot access /proc/pid/smaps?**
```
Error: Cannot access /proc/12345/smaps
Please ensure:
  • Device is rooted
  • ADB connection is working  
  • PID exists and is correct
```

**A:** Ensure device is rooted and authorize `adb su` permission. Test permission with `adb shell su -c "ls /proc/"`.

**Q: Some memory types show 0?**

**A:** This is normal, different Android versions support different memory types. The script automatically adapts to versions and displays corresponding memory types.

---

## ☕ HPROF Java Heap Analysis

### Feature Introduction

HPROF analysis tool specifically for Android application Java heap memory analysis, capable of:
- Automatically dump application Java heap memory
- Parse HPROF file format
- Analyze object and class memory usage
- Identify potential memory leaks

**Advantages**:
- ✅ No Root permission required
- ✅ Support all Android versions
- ✅ Automated dump process
- ✅ Detailed object-level analysis

### HPROF Dump Tool

#### Basic Usage

```bash
# Dump by package name (recommended)
python3 tools/hprof_dumper.py -pkg com.example.app

# Dump by process PID
python3 tools/hprof_dumper.py -p 12345

# Specify output directory
python3 tools/hprof_dumper.py -pkg com.example.app -o /path/to/output

# List running applications
python3 tools/hprof_dumper.py --list
```

#### Output Example

```bash
$ python3 tools/hprof_dumper.py -pkg com.tencent.mm

Found application com.tencent.mm PID: 8234
Starting to dump memory file for process 8234...
Executing command: adb shell "am dumpheap com.tencent.mm /data/local/tmp/com.tencent.mm_8234_20250112_143022.hprof"
Waiting for hprof file generation...
hprof file generated: /data/local/tmp/com.tencent.mm_8234_20250112_143022.hprof
Pulling file to local: adb pull /data/local/tmp/com.tencent.mm_8234_20250112_143022.hprof ./com.tencent.mm_8234_20250112_143022.hprof
hprof file saved to: ./com.tencent.mm_8234_20250112_143022.hprof

hprof file dump completed: ./com.tencent.mm_8234_20250112_143022.hprof
Now you can use hprof_parser.py to analyze this file
```

### HPROF Parser Tool

#### Basic Usage

```bash
# Parse HPROF file
python3 tools/hprof_parser.py -f app.hprof

# Specify output file
python3 tools/hprof_parser.py -f app.hprof -o analysis_report.txt

# Show TOP 50 memory consuming classes
python3 tools/hprof_parser.py -f app.hprof -t 50

# Set minimum display threshold (only show classes > 5MB)
python3 tools/hprof_parser.py -f app.hprof -m 5.0

# Simple output (no detailed object lists)
python3 tools/hprof_parser.py -f app.hprof -s
```

#### Analysis Output Example

```bash
$ python3 tools/hprof_parser.py -f com.tencent.mm_8234_20250112_143022.hprof

Starting HPROF file parsing: com.tencent.mm_8234_20250112_143022.hprof
HPROF version: JAVA PROFILE 1.0.3
Identifier size: 4 bytes
Timestamp: 2025-01-12 14:30:22

=== Memory Analysis Complete ===
Total instances: 2,456,789
Instance total size: 89.34 MB
Total arrays: 345,678
Array total size: 23.45 MB
Total memory usage: 112.79 MB

=== TOP 20 Memory Consuming Classes (minimum 0.1MB) ===
Class Name                                        Instances    Total Size(MB)  Avg Size(KB)
--------------------------------------------------------------------------------------
java.lang.String                                234,567      15.67           0.07
android.graphics.Bitmap                         1,234        12.34           10.24
com.tencent.mm.ui.ChatActivity                  45           8.91            203.56
byte[]                                           89,012       7.23            0.08
java.util.HashMap$Node                          123,456      6.78            0.06
android.view.View                                45,678       5.43            0.12
com.tencent.mm.model.Message                    23,456       4.32            0.19

=== TOP 10 Primitive Array Memory Usage ===
Array Type            Array Count    Total Size(MB)  Avg Size(KB)
----------------------------------------------------------
byte[]               89,012         7.23            0.08
int[]                12,345         3.45            0.29
char[]               56,789         2.78            0.05
long[]               3,456          1.23            0.37

=== String Memory Statistics ===
String instances: 234,567
String total size: 15.67 MB
Average string size: 70.12 bytes

Analysis results exported to: com.tencent.mm_8234_20250112_143022_analysis.txt
```

#### Supported Parameters

| Parameter | Description | Example |
|-----------|-------------|---------|
| `-f, --file` | HPROF file path (required) | `-f app.hprof` |
| `-o, --output` | Analysis result output file | `-o report.txt` |
| `-t, --top` | Show TOP N memory consuming classes | `-t 50` |
| `-m, --min-size` | Minimum display size MB | `-m 1.0` |
| `-s, --simple` | Simple output mode | `-s` |

### Complete HPROF Workflow

```bash
# 1. Find target application
python3 tools/hprof_dumper.py --list

# 2. Dump application memory
python3 tools/hprof_dumper.py -pkg com.example.app

# 3. Parse HPROF file
python3 tools/hprof_parser.py -f com.example.app_12345_20250112_143022.hprof

# 4. View detailed analysis report
cat com.example.app_12345_20250112_143022_analysis.txt
```

### Memory Leak Detection

**Compare two HPROF files to detect memory leaks**:

```bash
# First dump (before operation)
python3 tools/hprof_dumper.py -pkg com.example.app -o ./before/
python3 tools/hprof_parser.py -f ./before/app_before.hprof -o before_analysis.txt

# Perform potentially leak-causing operation...

# Second dump (after operation)  
python3 tools/hprof_dumper.py -pkg com.example.app -o ./after/
python3 tools/hprof_parser.py -f ./after/app_after.hprof -o after_analysis.txt

# Compare analysis results
diff before_analysis.txt after_analysis.txt
```

### Common Issues

**Q: HPROF dump failed?**

```
Error: dump command execution failed
```

**A:** Check the following:
- Is the application running
- Is the package name correct
- Is there enough device storage space
- Is ADB connection working

**Q: Not enough memory when parsing large HPROF files?**

**A:** HPROF files are usually large (hundreds of MB), parsing requires sufficient memory. Suggestions:
- Run on a machine with sufficient memory
- Use `-s` parameter for simplified analysis
- Analyze different memory types in batches

---

## 📈 Comprehensive Memory Analysis

### Feature Introduction

Comprehensive analysis tool combines SMAPS and HPROF data to provide complete memory analysis reports.

### Basic Usage

```bash
# Analyze both HPROF and SMAPS
python3 tools/memory_analyzer.py --hprof app.hprof --smaps smaps_file

# Analyze HPROF only
python3 tools/memory_analyzer.py --hprof app.hprof

# Auto-get SMAPS by PID and analyze
python3 tools/memory_analyzer.py --hprof app.hprof -p 12345

# Analyze SMAPS only
python3 tools/memory_analyzer.py --smaps smaps_file

# Specify output format
python3 tools/memory_analyzer.py --hprof app.hprof --json-output analysis.json
```

### Comprehensive Analysis Output Example

```bash
$ python3 tools/memory_analyzer.py --hprof app.hprof --smaps smaps_file

==========================================================
          Android Application Memory Comprehensive Analysis Report
==========================================================

📊 Memory Usage Summary:
------------------------------
Total Memory Usage: 245.67 MB
Java Heap Memory: 89.34 MB  
Native Heap Memory: 34.21 MB
Dalvik Runtime: 12.45 MB
Native Code: 23.78 MB
Java Heap Percentage: 36.4%

☕ Java Heap Memory Details:
------------------------------
Total Objects: 245,678
Total Arrays: 12,345
String Objects: 34,567
String Memory: 15.67 MB

🏆 TOP 10 Memory Consuming Classes:
Class Name                                     Instances  Total Size(MB)   Avg Size(KB)
------------------------------------------------------------------------
java.lang.String                              34567      15.67            0.46
android.graphics.Bitmap                       234        12.34            54.23
com.tencent.mm.plugin.ChatActivity           1          8.91             8930.45
android.view.ViewGroup                         4567       7.89             1.77
java.util.HashMap$Node                        89012      6.54             0.08

🔧 Native Memory Details:
------------------------------
Native Heap Memory: 34.21 MB
Native Code: 23.78 MB
Graphics Memory: 45.67 MB
OpenGL Memory: 12.34 MB

📈 Memory Category Usage (>1MB):
------------------------------
Dalvik (Dalvik Virtual Machine Runtime Memory): 89.23 MB
graphics (Graphics Related Memory): 45.67 MB
Native (Native C/C++ Code Memory): 34.21 MB
.so mmap (Dynamic Library Mapped Memory): 23.78 MB
native heap (Native Heap Memory): 12.45 MB

💡 Optimization Recommendations:
------------------------------
⚠️ [Java Heap Memory] Java heap memory usage is large (89.3MB), recommend checking for memory leaks
ℹ️ [String Optimization] Strings occupy 15.7MB, recommend optimizing string usage, consider using StringBuilder or string constant pool
ℹ️ [Graphics Memory] Graphics memory usage is high (45.7MB), check bitmap cache and GPU memory usage
ℹ️ [Native Memory] Native heap memory usage is high (34.2MB), check JNI code and third-party libraries

==========================================================
```

### Supported Parameters

| Parameter | Description | Example |
|-----------|-------------|---------|
| `--hprof` | HPROF file path | `--hprof app.hprof` |
| `--smaps` | SMAPS file path | `--smaps smaps_file` |
| `-p, --pid` | Process PID (auto-get smaps) | `-p 12345` |
| `-o, --output` | Analysis result output file | `-o report.txt` |
| `--json-output` | JSON format output file | `--json-output data.json` |

---

## 🔧 Environment Requirements & Configuration

### System Requirements

- **Python**: 3.6+
- **Android SDK**: adb tool
- **Device Requirements**: 
  - SMAPS analysis: Requires Root permission
  - HPROF analysis: No Root required
- **Operating System**: Windows, macOS, Linux

### Installation & Configuration

```bash
# 1. Check Python version
python3 --version

# 2. Check ADB connection
adb devices

# 3. Check device Root permission (required for SMAPS analysis)
adb shell "su -c 'id'"

# 4. Give script execution permission
chmod +x scripts/analyze_memory.sh

# 5. Test tools
python3 tools/hprof_dumper.py --list
```

### ADB Setup

Ensure ADB debugging is enabled:

1. **Developer Options**: Settings → Developer Options
2. **USB Debugging**: Enable USB debugging
3. **Root Permission**: SMAPS analysis requires Root authorization

```bash
# Test ADB connection
adb devices

# Test Root permission
adb shell "su -c 'whoami'"
```

---

## 📚 Advanced Usage & Best Practices

### Batch Analysis

**Analyze multiple applications**:

```bash
#!/bin/bash
# Batch analysis script example

apps=("com.tencent.mm" "com.tencent.mobileqq" "com.example.myapp")

for app in "${apps[@]}"; do
    echo "Analyzing application: $app"
    ./scripts/analyze_memory.sh --full -pkg $app -o "results/$app"
done
```

**Scheduled memory monitoring**:

```bash
#!/bin/bash
# Scheduled monitoring script

while true; do
    timestamp=$(date +%Y%m%d_%H%M%S)
    ./scripts/analyze_memory.sh --smaps-only -pkg com.example.app -o "monitor/monitor_$timestamp"
    sleep 300  # Every 5 minutes
done
```

### Performance Analysis Workflow

**1. Baseline Testing**
```bash
# Analyze immediately after app startup
./scripts/analyze_memory.sh --full -pkg com.example.app -o baseline/
```

**2. Stress Testing**
```bash
# Analyze during high app load
./scripts/analyze_memory.sh --full -pkg com.example.app -o stress_test/
```

**3. Long-term Running Test**
```bash
# Analyze after running for hours
./scripts/analyze_memory.sh --full -pkg com.example.app -o long_running/
```

### Memory Leak Detection Process

**Systematic memory leak detection**:

```bash
# 1. Baseline state after app startup
./scripts/analyze_memory.sh --hprof-only -pkg com.example.app -o step1_baseline/

# 2. Perform target operations (e.g., open pages, load data, etc.)

# 3. State after operations
./scripts/analyze_memory.sh --hprof-only -pkg com.example.app -o step2_after_action/

# 4. Trigger GC and test again
adb shell "am broadcast -a com.example.app.FORCE_GC"
sleep 5
./scripts/analyze_memory.sh --hprof-only -pkg com.example.app -o step3_after_gc/

# 5. Compare analysis results
python3 -c "
import json
with open('step1_baseline/analysis.json') as f1, open('step3_after_gc/analysis.json') as f3:
    baseline = json.load(f1)
    after_gc = json.load(f3)
    print(f'Memory growth: {after_gc[\"summary\"][\"java_heap_mb\"] - baseline[\"summary\"][\"java_heap_mb\"]:.2f} MB')
"
```

---

## 🚨 Troubleshooting

### Common Errors & Solutions

#### SMAPS Related Issues

**Error**: `Cannot access /proc/pid/smaps`
```bash
Error: Cannot access /proc/12345/smaps
Please ensure:
  • Device is rooted  
  • ADB connection is working
  • PID exists and is correct
```

**Solution**:
```bash
# 1. Check Root permission
adb shell "su -c 'whoami'"

# 2. Check if process exists
adb shell "ps | grep 12345"

# 3. Test permission
adb shell "su -c 'ls -la /proc/12345/'"
```

**Error**: `smaps file is empty`

**Solution**:
```bash
# 1. Check process status
adb shell "cat /proc/12345/status"

# 2. Try alternative method
adb shell "su -c 'cat /proc/12345/maps'" > maps_file.txt
```

#### HPROF Related Issues

**Error**: `dump command execution failed`

**Solution**:
```bash
# 1. Check if package name is correct
adb shell "pm list packages | grep com.example"

# 2. Check if application is running
adb shell "ps | grep com.example"

# 3. Check storage space
adb shell "df /data/local/tmp/"

# 4. Manually execute dump command
adb shell "am dumpheap com.example.app /data/local/tmp/test.hprof"
```

**Error**: `HPROF file parsing failed`

**Solution**:
```bash
# 1. Check file size
ls -lh app.hprof

# 2. Check file format (should start with "JAVA PROFILE")
head -c 20 app.hprof

# 3. Use simplified mode for parsing
python3 tools/hprof_parser.py -f app.hprof -s
```

---

## 📖 Documentation

### Chinese Documentation
- **Application Memory**: [dumpsys meminfo Guide](./docs/zh/meminfo_interpretation_guide.md)
- **System Memory**: [/proc/meminfo Guide](./docs/zh/proc_meminfo_interpretation_guide.md)
- **Process Overview**: [showmap Guide](./docs/zh/showmap_interpretation_guide.md)
- **Detailed Mapping**: [smaps Guide](./docs/zh/smaps_interpretation_guide.md)
- **Analysis Results**: [Results Interpretation Guide](./docs/zh/analysis_results_interpretation_guide.md)

### English Documentation
- **Application Memory**: [dumpsys meminfo Guide](./docs/en/meminfo_interpretation_guide.md)
- **System Memory**: [/proc/meminfo Guide](./docs/en/proc_meminfo_interpretation_guide.md)
- **Process Overview**: [showmap Guide](./docs/en/showmap_interpretation_guide.md)
- **Detailed Mapping**: [smaps Guide](./docs/en/smaps_interpretation_guide.md)
- **Analysis Results**: [Results Interpretation Guide](./docs/en/analysis_results_interpretation_guide.md)

---

## 🤝 Contributing & Support

### Contributing Guidelines

Welcome to contribute code, report issues, or suggest features.

**Development Environment Setup**:
```bash
git clone https://github.com/your-repo/Android-App-Memory-Analysis.git
cd Android-App-Memory-Analysis
python3 -m pytest tests/  # Run tests
```

### Issue Feedback

If you encounter issues, please provide the following information:
- Android device model and system version
- Python version
- Error logs
- Reproduction steps

### Changelog

**v2.1 (2025-01)**
- ✅ Merged Android 16 support to main branch
- ✅ Added HPROF analysis functionality
- ✅ Added comprehensive analysis tools
- ✅ Restructured documentation

**v2.0 (2024-12)**
- ✅ Support Android 15+ new memory types
- ✅ Added memory anomaly detection
- ✅ Optimized ADB command compatibility

**v1.0 (2019-06)**
- ✅ Basic SMAPS parsing functionality
- ✅ Support Android 4.0-14

---

## 📄 License

This project is licensed under the MIT License. See LICENSE file for details.

---

## 🔗 Related Resources

- [Android Memory Management Official Documentation](https://developer.android.com/topic/performance/memory)
- [HPROF File Format Specification](https://docs.oracle.com/javase/8/docs/technotes/samples/hprof.html)
- [Linux /proc/pid/smaps Documentation](https://www.kernel.org/doc/Documentation/filesystems/proc.txt)
- [Android ART Memory Management](https://source.android.com/docs/core/runtime/art-gc)