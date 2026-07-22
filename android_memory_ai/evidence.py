"""Discover, validate, and describe Android memory evidence without reading it wholesale."""

import gzip
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from .contracts import ArtifactEvidence, EvidenceConflict
from .history import (
    HISTORY_ARTIFACT_TYPES,
    validate_previous_analysis_report,
    validate_previous_context,
)
from .log_signals import scan_android_log


MAX_SNIFF_BYTES = 128 * 1024
MAX_DEFAULT_HASH_BYTES = 512 * 1024 * 1024
MAX_TOTAL_DEFAULT_HASH_BYTES = 1024 * 1024 * 1024
MAX_MULTIPLE_ARTIFACTS_PER_TYPE = 64

Validator = Callable[[Path], Tuple[str, List[str], Dict[str, Any]]]


@dataclass(frozen=True)
class ArtifactSpec:
    artifact_type: str
    filenames: Sequence[str]
    globs: Sequence[str]
    accounting_domain: str
    perturbation: str
    validator: Validator
    allow_multiple: bool = True


def _read_text(path: Path, limit: int = MAX_SNIFF_BYTES) -> str:
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        return handle.read(limit)


def _validate_markers(
    path: Path,
    marker_groups: Sequence[Sequence[str]],
    label: str,
) -> Tuple[str, List[str], Dict[str, Any]]:
    content = _read_text(path)
    lowered = content.lower()
    for group in marker_groups:
        if all(marker.lower() in lowered for marker in group):
            return "ok", ["{} markers recognized".format(label)], {}
    return "invalid", ["content does not look like {}".format(label)], {}


def _validate_nonempty_text(path: Path) -> Tuple[str, List[str], Dict[str, Any]]:
    content = _read_text(path)
    if not content.strip():
        return "empty", ["file is empty"], {}
    lowered = content.lower()
    if "permission denied" in lowered or "avc: denied" in lowered:
        return "permission_denied", ["artifact contains a permission-denied error"], {}
    if "not found" in lowered or "unknown command" in lowered:
        return "command_failed", ["artifact contains a command failure"], {}
    return "ok", ["non-empty text artifact"], {}


def _validate_meminfo(path: Path) -> Tuple[str, List[str], Dict[str, Any]]:
    status, messages, metadata = _validate_markers(
        path,
        [
            ("total pss", "app summary"),
            ("meminfo in pid", "total"),
            ("applications memory usage", "total"),
        ],
        "dumpsys meminfo",
    )
    if status == "ok":
        content = _read_text(path)
        match = re.search(r"MEMINFO\s+in\s+pid\s+(\d+)\s+\[([^\]]+)\]", content, re.I)
        if match:
            metadata.update({"pid": match.group(1), "package": match.group(2).strip()})
    return status, messages, metadata


def _validate_smaps(path: Path) -> Tuple[str, List[str], Dict[str, Any]]:
    content = _read_text(path)
    header_count = len(
        re.findall(r"(?m)^[0-9a-fA-F]+-[0-9a-fA-F]+\s+[rwxps-]{4}\s+", content)
    )
    if header_count and "Pss:" in content:
        return "ok", ["recognized smaps VMA headers and Pss fields"], {"sampled_vmas": header_count}
    return "invalid", ["content does not look like /proc/<pid>/smaps"], {}


def _validate_showmap(path: Path) -> Tuple[str, List[str], Dict[str, Any]]:
    return _validate_markers(
        path,
        [("pss", "rss"), ("virtual size", "private dirty")],
        "showmap output",
    )


def _validate_hprof(path: Path) -> Tuple[str, List[str], Dict[str, Any]]:
    try:
        with path.open("rb") as source:
            is_gzip = source.read(2) == b"\x1f\x8b"
        if is_gzip:
            with gzip.open(str(path), "rb") as handle:
                header = handle.read(64)
        else:
            with path.open("rb") as handle:
                header = handle.read(64)
    except (OSError, EOFError) as exc:
        return "invalid", ["cannot read HPROF header: {}".format(exc)], {}
    if header.startswith(b"JAVA PROFILE "):
        version = header.split(b"\x00", 1)[0].decode("ascii", errors="replace")
        return "ok", ["recognized HPROF header"], {"hprof_version": version}
    return "invalid", ["file does not start with a JAVA PROFILE header"], {}


def _validate_proc_meminfo(path: Path) -> Tuple[str, List[str], Dict[str, Any]]:
    return _validate_markers(
        path,
        [("MemTotal:", "MemFree:"), ("MemTotal:", "MemAvailable:")],
        "/proc/meminfo",
    )


def _validate_pressure(path: Path) -> Tuple[str, List[str], Dict[str, Any]]:
    return _validate_markers(
        path,
        [("some avg10=", "full avg10=")],
        "/proc/pressure/memory",
    )


def _validate_zram(path: Path) -> Tuple[str, List[str], Dict[str, Any]]:
    return _validate_markers(
        path,
        [("/proc/swaps",), ("mm_stat",), ("zram",)],
        "ZRAM/swap evidence",
    )


def _validate_gfxinfo(path: Path) -> Tuple[str, List[str], Dict[str, Any]]:
    return _validate_markers(
        path,
        [
            ("graphics info for pid",),
            ("janky frames",),
            ("profile data in ms",),
            ("view hierarchy",),
        ],
        "dumpsys gfxinfo",
    )


def _validate_dmabuf(path: Path) -> Tuple[str, List[str], Dict[str, Any]]:
    status, messages, metadata = _validate_nonempty_text(path)
    if status != "ok":
        return status, messages, metadata
    content = _read_text(path).lower()
    if "dma" in content or "size" in content or "inode" in content:
        return "ok", ["recognized non-empty DMA-BUF evidence"], {}
    return "invalid", ["non-empty file lacks recognizable DMA-BUF fields"], {}


def _validate_device_context(path: Path) -> Tuple[str, List[str], Dict[str, Any]]:
    if path.suffix.lower() == ".json":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return "invalid", ["invalid context JSON: {}".format(exc)], {}
        flattened = json.dumps(data, ensure_ascii=False).lower()
        if "fingerprint" in flattened or "android_sdk" in flattened or "api_level" in flattened:
            return "ok", ["device context fields recognized"], {}
        return "invalid", ["JSON lacks device identity fields"], {}
    content = _read_text(path)
    lowered = content.lower()
    markers = ("buildfingerprint", "build_fingerprint", "ro.build.fingerprint", "androidsdk")
    if any(marker in lowered for marker in markers):
        return "ok", ["device context fields recognized"], {}
    if path.name in ("build_fingerprint.txt", "android_sdk.txt", "getprop.txt") and content.strip():
        return "ok", ["standalone device context artifact"], {}
    return "invalid", ["file lacks recognizable device context"], {}


def _validate_phase_metadata(path: Path) -> Tuple[str, List[str], Dict[str, Any]]:
    content = _read_text(path)
    lowered = content.lower()
    markers = (
        "phase",
        "scenario",
        "loops",
        "cooldown",
        "cool_down",
        "case_id",
        "perturbation",
        "collection_mode",
        "timestamp",
        "captured_at",
        "package",
        "pid",
        "process_role",
        "user_profile",
        "current_user",
    )
    found = sorted(marker for marker in markers if marker in lowered)
    if found:
        canonical = set(found)
        if "cool_down" in canonical:
            canonical.add("cooldown")
        if "case_id" in canonical:
            canonical.add("scenario")
        if "captured_at" in canonical:
            canonical.add("timestamp")
        if "current_user" in canonical:
            canonical.add("user_profile")
        comparison_fields = {
            "timestamp",
            "package",
            "pid",
            "process_role",
            "user_profile",
            "scenario",
            "phase",
            "loops",
            "cooldown",
            "collection_mode",
            "perturbation",
        }
        comparison_context_complete = comparison_fields.issubset(canonical)
        messages = ["phase metadata recognized: {}".format(", ".join(found))]
        if not comparison_context_complete:
            messages.append(
                "comparison context incomplete; missing {}".format(
                    ", ".join(sorted(comparison_fields - canonical))
                )
            )
        return "ok", messages, {
            "fields": found,
            "comparison_context_complete": comparison_context_complete,
        }
    return "invalid", ["metadata lacks phase/scenario/loop/cooldown fields"], {}


def _validate_json_report(path: Path) -> Tuple[str, List[str], Dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return "invalid", ["invalid JSON report: {}".format(exc)], {}
    if not isinstance(data, dict):
        return "invalid", ["analysis report root must be an object"], {}
    keys = set(data)
    if "memory_overview" in keys:
        report_type = "panorama"
    elif {"summary", "native_memory"}.issubset(keys):
        report_type = "combined"
    elif "changes" in keys or "comparison" in keys or "diff" in path.name.lower():
        report_type = "comparison"
    else:
        return "invalid", ["JSON does not match a known analysis report"], {"keys": sorted(keys)}
    return "ok", ["recognized {} report".format(report_type)], {
        "report_type": report_type,
        "schema_version": data.get("schema_version", "unversioned"),
        "keys": sorted(keys),
    }


def _validate_perfetto(path: Path) -> Tuple[str, List[str], Dict[str, Any]]:
    if path.stat().st_size < 16:
        return "invalid", ["trace is too small to be a Perfetto artifact"], {}
    return "ok", ["non-empty trace artifact; semantic validation requires trace_processor"], {}


def _validate_android_log(path: Path) -> Tuple[str, List[str], Dict[str, Any]]:
    scan = scan_android_log(path)
    if not scan["text_content_recognized"]:
        return "invalid", ["file content appears binary rather than a text log"], {
            "log_scan": scan
        }
    matches = scan["memory_signal_matches"]
    message = "bounded Android log scan found {} memory signal matches".format(matches)
    if scan["scan_truncated"]:
        message += "; scan stopped at {} bytes".format(scan["scan_limit_bytes"])
    return "ok", [message], {"log_scan": scan}


def _validate_qa_screenshot(path: Path) -> Tuple[str, List[str], Dict[str, Any]]:
    with path.open("rb") as handle:
        header = handle.read(1024 * 1024)
    image = _image_metadata(header)
    if not image:
        return "invalid", ["file does not have a recognized PNG, JPEG, or WebP header"], {}
    dimensions = "{}x{}".format(image["width"], image["height"])
    return "ok", ["recognized {} screenshot ({})".format(image["format"], dimensions)], {
        "image": image,
        "visual_review_required": True,
        "ocr_performed": False,
    }


def _image_metadata(data: bytes) -> Optional[Dict[str, Any]]:
    if (
        data.startswith(b"\x89PNG\r\n\x1a\n")
        and len(data) >= 24
        and data[12:16] == b"IHDR"
    ):
        width = int.from_bytes(data[16:20], "big")
        height = int.from_bytes(data[20:24], "big")
        return _valid_dimensions("png", width, height)
    if data.startswith(b"\xff\xd8"):
        dimensions = _jpeg_dimensions(data)
        if dimensions:
            return _valid_dimensions("jpeg", dimensions[0], dimensions[1])
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        dimensions = _webp_dimensions(data)
        if dimensions:
            return _valid_dimensions("webp", dimensions[0], dimensions[1])
    return None


def _valid_dimensions(image_format: str, width: int, height: int) -> Optional[Dict[str, Any]]:
    if width <= 0 or height <= 0:
        return None
    return {"format": image_format, "width": width, "height": height}


def _jpeg_dimensions(data: bytes) -> Optional[Tuple[int, int]]:
    position = 2
    start_of_frame = {
        0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
        0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF,
    }
    while position + 4 <= len(data):
        if data[position] != 0xFF:
            position += 1
            continue
        marker = data[position + 1]
        position += 2
        if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
            continue
        segment_length = int.from_bytes(data[position:position + 2], "big")
        if segment_length < 2 or position + segment_length > len(data):
            return None
        if marker in start_of_frame and segment_length >= 7:
            height = int.from_bytes(data[position + 3:position + 5], "big")
            width = int.from_bytes(data[position + 5:position + 7], "big")
            return width, height
        position += segment_length
    return None


def _webp_dimensions(data: bytes) -> Optional[Tuple[int, int]]:
    if len(data) < 30:
        return None
    chunk = data[12:16]
    if chunk == b"VP8X":
        width = int.from_bytes(data[24:27], "little") + 1
        height = int.from_bytes(data[27:30], "little") + 1
        return width, height
    if chunk == b"VP8L" and len(data) >= 25 and data[20] == 0x2F:
        bits = int.from_bytes(data[21:25], "little")
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    if chunk == b"VP8 ":
        marker = data.find(b"\x9d\x01\x2a", 20)
        if marker >= 0 and marker + 7 <= len(data):
            width = int.from_bytes(data[marker + 3:marker + 5], "little") & 0x3FFF
            height = int.from_bytes(data[marker + 5:marker + 7], "little") & 0x3FFF
            return width, height
    return None


ARTIFACT_SPECS: Tuple[ArtifactSpec, ...] = (
    ArtifactSpec(
        "previous_ai_context",
        ("android-memory-context.json", "ai-context.json"),
        ("**/*android*memory*context*.json", "**/*ai-context*.json"),
        "analysis-history",
        "none",
        validate_previous_context,
    ),
    ArtifactSpec(
        "previous_analysis_report",
        (
            "android-memory-analysis.md",
            "memory-analysis.md",
            "analysis.md",
            "diagnosis.md",
        ),
        (
            "**/*memory*analysis*.md",
            "**/*diagnos*.md",
            "**/*分析*.md",
            "**/*结论*.md",
            "**/*memory*analysis*.json",
        ),
        "analysis-history",
        "none",
        validate_previous_analysis_report,
    ),
    ArtifactSpec("device_context", ("manifest.json", "meta.txt", "getprop.txt", "build_fingerprint.txt", "android_sdk.txt"), (), "capture-context", "none", _validate_device_context),
    ArtifactSpec("phase_metadata", ("run_config.json", "run_config.txt", "artifact-manifest.json", "artifact-manifest.tsv", "manifest.json", "notes.md"), (), "capture-context", "none", _validate_phase_metadata),
    ArtifactSpec("meminfo", ("meminfo.txt", "meminfo-local.txt", "meminfo_local.txt"), ("*meminfo*.txt",), "process-pages", "low-to-medium", _validate_meminfo),
    ArtifactSpec("smaps", ("smaps", "smaps.txt"), ("*smaps*.txt",), "process-pages", "low", _validate_smaps),
    ArtifactSpec("showmap", ("showmap.txt",), ("*showmap*.txt",), "process-pages", "low", _validate_showmap),
    ArtifactSpec("hprof", ("heap.hprof", "app.hprof", "heapdump.hprof", "heapdump_latest.hprof.gz"), ("*.hprof", "*.hprof.gz"), "object-graph", "high", _validate_hprof),
    ArtifactSpec("gfxinfo", ("gfxinfo.txt",), ("*gfxinfo*.txt",), "rendering", "low", _validate_gfxinfo),
    ArtifactSpec("proc_meminfo", ("proc_meminfo.txt", "proc-meminfo.txt"), ("*proc*meminfo*.txt",), "system-pages", "low", _validate_proc_meminfo),
    ArtifactSpec("pressure_memory", ("pressure_memory.txt", "pressure-memory.txt"), ("*pressure*memory*.txt",), "pressure-time", "low", _validate_pressure),
    ArtifactSpec("zram", ("zram_swap.txt", "proc_swaps.txt", "proc-swaps.txt"), ("*zram*.txt", "*swaps*.txt"), "swap", "low", _validate_zram),
    ArtifactSpec("dmabuf", ("dmabuf_debug.txt", "dmabuf.txt", "bufinfo.txt"), ("*dmabuf*.txt", "*dma_buf*.txt"), "cross-process-buffers", "low", _validate_dmabuf),
    ArtifactSpec("exit_info", ("exit_info.txt", "exit-info.txt"), ("*exit*info*.txt",), "process-exit", "low", _validate_nonempty_text),
    ArtifactSpec("memory_limiter_status", ("memory_limiter_status.txt", "memory-limiter-status.txt"), (), "device-policy", "low", _validate_nonempty_text),
    ArtifactSpec("native_heap_profile", (), ("*heap_profile*.perfetto-trace", "*heapprofd*.perfetto-trace"), "allocation-profile", "medium", _validate_perfetto),
    ArtifactSpec("perfetto_trace", ("trace.perfetto-trace", "trace.perfetto"), ("*.perfetto-trace", "*.perfetto"), "timeline", "medium", _validate_perfetto),
    ArtifactSpec("analysis_report", ("panorama_report.json", "panorama.json", "report.json", "combined.json"), ("*panorama*.json", "*combined*.json"), "derived-analysis", "none", _validate_json_report),
    ArtifactSpec("comparison_report", ("comparison.json", "diff_report.json", "diff.json"), ("*comparison*.json", "*diff*.json"), "derived-comparison", "none", _validate_json_report),
    ArtifactSpec(
        "android_log",
        ("logcat.txt", "logcat.log", "android.log", "leakcanary.txt"),
        (
            "**/*.log",
            "**/*.log.gz",
            "**/logcat*.txt",
            "**/logcat*.txt.gz",
            "**/*leakcanary*.txt",
            "**/*bugreport*.txt",
            "**/*bugreport*.zip",
            "**/*tombstone*.txt",
            "**/*anr*.txt",
        ),
        "diagnostic-log",
        "none-to-low",
        _validate_android_log,
        True,
    ),
    ArtifactSpec(
        "qa_screenshot",
        (),
        ("**/*.png", "**/*.jpg", "**/*.jpeg", "**/*.webp"),
        "qa-visual-observation",
        "none",
        _validate_qa_screenshot,
        True,
    ),
)


def discover_artifacts(
    root: Path,
    overrides: Optional[Dict[str, Any]] = None,
    hash_large_files: bool = False,
    folder_files: Optional[Sequence[Path]] = None,
) -> List[ArtifactEvidence]:
    root = root.resolve()
    override_map = overrides or {}
    if folder_files is None:
        from .folder_scan import scan_evidence_tree

        folder_files, _ = scan_evidence_tree(root)
    indexed_files = list(folder_files)
    artifacts = []
    deferred_paths = set()
    hash_state: Dict[str, Any] = {"hashed_bytes": 0, "digests": {}}
    for spec in ARTIFACT_SPECS:
        explicit_candidates = _override_candidates(
            override_map.get(spec.artifact_type, [])
        )
        discovered_candidates = _find_candidates(root, spec, indexed_files)
        if spec.allow_multiple:
            candidates, source_by_path = _merge_candidates(
                explicit_candidates, discovered_candidates
            )
            deferred_paths.update(
                candidate.resolve()
                for candidate in candidates[MAX_MULTIPLE_ARTIFACTS_PER_TYPE:]
            )
            if not candidates:
                artifacts.append(
                    _inspect_candidate(
                        root,
                        spec,
                        None,
                        "discovered",
                        hash_large_files,
                        hash_state=hash_state,
                    )
                )
                continue
            artifacts.extend(
                _inspect_multiple_candidates(
                    root,
                    spec,
                    candidates,
                    source_by_path,
                    hash_large_files,
                    hash_state,
                )
            )
            continue

        if explicit_candidates:
            artifacts.append(
                _inspect_candidate(
                    root,
                    spec,
                    explicit_candidates[0],
                    "explicit",
                    hash_large_files,
                    hash_state=hash_state,
                )
            )
        else:
            candidates = discovered_candidates
            if not candidates:
                artifacts.append(
                    _inspect_candidate(
                        root,
                        spec,
                        None,
                        "discovered",
                        hash_large_files,
                        hash_state=hash_state,
                    )
                )
                continue
            first_inspected = None
            selected = None
            for candidate in candidates:
                inspected = _inspect_candidate(
                    root,
                    spec,
                    candidate,
                    "discovered",
                    hash_large_files,
                    hash_state=hash_state,
                )
                if first_inspected is None:
                    first_inspected = inspected
                if inspected.status == "ok":
                    selected = inspected
                    break
            artifacts.append(selected or first_inspected)
    processed_counts: Dict[str, int] = {}
    for artifact in artifacts:
        if artifact.local_path:
            processed_counts[artifact.artifact_type] = (
                processed_counts.get(artifact.artifact_type, 0) + 1
            )

    content_overflow: Dict[str, int] = {}
    for candidate in indexed_files:
        resolved_candidate = candidate.resolve()
        if resolved_candidate in deferred_paths:
            continue
        local_path = str(resolved_candidate)
        existing = [
            artifact for artifact in artifacts
            if artifact.local_path == local_path
        ]
        if any(
            artifact.source == "explicit" or artifact.status != "invalid"
            for artifact in existing
        ):
            continue
        classified = _classify_additional_file(
            root, candidate, hash_large_files, hash_state
        )
        artifact_type = classified.artifact_type
        if processed_counts.get(artifact_type, 0) >= MAX_MULTIPLE_ARTIFACTS_PER_TYPE:
            content_overflow[artifact_type] = content_overflow.get(artifact_type, 0) + 1
            continue
        artifacts.append(classified)
        processed_counts[artifact_type] = processed_counts.get(artifact_type, 0) + 1

    for artifact_type, overflow_count in sorted(content_overflow.items()):
        spec = _spec_for(artifact_type)
        artifact_id = "artifact:{}:candidate-limit".format(artifact_type)
        existing_limit = next(
            (artifact for artifact in artifacts if artifact.artifact_id == artifact_id),
            None,
        )
        if existing_limit:
            existing_limit.metadata["candidate_count"] += overflow_count
        else:
            _append_candidate_limit(
                artifacts,
                spec,
                "content-signature",
                processed_counts.get(artifact_type, 0) + overflow_count,
                processed_counts.get(artifact_type, 0),
            )
    _apply_capture_manifest_statuses(root, artifacts)
    return artifacts


def _override_candidates(value: Any) -> List[Path]:
    values = value if isinstance(value, (list, tuple)) else [value]
    return [Path(item).expanduser().resolve() for item in values if item]


def _merge_candidates(
    explicit: Sequence[Path],
    discovered: Sequence[Path],
) -> Tuple[List[Path], Dict[str, str]]:
    candidates = []
    source_by_path = {}
    for source, paths in (("explicit", explicit), ("discovered", discovered)):
        for path in paths:
            key = str(path.resolve())
            if key in source_by_path:
                continue
            candidates.append(path)
            source_by_path[key] = source
    return candidates, source_by_path


def _inspect_multiple_candidates(
    root: Path,
    spec: ArtifactSpec,
    candidates: Sequence[Path],
    source_by_path: Dict[str, str],
    hash_large_files: bool,
    hash_state: Dict[str, Any],
) -> List[ArtifactEvidence]:
    selected = list(candidates[:MAX_MULTIPLE_ARTIFACTS_PER_TYPE])
    artifacts = [
        _inspect_candidate(
            root,
            spec,
            candidate,
            source_by_path[str(candidate.resolve())],
            hash_large_files,
            hash_state=hash_state,
        )
        for candidate in selected
    ]
    if len(candidates) > MAX_MULTIPLE_ARTIFACTS_PER_TYPE:
        sources = {source_by_path[str(candidate.resolve())] for candidate in candidates}
        _append_candidate_limit(
            artifacts,
            spec,
            sources.pop() if len(sources) == 1 else "mixed",
            len(candidates),
            len(selected),
        )
    return artifacts


def _append_candidate_limit(
    artifacts: List[ArtifactEvidence],
    spec: ArtifactSpec,
    source: str,
    candidate_count: int,
    processed_count: int,
) -> None:
    artifact_id = "artifact:{}:candidate-limit".format(spec.artifact_type)
    existing = next(
        (artifact for artifact in artifacts if artifact.artifact_id == artifact_id),
        None,
    )
    if existing:
        existing.metadata["candidate_count"] = max(
            existing.metadata.get("candidate_count", 0), candidate_count
        )
        existing.metadata["processed_count"] = max(
            existing.metadata.get("processed_count", 0), processed_count
        )
        return
    artifacts.append(
        ArtifactEvidence(
            artifact_id=artifact_id,
            artifact_type=spec.artifact_type,
            status="not_collected",
            accounting_domain=spec.accounting_domain,
            perturbation=spec.perturbation,
            validation=[
                "candidate limit reached; inspect or split the remaining files"
            ],
            source=source,
            metadata={
                "candidate_count": candidate_count,
                "processed_count": processed_count,
                "candidate_limit": MAX_MULTIPLE_ARTIFACTS_PER_TYPE,
            },
        )
    )


def _classify_additional_file(
    root: Path,
    candidate: Path,
    hash_large_files: bool,
    hash_state: Dict[str, Any],
) -> ArtifactEvidence:
    try:
        header = _read_sniff_bytes(candidate)
    except (OSError, EOFError):
        return _inspect_candidate(
            root,
            _spec_for("unclassified_file"),
            candidate,
            "folder-scan",
            hash_large_files,
            hash_state=hash_state,
        )

    if _image_metadata(header):
        return _inspect_candidate(
            root, _spec_for("qa_screenshot"), candidate, "content-signature",
            hash_large_files, hash_state=hash_state,
        )
    if header.startswith(b"JAVA PROFILE "):
        return _inspect_candidate(
            root, _spec_for("hprof"), candidate, "content-signature",
            hash_large_files, hash_state=hash_state,
        )
    if header[:4] in (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"):
        spec = _spec_for("android_log")
        validation = _validated(spec, candidate)
        if validation:
            return _inspect_candidate(
                root,
                spec,
                candidate,
                "content-signature",
                hash_large_files,
                validation,
                hash_state,
            )
    if candidate.suffix.lower() in (".perfetto", ".perfetto-trace"):
        return _inspect_candidate(
            root, _spec_for("perfetto_trace"), candidate, "content-signature",
            hash_large_files, hash_state=hash_state,
        )

    text = _decode_text_sample(header)
    if text is not None:
        stripped = text.lstrip()
        if candidate.suffix.lower() == ".json" or (
            stripped.startswith("{")
            and any(
                marker in text
                for marker in ('"memory_overview"', '"native_memory"', '"changes"')
            )
        ):
            previous_context = _validated(_spec_for("previous_ai_context"), candidate)
            if previous_context:
                return _inspect_candidate(
                    root,
                    _spec_for("previous_ai_context"),
                    candidate,
                    "content-signature",
                    hash_large_files,
                    previous_context,
                    hash_state,
                )
            report = _validated(_spec_for("analysis_report"), candidate)
            if report and report[2].get("report_type") == "comparison":
                return _inspect_candidate(
                    root,
                    _spec_for("comparison_report"),
                    candidate,
                    "content-signature",
                    hash_large_files,
                    report,
                    hash_state,
                )
            if report:
                return _inspect_candidate(
                    root,
                    _spec_for("analysis_report"),
                    candidate,
                    "content-signature",
                    hash_large_files,
                    report,
                    hash_state,
                )

        if _looks_like_previous_analysis(text):
            previous_analysis = _validated(
                _spec_for("previous_analysis_report"), candidate
            )
            if previous_analysis:
                return _inspect_candidate(
                    root,
                    _spec_for("previous_analysis_report"),
                    candidate,
                    "content-signature",
                    hash_large_files,
                    previous_analysis,
                    hash_state,
                )

        for artifact_type in (
            "meminfo",
            "smaps",
            "showmap",
            "proc_meminfo",
            "pressure_memory",
            "zram",
            "gfxinfo",
            "device_context",
        ):
            spec = _spec_for(artifact_type)
            validation = _validated(spec, candidate)
            if validation:
                return _inspect_candidate(
                    root,
                    spec,
                    candidate,
                    "content-signature",
                    hash_large_files,
                    validation,
                    hash_state,
                )

        if _looks_like_phase_metadata(text):
            spec = _spec_for("phase_metadata")
            validation = _validated(spec, candidate)
            if validation:
                return _inspect_candidate(
                    root,
                    spec,
                    candidate,
                    "content-signature",
                    hash_large_files,
                    validation,
                    hash_state,
                )

        if candidate.suffix.lower() in (".log", ".gz") or _looks_like_android_log(text):
            spec = _spec_for("android_log")
            validation = _validated(spec, candidate)
            if validation:
                scan = validation[2].get("log_scan", {})
                if (
                    candidate.suffix.lower() in (".log", ".gz")
                    or scan.get("android_format_recognized")
                    or scan.get("memory_signal_matches", 0) > 0
                ):
                    return _inspect_candidate(
                        root,
                        spec,
                        candidate,
                        "content-signature",
                        hash_large_files,
                        validation,
                        hash_state,
                    )

    return _inspect_candidate(
        root,
        _spec_for("unclassified_file"),
        candidate,
        "folder-scan",
        hash_large_files,
        hash_state=hash_state,
    )


def _read_sniff_bytes(path: Path) -> bytes:
    with path.open("rb") as handle:
        prefix = handle.read(2)
    if prefix == b"\x1f\x8b":
        with gzip.open(str(path), "rb") as handle:
            return handle.read(MAX_SNIFF_BYTES)
    with path.open("rb") as handle:
        return handle.read(MAX_SNIFF_BYTES)


def _looks_like_android_log(text: str) -> bool:
    return bool(
        re.search(
            r"(?m)^(?:\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+\s+\d+\s+\d+\s+"
            r"[VDIWEFAS]\s+[^:]{1,80}\s*:|[VDIWEFAS]/[^(:\n]{1,80}(?:\(\s*\d+\))?:)",
            text,
        )
        or any(
            marker in text
            for marker in (
                "*** *** *** *** *** *** *** *** *** *** *** *** *** *** *** ***",
                "Abort message:",
                "backtrace:",
                "ANR in ",
                "GC Root:",
                "LeakCanary",
            )
        )
    )


def _looks_like_previous_analysis(text: str) -> bool:
    return (
        '"record_type"' in text
        and "android-memory-analysis-record" in text
    ) or bool(
        re.search(
            r"(?im)^(?:#{1,4}\s*)?(?:bounded conclusion|analysis conclusion|conclusion|"
            r"revision status|分析结论|结论|修订状态)\s*[:：]?\s*$",
            text,
        )
    )


def _validated(
    spec: ArtifactSpec,
    candidate: Path,
) -> Optional[Tuple[str, List[str], Dict[str, Any]]]:
    try:
        validation = spec.validator(candidate)
    except OSError:
        return None
    return validation if validation[0] == "ok" else None


def _decode_text_sample(data: bytes) -> Optional[str]:
    if not data:
        return ""
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", errors="replace")
    if data.count(b"\x00") > max(4, len(data) // 100):
        return None
    return data.decode("utf-8", errors="replace")


def _looks_like_phase_metadata(text: str) -> bool:
    keys = set(
        match.group(1).lower()
        for match in re.finditer(
            r"(?im)^(timestamp(?:_utc)?|captured_at|package|pid|process_role|"
            r"user_profile|scenario|phase|loops|cooldown_seconds|"
            r"collection_mode|perturbation)\s*[:=]",
            text,
        )
    )
    return len(keys) >= 2


def _validate_unclassified(path: Path) -> Tuple[str, List[str], Dict[str, Any]]:
    try:
        with path.open("rb") as handle:
            sample = handle.read(4096)
    except OSError as exc:
        return "unreadable", ["cannot inspect folder item: {}".format(exc)], {}
    return "unclassified", ["folder item did not match a supported content signature"], {
        "extension": "".join(path.suffixes).lower() or "<none>",
        "content_kind": "text" if _decode_text_sample(sample) is not None else "binary",
        "manual_review_required": True,
    }


def _spec_for(artifact_type: str) -> ArtifactSpec:
    if artifact_type == "unclassified_file":
        return ArtifactSpec(
            "unclassified_file",
            (),
            (),
            "unknown",
            "unknown",
            _validate_unclassified,
            True,
        )
    return next(spec for spec in ARTIFACT_SPECS if spec.artifact_type == artifact_type)


def _apply_capture_manifest_statuses(
    root: Path,
    artifacts: List[ArtifactEvidence],
) -> None:
    """Preserve collector outcomes when no usable artifact reached disk."""
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        return
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if manifest.get("manifest_type") != "android-memory-capture-manifest":
        return

    type_aliases = {"zram_swap": "zram"}
    outcomes = {}
    for item in manifest.get("artifacts", []):
        if not isinstance(item, dict):
            continue
        manifest_type = item.get("artifact_type")
        artifact_type = type_aliases.get(manifest_type, manifest_type)
        if artifact_type:
            outcomes[artifact_type] = item

    for artifact in artifacts:
        if artifact.source != "discovered" or artifact.status != "missing":
            continue
        outcome = outcomes.get(artifact.artifact_type)
        if not outcome:
            continue
        manifest_status = outcome.get("status")
        if manifest_status == "ok":
            artifact.status = "invalid"
            artifact.validation = [
                "capture manifest reports ok but the referenced artifact is missing"
            ]
        elif manifest_status in {
            "empty",
            "permission_denied",
            "not_supported",
            "command_failed",
            "skipped",
            "not_applicable",
            "not_collected",
        }:
            artifact.status = manifest_status
            artifact.validation = [
                outcome.get("reason") or "status preserved from capture manifest"
            ]
        else:
            continue
        artifact.path = outcome.get("path") or artifact.path
        artifact.source = "capture-manifest"
        artifact.metadata = {
            "capture_status": manifest_status,
            "command_template": outcome.get("command_template"),
            "error_path": outcome.get("error_path"),
            "error_size_bytes": outcome.get("error_size_bytes"),
            "error_sha256": outcome.get("error_sha256"),
        }


def _find_candidates(
    root: Path,
    spec: ArtifactSpec,
    folder_files: Sequence[Path],
) -> List[Path]:
    candidates: List[Path] = []
    seen = set()
    ordered_files = sorted(
        folder_files,
        key=lambda path: (
            0 if path.parent.resolve() == root else 1,
            path.relative_to(root).as_posix(),
        ),
    )
    for filename in spec.filenames:
        for candidate in ordered_files:
            if candidate.name == filename and candidate not in seen:
                candidates.append(candidate)
                seen.add(candidate)
    for pattern in spec.globs:
        for candidate in ordered_files:
            relative = candidate.relative_to(root)
            matches = relative.match(pattern)
            if not matches and pattern.startswith("**/"):
                matches = relative.match(pattern[3:])
            if matches and candidate not in seen:
                candidates.append(candidate)
                seen.add(candidate)
    return candidates


def _inspect_candidate(
    root: Path,
    spec: ArtifactSpec,
    candidate: Optional[Path],
    source: str,
    hash_large_files: bool,
    prevalidated: Optional[Tuple[str, List[str], Dict[str, Any]]] = None,
    hash_state: Optional[Dict[str, Any]] = None,
) -> ArtifactEvidence:
    artifact_id = _artifact_id(root, spec, candidate)
    if candidate is None:
        return ArtifactEvidence(
            artifact_id=artifact_id,
            artifact_type=spec.artifact_type,
            status="missing",
            accounting_domain=spec.accounting_domain,
            perturbation=spec.perturbation,
            validation=["no matching artifact found"],
            source=source,
        )
    if not candidate.exists():
        return ArtifactEvidence(
            artifact_id=artifact_id,
            artifact_type=spec.artifact_type,
            status="missing",
            accounting_domain=spec.accounting_domain,
            perturbation=spec.perturbation,
            path=_display_path(root, candidate),
            local_path=str(candidate),
            validation=["explicit artifact path does not exist"],
            source=source,
        )
    if not candidate.is_file():
        return ArtifactEvidence(
            artifact_id=artifact_id,
            artifact_type=spec.artifact_type,
            status="invalid",
            accounting_domain=spec.accounting_domain,
            perturbation=spec.perturbation,
            path=_display_path(root, candidate),
            local_path=str(candidate.resolve()),
            validation=["artifact path is not a file"],
            source=source,
        )

    size = candidate.stat().st_size
    if size == 0:
        status, messages, metadata = "empty", ["file is empty"], {}
    elif prevalidated is not None:
        status, messages, metadata = prevalidated
    else:
        try:
            status, messages, metadata = spec.validator(candidate)
        except OSError as exc:
            status, messages, metadata = "unreadable", ["cannot inspect artifact: {}".format(exc)], {}

    digest = None
    cache_key = str(candidate.resolve())
    digest_cache = hash_state.get("digests", {}) if hash_state is not None else {}
    if cache_key in digest_cache:
        digest = digest_cache[cache_key]
    hashed_bytes = hash_state.get("hashed_bytes", 0) if hash_state is not None else 0
    within_total_budget = hashed_bytes + size <= MAX_TOTAL_DEFAULT_HASH_BYTES
    if digest is None and (
        hash_large_files or (size <= MAX_DEFAULT_HASH_BYTES and within_total_budget)
    ):
        try:
            digest = _sha256(candidate)
            if hash_state is not None:
                hash_state["hashed_bytes"] = hashed_bytes + size
                hash_state.setdefault("digests", {})[cache_key] = digest
        except OSError as exc:
            messages.append("sha256 unavailable: {}".format(exc))
    elif digest is None and size <= MAX_DEFAULT_HASH_BYTES:
        messages.append(
            "sha256 skipped because the folder exceeded the default {} byte total hash budget; use --hash-large-files to opt in".format(
                MAX_TOTAL_DEFAULT_HASH_BYTES
            )
        )
    elif digest is None:
        messages.append(
            "sha256 skipped for file larger than {} bytes; use --hash-large-files to opt in".format(
                MAX_DEFAULT_HASH_BYTES
            )
        )

    return ArtifactEvidence(
        artifact_id=artifact_id,
        artifact_type=spec.artifact_type,
        status=status,
        accounting_domain=spec.accounting_domain,
        perturbation=spec.perturbation,
        path=_display_path(root, candidate),
        local_path=str(candidate.resolve()),
        size_bytes=size,
        sha256=digest,
        source=source,
        validation=messages,
        metadata=metadata,
    )


def _artifact_id(root: Path, spec: ArtifactSpec, candidate: Optional[Path]) -> str:
    base = "artifact:{}".format(spec.artifact_type)
    if not spec.allow_multiple or candidate is None:
        return base
    stable_path = str(candidate.expanduser().resolve())
    suffix = hashlib.sha256(stable_path.encode("utf-8")).hexdigest()[:12]
    return "{}:{}".format(base, suffix)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _display_path(root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(root))
    except ValueError:
        return "<external>/{}".format(path.name)


def available_artifact_types(artifacts: Iterable[ArtifactEvidence]) -> List[str]:
    return sorted({
        artifact.artifact_type
        for artifact in artifacts
        if (
            artifact.status == "ok"
            and artifact.artifact_type not in HISTORY_ARTIFACT_TYPES
        )
    })


def collect_subject_context(
    root: Path,
    artifacts: Iterable[ArtifactEvidence],
    explicit: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], List[EvidenceConflict], Dict[str, Dict[str, Any]]]:
    candidates: Dict[str, Dict[str, Any]] = {
        "package": {},
        "pid": {},
        "timestamp": {},
        "android_release": {},
        "android_sdk": {},
        "build_fingerprint": {},
        "page_size": {},
        "phase": {},
    }
    for key, value in (explicit or {}).items():
        if key in candidates and value not in (None, ""):
            candidates[key]["explicit"] = value

    artifact_groups: Dict[str, List[ArtifactEvidence]] = {}
    for item in artifacts:
        if item.path:
            artifact_groups.setdefault(item.artifact_type, []).append(item)
    _collect_meta_candidates(root, candidates)
    _collect_standalone_context(root, candidates)
    _collect_explicit_context(candidates, artifact_groups)
    _collect_artifact_metadata(candidates, artifact_groups)
    _collect_directory_context(root, candidates)

    priority = (
        "explicit",
        "explicit_artifact",
        "manifest",
        "meta",
        "standalone",
        "artifact",
        "directory",
    )
    subject: Dict[str, Any] = {}
    conflicts: List[EvidenceConflict] = []
    for field_name, values in candidates.items():
        normalized_values = {
            source: _normalize_context_value(field_name, value)
            for source, value in values.items()
            if value not in (None, "")
        }
        chosen = next(
            (
                value
                for preferred in priority
                for source, value in normalized_values.items()
                if source == preferred or source.startswith(preferred + ":")
            ),
            None,
        )
        if chosen is not None:
            subject[field_name] = chosen
        distinct = {str(value) for value in normalized_values.values()}
        if len(distinct) > 1:
            conflicts.append(
                EvidenceConflict(
                    field=field_name,
                    values=normalized_values,
                    severity="warning",
                    explanation_zh="不同来源给出了不一致的 {}，不会静默合并；请确认目标进程与采集窗口。".format(field_name),
                    explanation_en="Evidence sources disagree on {}; confirm the target process and capture window.".format(field_name),
                )
            )
    return subject, conflicts, candidates


def _collect_meta_candidates(root: Path, candidates: Dict[str, Dict[str, Any]]) -> None:
    manifest_path = root / "manifest.json"
    if manifest_path.is_file():
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        subject = data.get("subject", data)
        device = subject.get("device", {}) if isinstance(subject, dict) else {}
        if isinstance(subject, dict):
            mapping = {
                "package": subject.get("package"),
                "pid": subject.get("pid"),
                "timestamp": subject.get("timestamp") or subject.get("captured_at"),
                "android_release": subject.get("android_release") or device.get("android_release"),
                "android_sdk": subject.get("android_sdk") or subject.get("api_level") or device.get("android_sdk"),
                "build_fingerprint": subject.get("build_fingerprint") or device.get("build_fingerprint"),
                "page_size": subject.get("page_size") or device.get("page_size"),
                "phase": subject.get("phase"),
            }
            for key, value in mapping.items():
                if value not in (None, ""):
                    candidates[key]["manifest"] = value

    meta_path = root / "meta.txt"
    if meta_path.is_file():
        try:
            lines = _read_text(meta_path).splitlines()
        except OSError:
            lines = []
        mapping = {
            "package": "package",
            "pid": "pid",
            "timestamp": "timestamp",
            "androidrelease": "android_release",
            "androidsdk": "android_sdk",
            "buildfingerprint": "build_fingerprint",
            "pagesize": "page_size",
            "phase": "phase",
        }
        for line in lines:
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            target = mapping.get(key.strip().replace("_", "").lower())
            if target and value.strip():
                candidates[target]["meta"] = value.strip()


def _collect_standalone_context(root: Path, candidates: Dict[str, Dict[str, Any]]) -> None:
    mapping = {
        "android_release": "android_release.txt",
        "android_sdk": "android_sdk.txt",
        "build_fingerprint": "build_fingerprint.txt",
        "page_size": "page_size.txt",
    }
    for field_name, filename in mapping.items():
        path = root / filename
        if path.is_file():
            try:
                value = _read_text(path, limit=4096).strip()
            except OSError:
                continue
            if value:
                candidates[field_name]["standalone"] = value


def _collect_artifact_metadata(
    candidates: Dict[str, Dict[str, Any]],
    artifact_groups: Dict[str, List[ArtifactEvidence]],
) -> None:
    valid_meminfo = [
        artifact for artifact in artifact_groups.get("meminfo", [])
        if artifact.status == "ok"
    ]
    for meminfo in valid_meminfo:
        source = "artifact:{}".format(meminfo.artifact_id)
        for key in ("package", "pid"):
            value = meminfo.metadata.get(key)
            if value:
                candidates[key][source] = value


def _collect_explicit_context(
    candidates: Dict[str, Dict[str, Any]],
    artifact_groups: Dict[str, List[ArtifactEvidence]],
) -> None:
    for artifact_type in ("device_context", "phase_metadata"):
        context_artifacts = [
            artifact for artifact in artifact_groups.get(artifact_type, [])
            if artifact.status == "ok"
        ]
        for artifact in context_artifacts:
            if not artifact.local_path:
                continue
            path = Path(artifact.local_path)
            try:
                content = _read_text(path)
            except OSError:
                continue
            if path.suffix.lower() == ".json":
                try:
                    data = json.loads(content)
                except json.JSONDecodeError:
                    data = {}
                subject = data.get("subject", data) if isinstance(data, dict) else {}
                device = subject.get("device", {}) if isinstance(subject, dict) else {}
                values = {
                    "package": subject.get("package"),
                    "pid": subject.get("pid"),
                    "timestamp": subject.get("timestamp") or subject.get("captured_at"),
                    "android_release": subject.get("android_release") or device.get("android_release"),
                    "android_sdk": subject.get("android_sdk") or subject.get("api_level") or device.get("android_sdk"),
                    "build_fingerprint": subject.get("build_fingerprint") or device.get("build_fingerprint"),
                    "page_size": subject.get("page_size") or device.get("page_size"),
                    "phase": subject.get("phase"),
                }
            else:
                patterns = {
                    "package": r"(?im)^Package\s*[:=]\s*(.+)$",
                    "pid": r"(?im)^PID\s*[:=]\s*(\d+)$",
                    "timestamp": r"(?im)^(?:Timestamp|timestamp_utc|captured_at)\s*[:=]\s*(.+)$",
                    "android_release": r"(?im)^(?:AndroidRelease|android_release)\s*[:=]\s*\[?([^\]\n]+)|^\[ro\.build\.version\.release\]:\s*\[?([^\]\n]+)",
                    "android_sdk": r"(?im)^(?:AndroidSdk|android_sdk)\s*[:=]\s*\[?([^\]\n]+)|^\[ro\.build\.version\.sdk\]:\s*\[?([^\]\n]+)",
                    "build_fingerprint": r"(?im)^(?:BuildFingerprint|build_fingerprint)\s*[:=]\s*\[?([^\]\n]+)|^\[ro\.build\.fingerprint\]:\s*\[?([^\]\n]+)",
                    "page_size": r"(?im)^(?:PageSize|page_size)\s*[:=]\s*(\d+)$",
                    "phase": r"(?im)^Phase\s*[:=]\s*(.+)$",
                }
                values = {}
                for key, pattern in patterns.items():
                    match = re.search(pattern, content)
                    values[key] = next(
                        (
                            group.strip()
                            for group in match.groups()
                            if group not in (None, "")
                        ),
                        None,
                    ) if match else None
            prefix = "explicit_artifact" if artifact.source == "explicit" else "artifact"
            source = "{}:{}".format(prefix, artifact.artifact_id)
            for key, value in values.items():
                if value not in (None, ""):
                    candidates[key][source] = value


def _collect_directory_context(root: Path, candidates: Dict[str, Dict[str, Any]]) -> None:
    match = re.match(r"(.+)_([0-9]{8}_[0-9]{6})$", root.name)
    if match:
        candidates["package"]["directory"] = match.group(1)
        candidates["timestamp"]["directory"] = match.group(2)


def _normalize_context_value(field_name: str, value: Any) -> Any:
    if field_name in ("pid", "android_sdk", "page_size"):
        text = str(value).strip()
        return int(text) if text.isdigit() else text
    return str(value).strip()


def load_report_summaries(root: Path, artifacts: Iterable[ArtifactEvidence]) -> List[Dict[str, Any]]:
    artifact_list = list(artifacts)
    available = set(available_artifact_types(artifact_list))
    reports = []
    for artifact in artifact_list:
        if artifact.artifact_type not in ("analysis_report", "comparison_report"):
            continue
        if artifact.status != "ok" or not artifact.path:
            continue
        if not artifact.local_path:
            continue
        path = Path(artifact.local_path)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        report_type = artifact.metadata.get("report_type", "unknown")
        reports.append(_normalize_report(path.name, report_type, data, available))
    return reports


def _normalize_report(
    filename: str,
    report_type: str,
    data: Dict[str, Any],
    available: Iterable[str],
) -> Dict[str, Any]:
    if report_type == "panorama":
        selected_keys = (
            "package_name",
            "pid",
            "timestamp",
            "memory_overview",
            "native_tracking",
            "smaps_context",
            "system_memory",
            "zram_swap",
            "dmabuf_context",
            "anomalies",
            "recommendations",
        )
        accounting_domains = ["process-pages", "system-pages", "runtime-heap", "memtrack", "derived-analysis"]
    elif report_type == "combined":
        selected_keys = ("timestamp", "summary", "native_memory", "memory_breakdown", "recommendations")
        accounting_domains = ["object-graph", "process-pages", "memtrack", "derived-analysis"]
    else:
        selected_keys = tuple(data.keys())
        accounting_domains = ["derived-comparison"]
    selected = {key: data[key] for key in selected_keys if key in data}
    selected, summary_truncated = _bound_report_summary(selected)
    limitations = [
        "Existing analyzer report is derived evidence; verify important claims against raw artifacts.",
    ]
    if not data.get("schema_version"):
        limitations.append("Report has no schema_version and is treated as an unversioned legacy contract.")
    if summary_truncated:
        limitations.append(
            "Report summary exceeded the context budget and was truncated; open the hashed raw report locally for omitted fields."
        )
    if report_type == "combined":
        summary = data.get("summary", {})
        java_heap = summary.get("java_heap_mb")
        total = summary.get("total_memory_mb")
        if isinstance(java_heap, (int, float)) and isinstance(total, (int, float)) and java_heap > total:
            limitations.append(
                "java_heap_mb exceeds total_memory_mb because object/runtime and page-accounting ledgers are mixed; do not subtract or calculate a percentage across them."
            )
    dependencies = _report_dependencies(report_type, data)
    unverified_dependencies = sorted(set(dependencies).difference(available))
    if unverified_dependencies:
        limitations.append(
            "Report contains fields derived from unavailable raw artifacts: {}. Treat those fields as unverified navigation only.".format(
                ", ".join(unverified_dependencies)
            )
        )
    return {
        "filename": filename,
        "report_type": report_type,
        "schema_version": data.get("schema_version", "unversioned"),
        "accounting_domains": accounting_domains,
        "summary": selected,
        "summary_truncated": summary_truncated,
        "source_dependencies": dependencies,
        "unverified_dependencies": unverified_dependencies,
        "limitations": limitations,
    }


def _report_dependencies(report_type: str, data: Dict[str, Any]) -> List[str]:
    if report_type == "panorama":
        key_dependencies = {
            "memory_overview": "meminfo",
            "native_tracking": "smaps",
            "hprof_summary": "hprof",
            "system_memory": "proc_meminfo",
            "dmabuf_context": "dmabuf",
            "zram_swap": "zram",
            "frame_stats": "gfxinfo",
        }
        return [
            artifact_type
            for key, artifact_type in key_dependencies.items()
            if data.get(key) is not None
        ]
    if report_type == "combined":
        return ["hprof", "smaps"]
    return []


def _bound_report_summary(value: Any) -> Tuple[Any, bool]:
    budget = {"nodes": 500, "characters": 32 * 1024}

    def visit(item: Any, depth: int) -> Tuple[Any, bool]:
        if budget["nodes"] <= 0 or depth > 6:
            return None, True
        budget["nodes"] -= 1
        if isinstance(item, str):
            available = min(2048, budget["characters"])
            budget["characters"] -= min(len(item), available)
            if len(item) > available:
                return item[:available] + "…", True
            return item, False
        if isinstance(item, list):
            output = []
            truncated = len(item) > 50
            for child in item[:50]:
                if budget["nodes"] <= 0:
                    truncated = True
                    break
                normalized, child_truncated = visit(child, depth + 1)
                output.append(normalized)
                truncated = truncated or child_truncated
            return output, truncated
        if isinstance(item, dict):
            output = {}
            entries = list(item.items())
            truncated = len(entries) > 64
            for key, child in entries[:64]:
                if budget["nodes"] <= 1:
                    truncated = True
                    break
                normalized_key, key_truncated = visit(str(key), depth + 1)
                normalized, child_truncated = visit(child, depth + 1)
                output[normalized_key] = normalized
                truncated = truncated or key_truncated or child_truncated
            return output, truncated
        return item, False

    return visit(value, 0)
