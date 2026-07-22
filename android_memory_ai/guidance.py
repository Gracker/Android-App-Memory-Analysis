"""Intent selection, evidence requirements, and collection guidance."""

from typing import Any, Dict, Iterable, List, Tuple

from .contracts import ArtifactEvidence, EvidenceCoverage, EvidenceGap


INTENT_PROFILES: Dict[str, Dict[str, Any]] = {
    "quick-triage": {
        "required": ["meminfo"],
        "supporting": ["device_context", "smaps", "proc_meminfo", "analysis_report"],
        "any_of": [],
    },
    "java-leak": {
        "required": ["phase_metadata", "comparison_report"],
        "supporting": ["meminfo", "smaps", "analysis_report"],
        "any_of": [["hprof", "android_log"]],
    },
    "native-memory": {
        "required": ["meminfo"],
        "supporting": ["device_context", "phase_metadata", "native_heap_profile", "analysis_report"],
        "any_of": [["smaps", "showmap"]],
    },
    "graphics": {
        "required": ["meminfo"],
        "supporting": ["gfxinfo", "dmabuf", "smaps", "device_context", "analysis_report"],
        "any_of": [["gfxinfo", "dmabuf", "smaps"]],
    },
    "system-pressure": {
        "required": ["proc_meminfo"],
        "supporting": ["pressure_memory", "zram", "exit_info", "perfetto_trace", "device_context"],
        "any_of": [["pressure_memory", "exit_info", "perfetto_trace"]],
    },
    "regression": {
        "required": ["phase_metadata", "comparison_report"],
        "supporting": ["meminfo", "smaps", "analysis_report"],
        "any_of": [],
    },
}


INTENT_KEYWORDS: Dict[str, Tuple[str, ...]] = {
    "java-leak": (
        "java leak", "java heap", "hprof", "gc root", "retained", "java 泄漏",
        "activity leak", "fragment leak", "activity 泄漏", "fragment 泄漏", "对象", "引用链",
    ),
    "native-memory": (
        "native", "jni", "scudo", "malloc", "directbytebuffer", "heapprofd", "本地内存",
    ),
    "graphics": (
        "graphics", "bitmap", "gpu", "dmabuf", "egl", "webview", "图形", "纹理", "显存",
    ),
    "system-pressure": (
        "lmkd", "low memory", "pressure", "psi", "zram", "swap", "oom", "卡顿", "低内存", "杀进程",
    ),
    "regression": (
        "regression", "before", "after", "compare", "growth", "grow", "increase", "rising",
        "memory leak", "gets larger", "higher memory", "leak", "回归", "前后", "增长", "持续增长",
        "变多", "越来越多", "上涨", "升高", "不回落", "泄漏", "泄露", "对比",
    ),
}


COLLECTION_GUIDANCE: Dict[str, Dict[str, Any]] = {
    "device_context": {
        "command": "adb shell getprop > getprop.txt && adb shell getconf PAGE_SIZE > page_size.txt",
        "reason_zh": "缺少 API、fingerprint、页大小和厂商背景时，版本与跨设备结论都不可靠。",
        "reason_en": "API level, fingerprint, page size, and vendor context bound version-sensitive conclusions.",
        "prerequisites_zh": ["已连接并授权的 adb 设备"],
        "prerequisites_en": ["An adb-connected and authorized device"],
        "perturbation": "low",
    },
    "phase_metadata": {
        "command": "printf 'timestamp_utc=%s\\npackage=%s\\npid=%s\\nprocess_role=%s\\nuser_profile=%s\\nscenario=%s\\nphase=%s\\nloops=%s\\ncooldown_seconds=%s\\ncollection_mode=%s\\nperturbation=%s\\n' '<YYYY-MM-DDTHH:MM:SSZ>' '<package>' '<pid>' '<main|named process>' '<Android user/profile>' '<exact steps>' '<baseline|after|cooldown>' '<count>' '<seconds>' '<commands and switches>' '<low|medium|high>' > run_config.txt",
        "reason_zh": "泄漏与回归需要场景、轮次、等待时间、PID 和采集扰动，单点文件无法证明增长。",
        "reason_en": "Leak and regression claims need scenario, loop, cooldown, PID, and perturbation metadata.",
        "prerequisites_zh": ["记录可复现步骤、时间点与进程身份"],
        "prerequisites_en": ["Record reproducible steps, timestamps, and process identity"],
        "perturbation": "none",
    },
    "meminfo": {
        "command": "adb shell dumpsys meminfo --local <package-or-pid> > meminfo.txt",
        "reason_zh": "缺少进程页账时，无法判断 Java、Native、Graphics 或其他分类的主方向。",
        "reason_en": "A process page-accounting snapshot is needed to choose the Java, native, graphics, or other branch.",
        "prerequisites_zh": ["目标进程正在运行", "把 `<package-or-pid>` 替换为真实目标"],
        "prerequisites_en": ["The target process is running", "Replace `<package-or-pid>` with the real target"],
        "perturbation": "low",
        "alternatives": ["python3 \"$ANDROID_MEMORY_ANALYSIS_ROOT/analyze.py\" live --package <package> --skip-hprof"],
    },
    "smaps": {
        "command": "adb shell cat /proc/<pid>/smaps > smaps.txt",
        "reason_zh": "没有 VMA 证据时，Native/Unknown/Code 分类不能归因到具体映射或 owner。",
        "reason_en": "VMA evidence is required before native, unknown, or code buckets can be attributed to mappings or owners.",
        "prerequisites_zh": ["目标 PID 稳定", "userdebug/eng、root 或允许读取 procfs 的环境"],
        "prerequisites_en": ["A stable target PID", "userdebug/eng, root, or procfs access"],
        "perturbation": "low",
        "alternatives": ["adb shell showmap <pid> > showmap.txt"],
    },
    "showmap": {
        "command": "adb shell showmap <pid> > showmap.txt",
        "reason_zh": "需要保留到映射粒度的页账来拆解 Android 汇总分类。",
        "reason_en": "Mapping-level page accounting is needed to decompose Android summary buckets.",
        "prerequisites_zh": ["目标 PID 稳定", "设备提供 showmap 且具备读取权限"],
        "prerequisites_en": ["A stable target PID", "showmap and sufficient permissions on the device"],
        "perturbation": "low",
        "alternatives": ["adb shell cat /proc/<pid>/smaps > smaps.txt"],
    },
    "hprof": {
        "command": "adb shell am dumpheap <package> /data/local/tmp/app.hprof && adb pull /data/local/tmp/app.hprof ./app.hprof",
        "reason_zh": "没有对象图、GC Root 和引用链时，只能提出 Java 泄漏假设，不能定位 owner。",
        "reason_en": "Without an object graph, GC roots, and reference paths, a Java leak remains a hypothesis.",
        "prerequisites_zh": ["debuggable/profileable 能力或 root", "受控场景与隐私授权", "足够磁盘空间"],
        "prerequisites_en": ["debuggable/profileable capability or root", "A controlled scenario and privacy approval", "Enough storage"],
        "perturbation": "high",
        "alternatives": ["Android Studio Memory Profiler", "LeakCanary report with retained paths"],
    },
    "android_log": {
        "command": "adb logcat -b main,system,crash -v threadtime -T '<start-time>' > logcat.txt",
        "reason_zh": "QA 日志可以保存 LeakCanary 引用链、组件/资源未释放、OOM、GC 压力与 LMKD 事件；必须保留时间、tag、PID 和上下文行，单条匹配不能独立证明 owner 或增长。",
        "reason_en": "QA logs can preserve LeakCanary paths, component/resource cleanup warnings, OOMs, GC pressure, and LMKD events; retain time, tag, PID, and surrounding lines because one match cannot prove ownership or growth.",
        "prerequisites_zh": ["固定复现时间窗与目标 package/PID", "确认 main/system/crash buffer 访问范围", "上传前检查账号、URL、token、业务内容与用户数据"],
        "prerequisites_en": ["A fixed reproduction window and target package/PID", "Access to the required main/system/crash buffers", "Privacy review for accounts, URLs, tokens, business content, and user data"],
        "perturbation": "none-to-low",
        "alternatives": [
            "adb logcat -d -b main,system,crash -v threadtime > logcat.txt",
            "Export the complete LeakCanary leak trace, not only the notification screenshot",
        ],
    },
    "native_heap_profile": {
        "command": "python3 \"$ANDROID_MEMORY_ANALYSIS_ROOT/tools/perfetto_helper.py\" record --package <package> --duration 30s --output native-heap.perfetto-trace",
        "reason_zh": "smaps/showmap 只能定位单点映射大小或多 phase 的映射差值；Native owner 需要符号化的 heapprofd/malloc 调用栈或等价分配证据。",
        "reason_en": "smaps/showmap locates mapping size or phase deltas; native ownership needs symbolized heapprofd or equivalent allocation call stacks.",
        "prerequisites_zh": ["设置 ANDROID_MEMORY_ANALYSIS_ROOT 为工具仓库路径", "Android 10+", "profileable/debuggable 或平台允许的 profiling 权限", "可符号化的构建产物"],
        "prerequisites_en": ["Set ANDROID_MEMORY_ANALYSIS_ROOT to the tool repository", "Android 10+", "profileable/debuggable or platform profiling access", "Symbolization artifacts"],
        "perturbation": "medium",
        "alternatives": [
            "Open native-heap.perfetto-trace in Perfetto, select the Heap Profile track, and symbolize with matching unstripped binaries/build IDs",
            "Use malloc_debug or app-owned allocation tracing when heapprofd is unavailable",
        ],
    },
    "gfxinfo": {
        "command": "adb shell dumpsys gfxinfo <package> > gfxinfo.txt",
        "reason_zh": "图形问题需要渲染资源与帧统计，不能只看 Java Bitmap 数量。",
        "reason_en": "Graphics investigations need rendering resource and frame evidence, not only Java Bitmap counts.",
        "prerequisites_zh": ["目标应用运行过待分析场景"],
        "prerequisites_en": ["The target app has exercised the scenario"],
        "perturbation": "low",
    },
    "dmabuf": {
        "command": "adb shell cat /sys/kernel/debug/dma_buf/bufinfo > dmabuf_debug.txt",
        "reason_zh": "跨进程图形/共享缓冲需要 DMA-BUF owner 证据，meminfo 分类可能重复或只展示局部。",
        "reason_en": "Cross-process graphics and shared buffers need DMA-BUF ownership evidence; meminfo may be partial or overlapping.",
        "prerequisites_zh": ["root/userdebug 或可读 debugfs", "OEM 内核暴露 DMA-BUF 统计"],
        "prerequisites_en": ["root/userdebug or readable debugfs", "Kernel DMA-BUF statistics"],
        "perturbation": "low",
    },
    "proc_meminfo": {
        "command": "adb shell cat /proc/meminfo > proc_meminfo.txt",
        "reason_zh": "App 快照不能证明整机低内存；需要系统容量、可用页、缓存、slab 与 swap 背景。",
        "reason_en": "An app snapshot cannot prove device pressure; system capacity, available pages, cache, slab, and swap context are required.",
        "prerequisites_zh": ["已连接并授权的 adb 设备"],
        "prerequisites_en": ["An adb-connected and authorized device"],
        "perturbation": "low",
    },
    "pressure_memory": {
        "command": "adb shell cat /proc/pressure/memory > pressure_memory.txt",
        "reason_zh": "PSI 时间窗口能说明任务因内存短缺而停顿，单个 MemAvailable 数字不能替代。",
        "reason_en": "PSI windows show stalls caused by memory shortage; a single MemAvailable value cannot replace them.",
        "prerequisites_zh": ["内核启用 PSI 并允许读取 `/proc/pressure/memory`"],
        "prerequisites_en": ["Kernel PSI support and access to `/proc/pressure/memory`"],
        "perturbation": "low",
    },
    "zram": {
        "command": "adb shell cat /proc/swaps > proc_swaps.txt",
        "reason_zh": "SwapPss 只能说明进程换出页；ZRAM 容量、压缩和 I/O 状态需要系统证据。",
        "reason_en": "SwapPss describes swapped process pages; ZRAM capacity, compression, and I/O need system evidence.",
        "prerequisites_zh": ["设备启用并暴露 swap/ZRAM 接口"],
        "prerequisites_en": ["Exposed swap/ZRAM interfaces"],
        "perturbation": "low",
    },
    "exit_info": {
        "command": "adb shell dumpsys activity exit-info <package> > exit_info.txt",
        "reason_zh": "进程消失或被杀时，需要退出原因与时间；最后 RSS 不是精确死亡前快照。",
        "reason_en": "A missing or killed process needs exit reason and timing; last RSS is not an exact pre-death snapshot.",
        "prerequisites_zh": ["Android 11+/API 30+", "替换真实包名"],
        "prerequisites_en": ["Android 11+/API 30+", "Replace the package placeholder"],
        "perturbation": "low",
    },
    "comparison_report": {
        "command": "python3 \"$ANDROID_MEMORY_ANALYSIS_ROOT/analyze.py\" diff -b <before-dir> -a <after-dir> --json -o comparison.json",
        "reason_zh": "增长结论需要同设备、同场景、同 PID 语义的至少两个 phase。",
        "reason_en": "Growth claims require at least two phases with matching device, scenario, and PID semantics.",
        "prerequisites_zh": ["设置 ANDROID_MEMORY_ANALYSIS_ROOT 为工具仓库路径", "可比的 before/after 目录", "相同采集模式与冷却策略"],
        "prerequisites_en": ["Set ANDROID_MEMORY_ANALYSIS_ROOT to the tool repository", "Comparable before/after directories", "Matching capture and cooldown policy"],
        "perturbation": "none",
    },
    "analysis_report": {
        "command": "python3 \"$ANDROID_MEMORY_ANALYSIS_ROOT/analyze.py\" panorama -d <dump-dir> --json -o panorama_report.json",
        "reason_zh": "结构化解析摘要能降低 AI 直接读取大文件时的误读，但仍必须保留原始证据边界。",
        "reason_en": "A structured parser summary reduces AI misreads of large files while preserving raw-evidence boundaries.",
        "prerequisites_zh": ["设置 ANDROID_MEMORY_ANALYSIS_ROOT 为工具仓库路径", "目录包含至少一种受支持的原始证据"],
        "prerequisites_en": ["Set ANDROID_MEMORY_ANALYSIS_ROOT to the tool repository", "The directory contains at least one supported raw artifact"],
        "perturbation": "none",
    },
    "perfetto_trace": {
        "command": "python3 \"$ANDROID_MEMORY_ANALYSIS_ROOT/tools/perfetto_helper.py\" record --package <package> --duration 30s",
        "reason_zh": "系统压力和恢复成本是时间线问题，需要调度、进程状态、内存计数器或分配事件。",
        "reason_en": "System pressure and recovery cost are timeline problems needing scheduling, process state, counters, or allocation events.",
        "prerequisites_zh": ["设置 ANDROID_MEMORY_ANALYSIS_ROOT 为工具仓库路径", "设备提供 Perfetto", "固定复现场景和 trace 时间窗"],
        "prerequisites_en": ["Set ANDROID_MEMORY_ANALYSIS_ROOT to the tool repository", "Perfetto on the device", "A fixed scenario and trace window"],
        "perturbation": "medium",
    },
}


def infer_intent(requested: str, question: str) -> Tuple[str, List[str]]:
    if requested and requested != "auto":
        if requested not in INTENT_PROFILES:
            raise ValueError("unsupported intent: {}".format(requested))

    normalized = (question or "").lower()
    scores = []
    for intent, keywords in INTENT_KEYWORDS.items():
        score = sum(1 for keyword in keywords if keyword in normalized)
        if score:
            scores.append((score, intent))
    scores.sort(key=lambda item: (-item[0], item[1]))
    inferred = [intent for _, intent in scores]
    if requested and requested != "auto":
        candidates = [requested] + [intent for intent in inferred if intent != requested]
        return requested, candidates
    candidates = inferred
    return (candidates[0] if candidates else "quick-triage"), candidates


def assess_coverage(
    intent: str,
    available_types: Iterable[str],
    inadequate_types: Iterable[str] = (),
) -> EvidenceCoverage:
    profile = INTENT_PROFILES[intent]
    available = sorted(set(available_types))
    available_set = set(available)
    inadequate = sorted(set(inadequate_types).intersection(available_set))
    effective_set = available_set.difference(inadequate)
    required = list(profile["required"])
    supporting = list(profile["supporting"])
    missing_required = [item for item in required if item not in effective_set]
    missing_supporting = [item for item in supporting if item not in effective_set]
    satisfied_any_of = []
    missing_any_of = []
    for group in profile.get("any_of", []):
        if effective_set.intersection(group):
            satisfied_any_of.append(list(group))
        else:
            missing_any_of.append(list(group))

    if missing_required or missing_any_of:
        level = "insufficient"
        rationale_zh = "必需证据缺失、内容不完整，或至少一组选一证据未满足，只能给出受限解释和补证路线。"
        rationale_en = "Required evidence is missing or incomplete, or an any-of evidence group is unsatisfied; only bounded interpretation is supported."
    elif missing_supporting:
        level = "limited" if len(missing_supporting) > len(supporting) / 2.0 else "supported"
        rationale_zh = "核心证据可用，但仍有支持证据缺失，结论必须保留替代解释。"
        rationale_en = "Core evidence is available, but missing supporting inputs require alternative explanations to remain open."
    else:
        level = "strong"
        rationale_zh = "当前意图定义的核心与支持证据齐全；具体结论仍需逐条绑定证据。"
        rationale_en = "The intent's core and supporting evidence is present; each claim must still bind to concrete evidence."

    return EvidenceCoverage(
        level=level,
        intent=intent,
        required=required,
        supporting=supporting,
        available=available,
        missing_required=missing_required,
        missing_supporting=missing_supporting,
        inadequate=inadequate,
        satisfied_any_of=satisfied_any_of,
        missing_any_of=missing_any_of,
        rationale_zh=rationale_zh,
        rationale_en=rationale_en,
    )


def build_gaps(coverage: EvidenceCoverage) -> List[EvidenceGap]:
    ordered: List[Tuple[str, str]] = []
    for artifact_type in coverage.missing_required:
        ordered.append((artifact_type, "required"))
    for group in coverage.missing_any_of:
        for artifact_type in group:
            ordered.append((artifact_type, "one-of"))
    for artifact_type in coverage.missing_supporting:
        ordered.append((artifact_type, "supporting"))

    collection_order = {
        "device_context": 0,
        "phase_metadata": 1,
        "meminfo": 2,
        "proc_meminfo": 2,
    }
    ordered.sort(key=lambda item: collection_order.get(item[0], 10))

    gaps = []
    seen = set()
    for artifact_type, priority in ordered:
        if artifact_type in seen:
            continue
        seen.add(artifact_type)
        guide = COLLECTION_GUIDANCE.get(artifact_type)
        if not guide:
            continue
        gaps.append(
            EvidenceGap(
                artifact_type=artifact_type,
                priority=priority,
                reason_zh=guide["reason_zh"],
                reason_en=guide["reason_en"],
                command=guide.get("command"),
                prerequisites_zh=list(guide.get("prerequisites_zh", [])),
                prerequisites_en=list(guide.get("prerequisites_en", [])),
                perturbation=guide["perturbation"],
                alternatives=list(guide.get("alternatives", [])),
            )
        )
    return gaps


def intent_inadequate_artifacts(
    intent: str,
    artifacts: Iterable[ArtifactEvidence],
) -> List[str]:
    inadequate = []
    for artifact in artifacts:
        if (
            artifact.artifact_type == "phase_metadata"
            and artifact.status == "ok"
            and artifact.metadata.get("comparison_context_complete") is False
        ):
            if intent in ("java-leak", "native-memory", "regression"):
                inadequate.append("phase_metadata")
            break
    if intent == "java-leak":
        logs = [
            artifact for artifact in artifacts
            if artifact.artifact_type == "android_log" and artifact.status == "ok"
        ]
        if logs and not any(
            artifact.metadata.get("log_scan", {}).get("managed_owner_path_candidate")
            for artifact in logs
        ):
            inadequate.append("android_log")
    return inadequate
