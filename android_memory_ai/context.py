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
from .guidance import (
    assess_coverage,
    build_gaps,
    infer_intent,
    intent_inadequate_artifacts,
)


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
        "id": "fixes-need-verification",
        "zh": "代码修改必须说明 owner、机制、预期变化、回归风险、同场景 before/after/cooldown 验证和回滚条件。",
        "en": "Code changes must state owner, mechanism, expected change, regression risk, matching before/after/cooldown validation, and rollback conditions.",
    },
]


def build_ai_context(
    root: Path,
    intent: str = "auto",
    question: str = "",
    artifact_overrides: Optional[Dict[str, str]] = None,
    subject_overrides: Optional[Dict[str, Any]] = None,
    catalog_path: Optional[Path] = None,
    hash_large_files: bool = False,
    include_local_paths: bool = False,
) -> Dict[str, Any]:
    root_path = Path(root).expanduser().resolve()
    if not root_path.is_dir():
        raise ValueError(
            "dump directory does not exist or is not a directory: {}".format(
                root_path
            )
        )

    resolved_intent, candidates = infer_intent(intent, question)
    artifacts = discover_artifacts(
        root_path,
        overrides=artifact_overrides,
        hash_large_files=hash_large_files,
    )
    available = available_artifact_types(artifacts)
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
            "intent_source": "explicit" if intent != "auto" else "inferred",
            "intent_candidates": candidates,
            "evaluated_intents": evaluated_intents,
            "question": question,
        },
        "subject": subject,
        "subject_candidates": context_candidates,
        "evidence": {
            **evidence_location,
            "artifacts": serialized_artifacts,
            "coverage": coverage.to_dict(),
            "intent_coverage": {
                evaluated_intent: intent_coverage.to_dict()
                for evaluated_intent, intent_coverage in coverage_by_intent.items()
            },
            "conflicts": [conflict.to_dict() for conflict in conflicts],
            "derived_reports": reports,
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
                "policy_zh": "上下文不嵌入原始 HPROF、trace 或任意文件正文；向外部 AI 发送文件前必须单独做授权与隐私审查。",
                "policy_en": "The context embeds no raw HPROF, trace, or arbitrary file contents; review authorization and privacy before sending artifacts to an external AI.",
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
