# Android Showmap 输出详解指南

## 📋 概述

`showmap` 是 Android 提供的内存映射分析工具，显示指定进程的内存映射详情。它比 `/proc/pid/maps` 提供更多的内存使用统计信息，是进程级内存分析的重要工具。

---

## 🔍 获取 Showmap 的方法

```bash
# 方法1: 直接使用 showmap 命令
adb shell "showmap <pid>"

# 方法2: 通过包名获取 PID 再分析
adb shell "showmap $(pidof <package_name>)"

# 方法3: 保存到文件进行分析
adb shell "showmap <pid>" > showmap_output.txt

# 方法4: 获取多个进程的 showmap
adb shell "ps | grep <app_name> | awk '{print \$2}' | xargs showmap"
```

---

## 📊 Showmap 输出格式详解

### 输出头部信息

```
  virtual                     shared   shared  private  private
     size      RSS      PSS    clean    dirty    clean    dirty     swap  swapPSS
--------  --------  --------  -------  -------  -------  -------  -------  -------
```

#### 字段含义详解

| 字段 | 英文全称 | 中文含义 | 计算方式 | 重要性 |
|------|----------|----------|----------|--------|
| **virtual** | Virtual Size | 虚拟内存大小 | 进程地址空间映射大小 | 🔵 参考 |
| **RSS** | Resident Set Size | 驻留内存大小 | 实际占用物理内存 | 🟡 重要 |
| **PSS** | Proportional Set Size | 比例分配内存 | RSS + (共享内存/共享进程数) | 🔴 关键 |
| **shared clean** | Shared Clean Pages | 共享只读页面 | 多进程共享的只读内存 | 🟢 优化 |
| **shared dirty** | Shared Dirty Pages | 共享可写页面 | 多进程共享的可写内存 | 🟡 监控 |
| **private clean** | Private Clean Pages | 私有只读页面 | 进程独有的只读内存 | 🟢 正常 |
| **private dirty** | Private Dirty Pages | 私有可写页面 | 进程独有的可写内存 | 🔴 关键 |
| **swap** | Swap Size | 交换空间大小 | 被换出到存储的内存 | 🟡 性能 |
| **swapPSS** | Swap PSS | 交换空间PSS | 按比例分配的交换内存 | 🟡 性能 |

---

## 📖 典型输出示例分析

### 1. Dalvik 堆内存

```
[anon:dalvik-main space (region space)]
    49152     2500     2500        0        0        0     2500        0        0
```

**详细解释**:
- **virtual (49152 kB)**: Dalvik 为主堆空间保留的虚拟地址空间
  - **来源**: ART 虚拟机分配的连续地址空间
  - **特点**: 通常远大于实际使用量，为堆扩展预留空间
  - **问题诊断**: 过大可能影响地址空间利用率

- **RSS (2500 kB)**: 实际占用的物理内存
  - **来源**: 应用实际分配和使用的 Java 对象
  - **重要性**: 直接影响系统内存压力
  - **问题诊断**: 持续增长表明可能有内存泄漏

- **PSS (2500 kB)**: 比例分配内存 (与 RSS 相等说明无共享)
  - **来源**: 该内存区域完全为当前进程私有
  - **重要性**: 最准确反映进程对系统内存的贡献
  - **下一步工具**: 使用 HPROF 分析具体对象占用

- **private dirty (2500 kB)**: 私有脏页
  - **含义**: 被修改过的私有内存页面
  - **特点**: 无法与其他进程共享，无法换出
  - **优化建议**: 监控增长趋势，避免不必要的对象创建

### 2. Native 堆内存

```
[anon:scudo:primary]
    16384    16000    16000        0        0        0    16000        0        0
```

**详细解释**:
- **scudo:primary**: Android 新的内存分配器
  - **来源**: C/C++ 代码的 malloc/new 分配
  - **特点**: 提供内存安全保护机制
  - **版本**: Android 11+ 默认启用

- **高 private dirty (16000 kB)**: 
  - **含义**: Native 代码大量内存分配
  - **问题诊断**: 检查 JNI 调用、第三方库、NDK 代码
  - **下一步工具**: 
    ```bash
    # 分析 Native 内存详情
    adb shell "dumpsys meminfo <package> -d"
    # 查看调用栈
    adb shell "debuggerd -b <pid>"
    ```

### 3. 图形内存

```
/dev/kgsl-3d0
     6016     6016     6016        0        0        0     6016        0        0
```

**详细解释**:
- **kgsl-3d0**: GPU 图形内存设备
  - **来源**: OpenGL/Vulkan 纹理、缓冲区、着色器
  - **特点**: 直接映射GPU内存，无法换出
  - **重要性**: 影响图形性能和内存使用

- **高 PSS 值**: 图形内存密集使用
  - **问题诊断**: 检查纹理大小、缓冲区数量
  - **优化建议**: 
    - 压缩纹理格式
    - 及时释放不用的图形资源
    - 使用对象池减少频繁分配

- **下一步工具**:
  ```bash
  # GPU 内存详情
  adb shell "cat /d/kgsl/proc/<pid>/mem"
  # 图形性能分析
  adb shell "dumpsys gfxinfo <package>"
  ```

### 4. 共享库内存

```
/vendor/lib64/libllvm-glnext.so
     3568      859      215      644        0        0        0        0        0
```

**详细解释**:
- **virtual vs RSS**: 虚拟空间大但实际占用小
  - **原因**: 按需加载机制，只加载使用的代码段
  - **优化**: 说明系统内存管理高效

- **高 shared clean (644 kB)**:
  - **含义**: 多进程共享只读代码段
  - **优势**: 节省系统内存，一份代码多进程使用
  - **计算**: PSS = private + shared/共享进程数

- **低 PSS (215 kB)**:
  - **含义**: 虽然库很大，但分摊到进程的内存很少
  - **重要性**: 体现了共享内存的效率

### 5. APK 文件映射

```
/system_ext/priv-app/Launcher3QuickStep/Launcher3QuickStep.apk
     2560     2480      620     1860        0        0        0        0        0
```

**详细解释**:
- **APK 内存映射**: 直接映射到内存的应用包
  - **包含**: DEX 代码、资源文件、Native 库
  - **特点**: 只读映射，可以被系统回收后重新加载

- **高 shared clean (1860 kB)**:
  - **优势**: 同一 APK 的多个组件可以共享相同代码
  - **来源**: 系统将 APK 映射为共享只读内存

- **PSS 计算示例**:
  ```
  PSS = private clean + shared clean / 共享进程数
  620 = 0 + 1860 / 3 (假设3个进程共享)
  ```

---

## 🔍 内存分类统计

### 典型的 showmap 总结部分

```
   -------- -------- -------- ------- ------- ------- ------- ------- -------
    332928    50816    49702   24056    2100       48   24612       0       0 TOTAL
```

#### 总计行解读

- **virtual (332928 kB)**: 总虚拟地址空间
  - **32位进程**: 理论最大 4GB，实际可用约 3GB
  - **64位进程**: 理论最大非常大，实际受限于系统配置
  - **问题**: 过大可能导致地址空间碎片化

- **RSS (50816 kB)**: 总物理内存使用
  - **系统影响**: 直接影响可用内存
  - **对比**: 与 `ps` 命令的 VSZ/RSS 对应
  - **监控**: 持续增长需要关注

- **PSS (49702 kB)**: 实际内存贡献
  - **最重要指标**: 进程对系统内存压力的真实贡献
  - **计算**: 考虑了共享内存的分摊
  - **优化目标**: 主要优化目标

- **shared clean (24056 kB)**: 共享只读内存
  - **优势**: 不占用额外内存，多进程共享
  - **来源**: 系统库、APK 文件、只读数据

- **private dirty (24612 kB)**: 私有脏页
  - **关键指标**: 真正消耗系统内存的部分
  - **无法回收**: 这部分内存无法被系统回收
  - **优化重点**: 减少此类内存是优化重点

---

## 🚨 问题诊断模式

### 1. 内存泄漏检测

#### 症状识别
```bash
# 第一次测量
adb shell "showmap <pid>" > showmap_1.txt

# 执行可能泄漏的操作
# ... 用户操作 ...

# 第二次测量
adb shell "showmap <pid>" > showmap_2.txt

# 对比分析
diff showmap_1.txt showmap_2.txt
```

#### 关键指标变化
- **PSS 持续增长**: 总体内存泄漏
- **private dirty 增长**: 堆内存泄漏
- **特定映射区域增长**: 定向分析

#### 诊断流程
1. **Java 堆泄漏**:
   ```bash
   # 检查 Dalvik 相关行是否增长
   grep "dalvik" showmap_output.txt
   # 进一步 HPROF 分析
   python3 tools/hprof_dumper.py -pkg <package>
   # 或使用一键分析
   python3 analyze.py live --package <package>
   ```

2. **Native 内存泄漏**:
   ```bash
   # 检查 anon 匿名内存增长
   grep "anon:" showmap_output.txt
   # 分析 Native 内存详情
   adb shell "dumpsys meminfo <package> -d"
   ```

3. **文件描述符泄漏**:
   ```bash
   # 检查映射文件数量
   adb shell "ls -la /proc/<pid>/fd | wc -l"
   # 查看打开的文件
   adb shell "ls -la /proc/<pid>/fd"
   ```

### 2. 内存使用模式分析

#### 健康的内存模式
```
- 大量 shared clean (共享库、APK)
- 适量 private dirty (应用数据)
- 较少 private clean (临时数据)
- 极少或无 swap
```

#### 异常模式识别

**模式 1: 图形内存过载**
```
/dev/kgsl-3d0        大量内存占用
/dev/mali0           GPU设备占用过多
```
- **问题**: 纹理、缓冲区管理不当
- **下一步**: 使用 GPU 分析工具

**模式 2: 库加载过多**
```
多个 .so 文件       大量库映射
virtual 远大于RSS   库加载但未使用
```
- **问题**: 不必要的库加载
- **下一步**: 分析应用依赖，延迟加载

**模式 3: 数据缓存过大**
```
private dirty 持续增长
[anon:...] 类型增长
```
- **问题**: 缓存策略不当
- **下一步**: 检查缓存实现和清理机制

### 3. 性能影响评估

#### 内存效率指标

**共享效率**:
```bash
共享效率 = shared memory / (shared + private) * 100%
高效: >40%
一般: 20-40%  
低效: <20%
```

**内存密度**:
```bash
内存密度 = RSS / virtual * 100%
高密度: >30% (内存利用充分)
低密度: <10% (可能有内存浪费)
```

**脏页比例**:
```bash
脏页比例 = private dirty / RSS * 100%
正常: <70%
异常: >90% (大量不可回收内存)
```

---

## 📊 与其他工具的数据对比

### 与 `/proc/pid/status` 对比

```bash
# showmap 总计
PSS: 49702 kB

# /proc/pid/status
VmRSS: 50816 kB    # 对应 showmap RSS
VmSize: 332928 kB  # 对应 showmap virtual
```

### 与 `dumpsys meminfo` 对比

```bash
# dumpsys meminfo 中的 PSS 总计应该接近 showmap PSS
# 但分类方式不同：
# dumpsys: 按功能分类 (Dalvik, Native, Graphics...)
# showmap: 按内存映射分类 (文件映射, 匿名映射...)
```

### 数据一致性检查

```bash
#!/bin/bash
PID=$1

echo "=== 数据一致性检查 ==="
echo "showmap PSS:"
adb shell "showmap $PID" | tail -1 | awk '{print $3}'

echo "dumpsys PSS:"
adb shell "dumpsys meminfo $PID" | grep "TOTAL PSS:" | awk '{print $3}'

echo "status VmRSS:"
adb shell "cat /proc/$PID/status" | grep VmRSS | awk '{print $2}'
```

---

## 🔧 高级分析技巧

### 1. 自动化监控脚本

```bash
#!/bin/bash
# showmap_monitor.sh

PID=$1
INTERVAL=${2:-60}  # 默认60秒间隔
LOG_FILE="showmap_monitor_$(date +%Y%m%d_%H%M%S).log"

echo "开始监控进程 $PID，间隔 $INTERVAL 秒"
echo "时间戳,Virtual,RSS,PSS,SharedClean,SharedDirty,PrivateClean,PrivateDirty" > $LOG_FILE

while true; do
    TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
    SHOWMAP_OUTPUT=$(adb shell "showmap $PID" 2>/dev/null | tail -1)
    
    if [ $? -eq 0 ]; then
        echo "$TIMESTAMP,$SHOWMAP_OUTPUT" >> $LOG_FILE
        echo "[$TIMESTAMP] PSS: $(echo $SHOWMAP_OUTPUT | awk '{print $3}') kB"
    else
        echo "[$TIMESTAMP] 进程可能已退出"
        break
    fi
    
    sleep $INTERVAL
done
```

### 2. 内存热点分析

```bash
#!/bin/bash
# memory_hotspot.sh

PID=$1

echo "=== 内存热点分析 ==="
echo "1. 最大内存映射区域："
adb shell "showmap $PID" | grep -v "TOTAL" | sort -k3 -nr | head -5

echo ""
echo "2. 私有脏页最多的区域："
adb shell "showmap $PID" | grep -v "TOTAL" | sort -k8 -nr | head -5

echo ""
echo "3. 可能的内存泄漏点："
adb shell "showmap $PID" | grep -E "(anon:|dalvik)" | sort -k3 -nr
```

### 3. 内存基准对比

```bash
#!/bin/bash
# memory_baseline.sh

PACKAGE=$1
OPERATION=$2

echo "=== 内存基准测试 ==="

# 获取 PID
PID=$(adb shell "pidof $PACKAGE")
if [ -z "$PID" ]; then
    echo "应用未运行: $PACKAGE"
    exit 1
fi

# 基准状态
echo "记录基准状态..."
adb shell "showmap $PID" > baseline_showmap.txt
BASELINE_PSS=$(tail -1 baseline_showmap.txt | awk '{print $3}')

echo "基准 PSS: $BASELINE_PSS kB"
echo "执行操作: $OPERATION"
echo "按回车继续..."
read

# 操作后状态
echo "记录操作后状态..."
adb shell "showmap $PID" > after_showmap.txt
AFTER_PSS=$(tail -1 after_showmap.txt | awk '{print $3}')

# 计算差异
DIFF_PSS=$((AFTER_PSS - BASELINE_PSS))
echo ""
echo "=== 结果分析 ==="
echo "基准 PSS: $BASELINE_PSS kB"
echo "操作后 PSS: $AFTER_PSS kB"
echo "PSS 变化: $DIFF_PSS kB"

if [ $DIFF_PSS -gt 1000 ]; then
    echo "⚠️  内存增长超过 1MB，建议检查内存泄漏"
elif [ $DIFF_PSS -gt 500 ]; then
    echo "⚠️  内存增长较大，需要关注"
else
    echo "✅ 内存增长在正常范围"
fi

# 详细对比
echo ""
echo "=== 详细对比 ==="
diff -u baseline_showmap.txt after_showmap.txt
```

---

## 🔗 相关工具链接

- **应用级分析**: [dumpsys meminfo 解释指南](./meminfo_interpretation_guide.md)
- **系统级分析**: [/proc/meminfo 解释指南](./proc_meminfo_interpretation_guide.md)
- **进程详细分析**: [smaps 解释指南](./smaps_interpretation_guide.md)  
- **应用内存分析**: [解析结果指南](./analysis_results_interpretation_guide.md)

---

## 💡 最佳实践建议

### 1. 日常监控
- 建立应用内存基准数据
- 定期使用 showmap 检查内存趋势
- 结合 dumpsys meminfo 进行交叉验证

### 2. 问题诊断
- 使用差异对比法检测内存泄漏
- 关注 private dirty 的增长趋势
- 重点分析 PSS 值而非 virtual 大小

### 3. 性能优化
- 优先减少 private dirty 内存
- 充分利用共享内存 (shared clean)
- 避免不必要的大文件映射

### 4. 工具组合
- showmap 提供概览，HPROF 提供细节
- 结合 GPU profiler 分析图形内存
- 使用 Native 内存工具分析 C/C++ 内存

通过深入理解 showmap 输出的每个字段和内存映射模式，可以快速识别内存使用异常，为深入的内存优化提供方向指导。