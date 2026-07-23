#!/usr/bin/env python3
"""Build and render a meminfo-first ledger supplemented by smaps evidence."""

import os
import sys
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.meminfo_parser import MeminfoData, MemoryCategory, parse_meminfo_file
from tools import smaps_parser


LEDGER_SCHEMA_VERSION = "1.0"


def build_accounting_ledger_from_files(
    meminfo_path: str,
    smaps_path: Optional[str] = None,
    source_artifacts: Optional[Dict[str, str]] = None,
    include_top_mappings: bool = True,
) -> Dict[str, Any]:
    """Parse raw files and return the canonical meminfo/smaps ledger."""
    meminfo_data = parse_meminfo_file(meminfo_path)
    smaps_data = (
        smaps_parser.parse_smaps_summary(smaps_path)
        if smaps_path
        else None
    )
    return build_accounting_ledger(
        meminfo_data,
        smaps_data,
        source_artifacts=source_artifacts,
        include_top_mappings=include_top_mappings,
    )


def build_accounting_ledger(
    meminfo_data: MeminfoData,
    smaps_data: Optional[Dict[str, Any]] = None,
    source_artifacts: Optional[Dict[str, str]] = None,
    include_top_mappings: bool = True,
) -> Dict[str, Any]:
    """
    Keep dumpsys meminfo as the primary Android accounting view.

    smaps values are attached only where the AOSP-style category is directly
    comparable. Driver/HAL memtrack rows remain meminfo-only and are used only
    in the explicitly labelled total reconciliation formula.
    """
    source_boundary = {
        "primary": "dumpsys-meminfo",
        "supplemental": "proc-pid-smaps" if smaps_data is not None else None,
        "policy_zh": "meminfo 保留 Android 熟悉的逐行分类；smaps 只补充同类进程页、SwapPss 和映射明细，不覆盖 meminfo。",
        "policy_en": "meminfo preserves Android's familiar row categories; smaps only supplements comparable process pages, SwapPss, and mapping detail without overwriting meminfo.",
    }
    if not meminfo_data.categories:
        return {
            "schema_version": LEDGER_SCHEMA_VERSION,
            "status": "unavailable",
            "reason": "meminfo-main-table-not-parsed",
            "view": "meminfo-primary-smaps-supplemental",
            "source_boundary": source_boundary,
            "source_artifacts": source_artifacts or {},
            "identity": {
                "package_name": meminfo_data.package_name,
                "pid": meminfo_data.pid,
            },
            "meminfo_columns": [],
        }

    main_mapping, detail_mapping = _row_type_mappings()
    by_type = {
        row["type_id"]: row for row in (smaps_data or {}).get("by_type", [])
    }
    by_subtype = {
        row["type_id"]: row for row in (smaps_data or {}).get("by_subtype", [])
    }
    total_pss = meminfo_data.total_pss or _category_value(
        meminfo_data.categories.get("TOTAL"),
        "pss_total",
    )

    rows = [
        _build_row(
            section="main",
            category=category,
            type_ids=main_mapping.get(name),
            smaps_rows=by_type,
            smaps_available=smaps_data is not None,
            total_pss_kb=total_pss,
            include_top_mappings=include_top_mappings,
        )
        for name, category in meminfo_data.categories.items()
    ]
    detail_rows = [
        _build_row(
            section="dalvik_details",
            category=category,
            type_ids=detail_mapping.get(name),
            smaps_rows=by_subtype,
            smaps_available=smaps_data is not None,
            total_pss_kb=total_pss,
            include_top_mappings=include_top_mappings,
        )
        for name, category in meminfo_data.dalvik_details.items()
    ]
    _attach_native_allocator_evidence(rows, smaps_data)

    external_rows = [
        row
        for row in rows
        if row["name"] != "TOTAL" and _is_memtrack_row(row["name"])
    ]
    external_pss_kb = sum(
        row["meminfo"]["pss_total_kb"] for row in external_rows
    )
    smaps_total_pss_kb = (
        (smaps_data or {}).get("total_pss_kb") if smaps_data else None
    )
    reconciled_total_kb = (
        smaps_total_pss_kb + external_pss_kb
        if smaps_total_pss_kb is not None
        else None
    )
    total_comparison = _compare_values(total_pss, reconciled_total_kb)
    if smaps_data is None:
        total_comparison.update({
            "status": "smaps-not-collected",
            "note_zh": "未提供 smaps，当前只展示 dumpsys meminfo 主账本。",
            "note_en": "smaps was not supplied; this ledger currently shows only the dumpsys meminfo primary view.",
        })
    else:
        total_comparison.update({
            "formula": "smaps_total_pss_kb + meminfo_memtrack_only_pss_kb",
            "smaps_total_pss_kb": smaps_total_pss_kb,
            "meminfo_memtrack_only_pss_kb": external_pss_kb,
            "reconciled_total_pss_kb": reconciled_total_kb,
            "note_zh": (
                "总量只按明确公式对账：smaps 进程页 PSS + meminfo 中 smaps 不可见的 mtrack 行；"
                "不把 HPROF、DMA-BUF 系统总量或其他账本相加。"
            ),
            "note_en": (
                "The total is reconciled only as smaps process-page PSS plus meminfo mtrack rows "
                "that smaps cannot see. HPROF, system DMA-BUF totals, and other ledgers are not added."
            ),
        })

    mapped_main_ids = {
        type_id
        for name in meminfo_data.categories
        for type_id in (main_mapping.get(name) or ())
    }
    unmapped_smaps_types = [
        _copy_smaps_row(row, include_top_mappings)
        for row in (smaps_data or {}).get("by_type", [])
        if row["type_id"] not in mapped_main_ids and row.get("pss_kb", 0) > 0
    ]

    return {
        "schema_version": LEDGER_SCHEMA_VERSION,
        "status": "available",
        "view": "meminfo-primary-smaps-supplemental",
        "source_boundary": source_boundary,
        "source_artifacts": source_artifacts or {},
        "identity": {
            "package_name": meminfo_data.package_name,
            "pid": meminfo_data.pid,
        },
        "meminfo_columns": list(meminfo_data.table_columns),
        "rows": rows,
        "dalvik_detail_rows": detail_rows,
        "total_reconciliation": total_comparison,
        "unmapped_smaps_types": unmapped_smaps_types,
    }


def _row_type_mappings():
    main = {
        "Native Heap": (smaps_parser.HEAP_NATIVE,),
        "Dalvik Heap": (smaps_parser.HEAP_DALVIK,),
        "Dalvik Other": (smaps_parser.HEAP_DALVIK_OTHER,),
        "Stack": (smaps_parser.HEAP_STACK,),
        "Cursor": (smaps_parser.HEAP_CURSOR,),
        "Ashmem": (smaps_parser.HEAP_ASHMEM,),
        "Gfx dev": (smaps_parser.HEAP_GL_DEV,),
        "Other dev": (smaps_parser.HEAP_UNKNOWN_DEV,),
        ".so mmap": (smaps_parser.HEAP_SO,),
        ".jar mmap": (smaps_parser.HEAP_JAR,),
        ".apk mmap": (smaps_parser.HEAP_APK,),
        ".ttf mmap": (smaps_parser.HEAP_TTF,),
        ".dex mmap": (smaps_parser.HEAP_DEX,),
        ".oat mmap": (smaps_parser.HEAP_OAT,),
        ".art mmap": (smaps_parser.HEAP_ART,),
        "Other mmap": (smaps_parser.HEAP_UNKNOWN_MAP,),
        "Unknown": (smaps_parser.HEAP_UNKNOWN,),
    }
    details = {
        ".Heap": (smaps_parser.HEAP_DALVIK_NORMAL,),
        ".LOS": (smaps_parser.HEAP_DALVIK_LARGE,),
        ".Zygote": (smaps_parser.HEAP_DALVIK_ZYGOTE,),
        ".NonMoving": (smaps_parser.HEAP_DALVIK_NON_MOVING,),
        ".LinearAlloc": (smaps_parser.HEAP_DALVIK_OTHER_LINEARALLOC,),
        ".GC": (smaps_parser.HEAP_DALVIK_OTHER_ACCOUNTING,),
        ".ZygoteJIT": (smaps_parser.HEAP_DALVIK_OTHER_ZYGOTE_CODE_CACHE,),
        ".AppJIT": (smaps_parser.HEAP_DALVIK_OTHER_APP_CODE_CACHE,),
        ".CompilerMetadata": (
            smaps_parser.HEAP_DALVIK_OTHER_COMPILER_METADATA,
        ),
        ".IndirectRef": (
            smaps_parser.HEAP_DALVIK_OTHER_INDIRECT_REFERENCE_TABLE,
        ),
        ".Boot vdex": (smaps_parser.HEAP_DEX_BOOT_VDEX,),
        ".App dex": (smaps_parser.HEAP_DEX_APP_DEX,),
        ".App vdex": (smaps_parser.HEAP_DEX_APP_VDEX,),
        ".App art": (smaps_parser.HEAP_ART_APP,),
        ".Boot art": (smaps_parser.HEAP_ART_BOOT,),
    }
    return main, details


def _build_row(
    section: str,
    category: MemoryCategory,
    type_ids: Optional[Sequence[int]],
    smaps_rows: Dict[int, Dict[str, Any]],
    smaps_available: bool,
    total_pss_kb: int,
    include_top_mappings: bool,
) -> Dict[str, Any]:
    meminfo = category.to_kb_dict()
    if category.name == "TOTAL":
        smaps = {
            "status": "see-total-reconciliation",
            "comparable": False,
        }
        comparison = {
            "status": "see-total-reconciliation",
            "basis": "explicit-total-formula",
        }
    elif _is_memtrack_row(category.name):
        smaps = {
            "status": "not-comparable",
            "comparable": False,
            "reason": "driver-hal-memtrack-is-not-a-proc-smaps-vma-category",
        }
        comparison = {
            "status": "not-comparable",
            "basis": "different-accounting-source",
        }
    elif not smaps_available:
        smaps = {"status": "not-collected", "comparable": False}
        comparison = {"status": "smaps-not-collected", "basis": None}
    elif not type_ids:
        smaps = {
            "status": "no-stable-category-mapping",
            "comparable": False,
        }
        comparison = {
            "status": "not-comparable",
            "basis": "no-stable-category-mapping",
        }
    else:
        matched_rows = [
            smaps_rows[type_id] for type_id in type_ids if type_id in smaps_rows
        ]
        smaps = _merge_smaps_rows(
            matched_rows,
            include_top_mappings=include_top_mappings,
        )
        smaps.update({
            "status": "available",
            "comparable": True,
            "matched_type_ids": list(type_ids),
        })
        comparison = _compare_values(
            category.pss_total,
            smaps["pss_kb"],
        )
        comparison["basis"] = "same-category-process-pages-pss"

    observations_zh, observations_en = _row_observations(
        category,
        smaps,
        comparison,
        total_pss_kb,
    )
    return {
        "section": section,
        "name": category.name,
        "meminfo": meminfo,
        "smaps": smaps,
        "comparison": comparison,
        "observations_zh": observations_zh,
        "observations_en": observations_en,
    }


def _merge_smaps_rows(
    rows: Iterable[Dict[str, Any]],
    include_top_mappings: bool,
) -> Dict[str, Any]:
    rows = list(rows)
    merged = {
        "pss_kb": sum(row.get("pss_kb", 0) for row in rows),
        "swap_pss_kb": sum(row.get("swap_pss_kb", 0) for row in rows),
        "mapping_count": sum(row.get("count", 0) for row in rows),
        "matched_types": [row.get("type") for row in rows],
    }
    if include_top_mappings:
        top_pss = [
            item
            for row in rows
            for item in row.get("top_pss_mappings", [])
        ]
        top_swap = [
            item
            for row in rows
            for item in row.get("top_swap_mappings", [])
        ]
        merged["top_pss_mappings"] = sorted(
            top_pss,
            key=lambda item: item.get("pss_kb", 0),
            reverse=True,
        )[:5]
        merged["top_swap_mappings"] = sorted(
            top_swap,
            key=lambda item: item.get("swap_pss_kb", 0),
            reverse=True,
        )[:5]
    return merged


def _attach_native_allocator_evidence(
    rows: List[Dict[str, Any]],
    smaps_data: Optional[Dict[str, Any]],
) -> None:
    """Attach the structured allocator partition to the Native Heap row."""
    if not smaps_data:
        return
    aggregates = smaps_data.get("aggregates", {})
    native_total = aggregates.get("native_heap_kb", 0)
    known = {
        "legacy_heap_pss_kb": aggregates.get("native_legacy_heap_kb", 0),
        "libc_malloc_pss_kb": aggregates.get("native_libc_malloc_kb", 0),
        "scudo_pss_kb": aggregates.get("native_scudo_kb", 0),
        "gwp_asan_pss_kb": aggregates.get("native_gwp_asan_kb", 0),
    }
    if native_total <= 0 and not any(known.values()):
        return
    breakdown = {
        "native_total_pss_kb": native_total,
        **known,
        "other_native_pss_kb": max(native_total - sum(known.values()), 0),
    }
    native_row = next(
        (row for row in rows if row["name"] == "Native Heap"),
        None,
    )
    if not native_row:
        return
    native_row["smaps"]["allocator_breakdown"] = breakdown
    visible = [
        "{} {} kB".format(label, breakdown[key])
        for key, label in (
            ("scudo_pss_kb", "Scudo"),
            ("libc_malloc_pss_kb", "libc_malloc"),
            ("legacy_heap_pss_kb", "[heap]/[anon:native]"),
            ("gwp_asan_pss_kb", "GWP-ASan"),
            ("other_native_pss_kb", "other"),
        )
        if breakdown[key] > 0
    ]
    if visible:
        native_row["observations_zh"].append(
            "smaps Native allocator 分解为 {}。".format(
                "、".join(visible)
            )
        )
        native_row["observations_en"].append(
            "smaps Native allocator breakdown: {}.".format(
                ", ".join(visible)
            )
        )


def _copy_smaps_row(
    row: Dict[str, Any],
    include_top_mappings: bool,
) -> Dict[str, Any]:
    copied = {
        key: value
        for key, value in row.items()
        if include_top_mappings or not key.startswith("top_")
    }
    return copied


def _compare_values(
    meminfo_pss_kb: Optional[int],
    smaps_pss_kb: Optional[int],
) -> Dict[str, Any]:
    if meminfo_pss_kb is None or smaps_pss_kb is None:
        return {
            "status": "not-comparable",
            "delta_kb": None,
            "delta_percent": None,
        }
    delta_kb = meminfo_pss_kb - smaps_pss_kb
    denominator = max(meminfo_pss_kb, smaps_pss_kb, 1)
    delta_percent = abs(delta_kb) / denominator * 100
    tolerance_kb = max(1024, int(denominator * 0.05))
    return {
        "status": "aligned" if abs(delta_kb) <= tolerance_kb else "different",
        "delta_kb": delta_kb,
        "delta_percent": round(delta_percent, 2),
        "tolerance_kb": tolerance_kb,
    }


def _row_observations(
    category: MemoryCategory,
    smaps: Dict[str, Any],
    comparison: Dict[str, Any],
    total_pss_kb: int,
) -> Tuple[List[str], List[str]]:
    zh = []
    en = []
    if category.name != "TOTAL" and total_pss_kb > 0:
        share = category.pss_total / total_pss_kb * 100
        zh.append(
            "meminfo PSS 占 Total PSS 的 {:.1f}%。".format(share)
        )
        en.append(
            "meminfo PSS accounts for {:.1f}% of Total PSS.".format(share)
        )
    if category.pss_total > 0 and category.private_dirty > 0:
        ratio = category.private_dirty / category.pss_total * 100
        zh.append("Private Dirty / PSS 为 {:.1f}%。".format(ratio))
        en.append("Private Dirty / PSS is {:.1f}%.".format(ratio))
    if category.heap_size > 0:
        utilization = category.heap_alloc / category.heap_size * 100
        zh.append(
            "Heap Alloc / Size 为 {:.1f}%，Free 为 {} kB；这是运行时堆容量，不等同于驻留 PSS。".format(
                utilization,
                category.heap_free,
            )
        )
        en.append(
            "Heap Alloc / Size is {:.1f}% with {} kB free; runtime heap capacity is not resident PSS.".format(
                utilization,
                category.heap_free,
            )
        )
    if category.swap_pss > 0:
        zh.append("meminfo 记录 SwapPss {} kB。".format(category.swap_pss))
        en.append("meminfo records {} kB of SwapPss.".format(category.swap_pss))

    status = comparison.get("status")
    if status in ("aligned", "different"):
        zh.append(
            "同类 smaps PSS 为 {} kB，meminfo-smaps 差值为 {:+d} kB（{}）。".format(
                smaps.get("pss_kb", 0),
                comparison.get("delta_kb", 0),
                "口径接近" if status == "aligned" else "存在采集时点或分类差异",
            )
        )
        en.append(
            "Comparable smaps PSS is {} kB; meminfo minus smaps is {:+d} kB ({}).".format(
                smaps.get("pss_kb", 0),
                comparison.get("delta_kb", 0),
                "aligned" if status == "aligned" else "capture-time or classification difference",
            )
        )
    elif smaps.get("status") == "not-comparable":
        zh.append("该行来自 memtrack/驱动归因，不能强行与 /proc smaps VMA 相减。")
        en.append("This row comes from memtrack/driver attribution and must not be subtracted from /proc smaps VMAs.")
    elif smaps.get("status") == "not-collected":
        zh.append("未采集 smaps，当前没有行级映射旁证。")
        en.append("smaps was not collected, so no row-level mapping evidence is available.")
    elif category.name != "TOTAL":
        zh.append("当前 smaps 分类没有该 meminfo 行的稳定一一映射。")
        en.append("The current smaps classifier has no stable one-to-one mapping for this meminfo row.")
    return zh, en


def _is_memtrack_row(name: str) -> bool:
    return "mtrack" in name.lower()


def _category_value(
    category: Optional[MemoryCategory],
    field_name: str,
) -> int:
    return getattr(category, field_name, 0) if category else 0


def render_ledger_markdown(
    ledger: Dict[str, Any],
    language: str = "zh",
    heading_level: int = 2,
) -> str:
    """Render the shared ledger without changing its accounting semantics."""
    zh = language == "zh"
    h = "#" * heading_level
    lines = [
        "{} {}".format(
            h,
            "meminfo 主账本 + smaps 逐行旁证"
            if zh
            else "meminfo Primary Ledger + smaps Row Evidence",
        ),
        "",
        ledger["source_boundary"]["policy_zh" if zh else "policy_en"],
        "",
        "| {} | meminfo PSS | Private Dirty | Private Clean | SwapPss | RSS | smaps PSS | smaps SwapPss | Δ | {} |".format(
            "分类" if zh else "Category",
            "状态" if zh else "Status",
        ),
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in ledger["rows"]:
        meminfo = row["meminfo"]
        smaps = row["smaps"]
        comparison = row["comparison"]
        lines.append(
            "| {} | {} | {} | {} | {} | {} | {} | {} | {} | `{}` |".format(
                _escape_markdown_cell(row["name"]),
                _kb(meminfo["pss_total_kb"]),
                _kb(meminfo["private_dirty_kb"]),
                _kb(meminfo["private_clean_kb"]),
                _kb(meminfo["swap_pss_kb"]),
                _kb(meminfo["rss_total_kb"]),
                _kb_or_dash(smaps.get("pss_kb")),
                _kb_or_dash(smaps.get("swap_pss_kb")),
                _signed_kb_or_dash(comparison.get("delta_kb")),
                comparison.get("status", smaps.get("status", "unknown")),
            )
        )

    lines.extend([
        "",
        "{} {}".format(
            "#" * (heading_level + 1),
            "逐行解释" if zh else "Row-by-row interpretation",
        ),
        "",
    ])
    observation_key = "observations_zh" if zh else "observations_en"
    for row in ledger["rows"]:
        lines.append("- **{}**: {}".format(
            _escape_markdown_cell(row["name"]),
            " ".join(row[observation_key]) or ("无附加说明。" if zh else "No additional note."),
        ))
        mappings = row["smaps"].get("top_pss_mappings", [])
        if mappings:
            rendered = ", ".join(
                "`{}` {} kB".format(
                    _escape_markdown_code(item["name"]),
                    item["pss_kb"],
                )
                for item in mappings[:3]
            )
            lines.append(
                "  - {}: {}".format(
                    "smaps TOP 映射" if zh else "smaps top mappings",
                    rendered,
                )
            )

    details = ledger.get("dalvik_detail_rows", [])
    if details:
        lines.extend([
            "",
            "{} Dalvik Details".format("#" * (heading_level + 1)),
            "",
            "| {} | meminfo PSS | smaps PSS | Δ | {} |".format(
                "分类" if zh else "Category",
                "状态" if zh else "Status",
            ),
            "|---|---:|---:|---:|---|",
        ])
        for row in details:
            lines.append(
                "| {} | {} | {} | {} | `{}` |".format(
                    _escape_markdown_cell(row["name"]),
                    _kb(row["meminfo"]["pss_total_kb"]),
                    _kb_or_dash(row["smaps"].get("pss_kb")),
                    _signed_kb_or_dash(row["comparison"].get("delta_kb")),
                    row["comparison"].get("status", "unknown"),
                )
            )

    total = ledger["total_reconciliation"]
    lines.extend([
        "",
        "{} {}".format(
            "#" * (heading_level + 1),
            "总量对账" if zh else "Total reconciliation",
        ),
        "",
        "- {}: `{}`".format(
            "状态" if zh else "Status",
            total["status"],
        ),
    ])
    if total.get("formula"):
        lines.extend([
            "- Formula: `{}`".format(total["formula"]),
            "- `smaps_total_pss_kb`: `{}`".format(total["smaps_total_pss_kb"]),
            "- `meminfo_memtrack_only_pss_kb`: `{}`".format(
                total["meminfo_memtrack_only_pss_kb"]
            ),
            "- `reconciled_total_pss_kb`: `{}`".format(
                total["reconciled_total_pss_kb"]
            ),
            "- `meminfo_minus_reconciled_kb`: `{:+d}`".format(
                total["delta_kb"]
            ),
        ])
    lines.append("")
    lines.append(total["note_zh" if zh else "note_en"])
    return "\n".join(lines).rstrip()


def render_ledger_text(
    ledger: Dict[str, Any],
    language: str = "zh",
) -> str:
    """Render a compact terminal view followed by an explanation for every row."""
    zh = language == "zh"
    lines = [
        "[ meminfo 主账本 + smaps 逐行旁证 ]"
        if zh
        else "[ meminfo Primary Ledger + smaps Row Evidence ]",
        ledger["source_boundary"]["policy_zh" if zh else "policy_en"],
        "",
        "{:<16} {:>10} {:>10} {:>9} {:>10} {:>10} {:>25}".format(
            "分类" if zh else "Category",
            "Mem PSS",
            "PrivDirty",
            "SwapPss",
            "smaps PSS",
            "Delta",
            "Status",
        ),
        "-" * 101,
    ]
    for row in ledger["rows"]:
        lines.append(
            "{:<16} {:>10} {:>10} {:>9} {:>10} {:>10} {:>25}".format(
                row["name"][:16],
                row["meminfo"]["pss_total_kb"],
                row["meminfo"]["private_dirty_kb"],
                row["meminfo"]["swap_pss_kb"],
                _plain_or_dash(row["smaps"].get("pss_kb")),
                _signed_plain_or_dash(row["comparison"].get("delta_kb")),
                row["comparison"].get("status", "unknown"),
            )
        )
    lines.extend([
        "",
        "逐行解释:" if zh else "Row-by-row interpretation:",
    ])
    observation_key = "observations_zh" if zh else "observations_en"
    for row in ledger["rows"]:
        lines.append("- {}: {}".format(
            row["name"],
            " ".join(row[observation_key]) or ("无附加说明。" if zh else "No additional note."),
        ))
        mappings = row["smaps"].get("top_pss_mappings", [])
        if mappings:
            lines.append(
                "  {}: {}".format(
                    "smaps TOP 映射" if zh else "smaps top mappings",
                    ", ".join(
                        "{} {} kB".format(item["name"], item["pss_kb"])
                        for item in mappings[:3]
                    ),
                )
            )
    total = ledger["total_reconciliation"]
    lines.extend([
        "",
        "总量对账:" if zh else "Total reconciliation:",
        "- status: {}".format(total["status"]),
    ])
    if total.get("formula"):
        lines.append(
            "- {} = {} + {} = {} kB; meminfo delta {:+d} kB".format(
                total["formula"],
                total["smaps_total_pss_kb"],
                total["meminfo_memtrack_only_pss_kb"],
                total["reconciled_total_pss_kb"],
                total["delta_kb"],
            )
        )
    lines.append(total["note_zh" if zh else "note_en"])
    return "\n".join(lines)


def _kb(value: int) -> str:
    return "{} kB".format(value)


def _kb_or_dash(value: Optional[int]) -> str:
    return _kb(value) if value is not None else "—"


def _signed_kb_or_dash(value: Optional[int]) -> str:
    return "{:+d} kB".format(value) if value is not None else "—"


def _plain_or_dash(value: Optional[int]) -> str:
    return str(value) if value is not None else "-"


def _signed_plain_or_dash(value: Optional[int]) -> str:
    return "{:+d}".format(value) if value is not None else "-"


def _escape_markdown_cell(value: str) -> str:
    return value.replace("|", "\\|")


def _escape_markdown_code(value: str) -> str:
    return value.replace("`", "\\`")
