# 从一次“Java 堆不高但 PSS 爆了”的排查说起：Memory Lab Demo 全链路实战

> 配套仓库：`Android-App-Memory-Analysis`  
> 配套 Demo：`demo/memory-lab`

> 封面建议：问题现象、采集命令、结论三段式排版。

## 1. 问题为什么难

Android 内存问题最难的点，不是“看不到数据”，而是“数据之间对不上”。

- `dumpsys meminfo` 能看方向（Java/Native/Graphics），但很难定位到对象级根因。
- `HPROF` 能看到对象和持有链，却解释不了很多 Native 增量。
- `showmap/smaps` 能看到映射增长，但不直接告诉你是哪段业务行为触发。

这篇文章的目标是把三套视角变成一条证据链：**业务操作 -> 指标变化 -> 根因归属**。

## 2. Demo 设计思路

`Memory Lab` 不是功能 Demo，而是“故障注入器”。它把常见内存问题做成按钮化场景，保证可重复触发、可重复采集。

当前内置场景：

1. Java leak + collections
2. Bitmap duplicates + large bitmap
3. DirectByteBuffer native pressure
4. JNI malloc/mmap native pressure
5. Ashmem pressure
6. Thread stack pressure
7. WebView native pressure
8. View storm
9. UI jank storm
10. Fragment/Service/BroadcastReceiver leak set
11. Business LruCache misconfiguration

首页提供 `0) One-click trigger all scenarios`，可以一次性触发主要泄漏与压力模式。

实现入口：`demo/memory-lab/app/src/main/java/com/androidperformance/memorylab/MainActivity.java`。

> 图示建议：场景触发页（可放 MainActivity 按钮分组截图）。

## 3. 一套可落地的采集流程

### 3.1 准备变量

```bash
PKG=com.androidperformance.memorylab
TS=$(date +%Y%m%d_%H%M%S)
OUT=./captures/$TS
REMOTE_HPROF=/data/local/tmp/memory_lab_$TS.hprof

adb root
adb wait-for-device

PID=$(adb shell pidof $PKG)
mkdir -p "$OUT"
```

### 3.2 采集核心证据

```bash
adb shell showmap $PID > "$OUT/showmap.txt"
adb shell su -c "cat /proc/$PID/smaps" > "$OUT/smaps.txt"
adb shell dumpsys meminfo -d $PKG > "$OUT/meminfo.txt"
adb shell dumpsys gfxinfo $PKG > "$OUT/gfxinfo.txt"
adb shell am dumpheap $PKG $REMOTE_HPROF
adb pull $REMOTE_HPROF "$OUT/heap.hprof"
adb shell rm $REMOTE_HPROF
```

脚本版同样可用：`demo/memory-lab/scripts/capture_memory_lab.sh`。

### 3.3 分析命令

```bash
python3 analyze.py panorama -d "$OUT"

python3 analyze.py combined --modern \
  --hprof "$OUT/heap.hprof" \
  --smaps "$OUT/smaps.txt" \
  --meminfo "$OUT/meminfo.txt" \
  --json-output "$OUT/report.json"
```

> 图示建议：panorama 输出中的“内存概览 + 异常列表”区域。

## 4. 一次真实跑数（示例）

以 `demo/memory-lab/captures/latest` 为例：

- Total PSS：`329.87 MB`
- Native Heap：`78.93 MB`
- Graphics：`55.83 MB`
- WebViews：`4`
- Panorama 异常：`UNTRACKED_NATIVE`、`HIGH_JANK`、`TOO_MANY_VIEWS`

Combined 分析同时给出：

- `LeakySingletons` 的多类静态字段形成大规模保活（Java bucket、业务 LruCache、DirectBuffer、Fragment/Service/Receiver）
- 大尺寸 + 重复尺寸 Bitmap（`820x544` 反复出现）
- 低利用率大 HashMap 与空集合大量堆积
- DirectByteBuffer 持有链能追溯到 `LeakySingletons`

这类输出最有价值的地方是：你能把同一次操作，在三套数据源里看到一致变化，而不是“单点猜测”。

## 5. 场景与信号映射（排障时最实用）

### 场景 A：Java leak + collections

- 看点：Java Heap、对象持有链、集合容量利用率
- 证据：`meminfo` 的 Java Heap + `HPROF` 的 Retained/holder chain

### 场景 B：Bitmap duplicates + large bitmap

- 看点：Bitmap 数量、重复尺寸、Graphics 增量
- 证据：`HPROF` Bitmap 深度分析 + `meminfo/smaps` 图形口径

### 场景 C：DirectByteBuffer + JNI native

- 看点：Native Heap 快速上涨，但 Java 对象无法完全解释
- 证据：`smaps/showmap` Native 映射 + `HPROF` DirectByteBuffer 持有链

### 场景 D：Thread stack pressure

- 看点：Stack 区域是否同步增长
- 证据：`meminfo` Stack + `smaps` stack_and_tls

### 场景 E：WebView native pressure

- 看点：WebView 数量与 Native 增量耦合
- 证据：`Objects.WebViews` + Native Heap + WebView 相关映射

## 6. 当前覆盖边界：已经覆盖了什么，还缺什么

先说结论：当前 Demo 已覆盖主线问题（Java 泄漏、Bitmap、Native/JNI、DirectBuffer、Ashmem、线程栈、WebView），但还不是“全口径满覆盖”。

### 6.1 已覆盖（强）

- Java 泄漏与集合累积
- Bitmap 大图与重复图
- Native 未追踪增长（JNI + DirectByteBuffer）
- WebView 导致的 Native 压力
- 基础 Ashmem 与线程栈场景

### 6.2 仍是弱覆盖或未覆盖

1. **Tracked Bitmap 口径受 ROM 输出限制**  
   `meminfo -d` 在部分机型没有完整 `Native Allocations` 段，导致 `Bitmap (malloced/nonmalloced)` 统计不稳定。

2. **高阈值场景并非每次都能稳定打穿**  
   `high_dalvik_memory`、`high_native_memory`、`high_graphics_memory`、`high_jit_cache` 这类阈值并非每次都能触发。

3. **系统侧内存上下文未纳入案例主流程**  
   `proc_meminfo`、`zram/swap`、`dmabuf` 已被工具支持，但 Demo 教程里还没有固定采集与解释模板。

## 7. 建议补齐路线（按收益排序）

1. 增加 `mode` 参数（light/medium/heavy），保证不同设备上阈值触发稳定。  
2. 增加 ROM 能力探测，区分是否支持完整 `Native Allocations`。  
3. 扩展采集模板，固定纳入 `proc_meminfo`、`zram_swap`、`dmabuf`。

## 8. 复盘模板（团队实践）

每次演练建议沉淀 6 个字段：

- 触发步骤
- before/after 时间点
- meminfo 关键字段变化
- smaps/showmap 前 3 个增长映射
- HPROF 前 3 条关键持有链
- 修复动作与复验结果

> 图示建议：团队复盘模板（触发步骤 / 关键指标 / 复验结果）。

## 9. 总结

这套 Demo 的价值，不是“模拟所有线上问题”，而是建立一种稳定工作流：

**先用 meminfo 定方向 -> 再用 smaps/showmap 锁区域 -> 最后用 HPROF 落对象。**

当你把这个流程变成团队共识，内存排障就不再是经验主义，而是可复现的工程过程。
