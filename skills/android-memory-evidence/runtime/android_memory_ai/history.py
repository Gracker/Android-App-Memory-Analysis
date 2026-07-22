"""Recognize prior analysis artifacts and build a bounded iteration contract."""

import json
import math
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .contracts import ArtifactEvidence


MAX_PREVIOUS_CONTEXT_BYTES = 16 * 1024 * 1024
MAX_PREVIOUS_CONTEXTS = 8
MAX_PREVIOUS_ARTIFACTS = 4096
MAX_DELTA_ITEMS = 128
MAX_HISTORY_TEXT_CHARS = 2048
HISTORY_ARTIFACT_TYPES = {
    "previous_ai_context",
    "previous_analysis_report",
}
ANALYSIS_MODES = (
    "auto",
    "initial",
    "reanalysis",
    "supplement",
    "reanalysis-with-new-evidence",
)
SUBJECT_IDENTITY_FIELDS = (
    "package",
    "pid",
    "android_release",
    "android_sdk",
    "build_fingerprint",
    "page_size",
    "phase",
)
STABLE_IDENTITY_FIELDS = {
    "package",
    "android_sdk",
    "build_fingerprint",
}


def validate_previous_context(path: Path) -> Tuple[str, List[str], Dict[str, Any]]:
    size = path.stat().st_size
    if size > MAX_PREVIOUS_CONTEXT_BYTES:
        return "invalid", [
            "previous context exceeds the bounded history read limit"
        ], {"read_limit_bytes": MAX_PREVIOUS_CONTEXT_BYTES}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return "invalid", ["invalid previous AI context: {}".format(exc)], {}
    if not isinstance(data, dict) or data.get("context_type") != "android-memory-ai-context":
        return "invalid", ["JSON is not an android-memory-ai-context"], {}
    request = _as_dict(data.get("request"))
    analysis_contract = _as_dict(data.get("analysis_contract"))
    return "ok", ["recognized prior Android memory AI context"], {
        "schema_version": _bounded_scalar(data.get("schema_version")),
        "generated_at": _bounded_scalar(data.get("generated_at")),
        "generator": _summarize_generator(data.get("generator")),
        "previous_intent": _bounded_scalar(request.get("intent")),
        "previous_support_level": _bounded_scalar(
            analysis_contract.get("support_level")
        ),
        "raw_previous_context_embedded": False,
    }


def validate_previous_analysis_report(
    path: Path,
) -> Tuple[str, List[str], Dict[str, Any]]:
    if path.stat().st_size > MAX_PREVIOUS_CONTEXT_BYTES:
        return "invalid", [
            "previous analysis report exceeds the bounded history read limit"
        ], {"read_limit_bytes": MAX_PREVIOUS_CONTEXT_BYTES}
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return "unreadable", ["cannot read previous analysis report: {}".format(exc)], {}
    if not content.strip():
        return "empty", ["previous analysis report is empty"], {}

    report_format = "markdown-or-text"
    recognized = bool(
        re.search(
            r"(?im)^(?:#{1,4}\s*)?(?:bounded conclusion|analysis conclusion|conclusion|"
            r"observed|hypotheses|revision status|分析结论|结论|已观察|假设|"
            r"修订状态)\s*[:：]?\s*$",
            content[:256 * 1024],
        )
    )
    if path.suffix.lower() == ".json":
        try:
            data = json.loads(content)
        except ValueError:
            data = None
        if isinstance(data, dict) and data.get("record_type") == "android-memory-analysis-record":
            recognized = True
            report_format = "android-memory-analysis-record"
    if not recognized:
        return "invalid", [
            "file lacks a recognized prior-analysis record or conclusion heading"
        ], {}
    return "ok", ["recognized previous analysis report"], {
        "report_format": report_format,
        "manual_review_required": True,
        "raw_report_embedded": False,
    }


def build_analysis_history(
    artifacts: Sequence[ArtifactEvidence],
    serialized_artifacts: Sequence[Dict[str, Any]],
    question: str,
    requested_mode: str = "auto",
    folder_inventory: Optional[Dict[str, Any]] = None,
    current_subject: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if requested_mode not in ANALYSIS_MODES:
        raise ValueError("unsupported analysis mode: {}".format(requested_mode))
    all_previous_context_artifacts = [
        artifact
        for artifact in artifacts
        if artifact.artifact_type == "previous_ai_context"
        and artifact.status == "ok"
        and artifact.local_path
    ]
    all_previous_context_artifacts.sort(
        key=lambda artifact: str(artifact.metadata.get("generated_at") or ""),
        reverse=True,
    )
    previous_context_artifacts = all_previous_context_artifacts[
        :MAX_PREVIOUS_CONTEXTS
    ]
    previous_reports = [
        artifact
        for artifact in artifacts
        if artifact.artifact_type == "previous_analysis_report"
        and artifact.status == "ok"
    ]
    serialized_by_id = {
        item.get("artifact_id"): item
        for item in serialized_artifacts
        if isinstance(item, dict) and item.get("artifact_id")
    }

    contexts = []
    for artifact in previous_context_artifacts:
        loaded = _load_previous_context(Path(artifact.local_path))
        if loaded is None:
            continue
        display_path = serialized_by_id.get(artifact.artifact_id, {}).get(
            "path", artifact.path
        )
        contexts.append(
            _summarize_previous_context(artifact, loaded, display_path)
        )
    contexts.sort(
        key=lambda item: str(item.get("generated_at") or ""),
        reverse=True,
    )

    reports = [
        {
            "artifact_id": artifact.artifact_id,
            "path": serialized_by_id.get(artifact.artifact_id, {}).get(
                "path", artifact.path
            ),
            "sha256": artifact.sha256,
            "report_format": artifact.metadata.get("report_format"),
            "manual_review_required": True,
        }
        for artifact in previous_reports
    ]
    prior_declared = _request_declares_prior_analysis(question)
    follow_up_requested = prior_declared or requested_mode in {
        "reanalysis",
        "supplement",
        "reanalysis-with-new-evidence",
    }
    has_prior = bool(contexts or reports or follow_up_requested)
    baseline = contexts[0] if contexts else None
    candidate_delta = _build_evidence_delta(
        baseline,
        serialized_artifacts,
        folder_inventory or {},
    )
    mode, mode_source = _resolve_analysis_mode(
        requested_mode,
        question,
        has_prior,
        candidate_delta,
    )
    baseline_applied = bool(baseline and mode != "initial")
    delta = candidate_delta if baseline_applied else _build_evidence_delta(
        None,
        serialized_artifacts,
        folder_inventory or {},
    )
    identity = _compare_case_identity(
        baseline if baseline_applied else None,
        current_subject or {},
    )
    limitations = []
    if follow_up_requested and not contexts and not reports:
        limitations.append({
            "severity": "high",
            "zh": "用户要求二次分析，但目录中没有识别到旧 context 或旧分析报告；必须先检查当前会话历史，找不到时请用户提供旧结论，不能假装完成了结论对比。",
            "en": "The user requested a follow-up analysis, but no prior context or report was recognized in the folder. Inspect the current conversation history, or request the prior conclusion before claiming a conclusion delta.",
        })
    if len(all_previous_context_artifacts) > MAX_PREVIOUS_CONTEXTS:
        limitations.append({
            "severity": "medium",
            "zh": "旧 context 数量达到历史读取上限；当前只比较最新的有界集合。",
            "en": "The prior-context history limit was reached; only the newest bounded set was considered.",
        })
    if any(
        str(report.get("path") or "").startswith("<external>/")
        for report in reports
    ):
        limitations.append({
            "severity": "medium",
            "zh": "至少一份目录外旧分析报告的绝对路径已脱敏；消费 context 的 Agent 必须从当前任务参数取得原路径，或仅在同一授权机器上用 --include-local-paths 重建后再读取正文。",
            "en": "At least one external prior-analysis report path is redacted. The consuming agent needs the original task argument, or must rebuild with --include-local-paths on the same authorized machine, before reading that report.",
        })
    if baseline_applied and baseline and baseline.get("snapshot_truncated"):
        limitations.append({
            "severity": "high",
            "zh": "旧 context 的 artifact 数量超过历史快照上限；当前证据增量只与旧 context 的有界前缀比较，不能声称覆盖全部旧材料。",
            "en": "The prior context exceeded the history snapshot limit. The evidence delta compares only a bounded prefix and cannot claim coverage of every prior artifact.",
        })
    if identity["status"] == "different-case":
        limitations.append({
            "severity": "high",
            "zh": "旧 context 与当前材料的稳定 case 身份字段不一致；不能把它们当作同一问题的直接结论修订。",
            "en": "Stable case identity differs between the prior context and current evidence. Do not present them as a direct revision of the same case.",
        })
    elif identity["status"] == "requires-review":
        limitations.append({
            "severity": "medium",
            "zh": "旧 context 与当前材料的 PID、phase 或其他会话字段不同；必须解释可比性后才能沿用旧结论。",
            "en": "Session identity such as PID or phase differs between the prior context and current evidence. Establish comparability before carrying prior claims forward.",
        })
    elif baseline_applied and identity["status"] == "insufficient":
        limitations.append({
            "severity": "medium",
            "zh": "旧 context 与当前材料缺少可共同核对的 case 身份字段；证据增量可供导航，但不能独立证明属于同一目标/构建/场景。",
            "en": "The prior context and current evidence lack shared case identity fields. The delta can guide review but cannot prove they describe the same target, build, and scenario.",
        })

    public_contexts = [
        {key: value for key, value in context.items() if key != "snapshot"}
        for context in contexts
    ]
    return {
        "has_prior_analysis": has_prior,
        "prior_analysis_declared_by_request": prior_declared,
        "follow_up_requested": follow_up_requested,
        "mode": mode,
        "mode_source": mode_source,
        "baseline_applied": baseline_applied,
        "baseline_context_artifact_id": (
            baseline.get("artifact_id") if baseline_applied and baseline else None
        ),
        "previous_contexts": public_contexts,
        "previous_analysis_reports": reports,
        "case_identity": identity,
        "evidence_delta": delta,
        "limitations": limitations,
        "review_contract": _review_contract(mode),
    }


def _load_previous_context(path: Path) -> Optional[Dict[str, Any]]:
    try:
        if path.stat().st_size > MAX_PREVIOUS_CONTEXT_BYTES:
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("context_type") != "android-memory-ai-context":
        return None
    return data


def _summarize_previous_context(
    artifact: ArtifactEvidence,
    data: Dict[str, Any],
    display_path: Optional[str] = None,
) -> Dict[str, Any]:
    request = _as_dict(data.get("request"))
    evidence = _as_dict(data.get("evidence"))
    analysis_contract = _as_dict(data.get("analysis_contract"))
    all_previous_artifacts = evidence.get("artifacts")
    if not isinstance(all_previous_artifacts, list):
        all_previous_artifacts = []
    previous_artifacts = all_previous_artifacts[:MAX_PREVIOUS_ARTIFACTS]
    return {
        "artifact_id": artifact.artifact_id,
        "path": display_path if display_path is not None else artifact.path,
        "sha256": artifact.sha256,
        "schema_version": _bounded_scalar(data.get("schema_version")),
        "generated_at": _bounded_scalar(data.get("generated_at")),
        "generator": _summarize_generator(data.get("generator")),
        "request": {
            "intent": _bounded_scalar(request.get("intent")),
            "question": _bounded_scalar(request.get("question")),
        },
        "subject": _summarize_subject(data.get("subject")),
        "support_level": _bounded_scalar(analysis_contract.get("support_level")),
        "artifact_count": len(all_previous_artifacts),
        "snapshot_artifact_count": len(previous_artifacts),
        "snapshot_truncated": len(all_previous_artifacts) > len(previous_artifacts),
        "snapshot": _snapshot(previous_artifacts),
        "raw_context_embedded": False,
    }


def _build_evidence_delta(
    baseline: Optional[Dict[str, Any]],
    current_artifacts: Sequence[Dict[str, Any]],
    folder_inventory: Dict[str, Any],
) -> Dict[str, Any]:
    if not baseline:
        return {
            "status": "no-baseline-context",
            "added_count": 0,
            "changed_count": 0,
            "missing_since_previous_count": 0,
            "unchanged_by_fingerprint_count": 0,
            "added": [],
            "changed": [],
            "missing_since_previous": [],
            "item_limit": MAX_DELTA_ITEMS,
            "delta_lists_truncated": False,
            "limitations": [],
        }

    previous = baseline.get("snapshot", {})
    current = _snapshot(current_artifacts)
    previous_keys = set(previous)
    current_keys = set(current)
    added_keys = sorted(current_keys - previous_keys)
    missing_keys = sorted(previous_keys - current_keys)
    changed_keys = sorted(
        key
        for key in previous_keys.intersection(current_keys)
        if _fingerprint(previous[key]) != _fingerprint(current[key])
    )
    unchanged_count = len(previous_keys.intersection(current_keys)) - len(changed_keys)
    limitations = []
    if folder_inventory.get("index_truncated"):
        limitations.append(
            "Current folder indexing was truncated; missing-since-previous entries may be outside the current index rather than deleted."
        )
    if any(
        not item.get("sha256")
        for item in list(previous.values()) + list(current.values())
    ):
        limitations.append(
            "Some artifacts lack SHA-256; those comparisons fall back to type, status, and size metadata."
        )
    if baseline.get("snapshot_truncated"):
        limitations.append(
            "The prior artifact snapshot was truncated; added and unchanged counts cover only the bounded prior snapshot."
        )
    return {
        "status": "compared",
        "added_count": len(added_keys),
        "changed_count": len(changed_keys),
        "missing_since_previous_count": len(missing_keys),
        "unchanged_by_fingerprint_count": unchanged_count,
        "added": _bounded_items([current[key] for key in added_keys]),
        "changed": _bounded_items([
            {
                "path": current[key].get("path") or previous[key].get("path"),
                "artifact_type": current[key].get("artifact_type"),
                "before": previous[key],
                "after": current[key],
            }
            for key in changed_keys
        ]),
        "missing_since_previous": _bounded_items([
            previous[key] for key in missing_keys
        ]),
        "item_limit": MAX_DELTA_ITEMS,
        "delta_lists_truncated": any(
            len(items) > MAX_DELTA_ITEMS
            for items in (added_keys, changed_keys, missing_keys)
        ),
        "limitations": limitations,
    }


def _snapshot(artifacts: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        artifact_type = _bounded_scalar(artifact.get("artifact_type"))
        status = _bounded_scalar(artifact.get("status"))
        path = _bounded_scalar(artifact.get("path"))
        if (
            artifact_type in HISTORY_ARTIFACT_TYPES
            or status == "missing"
            or not path
        ):
            continue
        key = "{}\0{}".format(path, artifact_type)
        groups.setdefault(key, []).append({
            "artifact_id": _bounded_scalar(artifact.get("artifact_id")),
            "path": path,
            "artifact_type": artifact_type,
            "status": status,
            "size_bytes": _bounded_scalar(artifact.get("size_bytes")),
            "sha256": _bounded_scalar(artifact.get("sha256")),
        })
    snapshot = {}
    for key, items in groups.items():
        if len(items) == 1:
            snapshot[key] = items[0]
            continue
        items.sort(key=lambda item: (
            str(item.get("artifact_id") or ""),
            str(item.get("sha256") or ""),
            str(item.get("size_bytes") or ""),
        ))
        for index, item in enumerate(items):
            identity = item.get("artifact_id") or "duplicate-{}".format(index)
            duplicate_key = "{}\0{}\0{}".format(key, identity, index)
            snapshot[duplicate_key] = item
    return snapshot


def _compare_case_identity(
    baseline: Optional[Dict[str, Any]],
    current_subject: Dict[str, Any],
) -> Dict[str, Any]:
    if not baseline:
        return {
            "status": "no-baseline-context",
            "matching_fields": [],
            "differing_fields": {},
            "unknown_fields": list(SUBJECT_IDENTITY_FIELDS),
        }
    previous_subject = _summarize_subject(baseline.get("subject"))
    current = _summarize_subject(current_subject)
    matching = []
    differing = {}
    unknown = []
    for field in SUBJECT_IDENTITY_FIELDS:
        before = previous_subject.get(field)
        after = current.get(field)
        if before is None or after is None:
            unknown.append(field)
        elif str(before) == str(after):
            matching.append(field)
        else:
            differing[field] = {"before": before, "after": after}
    if any(field in STABLE_IDENTITY_FIELDS for field in differing):
        status = "different-case"
    elif differing:
        status = "requires-review"
    elif matching:
        status = "consistent-on-known-fields"
    else:
        status = "insufficient"
    return {
        "status": status,
        "matching_fields": matching,
        "differing_fields": differing,
        "unknown_fields": unknown,
    }


def _review_contract(mode: str) -> List[str]:
    if mode == "initial":
        return [
            "Treat discovered prior contexts and reports as inventory only; explicit initial mode does not apply them as a baseline."
        ]
    return [
        "Read the prior conclusion from the current conversation and every listed previous-analysis report before writing a follow-up conclusion.",
        "Treat prior conclusions as derived claims, never as raw evidence or ground truth.",
        "Revalidate prior claim bindings against the current artifact hashes and target/build/phase identity.",
        "Classify each material prior claim as confirmed, revised, retracted, or unresolved; list genuinely new claims separately.",
        "For reanalysis, rebuild the claim ledger from current evidence before comparing conclusions. For supplementation, carry a prior claim forward only after revalidating its unchanged evidence and case identity.",
    ]


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _bounded_scalar(value: Any, limit: int = MAX_HISTORY_TEXT_CHARS) -> Any:
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    text = str(value)
    if len(text) <= limit:
        return text
    return text[:limit] + "...[truncated]"


def _summarize_generator(value: Any) -> Dict[str, Any]:
    generator = _as_dict(value)
    return {
        key: _bounded_scalar(generator.get(key))
        for key in ("name", "version")
        if generator.get(key) is not None
    }


def _summarize_subject(value: Any) -> Dict[str, Any]:
    subject = _as_dict(value)
    return {
        key: _bounded_scalar(subject.get(key))
        for key in SUBJECT_IDENTITY_FIELDS
        if subject.get(key) is not None
    }


def _fingerprint(item: Dict[str, Any]) -> Tuple[Any, ...]:
    if item.get("sha256"):
        return ("sha256", item["sha256"], item.get("status"))
    return (
        "metadata",
        item.get("artifact_type"),
        item.get("status"),
        item.get("size_bytes"),
    )


def _bounded_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return items[:MAX_DELTA_ITEMS]


def _request_declares_prior_analysis(question: str) -> bool:
    normalized = (question or "").lower()
    return any(marker in normalized for marker in (
        "二次分析",
        "重新分析",
        "再分析",
        "重新看",
        "重新做",
        "重做分析",
        "不满意",
        "补充分析",
        "继续分析",
        "之前的分析",
        "上次分析",
        "在原结论",
        "reanaly",
        "analyze again",
        "previous analysis",
        "prior analysis",
        "supplement",
        "continue the analysis",
    ))


def _resolve_analysis_mode(
    requested_mode: str,
    question: str,
    has_prior: bool,
    evidence_delta: Dict[str, Any],
) -> Tuple[str, str]:
    if requested_mode != "auto":
        return requested_mode, "explicit"
    if not has_prior:
        return "initial", "default"
    normalized = (question or "").lower()
    reanalysis = any(marker in normalized for marker in (
        "不满意",
        "重新分析",
        "再分析",
        "重新看",
        "重新做",
        "重做分析",
        "从头分析",
        "质疑",
        "reanaly",
        "redo",
        "from scratch",
        "challenge the conclusion",
    ))
    supplement = any(marker in normalized for marker in (
        "补充",
        "新增",
        "又提供",
        "新材料",
        "继续分析",
        "在此基础",
        "在原结论",
        "supplement",
        "new evidence",
        "added files",
        "continue the analysis",
    ))
    material_delta = any(
        evidence_delta.get(field, 0) > 0
        for field in (
            "added_count",
            "changed_count",
            "missing_since_previous_count",
        )
    )
    if reanalysis and (supplement or material_delta):
        return (
            "reanalysis-with-new-evidence",
            "question-and-evidence-delta" if material_delta else "question",
        )
    if reanalysis:
        return "reanalysis", "question"
    if supplement:
        return "supplement", "question"
    if material_delta:
        return "supplement", "evidence-delta"
    return "clarification-required", "prior-analysis-detected"
