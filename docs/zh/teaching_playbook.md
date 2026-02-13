# 教学实践手册

这份手册用于统一培训、入项学习和团队复盘的执行流程。

## 标准分析流程

### 第一步：基线采集

```bash
python3 analyze.py live --package <package>
```

### 第二步：信号分诊

- 先看总内存趋势。
- 按 Java 堆、Native、Graphics、文件映射拆分。
- 先标记异常桶，再进入深挖。

### 第三步：根因定位

- `smaps` 与 `meminfo` 交叉验证，统一证据口径。
- 用 HPROF 补充对象持有链证据。
- 所有判断都绑定可复现的场景步骤。

### 第四步：修复与复验

- 用同一套采集命令复跑同一场景。
- 对比修复前后内存分布变化。
- 记录副作用和回归风险。

## 自动化基线脚本

```bash
#!/bin/bash

PACKAGE=$1
INTERVAL=${2:-300}
LOG_DIR="memory_logs"

mkdir -p "$LOG_DIR"

while true; do
  TIMESTAMP=$(date +%Y%m%d_%H%M%S)
  PID=$(adb shell "pidof $PACKAGE")

  if [ -n "$PID" ]; then
    python3 tools/smaps_parser.py -p "$PID" -o "$LOG_DIR/smaps_$TIMESTAMP.txt"
    TOTAL=$(grep -E "Total Memory Usage|总内存使用" "$LOG_DIR/smaps_$TIMESTAMP.txt" | grep -oE '[0-9.]+' | head -1)
    echo "$TIMESTAMP,$TOTAL" >> "$LOG_DIR/memory_trend.csv"
  fi

  sleep "$INTERVAL"
done
```

## 团队报告模板

```markdown
# 内存分析报告

## 基础信息
- 应用版本：
- Android 版本：
- 设备型号：
- 分析时间：

## 场景与复现
- 触发步骤：
- 预期行为：
- 实际行为：

## 内存快照摘要
- 总内存：
- Java 堆：
- Native 内存：
- 图形内存：

## 关键发现
1. [问题]
   - 影响等级：
   - 证据：
   - 根因：

## 修复方案与复验
1. [动作]
   - 预期收益：
   - 复验结果：

## 附件
- smaps 输出：
- meminfo 输出：
- hprof 输出：
```

## Code Review 检查项

- [ ] 是否存在无界集合增长
- [ ] 是否存在生命周期绑定对象泄漏
- [ ] 是否存在大图或大缓冲区滞留
- [ ] 是否存在不安全的 Native 分配模式
- [ ] 异步或回调链路是否存在缺失释放路径

## Android 16 兼容检查项

- 在 16KB page size 设备上验证解析与解读结果。
- 保持 `smaps` 采集兜底顺序：直接 cat -> `su -c` -> `su 0`。
- 确认非 root 场景依然能通过 meminfo 输出形成可用结论。
- 基线与复验必须使用同一套采集方式，避免口径漂移。
