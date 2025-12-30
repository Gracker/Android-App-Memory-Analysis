# Android SMAPS 输出详解指南

## 📋 概述

`/proc/pid/smaps` 文件提供了进程内存映射的最详细信息，是 Android 内存分析的核心数据源。每个内存映射区域都有完整的统计信息，包括物理内存使用、共享状态、交换信息等。

---

## 🔍 获取 SMAPS 的方法

```bash
# 方法1: 直接读取 (需要 Root 权限)
adb shell "su -c 'cat /proc/<pid>/smaps'"

# 方法2: 保存到文件分析
adb shell "su -c 'cat /proc/<pid>/smaps'" > smaps_file.txt

# 方法3: 使用本项目工具
python3 tools/smaps_parser.py -p <pid>
python3 tools/smaps_parser.py -f smaps_file.txt

# 方法4: 一键 Dump（推荐）
python3 analyze.py live --package <package>

# 方法4: 监控实时变化
watch -n 5 "adb shell 'su -c \"cat /proc/<pid>/smaps\" | tail -20'"
```

---

## 📊 SMAPS 文件结构详解

### 基本格式

每个内存映射区域包含两部分：
1. **映射行**: 地址范围和基本属性
2. **统计行**: 详细的内存使用统计

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

## 🗺️ 映射行详解

### 地址和权限信息

```
12c00000-32c00000 rw-p 00000000 00:00 0    [anon:dalvik-main space (region space)]
```

#### 各字段含义

| 字段 | 示例 | 含义 | 分析要点 |
|------|------|------|----------|
| **起始地址** | 12c00000 | 虚拟内存起始地址 | 地址空间分布 |
| **结束地址** | 32c00000 | 虚拟内存结束地址 | 映射区域大小 |
| **权限** | rw-p | 内存访问权限 | 安全性和用途 |
| **偏移** | 00000000 | 文件内偏移量 | 文件映射起点 |
| **设备** | 00:00 | 设备号 | 0:0表示匿名映射 |
| **inode** | 0 | 文件inode号 | 0表示匿名内存 |
| **路径/名称** | [anon:...] | 映射名称或文件路径 | 内存类型识别 |

#### 权限标志解析

| 标志 | 含义 | 说明 | 安全影响 |
|------|------|------|----------|
| **r** | read | 可读 | 正常数据访问 |
| **w** | write | 可写 | 数据可修改 |
| **x** | execute | 可执行 | 代码段特征 |
| **p** | private | 私有映射 | 修改不影响其他进程 |
| **s** | shared | 共享映射 | 修改影响其他进程 |

#### 常见权限组合

- **r--p**: 只读私有 (常量数据、只读文件)
- **r-xp**: 只读可执行 (代码段、共享库)
- **rw-p**: 读写私有 (堆内存、私有数据)
- **rw-s**: 读写共享 (共享内存、设备映射)

---

## 📈 内存统计字段详解

### 基础大小信息

#### Size (映射大小)
```
Size:             524288 kB
```
- **含义**: 虚拟地址空间中该映射的总大小
- **来源**: 结束地址 - 起始地址
- **特点**: 可能远大于实际使用的物理内存
- **问题诊断**: 
  - 过大的 Size 可能导致地址空间碎片化
  - Size >> RSS 表明大量预分配但未使用
- **下一步工具**: 检查应用的内存分配策略

#### KernelPageSize (内核页面大小)
```
KernelPageSize:        4 kB
```
- **含义**: 内核使用的页面大小
- **常见值**: 4KB (ARMv7/ARMv8), 16KB (ARMv8可选)
- **影响**: 影响内存分配粒度和效率
- **Android 16+**: 支持 16KB 页面优化

#### MMUPageSize (MMU页面大小)
```
MMUPageSize:           4 kB
```
- **含义**: 内存管理单元使用的页面大小
- **用途**: 硬件级内存管理
- **优化**: 页面大小影响TLB命中率和内存效率

### 物理内存使用

#### RSS (驻留内存)
```
Rss:                2500 kB
```
- **含义**: 当前实际占用的物理内存
- **重要性**: 🔴 **关键指标** - 直接影响系统内存压力
- **特点**: 实时变化，反映当前内存使用
- **问题诊断**:
  - RSS 持续增长: 可能有内存泄漏
  - RSS 突然增大: 应用加载了大量数据
  - RSS = 0: 页面被换出或还未访问
- **优化目标**: 减少不必要的 RSS 占用
- **下一步工具**:
  ```bash
  # 监控 RSS 变化
  watch -n 2 "cat /proc/<pid>/smaps | grep Rss: | awk '{sum+=\$2} END {print sum\" kB\"}'"
  
  # 找出 RSS 最大的映射
  cat /proc/<pid>/smaps | grep -A 12 "^[0-9a-f]" | grep -B 12 "Rss:" | sort -k2 -nr
  ```

#### PSS (比例分配内存)
```
Pss:                2500 kB
```
- **含义**: 最准确的内存占用指标
- **计算**: PSS = Private + Shared/共享进程数
- **重要性**: 🔴 **最关键指标** - 用于内存优化决策
- **优势**: 考虑了共享内存的公平分摊
- **应用场景**: 
  - 系统内存预算分配
  - 应用内存限制设定
  - 内存优化效果评估
- **问题诊断**:
  - PSS 与 RSS 相等: 完全私有内存，无共享
  - PSS 远小于 RSS: 大量共享内存，效率高
  - PSS 持续增长: 真正的内存泄漏
- **下一步工具**:
  ```bash
  # PSS 总计
  cat /proc/<pid>/smaps | awk '/Pss:/ {sum+=$2} END {print "Total PSS: " sum " kB"}'
  
  # 各类型内存 PSS 分布
  python3 tools/smaps_parser.py -p <pid>
  
  # 或使用全景分析
  python3 analyze.py panorama -S smaps.txt
  ```

### 共享内存状态

#### Shared_Clean (共享只读内存)
```
Shared_Clean:          0 kB
```
- **含义**: 与其他进程共享且未被修改的内存页面
- **特点**: 
  - 内存效率最高
  - 可以被系统安全回收
  - 不计入进程的内存占用
- **来源**: 
  - 共享库代码段
  - 只读资源文件
  - 系统缓存数据
- **优化价值**: 🟢 **优秀** - 不消耗额外内存
- **问题诊断**: 
  - 值为0但应该有共享: 可能是库加载问题
  - 异常大值: 可能有大文件被多进程访问
- **下一步工具**:
  ```bash
  # 查看共享最多的库
  cat /proc/<pid>/smaps | grep -B 1 "Shared_Clean" | grep "\.so" | sort -k2 -nr
  ```

#### Shared_Dirty (共享已修改内存)
```
Shared_Dirty:          0 kB
```
- **含义**: 与其他进程共享且被修改过的内存页面
- **特点**: 
  - 不能简单回收
  - 需要写回存储或交换分区
  - 修改影响所有共享进程
- **来源**: 
  - 共享内存对象
  - 可写的内存映射文件
  - 进程间通信缓冲区
- **问题诊断**: 
  - 异常增长: 可能有共享内存泄漏
  - 意外的大值: 检查是否误用共享内存
- **安全考虑**: 共享脏页可能被其他进程修改
- **下一步工具**:
  ```bash
  # 查找共享脏页来源
  cat /proc/<pid>/smaps | grep -B 1 -A 1 "Shared_Dirty:" | grep -v "0 kB"
  ```

### 私有内存状态

#### Private_Clean (私有只读内存)
```
Private_Clean:         0 kB
```
- **含义**: 进程私有且未被修改的内存页面
- **特点**: 
  - 内存压力时可以被丢弃
  - 需要时可以从文件重新加载
  - 不影响其他进程
- **来源**: 
  - 私有映射的只读文件
  - 代码段 (如果未共享)
  - 初始化但未修改的数据
- **优化价值**: 🟡 **良好** - 可回收但需要重新加载
- **问题诊断**: 
  - 持续增长: 可能有大量文件映射
  - 异常大值: 检查是否有不必要的私有映射
- **下一步工具**:
  ```bash
  # 查看私有只读内存来源
  cat /proc/<pid>/smaps | grep -B 12 "Private_Clean:" | grep -E "(r-x|r--)"
  ```

#### Private_Dirty (私有已修改内存)
```
Private_Dirty:      2500 kB
```
- **含义**: 进程私有且被修改过的内存页面
- **重要性**: 🔴 **关键** - 真正不可回收的内存消耗
- **特点**: 
  - 无法与其他进程共享
  - 无法被系统回收
  - 内存压力时只能交换到存储
- **来源**: 
  - 堆内存分配
  - 栈内存
  - 全局变量修改
  - 缓冲区数据
- **优化重点**: 🔴 **最重要** - 主要优化目标
- **问题诊断**:
  - 持续快速增长: 内存泄漏的明确信号
  - 突然增大: 大数据加载或缓存
  - 异常分布: 检查内存分配模式
- **下一步工具**:
  ```bash
  # 监控私有脏页增长
  while true; do 
    echo "$(date): $(cat /proc/<pid>/smaps | awk '/Private_Dirty/ {sum+=$2} END {print sum}')"
    sleep 10
  done
  
  # 找出私有脏页最多的区域
  cat /proc/<pid>/smaps | grep -B 12 "Private_Dirty:" | grep -E "^[0-9a-f]" | sort -k2 -nr
  ```

### 高级内存信息

#### Referenced (最近引用内存)
```
Referenced:         2500 kB
```
- **含义**: 最近被访问过的内存页面
- **用途**: 内核LRU算法的参考
- **特点**: 反映内存的活跃程度
- **优化意义**: 帮助识别热点内存区域

#### Anonymous (匿名内存)
```
Anonymous:          2500 kB
```
- **含义**: 不与文件关联的内存页面
- **包含**: 
  - 堆内存 (malloc/new)
  - 栈内存
  - 匿名 mmap
- **特点**: 无法从文件恢复，只能交换
- **问题诊断**: 
  - Anonymous = Private_Dirty: 典型的匿名私有内存
  - 异常增长: 堆内存泄漏或大量分配

#### AnonHugePages (匿名大页面)
```
AnonHugePages:         0 kB
```
- **含义**: 使用大页面 (2MB/1GB) 的匿名内存
- **优势**: 减少TLB miss，提高性能
- **Android**: 通常不使用，值为0
- **问题**: 大页面可能导致内存浪费

### 交换相关

#### Swap (交换空间)
```
Swap:                  0 kB
```
- **含义**: 被换出到存储设备的内存大小
- **Android特点**: 很多设备不启用传统swap
- **性能影响**: 换出的页面访问时需要从存储加载
- **问题诊断**: 
  - 有swap值: 内存压力导致页面换出
  - 持续增长: 内存不足，性能下降
- **下一步工具**:
  ```bash
  # 检查系统swap配置
  cat /proc/swaps
  
  # 监控swap活动
  vmstat 1
  ```

#### SwapPss (交换PSS)
```
SwapPss:               0 kB
```
- **含义**: 按比例分配的交换空间
- **计算**: 考虑共享交换页面的分摊
- **重要性**: 比Swap更准确的交换内存指标
- **问题诊断**: 
  - 有值表明内存压力严重
  - 需要检查内存使用和优化

### 内存锁定

#### Locked (锁定内存)
```
Locked:                0 kB
```
- **含义**: 被mlock()锁定在内存中的页面
- **特点**: 
  - 不能被换出
  - 不能被回收
  - 影响系统内存可用性
- **用途**: 关键数据、安全敏感信息
- **问题诊断**: 
  - 异常大值: 可能滥用内存锁定
  - 检查应用是否正确使用mlock

### 虚拟内存标志

#### VmFlags (虚拟内存标志)
```
VmFlags: rd wr mr mw me ac
```

| 标志 | 含义 | 说明 |
|------|------|------|
| **rd** | readable | 可读 |
| **wr** | writable | 可写 |
| **ex** | executable | 可执行 |
| **sh** | shared | 共享 |
| **mr** | may read | 可能读取 |
| **mw** | may write | 可能写入 |
| **me** | may execute | 可能执行 |
| **ms** | may share | 可能共享 |
| **gd** | grows down | 向下增长 (栈) |
| **pf** | pure PFN range | 纯PFN范围 |
| **dw** | disabled write | 禁用写入 |
| **lo** | locked | 锁定 |
| **io** | I/O mapping | I/O映射 |
| **sr** | sequential read | 顺序读取 |
| **rr** | random read | 随机读取 |
| **dc** | do not copy | 不复制 |
| **de** | do not expand | 不扩展 |
| **ac** | account | 计入 |
| **nr** | no reserve | 不保留 |
| **ht** | huge TLB | 大页面TLB |
| **ar** | architecture specific | 架构特定 |
| **dd** | do not dump | 不转储 |
| **sd** | soft dirty | 软脏页 |
| **mm** | mixed map | 混合映射 |
| **hg** | huge page | 大页面 |
| **nh** | no huge page | 非大页面 |
| **mg** | mergeable | 可合并 |

---

## 🔍 Android 特有内存类型解析

### Dalvik 虚拟机内存

#### 主要空间
```
[anon:dalvik-main space (region space)]
Size:             524288 kB
Rss:                2500 kB
Pss:                2500 kB
Private_Dirty:      2500 kB
```

**含义**: Dalvik/ART 主堆空间
- **用途**: Java 对象实例存储
- **特点**: 大虚拟空间，按需分配物理内存
- **问题诊断**: Private_Dirty 增长表明 Java 内存泄漏
- **下一步**: 使用 HPROF 分析具体对象

#### 大对象空间
```
[anon:dalvik-large object space]
Size:              65536 kB
Rss:                327 kB
Private_Dirty:      327 kB
```

**含义**: 大对象专用空间 (>12KB对象)
- **用途**: 存储大数组、位图等
- **问题**: 大对象容易引起内存碎片
- **优化**: 避免创建过多大对象

#### 非移动空间
```
[anon:dalvik-non moving space]
Size:               8192 kB
Rss:                300 kB
Private_Dirty:      300 kB
```

**含义**: 不可移动的对象空间
- **用途**: Class 对象、方法元数据
- **特点**: GC 时不会移动这些对象
- **正常**: 相对稳定，缓慢增长

#### Zygote 空间
```
[anon:dalvik-zygote space]
Size:               4096 kB
Rss:                656 kB
Shared_Clean:       656 kB
```

**含义**: Zygote 进程共享的空间
- **用途**: 系统类和预加载资源
- **优势**: 多进程共享，节省内存
- **特点**: 通常是 Shared_Clean

### Dalvik 辅助内存

#### LinearAlloc
```
[anon:dalvik-LinearAlloc]
Size:               8192 kB
Rss:               1145 kB
Private_Dirty:     1145 kB
```

**含义**: 类和方法的线性分配器
- **用途**: 存储类加载时的辅助数据
- **Android版本**: 老版本主要，新版本较少
- **问题**: 过多类加载会增加此区域

#### 间接引用表
```
[anon:dalvik-indirect ref table]
Size:               1024 kB
Rss:                100 kB
Private_Dirty:      100 kB
```

**含义**: JNI 引用管理表
- **用途**: JNI 全局引用和弱引用
- **问题**: JNI 引用泄漏会增加此区域
- **下一步**: 检查 JNI 代码中的引用管理

### Native 内存

#### Scudo 分配器 (Android 11+)
```
[anon:scudo:primary]
Size:              16384 kB
Rss:              16491 kB
Private_Dirty:    16491 kB
```

**含义**: 新的安全内存分配器
- **优势**: 提供内存安全保护
- **用途**: C/C++ malloc/new 分配
- **问题**: 高 Private_Dirty 表明 Native 内存使用多
- **下一步**: 分析 Native 代码内存分配

#### 传统堆内存
```
[heap]
Size:               8192 kB
Rss:               1234 kB
Private_Dirty:     1234 kB
```

**含义**: 传统的进程堆内存
- **用途**: C/C++ 动态内存分配
- **特点**: 纯私有内存，不可共享
- **优化**: 检查内存分配和释放配对

### 栈内存

#### 主线程栈
```
[stack]
Size:               8192 kB
Rss:                 60 kB
Private_Dirty:       60 kB
```

**含义**: 主线程的栈空间
- **用途**: 函数调用、局部变量
- **正常大小**: 通常几十KB到几MB
- **问题**: 过大可能有递归调用

#### 工作线程栈
```
[anon:stack_and_tls:22379]
Size:               1024 kB
Rss:                100 kB
Private_Dirty:      100 kB
```

**含义**: 工作线程的栈和TLS
- **包含**: 栈内存 + 线程本地存储
- **数量**: 每个线程一个
- **问题**: 过多线程会增加内存使用

### 图形和GPU内存

#### GPU设备内存
```
/dev/kgsl-3d0
Size:               6016 kB
Rss:               5884 kB
Pss:               5884 kB
Private_Dirty:     5884 kB
```

**含义**: GPU 图形内存设备
- **用途**: 纹理、顶点缓冲区、着色器
- **特点**: 无法换出，直接占用显存
- **问题**: 过大影响图形性能和系统内存
- **下一步**: 
  ```bash
  # GPU 内存详情
  cat /d/kgsl/proc/<pid>/mem
  # 图形性能分析
  dumpsys gfxinfo <package>
  ```

#### 共享内存
```
/dev/ashmem/GFXStats-21936 (deleted)
Size:                 4 kB
Rss:                  2 kB
Pss:                  1 kB
Shared_Clean:         2 kB
```

**含义**: 图形统计共享内存
- **用途**: 系统图形性能统计
- **特点**: 多进程共享
- **状态**: (deleted) 表示文件已删除但内存仍在使用

### 文件映射

#### 共享库
```
/vendor/lib64/libllvm-glnext.so
Size:               3568 kB
Rss:                859 kB
Pss:                215 kB
Shared_Clean:       644 kB
Private_Clean:      215 kB
```

**详细分析**:
- **高效共享**: Shared_Clean 表明代码段被多进程共享
- **按需加载**: Size >> RSS 说明只加载需要的部分
- **低PSS**: 共享降低了单进程的内存贡献

**优化价值**: 
- ✅ 共享效率高
- ✅ 内存使用合理
- ✅ 按需加载有效

#### APK 文件映射
```
/system_ext/priv-app/Launcher3QuickStep/Launcher3QuickStep.apk
Size:               2560 kB
Rss:               2480 kB
Pss:                620 kB
Shared_Clean:      1860 kB
```

**分析要点**:
- **APK 代码共享**: Shared_Clean 表明 DEX 代码被共享
- **PSS 计算**: 620 = 620(Private) + 1860/3(假设3进程共享)
- **内存效率**: 一份APK，多个组件共享

#### 字体文件
```
/system/fonts/Roboto-Regular.ttf
Size:                128 kB
Rss:                 15 kB
Pss:                  3 kB
Shared_Clean:        15 kB
```

**优化特点**:
- **完全共享**: 系统字体被所有应用共享
- **极低PSS**: 单个应用几乎不承担字体内存成本
- **按需加载**: 只加载使用的字符

### ART 运行时

#### Boot ART 文件
```
[anon:dalvik-/system/framework/boot-framework.art]
Size:               4096 kB
Rss:               1537 kB
Pss:                384 kB
Shared_Clean:      1153 kB
Private_Clean:      384 kB
```

**含义**: 系统框架的 ART 文件
- **共享**: 框架代码被多个应用共享
- **预编译**: AOT 编译的本地代码
- **效率**: 启动速度快，运行效率高

#### App ART 文件
```
[anon:dalvik-/data/dalvik-cache/arm64/app.art]
Size:               1024 kB
Rss:                344 kB
Pss:                344 kB
Private_Clean:      344 kB
```

**含义**: 应用特定的 ART 文件
- **私有**: 每个应用独有
- **预编译**: 应用代码的本地编译版本
- **性能**: 提升应用执行性能

### JIT 编译缓存

#### JIT 缓存
```
/memfd:jit-cache (deleted)
Size:                512 kB
Rss:                368 kB
Pss:                368 kB
Private_Dirty:      368 kB
```

**含义**: 即时编译代码缓存
- **动态**: 运行时热点代码编译
- **内存文件**: 存储在内存文件系统
- **私有**: 每个进程独有的编译缓存
- **优化**: 提高热点代码执行效率

---

## 🚨 问题模式识别

### 1. Java 内存泄漏

#### 典型症状
```bash
# Dalvik 相关区域持续增长
[anon:dalvik-main space]         - Private_Dirty 增长
[anon:dalvik-large object space] - Private_Dirty 增长
[anon:dalvik-non moving space]   - 缓慢增长正常
```

#### 诊断流程
```bash
# 1. 监控 Dalvik 内存趋势
grep -A 10 "dalvik-main space" /proc/<pid>/smaps | grep Private_Dirty

# 2. 对比 GC 前后
adb shell "am broadcast -a com.android.internal.intent.action.REQUEST_GC"
sleep 5
grep -A 10 "dalvik" /proc/<pid>/smaps

# 3. HPROF 深入分析
python3 tools/hprof_dumper.py -pkg <package>
python3 tools/hprof_parser.py -f <hprof_file>

# 或使用一键分析
python3 analyze.py live --package <package>
```

#### 下一步工具
- **HPROF 分析**: 具体对象和引用链
- **MAT 工具**: Eclipse Memory Analyzer
- **LeakCanary**: 自动内存泄漏检测

### 2. Native 内存泄漏

#### 典型症状
```bash
# Native 内存区域增长
[heap]                 - Private_Dirty 增长
[anon:scudo:primary]   - Private_Dirty 增长  
[anon:libc_malloc]     - Private_Dirty 增长
```

#### 诊断流程
```bash
# 1. 统计 Native 内存总量
cat /proc/<pid>/smaps | grep -E "(heap|scudo|malloc)" -A 10 | grep Private_Dirty | awk '{sum+=$2} END {print sum " kB"}'

# 2. 详细 Native 内存分析
adb shell "dumpsys meminfo <package> -d"

# 3. Native 内存工具
# AddressSanitizer、Valgrind 等
```

#### 下一步工具
- **ASan**: AddressSanitizer 内存错误检测
- **Valgrind**: Linux 内存分析工具
- **Malloc Debug**: Android Native 内存调试

### 3. 图形内存过度使用

#### 典型症状
```bash
# GPU 内存占用过大
/dev/kgsl-3d0          - 大量 Private_Dirty
/dev/mali0             - GPU 设备内存增长
[anon:graphics]        - 图形相关匿名内存
```

#### 问题分析
- **纹理内存**: 位图和纹理占用
- **缓冲区**: 顶点、索引缓冲区
- **渲染目标**: FBO、RenderBuffer

#### 下一步工具
```bash
# GPU 内存详情 (如果支持)
cat /sys/kernel/debug/kgsl/proc/<pid>/mem

# 图形性能分析
adb shell "dumpsys gfxinfo <package> framestats"

# GPU 调试工具
# RenderDoc、Mali Graphics Debugger
```

### 4. 文件映射异常

#### 典型症状
```bash
# 大量文件映射
大量 .so 文件          - 库加载过多
大量 .apk 映射         - 资源加载异常
异常文件路径          - 临时文件未清理
```

#### 诊断方法
```bash
# 1. 统计映射文件类型
cat /proc/<pid>/smaps | grep "^/" | cut -d' ' -f6 | sort | uniq -c | sort -nr

# 2. 查找大内存映射
cat /proc/<pid>/smaps | grep -B 12 "Size:" | grep "^/" | sort -k2 -nr

# 3. 检查临时文件
cat /proc/<pid>/smaps | grep "/tmp\|/cache\|deleted"
```

### 5. 线程过多问题

#### 典型症状
```bash
# 大量线程栈
[anon:stack_and_tls:xxxxx]  - 多个线程栈映射
[stack]                     - 主线程栈异常大
```

#### 分析方法
```bash
# 1. 统计线程数量
cat /proc/<pid>/smaps | grep "stack_and_tls" | wc -l

# 2. 查看线程信息
cat /proc/<pid>/status | grep Threads
ls /proc/<pid>/task/ | wc -l

# 3. 线程栈大小分析
cat /proc/<pid>/smaps | grep -A 10 "stack_and_tls" | grep Size
```

---

## 📊 内存健康评估

### 评估指标

#### 1. 内存效率指标

**共享内存比例**:
```bash
shared_ratio = (Shared_Clean + Shared_Dirty) / RSS * 100%
```
- 优秀: >30%
- 良好: 20-30%
- 一般: 10-20%
- 差: <10%

**私有脏页比例**:
```bash
dirty_ratio = Private_Dirty / RSS * 100%
```
- 优秀: <50%
- 良好: 50-70%
- 一般: 70-85%
- 差: >85%

#### 2. 内存分布健康度

**Dalvik 内存占比**:
```bash
dalvik_ratio = Dalvik_RSS / Total_RSS * 100%
```
- 正常: 30-60%
- 警告: >70%
- 危险: >85%

**Native 内存占比**:
```bash
native_ratio = Native_RSS / Total_RSS * 100%
```
- 正常: <40%
- 警告: 40-60%
- 危险: >60%

#### 3. 内存增长趋势

**增长率监控**:
```bash
# 每分钟内存增长率
growth_rate = (Current_PSS - Previous_PSS) / Previous_PSS * 100%
```
- 正常: <5%/分钟
- 警告: 5-10%/分钟
- 危险: >10%/分钟

### 自动化评估脚本

```bash
#!/bin/bash
# smaps_health_check.sh

PID=$1
OUTPUT_FILE="smaps_health_$(date +%Y%m%d_%H%M%S).txt"

echo "=== SMAPS 内存健康检查 ===" > $OUTPUT_FILE
echo "PID: $PID" >> $OUTPUT_FILE
echo "时间: $(date)" >> $OUTPUT_FILE
echo "" >> $OUTPUT_FILE

# 基础统计
TOTAL_RSS=$(cat /proc/$PID/smaps | awk '/^Rss:/ {sum+=$2} END {print sum}')
TOTAL_PSS=$(cat /proc/$PID/smaps | awk '/^Pss:/ {sum+=$2} END {print sum}')
SHARED_CLEAN=$(cat /proc/$PID/smaps | awk '/^Shared_Clean:/ {sum+=$2} END {print sum}')
SHARED_DIRTY=$(cat /proc/$PID/smaps | awk '/^Shared_Dirty:/ {sum+=$2} END {print sum}')
PRIVATE_CLEAN=$(cat /proc/$PID/smaps | awk '/^Private_Clean:/ {sum+=$2} END {print sum}')
PRIVATE_DIRTY=$(cat /proc/$PID/smaps | awk '/^Private_Dirty:/ {sum+=$2} END {print sum}')

echo "基础内存统计:" >> $OUTPUT_FILE
echo "  总 RSS: $TOTAL_RSS kB" >> $OUTPUT_FILE
echo "  总 PSS: $TOTAL_PSS kB" >> $OUTPUT_FILE
echo "  共享只读: $SHARED_CLEAN kB" >> $OUTPUT_FILE
echo "  共享脏页: $SHARED_DIRTY kB" >> $OUTPUT_FILE
echo "  私有只读: $PRIVATE_CLEAN kB" >> $OUTPUT_FILE
echo "  私有脏页: $PRIVATE_DIRTY kB" >> $OUTPUT_FILE
echo "" >> $OUTPUT_FILE

# 计算比例
SHARED_RATIO=$((($SHARED_CLEAN + $SHARED_DIRTY) * 100 / $TOTAL_RSS))
DIRTY_RATIO=$(($PRIVATE_DIRTY * 100 / $TOTAL_RSS))

echo "内存效率指标:" >> $OUTPUT_FILE
echo "  共享内存比例: $SHARED_RATIO%" >> $OUTPUT_FILE
echo "  私有脏页比例: $DIRTY_RATIO%" >> $OUTPUT_FILE

# 评估等级
if [ $SHARED_RATIO -gt 30 ]; then
    echo "  共享效率: 优秀 ✅" >> $OUTPUT_FILE
elif [ $SHARED_RATIO -gt 20 ]; then
    echo "  共享效率: 良好 🟡" >> $OUTPUT_FILE
else
    echo "  共享效率: 需要改善 ⚠️" >> $OUTPUT_FILE
fi

if [ $DIRTY_RATIO -lt 50 ]; then
    echo "  脏页比例: 优秀 ✅" >> $OUTPUT_FILE
elif [ $DIRTY_RATIO -lt 70 ]; then
    echo "  脏页比例: 良好 🟡" >> $OUTPUT_FILE
else
    echo "  脏页比例: 偏高 ⚠️" >> $OUTPUT_FILE
fi

echo "" >> $OUTPUT_FILE

# Dalvik 内存分析
DALVIK_RSS=$(cat /proc/$PID/smaps | grep -A 10 "dalvik" | awk '/^Rss:/ {sum+=$2} END {print sum}')
DALVIK_RATIO=$(($DALVIK_RSS * 100 / $TOTAL_RSS))

echo "内存分布分析:" >> $OUTPUT_FILE
echo "  Dalvik 内存: $DALVIK_RSS kB ($DALVIK_RATIO%)" >> $OUTPUT_FILE

if [ $DALVIK_RATIO -lt 60 ]; then
    echo "  Dalvik 占比: 正常 ✅" >> $OUTPUT_FILE
elif [ $DALVIK_RATIO -lt 70 ]; then
    echo "  Dalvik 占比: 偏高 🟡" >> $OUTPUT_FILE
else
    echo "  Dalvik 占比: 过高，检查内存泄漏 ⚠️" >> $OUTPUT_FILE
fi

# TOP 内存区域
echo "" >> $OUTPUT_FILE
echo "TOP 10 内存占用区域:" >> $OUTPUT_FILE
cat /proc/$PID/smaps | grep -B 12 "^Pss:" | grep -E "^[0-9a-f]" | sort -k3 -nr | head -10 >> $OUTPUT_FILE

echo "" >> $OUTPUT_FILE
echo "分析完成，详细报告保存在: $OUTPUT_FILE"
```

---

## 🔗 相关工具链接

- **应用级分析**: [dumpsys meminfo 解释指南](./meminfo_interpretation_guide.md)
- **系统级分析**: [/proc/meminfo 解释指南](./proc_meminfo_interpretation_guide.md)
- **进程级概览**: [showmap 解释指南](./showmap_interpretation_guide.md)  
- **解析结果理解**: [解析结果指南](./analysis_results_interpretation_guide.md)

---

## 💡 最佳实践建议

### 1. 日常监控
- 建立内存基准数据，定期对比
- 重点关注 Private_Dirty 的增长趋势
- 监控共享内存效率和 PSS 变化

### 2. 问题定位
- 优先分析 Private_Dirty 最大的区域
- 结合应用行为分析内存变化模式
- 使用 HPROF 和 Native 工具深入分析

### 3. 性能优化
- 减少不必要的 Private_Dirty 内存
- 提高共享内存使用效率
- 优化大对象和文件映射管理

### 4. 工具配合
- SMAPS 提供详细数据，showmap 提供概览
- 结合 HPROF 分析 Java 堆
- 使用 Native 工具分析 C/C++ 内存

通过深入理解 SMAPS 的每个字段和内存映射模式，可以精确定位内存问题根源，制定有效的优化策略。SMAPS 是 Android 内存分析最重要的数据源，掌握其解读方法对内存优化至关重要。