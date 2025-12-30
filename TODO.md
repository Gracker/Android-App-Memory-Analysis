# Android 内存分析工具 TODO

## 已完成功能

- [x] **一键 Dump**: 从设备采集 meminfo/gfxinfo/hprof/smaps
- [x] **全景分析**: 多数据源关联分析
- [x] **HPROF 分析**: Java 堆对象分析、泄漏检测、引用链追踪
- [x] **SMAPS 分析**: Native 内存映射分析（支持 Android 4.0-16+）
- [x] **Bitmap 关联**: Java Bitmap 对象与 Native 像素内存关联
- [x] **Native 追踪**: 可追踪 vs 未追踪 Native 内存分析

---

## Phase 1: 增强现有功能 ⚡ 可立即实现

### 1.1 Markdown 报告导出 ✅ 已完成

**目标**: 全景分析支持 `--markdown` 参数输出 Markdown 格式报告

**Action Items**:
- [x] 在 `panorama_analyzer.py` 添加 `--markdown` / `-md` 参数
- [x] 实现 `generate_markdown_report()` 方法
- [x] 输出包含表格、代码块的 Markdown 文件
- [x] 在 `analyze.py` 中传递 markdown 参数

**用法**:
```bash
python3 analyze.py panorama -d ./dump --markdown -o report.md
```

### 1.2 HPROF 集成到全景分析 ✅ 已完成

**目标**: 在全景报告中包含 HPROF 的 Java 对象统计

**Action Items**:
- [x] 在 `panorama_analyzer.py` 中导入 `hprof_parser`
- [x] 解析 HPROF 获取: 总实例数、总内存、TOP 类统计
- [x] 将 HPROF 数据整合到 `PanoramaResult`
- [x] 在报告中添加 "Java 堆详情" 部分
- [x] 关联 HPROF Bitmap 对象数量与 meminfo Bitmap 统计

**用法**:
```bash
python3 analyze.py panorama -m meminfo.txt -g gfxinfo.txt -H heap.hprof
```

### 1.3 对比分析 ✅ 已完成

**目标**: 支持两次 dump 的差异分析，发现内存增长

**Action Items**:
- [x] 创建 `tools/diff_analyzer.py`
- [x] 实现 meminfo 差异对比: PSS/Java Heap/Native 变化
- [x] 实现 gfxinfo 差异对比: View 数量变化、帧率变化
- [ ] 实现 HPROF 差异对比: 类实例数增减 (待完善)
- [x] 在 `analyze.py` 添加 `diff` 子命令
- [x] 高亮显示增长超过阈值的项目

**用法**:
```bash
python3 analyze.py diff -b ./dump_before -a ./dump_after
python3 analyze.py diff --before-meminfo m1.txt --after-meminfo m2.txt
```

### 1.4 历史趋势 ⏳ 后续实现

**目标**: 多次采集的内存趋势图

**依赖**: 需要 matplotlib 或其他图表库，暂缓

---

## Phase 2: 系统级数据采集 ⚡ 可立即实现

### 2.1 系统内存上下文 ✅ 已完成

**目标**: 解析 `/proc/meminfo`，提供系统内存压力分析

**Action Items**:
- [x] 创建 `tools/proc_meminfo_parser.py`
- [x] 解析关键字段: MemTotal, MemFree, MemAvailable, Buffers, Cached, SwapTotal, SwapFree
- [x] 计算内存压力指标: 可用内存比例、Swap 使用率
- [ ] 在 live_dumper 中采集 `/proc/meminfo` (待完善)
- [x] 在全景报告中添加 "系统内存上下文" 部分

**用法**:
```bash
# 单独分析
python3 tools/proc_meminfo_parser.py -f proc_meminfo.txt

# 集成到全景分析
python3 tools/panorama_analyzer.py -d ./dump -P proc_meminfo.txt
```

### 2.2 DMA-BUF 分析 ✅ 已完成

**目标**: 解析 `/sys/kernel/debug/dma_buf/bufinfo`，分析图形/相机/视频内存

**Action Items**:
- [x] 创建 `tools/dmabuf_parser.py`
- [x] 解析 DMA-BUF debugfs 输出格式
- [x] 按类型分类统计: GPU、Display、Camera、Video、Audio
- [x] 在全景报告中添加 "DMA-BUF 分析" 部分
- [ ] 在 live_dumper 中采集 dmabuf_debug.txt (待完善)

**用法**:
```bash
# 单独分析
python3 tools/dmabuf_parser.py -f dmabuf_debug.txt

# 集成到全景分析
python3 tools/panorama_analyzer.py -d ./dump -D dmabuf_debug.txt
```

### 2.3 进程状态监控 ⏳ 后续实现

**目标**: 持续采集分析内存增长趋势

**依赖**: 需要持续监控机制，暂缓

---

## Phase 3: Perfetto 集成 ✅ 已完成

### 3.1 Perfetto 配置生成器 ✅ 已完成

**目标**: 根据用户需求生成内存追踪配置

**Action Items**:
- [x] 创建 `tools/perfetto_helper.py`
- [x] 实现配置模板: 内存追踪、heapprofd、进程统计
- [x] 支持自定义参数: 采样间隔、目标进程、持续时间
- [x] 生成 .pbtxt 配置文件

**用法**:
```bash
python3 tools/perfetto_helper.py config -p com.example.app -d 30s -o config.pbtxt
```

### 3.2 Perfetto 启动/停止 ✅ 已完成

**目标**: 集成 Perfetto 追踪命令

**Action Items**:
- [x] 在 `perfetto_helper.py` 添加 start/stop 方法
- [x] 封装 `adb shell perfetto` 命令
- [x] 自动拉取 trace 文件到本地
- [x] 实现 record 子命令 (一键录制)

**用法**:
```bash
# 启动追踪
python3 tools/perfetto_helper.py start -p com.example.app -d 30s

# 停止追踪
python3 tools/perfetto_helper.py stop

# 一键录制 (推荐)
python3 tools/perfetto_helper.py record -d 10s -o trace.perfetto --analyze
```

### 3.3 Trace 解析 ✅ 已完成

**目标**: 解析 Perfetto trace 文件

**Action Items**:
- [x] 集成 trace_processor_shell (位于 `tools/perfetto-mac-arm64/`)
- [x] 实现默认分析查询 (追踪概览、进程信息、内存统计)
- [x] 支持自定义 SQL 查询
- [x] 支持交互式 shell 模式

**用法**:
```bash
# 分析 trace 文件
python3 tools/perfetto_helper.py analyze trace.perfetto

# 自定义查询
python3 tools/perfetto_helper.py analyze trace.perfetto -q "SELECT * FROM process"

# 交互式 shell
python3 tools/perfetto_helper.py analyze trace.perfetto -i
```

---

## Phase 4: eBPF 内存追踪 ⏳ 后续实现

**依赖**: 需要 Root + BCC 工具 + 内核支持，暂缓

---

## Phase 5: 高级分析功能 ⚡ 部分可实现

### 5.1 zRAM/Swap 分析 ✅ 已完成

**目标**: 解析 zRAM 压缩统计

**Action Items**:
- [x] 创建 `tools/zram_parser.py` 解析 zRAM/Swap 数据
- [x] 在 live_dumper 中采集 `/proc/swaps`、`/sys/block/zram*/mm_stat`
- [x] 解析 zRAM 统计: 原始大小、压缩大小、压缩率
- [x] 在全景报告中添加 "zRAM/Swap 分析" 部分
- [x] 支持 JSON 和 Markdown 输出

**用法**:
```bash
# 单独分析
python3 tools/zram_parser.py -f zram_swap.txt

# 集成到全景分析 (从 dump 目录自动读取)
python3 tools/panorama_analyzer.py -d ./dump

# 或指定文件
python3 tools/panorama_analyzer.py -m meminfo.txt -Z zram_swap.txt
```

**输出示例**:
```
────────────────────────────────────────
[ zRAM/Swap 分析 ]
────────────────────────────────────────
Swap 总量:       2048.0 MB (1 个设备)
Swap 已用:        512.0 MB (25.0%)
zRAM 磁盘:       2048.0 MB (1 个设备)
原始数据:        1200.0 MB
压缩后数据:       280.5 MB
实际内存占用:     300.2 MB
压缩率:            4.28x
节省空间:          76.6%
节省内存:         899.8 MB
```

---

## Phase 6: 自动化与 CI 集成 ⚡ 可立即实现

### 6.1 JSON 输出 ✅ 已完成

**目标**: 支持 JSON 格式输出，便于自动化处理

**Action Items**:
- [x] 在 `panorama_analyzer.py` 添加 `--json` 参数
- [x] 实现 `to_json()` 方法
- [x] 输出结构化 JSON 数据
- [x] 在 `analyze.py` 中传递 json 参数

**用法**:
```bash
python3 analyze.py panorama -d ./dump --json -o result.json
python3 analyze.py panorama -d ./dump --json  # 输出到 stdout
```

### 6.2 阈值告警 ✅ 已完成

**目标**: 设置内存阈值，超过时自动告警

**Action Items**:
- [x] 在 `panorama_analyzer.py` 添加阈值配置
- [x] 支持命令行参数设置阈值
- [x] 检查: PSS、Java Heap、Native Heap、Graphics、Native 未追踪比例、卡顿率、View 数量、Activity 数量、Bitmap 数量/大小
- [x] 返回非零 exit code 当超过阈值 (WARNING=1, ERROR=2)

**用法**:
```bash
# 设置 PSS 和 View 数量阈值
python3 tools/panorama_analyzer.py -d ./dump --threshold-pss 300 --threshold-views 500

# 完整阈值参数
--threshold-pss MB           # Total PSS 阈值
--threshold-java-heap MB     # Java Heap 阈值
--threshold-native-heap MB   # Native Heap 阈值
--threshold-graphics MB      # Graphics 阈值
--threshold-native-untracked %  # Native 未追踪比例阈值
--threshold-janky %          # 卡顿率阈值
--threshold-views N          # View 数量阈值
--threshold-activities N     # Activity 数量阈值
--threshold-bitmaps N        # Bitmap 数量阈值
--threshold-bitmap-size MB   # Bitmap 总大小阈值

# Exit code: 0=正常, 1=WARNING 级别违规, 2=ERROR 级别违规
```

### 6.3 CI 集成模板 ✅ 可实现

**目标**: 提供 GitHub Actions 模板

**Action Items**:
- [ ] 创建 `.github/workflows/memory-check.yml` 模板
- [ ] 文档说明如何集成到 CI

---

## 实现优先级

| 优先级 | 功能 | 复杂度 | 价值 | 状态 |
|--------|------|--------|------|------|
| P0 | 1.1 Markdown 导出 | 低 | 高 | ✅ 已完成 |
| P0 | 6.1 JSON 输出 | 低 | 高 | ✅ 已完成 |
| P1 | 1.3 对比分析 | 中 | 高 | ✅ 已完成 |
| P1 | 1.2 HPROF 集成 | 中 | 高 | ✅ 已完成 |
| P2 | 2.1 系统内存上下文 | 低 | 中 | ✅ 已完成 |
| P2 | 2.2 DMA-BUF 分析 | 中 | 中 | ✅ 已完成 |
| P2 | 6.2 阈值告警 | 低 | 中 | ✅ 已完成 |
| P3 | 3.1 Perfetto 配置 | 中 | 中 | ✅ 已完成 |
| P3 | 3.2 Perfetto 启停 | 中 | 中 | ✅ 已完成 |
| P3 | 3.3 Trace 解析 | 中 | 中 | ✅ 已完成 |
| P4 | 5.1 zRAM 分析 | 低 | 低 | ✅ 已完成 |

---

## 所需工具

### 已集成

- [x] **adb**: Android Debug Bridge
- [x] **hprof-conv**: HPROF 格式转换
- [x] **perfetto**: 系统级追踪 (位于 `tools/perfetto-mac-arm64/`)
- [x] **trace_processor_shell**: Perfetto trace 解析 (位于 `tools/perfetto-mac-arm64/`)
- [x] **zram_parser.py**: zRAM/Swap 数据解析器

---

## 参考资料

- [Android Memory Management](https://developer.android.com/topic/performance/memory)
- [Perfetto Documentation](https://perfetto.dev/docs/)
- [Linux Memory Management](https://www.kernel.org/doc/html/latest/admin-guide/mm/index.html)
- [AOSP android_os_Debug.cpp](https://cs.android.com/android/platform/superproject/+/master:frameworks/base/core/jni/android_os_Debug.cpp)
