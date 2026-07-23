"""Render the canonical AI context as JSON or a compact Markdown report."""

import json
from typing import Any, Dict, Iterable, List

from tools.accounting_ledger import render_ledger_markdown


def render_json(context: Dict[str, Any], indent: int = 2) -> str:
    return json.dumps(context, ensure_ascii=False, indent=indent, sort_keys=False) + "\n"


def render_markdown(context: Dict[str, Any], language: str = "zh") -> str:
    if language not in ("zh", "en"):
        raise ValueError("language must be zh or en")
    zh = language == "zh"
    lines: List[str] = []
    lines.append("# Android 内存 AI 证据上下文" if zh else "# Android Memory AI Evidence Context")
    lines.append("")
    lines.append("- Schema: `{}`".format(context["schema_version"]))
    lines.append("- {}: `{}`".format("分析意图" if zh else "Intent", context["request"]["intent"]))
    lines.append("- {}: `{}`".format(
        "证据支持级别" if zh else "Evidence support",
        context["analysis_contract"]["support_level"],
    ))
    if context["request"].get("question"):
        lines.append("- {}: {}".format("问题" if zh else "Question", context["request"]["question"]))

    lines.extend(["", "## {}".format("目标上下文" if zh else "Subject Context"), ""])
    subject = context.get("subject", {})
    if subject:
        for key, value in subject.items():
            lines.append("- `{}`: `{}`".format(key, _escape(value)))
    else:
        lines.append("- {}".format(
            "未识别；需要补充 package/PID/设备信息。"
            if zh else "Not identified; add package, PID, and device context."
        ))

    accounting_ledger = context["evidence"].get("accounting_ledger")
    if accounting_ledger and accounting_ledger.get("status") == "available":
        lines.extend([
            "",
            render_ledger_markdown(
                accounting_ledger,
                language=language,
                heading_level=2,
            ),
        ])
    elif accounting_ledger:
        lines.extend([
            "",
            "## {}".format(
                "meminfo/smaps 逐行对账"
                if zh else
                "meminfo/smaps Row Reconciliation"
            ),
            "",
            "- `{}`: `{}`".format(
                accounting_ledger.get("status", "unknown"),
                accounting_ledger.get("reason", "unspecified"),
            ),
        ])

    lines.extend(["", "## {}".format("证据清单" if zh else "Evidence Inventory"), ""])
    evidence = context["evidence"]
    lines.append("- {}: `{}`".format(
        "路径策略" if zh else "Path policy",
        evidence.get("path_policy", "unspecified"),
    ))
    lines.append("- {}: `{}`".format(
        "证据根标识" if zh else "Evidence root ID",
        evidence.get("root_id", "unknown"),
    ))
    if evidence.get("root"):
        lines.append("- {}: `{}`".format(
            "本地证据根" if zh else "Local evidence root",
            _escape(evidence["root"]),
        ))
    folder = evidence.get("folder_inventory", {})
    if folder:
        lines.append("- {}: `{}` / `{}`".format(
            "递归索引文件" if zh else "Recursively indexed files",
            folder.get("indexed_files", 0),
            folder.get("total_files", 0),
        ))
        lines.append("- {}: `{}`".format(
            "目录索引截断" if zh else "Folder index truncated",
            folder.get("index_truncated", False),
        ))
        lines.append("- {}: `{}`".format(
            "未分类文件" if zh else "Unclassified files",
            folder.get("unclassified_files", 0),
        ))
        lines.append("- {}: `{}` / `{}`".format(
            "已表示/已索引文件" if zh else "Represented/indexed files",
            folder.get("represented_paths", 0),
            folder.get("indexed_files", 0),
        ))
        lines.append("- {}: `{}`".format(
            "未哈希文件" if zh else "Unhashed files",
            folder.get("unhashed_files", 0),
        ))
        lines.append("- {}: `{}` / `{}`".format(
            "跳过符号链接/不可读条目" if zh else "Skipped symlinks/unreadable entries",
            folder.get("skipped_symlinks", 0),
            folder.get("unreadable_entries", 0),
        ))
    lines.append("")
    lines.append("| Type | Status | Domain | Perturbation | Path |")
    lines.append("|------|--------|--------|--------------|------|")
    for artifact in context["evidence"]["artifacts"]:
        lines.append("| `{}` | `{}` | `{}` | `{}` | {} |".format(
            artifact["artifact_type"],
            artifact["status"],
            artifact["accounting_domain"],
            artifact["perturbation"],
            _escape(artifact.get("path", "—")),
        ))

    qa = evidence.get("qa_observations", {})
    qa_logs = qa.get("android_logs", [])
    qa_screenshots = qa.get("screenshots", [])
    if qa_logs or qa_screenshots:
        lines.extend(["", "## {}".format("QA 日志与截图" if zh else "QA Logs and Screenshots"), ""])
    for log in qa_logs:
        lines.append("### `{}` · {}".format(
            log["artifact_id"],
            _escape(log.get("path", "—")),
        ))
        lines.append("")
        lines.append("- {}: `{}`".format(
            "内存信号匹配" if zh else "Memory signal matches",
            log.get("memory_signal_matches", 0),
        ))
        lines.append("- {}: `{}`".format(
            "扫描被截断" if zh else "Scan truncated",
            log.get("scan_truncated", False),
        ))
        for signal in log.get("signals", []):
            line_numbers = [sample["line_number"] for sample in signal.get("samples", [])]
            lines.append("- `{}` · `{}` · count `{}` · {} {}".format(
                signal["signal_type"],
                signal["strength"],
                signal["count"],
                "行" if zh else "lines",
                ", ".join(str(value) for value in line_numbers) or "—",
            ))
            lines.append("  - {}: {}".format(
                "不能证明" if zh else "Does not prove",
                signal["does_not_prove"],
            ))
    if qa_screenshots:
        lines.append("")
        lines.append("| Screenshot | Format | Dimensions | Review |")
        lines.append("|------------|--------|------------|--------|")
        for screenshot in qa_screenshots:
            image = screenshot.get("image", {})
            dimensions = "{}x{}".format(image.get("width", "?"), image.get("height", "?"))
            lines.append("| {} | `{}` | `{}` | {} |".format(
                _escape(screenshot.get("path", screenshot["artifact_id"])),
                image.get("format", "unknown"),
                dimensions,
                "必须查看可见区域" if zh else "inspect visible region",
            ))

    history = evidence.get("analysis_history", {})
    if history and (
        history.get("has_prior_analysis")
        or history.get("mode") != "initial"
    ):
        lines.extend(["", "## {}".format(
            "二次分析与历史" if zh else "Analysis Iteration and History"
        ), ""])
        lines.append("- {}: `{}` (`{}`)".format(
            "分析模式" if zh else "Analysis mode",
            history.get("mode", "unknown"),
            history.get("mode_source", "unknown"),
        ))
        lines.append("- {}: `{}` / `{}`".format(
            "旧 context / 旧结论报告" if zh else "Prior contexts / conclusion reports",
            len(history.get("previous_contexts", [])),
            len(history.get("previous_analysis_reports", [])),
        ))
        identity = history.get("case_identity", {})
        lines.append("- {}: `{}`".format(
            "Case 身份可比性" if zh else "Case identity comparability",
            identity.get("status", "unknown"),
        ))
        if identity.get("differing_fields"):
            lines.append("- {}: {}".format(
                "身份差异字段" if zh else "Differing identity fields",
                ", ".join(
                    "`{}`".format(_escape(field))
                    for field in sorted(identity["differing_fields"])
                ),
            ))
        delta = history.get("evidence_delta", {})
        lines.append("- {}: `{}` / `{}` / `{}` / `{}`".format(
            "新增/变更/缺失/未变" if zh else "Added/changed/missing/unchanged",
            delta.get("added_count", 0),
            delta.get("changed_count", 0),
            delta.get("missing_since_previous_count", 0),
            delta.get("unchanged_by_fingerprint_count", 0),
        ))
        for label, key in (
            ("新增证据" if zh else "Added evidence", "added"),
            ("变更证据" if zh else "Changed evidence", "changed"),
            ("上次存在、当前缺失" if zh else "Missing since previous", "missing_since_previous"),
        ):
            paths = [item.get("path", "—") for item in delta.get(key, [])]
            if paths:
                lines.append("- {}: {}".format(
                    label,
                    ", ".join("`{}`".format(_escape(path)) for path in paths),
                ))
        if history.get("mode") == "initial":
            lines.append("- {}".format(
                "显式 initial 模式只盘点旧分析，不把它用作当前 baseline。"
                if zh else
                "Explicit initial mode inventories prior analysis without applying it as the current baseline."
            ))
        else:
            lines.append("- {}".format(
                "必须先阅读旧结论，并逐项标记 confirmed、revised、retracted、unresolved；新增结论单列。"
                if zh else
                "Read the prior conclusion first, then mark material claims confirmed, revised, retracted, or unresolved and list new claims separately."
            ))

    coverage = context["evidence"]["coverage"]
    lines.extend(["", "## {}".format("证据覆盖" if zh else "Evidence Coverage"), ""])
    lines.append("- {}: `{}`".format("级别" if zh else "Level", coverage["level"]))
    lines.append("- {}: {}".format(
        "理由" if zh else "Rationale",
        coverage["rationale_zh" if zh else "rationale_en"],
    ))
    lines.append("- {}: {}".format("已满足" if zh else "Available", _code_list(coverage["available"])))
    lines.append("- {}: {}".format(
        "缺少必需证据" if zh else "Missing required",
        _code_list(coverage["missing_required"]),
    ))
    lines.append("- {}: {}".format(
        "缺少支持证据" if zh else "Missing supporting",
        _code_list(coverage["missing_supporting"]),
    ))
    lines.append("- {}: {}".format(
        "未满足选一组" if zh else "Unsatisfied any-of groups",
        _group_list(coverage["missing_any_of"]),
    ))
    lines.append("- {}: {}".format(
        "内容不足" if zh else "Inadequate for intent",
        _code_list(coverage.get("inadequate", [])),
    ))
    intent_coverage = context["evidence"].get("intent_coverage", {})
    if len(intent_coverage) > 1:
        lines.append("")
        lines.append("| Intent | Level | Missing required | Inadequate |")
        lines.append("|--------|-------|------------------|------------|")
        for evaluated_intent, evaluated in intent_coverage.items():
            lines.append("| `{}` | `{}` | {} | {} |".format(
                evaluated_intent,
                evaluated["level"],
                _code_list(evaluated["missing_required"]),
                _code_list(evaluated.get("inadequate", [])),
            ))

    conflicts = context["evidence"].get("conflicts", [])
    if conflicts:
        lines.extend(["", "## {}".format("证据冲突" if zh else "Evidence Conflicts"), ""])
        for conflict in conflicts:
            lines.append("- **{}**: {} — `{}`".format(
                conflict["field"],
                conflict["explanation_zh" if zh else "explanation_en"],
                _escape(json.dumps(conflict["values"], ensure_ascii=False, sort_keys=True)),
            ))

    reports = context["evidence"].get("derived_reports", [])
    if reports:
        lines.extend(["", "## {}".format("派生分析摘要" if zh else "Derived Analysis Summaries"), ""])
        for report in reports:
            lines.append("### `{}` · `{}`".format(report["filename"], report["report_type"]))
            lines.append("")
            lines.append(("账本域：" if zh else "Accounting domains: ") + _code_list(report["accounting_domains"]))
            for limitation in report["limitations"]:
                lines.append("- {}".format(limitation))
            lines.extend([
                "",
                "```json",
                json.dumps(report["summary"], ensure_ascii=False, indent=2),
                "```",
            ])

    lines.extend(["", "## {}".format("下一步补证" if zh else "Next Evidence"), ""])
    gaps = context.get("next_evidence", [])
    if not gaps:
        lines.append("- {}".format(
            "当前意图定义的证据已齐全。" if zh else "The intent-defined evidence set is complete."
        ))
    for gap in gaps:
        lines.append("### `{}` · `{}`".format(gap["artifact_type"], gap["priority"]))
        lines.append("")
        lines.append(gap["reason_zh" if zh else "reason_en"])
        if gap.get("command"):
            lines.extend(["", "```bash", gap["command"], "```"])
        prereq = gap["prerequisites_zh" if zh else "prerequisites_en"]
        if prereq:
            lines.append("")
            lines.append(("前提：" if zh else "Prerequisites: ") + "; ".join(prereq))
        lines.append("")
        lines.append(("扰动：" if zh else "Perturbation: ") + "`{}`".format(gap["perturbation"]))
        alternatives = gap.get("alternatives", [])
        if alternatives:
            lines.append("")
            lines.append("{} {}".format(
                "替代入口：" if zh else "Alternatives:",
                "; ".join(alternatives),
            ))

    lines.extend(["", "## {}".format("相关理论边界" if zh else "Relevant Knowledge Boundaries"), ""])
    for record in context["knowledge"]["records"]:
        lines.append("### `{}` · {}".format(record["id"], record["title"][language]))
        lines.append("")
        lines.append(record["summary"][language])
        lines.append("")
        lines.append(("不能证明：" if zh else "Does not prove: ") + record["does_not_prove"][language])
        lines.append("")
        lines.append(("来源：" if zh else "Sources: ") + ", ".join(
            "[{}]({})".format(source["title"], source["url"])
            for source in record["sources"]
        ))
        lines.append("")

    lines.extend(["## {}".format("AI 分析契约" if zh else "AI Analysis Contract"), ""])
    for rule in context["analysis_contract"]["rules"]:
        lines.append("- `{}`: {}".format(rule["id"], rule["zh" if zh else "en"]))
    privacy = context["analysis_contract"]["privacy"]
    lines.extend(["", "- `privacy`: {}".format(privacy["policy_zh" if zh else "policy_en"])])

    if context.get("limitations"):
        lines.extend(["", "## {}".format("限制" if zh else "Limitations"), ""])
        for limitation in context["limitations"]:
            lines.append("- `{}`: {}".format(
                limitation["severity"], limitation["zh" if zh else "en"]
            ))
    return "\n".join(lines).rstrip() + "\n"


def _escape(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _code_list(values: Iterable[str]) -> str:
    items = list(values)
    return ", ".join("`{}`".format(value) for value in items) if items else "—"


def _group_list(groups: Iterable[Iterable[str]]) -> str:
    items = [" / ".join("`{}`".format(value) for value in group) for group in groups]
    return "; ".join(items) if items else "—"
