"""Build the canonical provider-neutral AI context envelope."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .catalog import load_catalog, select_records
from .contracts import (
    RUNTIME_NAME,
    RUNTIME_VERSION,
    SCHEMA_VERSION,
    ArtifactEvidence,
    EvidenceConflict,
    EvidenceCoverage,
    EvidenceGap,
)
from .evidence import (
    available_artifact_types,
    collect_subject_context,
    discover_artifacts,
    load_report_summaries,
)
from .folder_scan import scan_evidence_tree, summarize_inventory
from .guidance import (
    assess_coverage,
    build_gaps,
    infer_intent,
    intent_inadequate_artifacts,
)
from .history import build_analysis_history
from tools.accounting_ledger import build_accounting_ledger_from_files


ANALYSIS_RULES = [
    {
        "id": "separate-claim-kinds",
        "zh": "把 observed（原始观察）、derived（确定性计算）、hypothesis（待证假设）和 recommendation（改动建议）分开写。",
        "en": "Separate observed raw facts, deterministic derived facts, hypotheses, and recommendations.",
    },
    {
        "id": "bind-every-claim",
        "zh": "每个诊断结论必须引用 artifact_id；理论解释同时引用 knowledge id 和官方 source URL。",
        "en": "Bind every diagnosis to artifact_id; bind theory explanations to a knowledge id and official source URL.",
    },
    {
        "id": "respect-accounting-domains",
        "zh": "不同 accounting_domain 的值默认不可直接相加、相减或计算占比，除非知识条目明确给出公式。",
        "en": "Do not add, subtract, or calculate ratios across accounting domains unless a knowledge record supplies the formula.",
    },
    {
        "id": "meminfo-primary-smaps-supplemental",
        "zh": "同时存在 meminfo 与同阶段 smaps 时，以 meminfo 原始行序作为主账本，逐行附加 smaps PSS、SwapPss 与映射旁证；mtrack 等不可比较行必须显式保留。",
        "en": "When same-phase meminfo and smaps exist, keep the original meminfo row order as the primary ledger and attach smaps PSS, SwapPss, and mapping evidence row by row; preserve non-comparable rows such as memtrack explicitly.",
    },
    {
        "id": "preserve-alternatives",
        "zh": "证据不足或冲突时列出替代解释与区分它们所需的下一份证据，不要选择听起来最合理的一条。",
        "en": "When evidence is missing or conflicting, preserve alternatives and name the evidence that would distinguish them.",
    },
    {
        "id": "thresholds-are-not-diagnoses",
        "zh": "绝对 MB、实例数或百分比阈值只能触发调查；没有产品预算、设备 bucket 和趋势时不能直接定性泄漏。",
        "en": "Absolute MB, count, or percentage thresholds trigger investigation; they do not diagnose a leak without product budgets, device buckets, and trends.",
    },
    {
        "id": "qa-artifacts-need-binding",
        "zh": "QA 截图是可见状态，日志匹配是诊断信号；必须绑定目标、时间、phase、原始行或可见区域，并用 owner/趋势证据复核，不能把单张截图或单条日志直接升级为已证明根因。",
        "en": "QA screenshots are visual observations and log matches are diagnostic signals; bind them to target, time, phase, original line or visible region, then verify ownership and trend before claiming a root cause.",
    },
    {
        "id": "prior-analysis-is-derived",
        "zh": "旧分析结论只能作为待复核的 derived claim：先用当前目录重新建立证据快照，再把旧结论逐项标记为 confirmed、revised、retracted 或 unresolved；新增结论单列。",
        "en": "Treat prior conclusions as derived claims awaiting review: rebuild the evidence snapshot from the current folder, then mark each material prior claim confirmed, revised, retracted, or unresolved and list new claims separately.",
    },
    {
        "id": "fixes-need-verification",
        "zh": "代码修改必须说明 owner、机制、预期变化、回归风险、同场景 before/after/cooldown 验证和回滚条件。",
        "en": "Code changes must state owner, mechanism, expected change, regression risk, matching before/after/cooldown validation, and rollback conditions.",
    },
]


def build_ai_context(
    root: Path,
    intent: str = "auto",
    question: str = "",
    artifact_overrides: Optional[Dict[str, Any]] = None,
    subject_overrides: Optional[Dict[str, Any]] = None,
    catalog_path: Optional[Path] = None,
    hash_large_files: bool = False,
    include_local_paths: bool = False,
    analysis_mode: str = "auto",
) -> Dict[str, Any]:
    root_path = Path(root).expanduser().resolve()
    if not root_path.is_dir():
        raise ValueError(
            "dump directory does not exist or is not a directory: {}".format(
                root_path
            )
        )

    resolved_intent, candidates = infer_intent(intent, question)
    question_candidates = list(candidates)
    evidence_candidates: List[str] = []
    primary_from_evidence = False
    folder_files, folder_scan = scan_evidence_tree(root_path)
    artifacts = discover_artifacts(
        root_path,
        overrides=artifact_overrides,
        hash_large_files=hash_large_files,
        folder_files=folder_files,
    )
    available = available_artifact_types(artifacts)
    if intent == "auto":
        evidence_candidates = _infer_evidence_intents(artifacts, available)
        candidates = list(dict.fromkeys(candidates + evidence_candidates))
        if resolved_intent == "quick-triage" and evidence_candidates:
            resolved_intent = evidence_candidates[0]
            primary_from_evidence = True
        if resolved_intent not in candidates and candidates:
            candidates.insert(0, resolved_intent)
    evaluated_intents = candidates or [resolved_intent]
    coverage_by_intent = {}
    for evaluated_intent in evaluated_intents:
        intent_inadequate = intent_inadequate_artifacts(evaluated_intent, artifacts)
        coverage_by_intent[evaluated_intent] = assess_coverage(
            evaluated_intent,
            available,
            intent_inadequate,
        )
    coverage = coverage_by_intent[resolved_intent]
    combined_support_level = _combined_support_level(coverage_by_intent.values())
    gaps = _merge_gaps(coverage_by_intent.values())
    subject, conflicts, context_candidates = collect_subject_context(
        root_path,
        artifacts,
        explicit=subject_overrides,
    )
    reports = load_report_summaries(root_path, artifacts)
    conflicts.extend(_report_subject_conflicts(subject, reports))
    catalog = load_catalog(catalog_path)
    knowledge = _select_knowledge(catalog, evaluated_intents, available)

    serialized_artifacts = [
        _serialize_artifact(artifact, include_local_paths)
        for artifact in artifacts
    ]
    qa_observations = _build_qa_observations(serialized_artifacts)
    accounting_ledger = _build_accounting_ledger(artifacts)
    folder_inventory = summarize_inventory(folder_scan, serialized_artifacts)
    analysis_history = build_analysis_history(
        artifacts,
        serialized_artifacts,
        question,
        requested_mode=analysis_mode,
        folder_inventory=folder_inventory,
        current_subject=subject,
    )
    unavailable_artifacts = [
        serialized
        for artifact, serialized in zip(artifacts, serialized_artifacts)
        if artifact.status not in ("ok", "missing")
    ]
    limitations = _build_limitations(
        combined_support_level,
        unavailable_artifacts,
        conflicts,
        reports,
    )
    if accounting_ledger and accounting_ledger.get("status") == "ambiguous":
        limitations.append({
            "severity": "high",
            "zh": "存在多份 meminfo 或 smaps，当前无法在不猜测 phase 的前提下建立逐行对账；先按 package/PID/scenario/phase 明确配对。",
            "en": "Multiple meminfo or smaps artifacts are present, so row reconciliation cannot be built without guessing the phase. Pair them explicitly by package, PID, scenario, and phase.",
        })
    elif accounting_ledger and accounting_ledger.get("status") in {
        "invalid",
        "unavailable",
    }:
        ledger_invalid = accounting_ledger.get("status") == "invalid"
        limitations.append({
            "severity": "high" if ledger_invalid else "medium",
            "zh": (
                "meminfo/smaps 逐行账本构建失败；不要用派生汇总替代缺失的行级证据。"
                if ledger_invalid
                else
                "meminfo 文件没有形成可用的完整主表；不要用 App Summary 或派生汇总冒充缺失的逐行证据。"
            ),
            "en": (
                "The meminfo/smaps row-ledger build failed. Do not substitute a derived overview for the missing row evidence."
                if ledger_invalid
                else
                "The meminfo artifact did not yield a usable complete main table. Do not substitute App Summary or a derived overview for the missing row evidence."
            ),
        })
    if any(item.get("scan_truncated") for item in qa_observations["android_logs"]):
        limitations.append({
            "severity": "medium",
            "zh": "至少一份 Android 日志超过有界扫描上限；当前信号清单不是整份日志的完整索引，应按时间窗拆分或显式检查未扫描部分。",
            "en": "At least one Android log exceeded the bounded scan limit; the signal inventory is not a complete index of that file. Split it by time window or inspect the unscanned remainder explicitly.",
        })
    if folder_inventory["index_truncated"]:
        limitations.append({
            "severity": "high",
            "zh": "证据目录文件数超过递归索引上限；当前 context 未覆盖全部文件，应拆分目录或提高受控扫描能力后重建。",
            "en": "The evidence folder exceeded the recursive file index limit; this context does not cover every file. Split the folder or rebuild with a controlled higher-capacity scanner.",
        })
    if (
        not folder_inventory["index_truncated"]
        and not folder_inventory["all_indexed_files_represented"]
    ):
        limitations.append({
            "severity": "medium",
            "zh": "至少一种同类材料超过每类处理上限；所有文件都已被目录索引发现，但部分文件只保留了 overflow 状态，需拆分后重建才能逐项分析。",
            "en": "At least one artifact type exceeded its per-type processing limit. Every file was discovered by the folder index, but some are represented only by an overflow status; split the folder and rebuild for per-file analysis.",
        })
    if folder_inventory["unhashed_files"]:
        limitations.append({
            "severity": "medium",
            "zh": "部分已索引文件因单文件或全目录默认哈希预算没有 SHA-256；需要强 provenance 时使用显式大文件哈希选项并评估时间/IO 成本。",
            "en": "Some indexed files have no SHA-256 because they exceeded the default per-file or folder hash budget. Use the explicit large-file hashing option when strong provenance is required and its time/I/O cost is acceptable.",
        })
    if folder_inventory["unclassified_files"]:
        limitations.append({
            "severity": "medium",
            "zh": "目录中存在无法按内容签名分类的文件；它们仍保留在 artifact inventory 中，不能静默忽略，应结合问题背景决定是否人工查看或补充解析器。",
            "en": "Some folder files did not match supported content signatures. They remain in the artifact inventory and must not be silently ignored; use the case context to decide whether to inspect them or add a parser.",
        })
    if folder_inventory["skipped_symlinks"]:
        limitations.append({
            "severity": "medium",
            "zh": "递归扫描跳过了符号链接，避免无意读取证据目录之外的内容；如链接目标属于授权证据，请复制到目录内或显式传入。",
            "en": "The recursive scan skipped symbolic links to avoid reading outside the evidence folder. Copy authorized targets into the folder or pass them explicitly.",
        })
    if folder_inventory["unreadable_entries"]:
        limitations.append({
            "severity": "high",
            "zh": "递归扫描遇到不可读目录或文件；这些内容没有进入当前 context，应先修复授权或由 QA 提供可读副本。",
            "en": "The recursive scan encountered unreadable files or directories. They are absent from this context; fix access or obtain readable copies from QA.",
        })
    limitations.extend(analysis_history["limitations"])

    evidence_location = {
        "root_id": root_path.name,
        "path_policy": "absolute-local" if include_local_paths else "relative-or-redacted",
    }
    if include_local_paths:
        evidence_location["root"] = str(root_path)

    return {
        "schema_version": SCHEMA_VERSION,
        "context_type": "android-memory-ai-context",
        "generator": {
            "name": RUNTIME_NAME,
            "version": RUNTIME_VERSION,
        },
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "request": {
            "intent": resolved_intent,
            "intent_source": _intent_source(
                intent,
                bool(question_candidates),
                bool(evidence_candidates),
                primary_from_evidence,
            ),
            "intent_candidates": candidates,
            "evaluated_intents": evaluated_intents,
            "question": question,
            "analysis_mode": analysis_history["mode"],
            "analysis_mode_source": analysis_history["mode_source"],
        },
        "subject": subject,
        "subject_candidates": context_candidates,
        "evidence": {
            **evidence_location,
            "folder_inventory": folder_inventory,
            "artifacts": serialized_artifacts,
            "coverage": coverage.to_dict(),
            "intent_coverage": {
                evaluated_intent: intent_coverage.to_dict()
                for evaluated_intent, intent_coverage in coverage_by_intent.items()
            },
            "conflicts": [conflict.to_dict() for conflict in conflicts],
            "derived_reports": reports,
            "accounting_ledger": accounting_ledger,
            "qa_observations": qa_observations,
            "analysis_history": analysis_history,
        },
        "knowledge": {
            "catalog_id": catalog["catalog_id"],
            "catalog_version": catalog.get("catalog_version"),
            "generated_from": catalog["generated_from"],
            "records": knowledge,
        },
        "analysis_contract": {
            "support_level": combined_support_level,
            "primary_intent_support_level": coverage.level,
            "rules": ANALYSIS_RULES,
            "privacy": {
                "raw_contents_embedded": False,
                "local_paths_included": include_local_paths,
                "policy_zh": "上下文不嵌入原始 HPROF、trace、截图像素或日志正文；日志只保留有界信号、行号与行哈希。向外部 AI 发送原始文件前必须单独做授权与隐私审查。",
                "policy_en": "The context embeds no raw HPROF, trace, screenshot pixels, or log lines; logs expose only bounded signals, line numbers, and line hashes. Review authorization and privacy before sending raw artifacts to an external AI.",
            },
        },
        "next_evidence": [gap.to_dict() for gap in gaps],
        "limitations": limitations,
    }


def _serialize_artifact(
    artifact: ArtifactEvidence,
    include_local_paths: bool,
) -> Dict[str, Any]:
    serialized = artifact.to_dict()
    if include_local_paths and artifact.local_path:
        serialized["path"] = artifact.local_path
    return serialized


def _build_accounting_ledger(
    artifacts: List[ArtifactEvidence],
) -> Optional[Dict[str, Any]]:
    meminfo_artifacts = [
        artifact
        for artifact in artifacts
        if artifact.artifact_type == "meminfo"
        and artifact.status == "ok"
        and artifact.local_path
    ]
    smaps_artifacts = [
        artifact
        for artifact in artifacts
        if artifact.artifact_type == "smaps"
        and artifact.status == "ok"
        and artifact.local_path
    ]
    if not meminfo_artifacts:
        return None
    if len(meminfo_artifacts) != 1:
        return {
            "status": "ambiguous",
            "reason": "multiple-meminfo-artifacts-require-explicit-phase-pairing",
            "meminfo_artifact_ids": [
                artifact.artifact_id for artifact in meminfo_artifacts
            ],
            "smaps_artifact_ids": [
                artifact.artifact_id for artifact in smaps_artifacts
            ],
        }
    if len(smaps_artifacts) > 1:
        return {
            "status": "ambiguous",
            "reason": "multiple-smaps-artifacts-require-explicit-phase-pairing",
            "meminfo_artifact_ids": [
                meminfo_artifacts[0].artifact_id
            ],
            "smaps_artifact_ids": [
                artifact.artifact_id for artifact in smaps_artifacts
            ],
        }

    meminfo = meminfo_artifacts[0]
    smaps = smaps_artifacts[0] if smaps_artifacts else None
    try:
        ledger = build_accounting_ledger_from_files(
            meminfo.local_path,
            smaps.local_path if smaps else None,
            source_artifacts={
                "meminfo": meminfo.artifact_id,
                **({"smaps": smaps.artifact_id} if smaps else {}),
            },
            include_top_mappings=False,
        )
        return ledger
    except (OSError, ValueError) as error:
        return {
            "status": "invalid",
            "reason": "accounting-ledger-build-failed",
            "error": str(error),
            "meminfo_artifact_ids": [meminfo.artifact_id],
            "smaps_artifact_ids": [smaps.artifact_id] if smaps else [],
        }


def _build_qa_observations(artifacts: List[Dict[str, Any]]) -> Dict[str, Any]:
    logs = []
    screenshots = []
    for artifact in artifacts:
        if artifact.get("status") != "ok":
            continue
        metadata = artifact.get("metadata", {})
        if artifact.get("artifact_type") == "android_log":
            scan = metadata.get("log_scan", {})
            logs.append({
                "artifact_id": artifact["artifact_id"],
                "path": artifact.get("path"),
                "bytes_scanned": scan.get("bytes_scanned"),
                "compression": scan.get("compression"),
                "scan_truncated": scan.get("scan_truncated", False),
                "archive_members_scanned": scan.get("archive_members_scanned"),
                "archive_members_examined": scan.get("archive_members_examined"),
                "archive_members_skipped": scan.get("archive_members_skipped"),
                "memory_signal_matches": scan.get("memory_signal_matches", 0),
                "managed_owner_path_candidate": scan.get(
                    "managed_owner_path_candidate", False
                ),
                "signals": scan.get("signals", []),
            })
        elif artifact.get("artifact_type") == "qa_screenshot":
            screenshots.append({
                "artifact_id": artifact["artifact_id"],
                "path": artifact.get("path"),
                "image": metadata.get("image", {}),
                "visual_review_required": True,
                "ocr_performed": False,
            })
    return {
        "android_logs": logs,
        "screenshots": screenshots,
        "raw_log_lines_embedded": False,
        "screenshot_pixels_embedded": False,
    }


def _infer_evidence_intents(
    artifacts: Iterable[ArtifactEvidence],
    available: Iterable[str],
) -> List[str]:
    available_types = set(available)
    signal_types = {
        signal.get("signal_type")
        for artifact in artifacts
        if artifact.status == "ok" and artifact.artifact_type == "android_log"
        for signal in artifact.metadata.get("log_scan", {}).get("signals", [])
    }
    intents = []
    if "hprof" in available_types or signal_types.intersection({
        "leakcanary-retained-object",
        "android-component-leak",
        "strictmode-resource-leak",
    }):
        intents.append("java-leak")
    if "native_heap_profile" in available_types or signal_types.intersection({
        "native-allocation-failure",
        "jni-reference-table-overflow",
    }):
        intents.append("native-memory")
    if "graphics-allocation-failure" in signal_types:
        intents.append("graphics")
    if signal_types.intersection({"lmkd-kill", "kernel-oom-kill"}):
        intents.append("system-pressure")
    if "comparison_report" in available_types:
        intents.append("regression")
    return intents


def _intent_source(
    requested_intent: str,
    question_inferred: bool,
    evidence_inferred: bool,
    primary_from_evidence: bool,
) -> str:
    if requested_intent != "auto":
        return "explicit"
    if primary_from_evidence:
        return "evidence"
    if question_inferred and evidence_inferred:
        return "question-and-evidence"
    if question_inferred:
        return "question"
    return "default"


def _combined_support_level(coverages: Iterable[EvidenceCoverage]) -> str:
    order = {"insufficient": 0, "limited": 1, "supported": 2, "strong": 3}
    return min((coverage.level for coverage in coverages), key=order.__getitem__)


def _merge_gaps(coverages: Iterable[EvidenceCoverage]) -> List[EvidenceGap]:
    priority_order = {"required": 0, "one-of": 1, "supporting": 2}
    merged = {}
    for coverage in coverages:
        for gap in build_gaps(coverage):
            current = merged.get(gap.artifact_type)
            if (
                current is None
                or priority_order[gap.priority] < priority_order[current.priority]
            ):
                merged[gap.artifact_type] = gap
    return list(merged.values())


def _select_knowledge(
    catalog: Dict[str, Any],
    intents: List[str],
    available: List[str],
) -> List[Dict[str, Any]]:
    selected = {}
    for intent in intents:
        for record in select_records(catalog, intent, available):
            selected.setdefault(record["id"], record)
    return list(selected.values())


def _report_subject_conflicts(
    subject: Dict[str, Any],
    reports: List[Dict[str, Any]],
) -> List[EvidenceConflict]:
    conflicts = []
    subject_package = subject.get("package")
    if not subject_package:
        return conflicts
    for report in reports:
        report_package = report.get("summary", {}).get("package_name")
        if report_package and report_package != subject_package:
            conflicts.append(
                EvidenceConflict(
                    field="package",
                    values={
                        "subject": subject_package,
                        "report:{}".format(report["filename"]): report_package,
                    },
                    severity="warning",
                    explanation_zh="派生报告的包名与采集上下文不一致；报告可能来自其他进程、错误自动识别或混合数据集。",
                    explanation_en="The derived report package differs from capture context; it may represent another process, a detector error, or a mixed dataset.",
                )
            )
    return conflicts


def _build_limitations(
    support_level: str,
    unavailable_artifacts: List[Dict[str, Any]],
    conflicts: List[EvidenceConflict],
    reports: List[Dict[str, Any]],
) -> List[Dict[str, str]]:
    limitations = []
    if support_level == "insufficient":
        limitations.append({
            "severity": "high",
            "zh": "当前证据没有满足一个或多个已评估意图的最低要求，不能给出确定根因或直接修改方案。",
            "en": "Current evidence does not meet one or more evaluated intent contracts; do not claim a root cause or direct code fix.",
        })
    elif support_level == "limited":
        limitations.append({
            "severity": "medium",
            "zh": "核心证据存在但支持证据不足，结论必须保留替代解释。",
            "en": "Core evidence exists but supporting evidence is sparse; preserve alternative explanations.",
        })
    high_risk_statuses = {
        artifact.get("status")
        for artifact in unavailable_artifacts
        if artifact.get("status") in {
            "empty",
            "invalid",
            "permission_denied",
            "command_failed",
            "unreadable",
        }
    }
    unavailable_statuses = {
        artifact.get("status")
        for artifact in unavailable_artifacts
        if artifact.get("status") in {
            "skipped",
            "not_applicable",
            "not_collected",
            "not_supported",
        }
    }
    if high_risk_statuses:
        limitations.append(
            {
                "severity": "high",
                "zh": (
                    "一个或多个输入为空、无权限、命令失败、不可读或格式不匹配；"
                    "不能把文件名当成有效证据。状态：{}。"
                ).format(", ".join(sorted(high_risk_statuses))),
                "en": (
                    "One or more inputs are empty, denied, command-failed, unreadable, "
                    "or malformed; filenames are not proof of valid evidence. Statuses: {}."
                ).format(", ".join(sorted(high_risk_statuses))),
            }
        )
    if unavailable_statuses:
        limitations.append(
            {
                "severity": "medium",
                "zh": (
                    "采集清单记录了未采集、跳过、不适用或不支持的证据；"
                    "这不代表对应内存分类不存在。状态：{}。"
                ).format(", ".join(sorted(unavailable_statuses))),
                "en": (
                    "The capture manifest records evidence as not collected, skipped, "
                    "not applicable, or unsupported; that does not mean the memory "
                    "category is absent. Statuses: {}."
                ).format(", ".join(sorted(unavailable_statuses))),
            }
        )
    if conflicts:
        limitations.append({
            "severity": "high",
            "zh": "上下文存在来源冲突；确认目标 package/PID/phase 前不要合并数字。",
            "en": "Sources conflict; do not merge values until package, PID, and phase identity are confirmed.",
        })
    if reports:
        limitations.append({
            "severity": "medium",
            "zh": "派生报告只作为导航；关键结论仍需回到带哈希的原始证据。",
            "en": "Derived reports are navigation aids; important claims must return to hashed raw evidence.",
        })
    return limitations
