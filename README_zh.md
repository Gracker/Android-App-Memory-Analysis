# Android-App-Memory-Analysis

Android 应用内存分析工具集，提供 SMAPS 和 HPROF 两大核心功能，帮助开发者深入分析应用内存使用情况。

## 📊 核心功能概述

### 🗺️ SMAPS 内存映射分析
- **功能**: 分析 Android 应用的 `/proc/pid/smaps` 文件
- **用途**: Native 内存、系统内存、映射文件分析
- **支持**: Android 4.0 - Android 16+ (全版本兼容)
- **权限**: 需要 Root 权限

### ☕ HPROF Java 堆分析  
- **功能**: dump 和解析 Android 应用 Java 堆内存
- **用途**: Java 对象分析、内存泄漏检测
- **支持**: 所有 Android 版本
- **权限**: 无需 Root 权限

### 📈 综合内存分析
- **功能**: 结合 SMAPS 和 HPROF 数据进行全面分析
- **用途**: 完整的内存性能评估和优化建议
- **输出**: 结构化报告和 JSON 数据

---

## 🚀 快速开始

### 自动化分析脚本 (推荐)

```bash
# 1. 列出正在运行的应用
./analyze_memory.sh --list

# 2. 完整内存分析 (SMAPS + HPROF + 综合分析)
./analyze_memory.sh --full -pkg com.example.app

# 3. 仅 Java 堆内存分析
./analyze_memory.sh --hprof-only -pkg com.example.app

# 4. 仅系统内存映射分析  
./analyze_memory.sh --smaps-only -p 12345

# 5. 指定输出目录
./analyze_memory.sh --full -pkg com.example.app -o /path/to/output
```

---

## 🗺️ SMAPS 内存映射分析

### 功能介绍

SMAPS (System Memory Maps) 分析工具解析 `/proc/pid/smaps` 文件，提供详细的进程内存映射信息。

**支持的内存类型 (Android 版本自适应)**:
- **基础类型** (Android 4.0+): Dalvik, Native, Stack, Graphics
- **扩展类型** (Android 5.0+): Dalvik 子类型, DEX/VDEX, ART
- **现代类型** (Android 15+): Native Heap, DMA-BUF, JIT Cache  
- **最新类型** (Android 16+): Scudo 分配器, GWP-ASan, 16KB 页面优化

### 基本用法

```bash
# 通过进程 PID 直接分析 (需要 Root 权限)
python3 smaps_parser.py -p 12345

# 分析现有的 smaps 文件
python3 smaps_parser.py -f /path/to/smaps_file

# 过滤特定内存类型
python3 smaps_parser.py -p 12345 -t "Native"

# 指定输出文件
python3 smaps_parser.py -p 12345 -o detailed_analysis.txt

# 简化输出模式
python3 smaps_parser.py -p 12345 -s
```

### 高级用法

```bash
# 分析特定内存类型
python3 smaps_parser.py -p 12345 -t "Dalvik"          # 仅 Dalvik 内存
python3 smaps_parser.py -p 12345 -t "graphics"        # 仅图形内存
python3 smaps_parser.py -p 12345 -t ".so mmap"        # 仅动态库内存

# 批量分析多个进程
for pid in 1234 5678 9012; do
    python3 smaps_parser.py -p $pid -o "analysis_$pid.txt"
done
```

### 获取 smaps 文件

如果你想手动获取 smaps 文件:

```bash
# 方法1: 直接拉取 (需要 Root)
adb shell "su -c 'cat /proc/PID/smaps'" > smaps_file.txt

# 方法2: 先拷贝再拉取  
adb shell "su -c 'cp /proc/PID/smaps /data/local/tmp/'"
adb pull /data/local/tmp/smaps ./
```

### SMAPS 输出说明

```
Android App Memory Analysis Report
========================================

内存概览 / Memory Overview:
总内存使用: 245.67 MB
总交换内存: 12.34 MB

Dalvik (Dalvik虚拟机运行时内存) : 89.234 MB
    PSS: 87.123 MB
    SwapPSS: 2.111 MB
        [anon:dalvik-main space] : 45123 kB
        [anon:dalvik-large object space] : 32456 kB

Native (本地C/C++代码内存) : 56.789 MB
    PSS: 54.321 MB  
    SwapPSS: 2.468 MB
        libc.so : 12345 kB
        libandroid_runtime.so : 8765 kB

graphics (图形相关内存) : 34.567 MB
    PSS: 34.567 MB
    SwapPSS: 0.000 MB

🚀 检测到的Android特性:
  • 检测到Android 16 Scudo安全分配器: 5.2MB
    说明: Scudo分配器提供内存安全保护

⚠️ 异常检测:
  • [HIGH] Dalvik堆内存过高: 89.2MB，可能存在Java内存泄漏
    建议: 检查对象引用、静态变量持有、监听器未注销等
```

### 支持的参数详解

| 参数 | 说明 | 示例 |
|------|------|------|
| `-p, --pid` | 目标进程PID | `-p 12345` |
| `-f, --filename` | smaps文件路径 | `-f ./smaps` |
| `-t, --type` | 内存类型过滤 | `-t "Dalvik"` |
| `-o, --output` | 输出文件路径 | `-o report.txt` |
| `-s, --simple` | 简化输出模式 | `-s` |
| `--version` | 显示版本信息 | `--version` |

### 常见问题

**Q: 提示无法访问 /proc/pid/smaps？**
```
错误: 无法访问 /proc/12345/smaps
请确保:
  • 设备已获得root权限
  • ADB连接正常  
  • PID存在且正确
```

**A:** 确保设备已 root 并授权 `adb su` 权限。可以通过 `adb shell su -c "ls /proc/"` 测试权限。

**Q: 某些内存类型显示为 0？**

**A:** 这是正常的，不同 Android 版本支持的内存类型不同。脚本会自动适配版本并显示相应的内存类型。

---

## ☕ HPROF Java 堆分析

### 功能介绍

HPROF 分析工具专门用于 Android 应用的 Java 堆内存分析，可以：
- 自动 dump 应用的 Java 堆内存
- 解析 HPROF 文件格式
- 分析对象和类的内存占用
- 识别潜在的内存泄漏

**优势**:
- ✅ 无需 Root 权限
- ✅ 支持所有 Android 版本
- ✅ 自动化 dump 流程
- ✅ 详细的对象级分析

### HPROF Dump 工具

#### 基本用法

```bash
# 通过包名 dump (推荐)
python3 hprof_dumper.py -pkg com.example.app

# 通过进程 PID dump
python3 hprof_dumper.py -p 12345

# 指定输出目录
python3 hprof_dumper.py -pkg com.example.app -o /path/to/output

# 列出正在运行的应用
python3 hprof_dumper.py --list
```

#### 输出示例

```bash
$ python3 hprof_dumper.py -pkg com.tencent.mm

找到应用 com.tencent.mm PID: 8234
开始dump进程 8234 的内存文件...
执行命令: adb shell "am dumpheap com.tencent.mm /data/local/tmp/com.tencent.mm_8234_20250112_143022.hprof"
等待hprof文件生成...
hprof文件已生成: /data/local/tmp/com.tencent.mm_8234_20250112_143022.hprof
拉取文件到本地: adb pull /data/local/tmp/com.tencent.mm_8234_20250112_143022.hprof ./com.tencent.mm_8234_20250112_143022.hprof
hprof文件已保存到: ./com.tencent.mm_8234_20250112_143022.hprof

hprof文件dump完成: ./com.tencent.mm_8234_20250112_143022.hprof
现在可以使用hprof_parser.py分析该文件
```

### HPROF 解析工具

#### 基本用法

```bash
# 解析 HPROF 文件
python3 hprof_parser.py -f app.hprof

# 指定输出文件
python3 hprof_parser.py -f app.hprof -o analysis_report.txt

# 显示 TOP 50 内存占用类
python3 hprof_parser.py -f app.hprof -t 50

# 设置最小显示阈值 (仅显示大于 5MB 的类)
python3 hprof_parser.py -f app.hprof -m 5.0

# 简化输出 (不显示详细对象列表)
python3 hprof_parser.py -f app.hprof -s
```

#### 分析输出示例

```bash
$ python3 hprof_parser.py -f com.tencent.mm_8234_20250112_143022.hprof

开始解析HPROF文件: com.tencent.mm_8234_20250112_143022.hprof
HPROF版本: JAVA PROFILE 1.0.3
标识符大小: 4 bytes
时间戳: 2025-01-12 14:30:22

=== 内存分析完成 ===
总实例数: 2,456,789
实例总大小: 89.34 MB
总数组数: 345,678
数组总大小: 23.45 MB
总内存使用: 112.79 MB

=== TOP 20 内存占用类 (最小 0.1MB) ===
类名                                          实例数      总大小(MB)    平均大小(KB)
--------------------------------------------------------------------------------------
java.lang.String                            234,567     15.67         0.07
android.graphics.Bitmap                     1,234       12.34         10.24
com.tencent.mm.ui.ChatActivity              45          8.91          203.56
byte[]                                       89,012      7.23          0.08
java.util.HashMap$Node                      123,456     6.78          0.06
android.view.View                            45,678      5.43          0.12
com.tencent.mm.model.Message                23,456      4.32          0.19

=== TOP 10 基本类型数组内存占用 ===
数组类型            数组数量      总大小(MB)    平均大小(KB)
----------------------------------------------------------
byte[]             89,012       7.23          0.08
int[]              12,345       3.45          0.29
char[]             56,789       2.78          0.05
long[]             3,456        1.23          0.37

=== 字符串内存统计 ===
字符串实例数: 234,567
字符串总大小: 15.67 MB
平均字符串大小: 70.12 bytes

分析结果已导出到: com.tencent.mm_8234_20250112_143022_analysis.txt
```

#### 支持的参数详解

| 参数 | 说明 | 示例 |
|------|------|------|
| `-f, --file` | HPROF文件路径 (必需) | `-f app.hprof` |
| `-o, --output` | 分析结果输出文件 | `-o report.txt` |
| `-t, --top` | 显示TOP N个内存占用类 | `-t 50` |
| `-m, --min-size` | 最小显示大小MB | `-m 1.0` |
| `-s, --simple` | 简单输出模式 | `-s` |

### 完整的 HPROF 工作流程

```bash
# 1. 找到目标应用
python3 hprof_dumper.py --list

# 2. Dump 应用内存
python3 hprof_dumper.py -pkg com.example.app

# 3. 解析 HPROF 文件
python3 hprof_parser.py -f com.example.app_12345_20250112_143022.hprof

# 4. 查看详细分析报告
cat com.example.app_12345_20250112_143022_analysis.txt
```

### 内存泄漏检测

**比较两次 HPROF 文件来检测内存泄漏**:

```bash
# 第一次 dump (操作前)
python3 hprof_dumper.py -pkg com.example.app -o ./before/
python3 hprof_parser.py -f ./before/app_before.hprof -o before_analysis.txt

# 进行可能导致内存泄漏的操作...

# 第二次 dump (操作后)  
python3 hprof_dumper.py -pkg com.example.app -o ./after/
python3 hprof_parser.py -f ./after/app_after.hprof -o after_analysis.txt

# 比较两次分析结果
diff before_analysis.txt after_analysis.txt
```

### 常见问题

**Q: HPROF dump 失败？**

```
错误: dump命令执行失败
```

**A:** 检查以下几点：
- 应用是否正在运行
- 包名是否正确
- 设备存储空间是否足够
- ADB 连接是否正常

**Q: 解析大 HPROF 文件时内存不足？**

**A:** HPROF 文件通常较大 (几百MB)，解析时需要足够内存。建议：
- 在内存充足的机器上运行
- 使用 `-s` 参数进行简化分析
- 分批分析不同的内存类型

---

## 📈 综合内存分析

### 功能介绍

综合分析工具结合 SMAPS 和 HPROF 数据，提供完整的内存分析报告。

### 基本用法

```bash
# 同时分析 HPROF 和 SMAPS
python3 memory_analyzer.py --hprof app.hprof --smaps smaps_file

# 仅分析 HPROF
python3 memory_analyzer.py --hprof app.hprof

# 通过 PID 自动获取 SMAPS 并分析
python3 memory_analyzer.py --hprof app.hprof -p 12345

# 仅分析 SMAPS
python3 memory_analyzer.py --smaps smaps_file

# 指定输出格式
python3 memory_analyzer.py --hprof app.hprof --json-output analysis.json
```

### 综合分析输出示例

```bash
$ python3 memory_analyzer.py --hprof app.hprof --smaps smaps_file

==========================================================
          Android 应用内存综合分析报告
==========================================================

📊 内存使用总结:
------------------------------
总内存使用: 245.67 MB
Java堆内存: 89.34 MB  
Native堆内存: 34.21 MB
Dalvik运行时: 12.45 MB
Native代码: 23.78 MB
Java堆占比: 36.4%

☕ Java堆内存详情:
------------------------------
总对象数: 245,678
总数组数: 12,345
字符串对象数: 34,567
字符串内存: 15.67 MB

🏆 TOP 10 内存占用类:
类名                                     实例数    总大小(MB)   平均大小(KB)
------------------------------------------------------------------------
java.lang.String                        34567     15.67        0.46
android.graphics.Bitmap                 234       12.34        54.23
com.tencent.mm.plugin.ChatActivity      1         8.91         8930.45
android.view.ViewGroup                   4567      7.89         1.77
java.util.HashMap$Node                  89012     6.54         0.08

🔧 Native内存详情:
------------------------------
Native堆内存: 34.21 MB
Native代码: 23.78 MB
图形内存: 45.67 MB
OpenGL内存: 12.34 MB

📈 内存分类占用 (>1MB):
------------------------------
Dalvik (Dalvik虚拟机运行时内存): 89.23 MB
graphics (图形相关内存): 45.67 MB
Native (本地C/C++代码内存): 34.21 MB
.so mmap (动态链接库映射内存): 23.78 MB
native heap (本地堆内存): 12.45 MB

💡 优化建议:
------------------------------
⚠️ [Java堆内存] Java堆内存使用量较大 (89.3MB)，建议检查内存泄漏
ℹ️ [字符串优化] 字符串占用 15.7MB，建议优化字符串使用，考虑使用StringBuilder或字符串常量池
ℹ️ [图形内存] 图形内存使用较高 (45.7MB)，检查位图缓存和GPU内存使用
ℹ️ [Native内存] Native堆内存使用较高 (34.2MB)，检查JNI代码和第三方库

==========================================================
```

### 支持的参数详解

| 参数 | 说明 | 示例 |
|------|------|------|
| `--hprof` | HPROF文件路径 | `--hprof app.hprof` |
| `--smaps` | SMAPS文件路径 | `--smaps smaps_file` |
| `-p, --pid` | 进程PID (自动获取smaps) | `-p 12345` |
| `-o, --output` | 分析结果输出文件 | `-o report.txt` |
| `--json-output` | JSON格式输出文件 | `--json-output data.json` |

---

## 🔧 环境要求与配置

### 系统要求

- **Python**: 3.6+
- **Android SDK**: adb 工具
- **设备要求**: 
  - SMAPS 分析: 需要 Root 权限
  - HPROF 分析: 无需 Root 权限
- **操作系统**: Windows, macOS, Linux

### 安装配置

```bash
# 1. 检查 Python 版本
python3 --version

# 2. 检查 ADB 连接
adb devices

# 3. 检查设备 Root 权限 (SMAPS 分析需要)
adb shell "su -c 'id'"

# 4. 给脚本执行权限
chmod +x analyze_memory.sh

# 5. 测试工具
python3 hprof_dumper.py --list
```

### ADB 设置

确保 ADB 调试已启用：

1. **开发者选项**: 设置 → 开发者选项
2. **USB 调试**: 启用 USB 调试
3. **Root 权限**: SMAPS 分析需要授权 Root 权限

```bash
# 测试 ADB 连接
adb devices

# 测试 Root 权限
adb shell "su -c 'whoami'"
```

---

## 📚 高级用法与最佳实践

### 批量分析

**分析多个应用**:

```bash
#!/bin/bash
# 批量分析脚本示例

apps=("com.tencent.mm" "com.tencent.mobileqq" "com.example.myapp")

for app in "${apps[@]}"; do
    echo "分析应用: $app"
    ./analyze_memory.sh --full -pkg $app -o "results/$app"
done
```

**定时内存监控**:

```bash
#!/bin/bash
# 定时监控脚本

while true; do
    timestamp=$(date +%Y%m%d_%H%M%S)
    ./analyze_memory.sh --smaps-only -pkg com.example.app -o "monitor/monitor_$timestamp"
    sleep 300  # 每5分钟一次
done
```

### 性能分析工作流

**1. 基准测试**
```bash
# 应用启动后立即分析
./analyze_memory.sh --full -pkg com.example.app -o baseline/
```

**2. 压力测试**
```bash
# 在应用高负载时分析
./analyze_memory.sh --full -pkg com.example.app -o stress_test/
```

**3. 长期运行测试**
```bash
# 应用运行数小时后分析
./analyze_memory.sh --full -pkg com.example.app -o long_running/
```

### 内存泄漏检测流程

**系统化的内存泄漏检测**:

```bash
# 1. 启动应用后的基准状态
./analyze_memory.sh --hprof-only -pkg com.example.app -o step1_baseline/

# 2. 执行目标操作 (如打开页面、加载数据等)

# 3. 操作后状态
./analyze_memory.sh --hprof-only -pkg com.example.app -o step2_after_action/

# 4. 触发 GC 后再次检测
adb shell "am broadcast -a com.example.app.FORCE_GC"
sleep 5
./analyze_memory.sh --hprof-only -pkg com.example.app -o step3_after_gc/

# 5. 比较分析结果
python3 -c "
import json
with open('step1_baseline/analysis.json') as f1, open('step3_after_gc/analysis.json') as f3:
    baseline = json.load(f1)
    after_gc = json.load(f3)
    print(f'内存增长: {after_gc[\"summary\"][\"java_heap_mb\"] - baseline[\"summary\"][\"java_heap_mb\"]:.2f} MB')
"
```

### 自定义分析脚本

**创建专门的应用分析脚本**:

```bash
#!/bin/bash
# my_app_analyzer.sh

APP_PACKAGE="com.example.myapp"
OUTPUT_DIR="./analysis_$(date +%Y%m%d_%H%M%S)"

echo "开始分析应用: $APP_PACKAGE"

# 1. 完整分析
./analyze_memory.sh --full -pkg $APP_PACKAGE -o "$OUTPUT_DIR"

# 2. 生成简要报告
echo "=== 内存分析摘要 ===" > "$OUTPUT_DIR/summary.txt"
grep "总内存使用\|Java堆内存\|Native堆内存" "$OUTPUT_DIR"/*.txt >> "$OUTPUT_DIR/summary.txt"

# 3. 检查关键指标
java_heap=$(grep "Java堆内存" "$OUTPUT_DIR"/*.txt | grep -o '[0-9.]*' | head -1)
if (( $(echo "$java_heap > 100" | bc -l) )); then
    echo "警告: Java堆内存超过100MB ($java_heap MB)" >> "$OUTPUT_DIR/summary.txt"
fi

echo "分析完成，结果保存在: $OUTPUT_DIR"
```

---

## 🚨 故障排除

### 常见错误及解决方案

#### SMAPS 相关问题

**错误**: `无法访问 /proc/pid/smaps`
```bash
错误: 无法访问 /proc/12345/smaps
请确保:
  • 设备已获得root权限  
  • ADB连接正常
  • PID存在且正确
```

**解决方案**:
```bash
# 1. 检查 Root 权限
adb shell "su -c 'whoami'"

# 2. 检查进程是否存在
adb shell "ps | grep 12345"

# 3. 测试权限
adb shell "su -c 'ls -la /proc/12345/'"
```

**错误**: `smaps文件为空`

**解决方案**:
```bash
# 1. 检查进程状态
adb shell "cat /proc/12345/status"

# 2. 尝试其他方式获取
adb shell "su -c 'cat /proc/12345/maps'" > maps_file.txt
```

#### HPROF 相关问题

**错误**: `dump命令执行失败`

**解决方案**:
```bash
# 1. 检查包名是否正确
adb shell "pm list packages | grep com.example"

# 2. 检查应用是否在运行
adb shell "ps | grep com.example"

# 3. 检查存储空间
adb shell "df /data/local/tmp/"

# 4. 手动执行 dump 命令
adb shell "am dumpheap com.example.app /data/local/tmp/test.hprof"
```

**错误**: `解析HPROF文件失败`

**解决方案**:
```bash
# 1. 检查文件大小
ls -lh app.hprof

# 2. 检查文件格式 (应该以 "JAVA PROFILE" 开头)
head -c 20 app.hprof

# 3. 使用简化模式解析
python3 hprof_parser.py -f app.hprof -s
```

#### 权限问题

**Android 设备权限配置**:

```bash
# 1. 启用开发者选项
# 设置 → 关于手机 → 版本号 (点击7次)

# 2. 启用 USB 调试
# 设置 → 开发者选项 → USB 调试

# 3. Root 设备 (SMAPS 分析需要)
# 使用 Magisk、SuperSU 等工具 Root 设备

# 4. 授权 ADB Root
adb shell "su -c 'setenforce 0'"  # 如果需要
```

### 性能优化

**大文件处理**:

```bash
# 1. 对于大 HPROF 文件，使用简化模式
python3 hprof_parser.py -f large_app.hprof -s -m 5.0

# 2. 分批处理多个文件
for file in *.hprof; do
    python3 hprof_parser.py -f "$file" -s &
    sleep 10  # 避免同时处理多个大文件
done
```

**内存不足处理**:

```bash
# 1. 增加虚拟内存 (Linux/macOS)
sudo sysctl -w vm.swappiness=60

# 2. 使用流式处理 (未来版本功能)
python3 hprof_parser.py -f huge_app.hprof --stream-mode

# 3. 云端分析 (对于超大文件)
# 将文件上传到云端虚拟机进行分析
```

---

## 📖 输出文件详解

### SMAPS 分析报告结构

```
smaps_analysis.txt
├── 文件头信息 (时间戳、版本)
├── 内存概览 (总内存、交换内存)
├── 分类内存统计
│   ├── Dalvik 相关内存
│   ├── Native 相关内存  
│   ├── 图形相关内存
│   └── 其他内存类型
├── 详细内存映射 (非简化模式)
└── 内存分析洞察
    ├── 检测到的Android特性
    ├── 异常检测
    └── 优化建议
```

### HPROF 分析报告结构

```
app_hprof_analysis.txt
├── HPROF 文件信息
├── 总体统计
│   ├── 实例数量统计
│   ├── 数组数量统计
│   └── 总内存使用
├── TOP N 内存占用类
│   ├── 类名
│   ├── 实例数量
│   ├── 总大小
│   └── 平均大小
├── 基本类型数组统计
└── 字符串统计
```

### 综合分析 JSON 格式

```json
{
  "timestamp": "2025-01-12T14:30:22",
  "summary": {
    "total_memory_mb": 245.67,
    "java_heap_mb": 89.34,
    "native_heap_mb": 34.21,
    "java_heap_percentage": 36.4
  },
  "java_heap": {
    "total_objects": 245678,
    "string_objects": 34567,
    "top_classes": [...]
  },
  "native_memory": {
    "native_heap_mb": 34.21,
    "graphics_mb": 45.67
  },
  "recommendations": [...]
}
```

---

## 🤝 贡献与支持

### 贡献指南

欢迎贡献代码、报告问题或提出功能建议。

**开发环境搭建**:
```bash
git clone https://github.com/your-repo/Android-App-Memory-Analysis.git
cd Android-App-Memory-Analysis
python3 -m pytest tests/  # 运行测试
```

### 问题反馈

如果遇到问题，请提供以下信息：
- Android 设备型号和系统版本
- Python 版本
- 错误日志
- 复现步骤

### 更新日志

**v2.1 (2025-01)**
- ✅ 合并 Android 16 支持到主分支
- ✅ 添加 HPROF 分析功能
- ✅ 增加综合分析工具
- ✅ 重构文档结构

**v2.0 (2024-12)**
- ✅ 支持 Android 15+ 新内存类型
- ✅ 添加内存异常检测
- ✅ 优化 ADB 命令兼容性

**v1.0 (2019-06)**
- ✅ 基础 SMAPS 解析功能
- ✅ 支持 Android 4.0-14

---

## 📄 许可证

本项目采用 MIT 许可证。详见 LICENSE 文件。

---

## 🔗 相关资源

- [Android 内存管理官方文档](https://developer.android.com/topic/performance/memory)
- [HPROF 文件格式规范](https://docs.oracle.com/javase/8/docs/technotes/samples/hprof.html)
- [Linux /proc/pid/smaps 文档](https://www.kernel.org/doc/Documentation/filesystems/proc.txt)
- [Android ART 内存管理](https://source.android.com/docs/core/runtime/art-gc)