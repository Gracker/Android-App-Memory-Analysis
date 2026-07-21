"""Create a structured manifest for live collection outcomes."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union


CAPTURE_SCHEMA_VERSION = "1.0"

ARTIFACT_DEFINITIONS = {
    "build_fingerprint": ("capture-context", "none", "getprop ro.build.fingerprint", False),
    "android_release": ("capture-context", "none", "getprop ro.build.version.release", False),
    "android_sdk": ("capture-context", "none", "getprop ro.build.version.sdk", False),
    "page_size": ("capture-context", "none", "getconf PAGE_SIZE", False),
    "package_uid": ("capture-context", "low", "cmd package list packages -U <package>", False),
    "processes": ("capture-context", "low", "ps -A", False),
    "activity_processes": ("capture-context", "low", "dumpsys activity processes", False),
    "exit_info": ("process-exit", "low", "dumpsys activity exit-info <package>", False),
    "memory_limiter_status": ("device-policy", "low", "am memory-limiter status", False),
    "showmap": ("process-pages", "low", "showmap <pid>", True),
    "smaps": ("process-pages", "low", "cat /proc/<pid>/smaps with permission fallbacks", True),
    "meminfo": ("android-summary", "medium", "dumpsys meminfo -d <package>", True),
    "gfxinfo": ("rendering", "low", "dumpsys gfxinfo <package>", True),
    "proc_meminfo": ("system-pages", "low", "cat /proc/meminfo", False),
    "zram_swap": ("swap", "low", "/proc/swaps and /sys/block/zram*", False),
    "dmabuf": ("cross-process-buffers", "low", "DMA-BUF debugfs with permission fallbacks", False),
    "hprof": ("object-graph", "high", "am dumpheap <package> <file>", True),
}


def build_capture_manifest(
    dump_dir: Path,
    package_name: str,
    pid: Optional[Union[int, str]],
    timestamp: str,
    results: Dict[str, Any],
    files: Dict[str, str],
    process_status: str,
    skip_hprof: bool,
) -> Dict[str, Any]:
    root = Path(dump_dir).resolve()
    artifacts = []
    for artifact_type, definition in ARTIFACT_DEFINITIONS.items():
        accounting_domain, perturbation, command, needs_process = definition
        path = Path(files[artifact_type])
        error_key = "{}_error".format(artifact_type)
        if artifact_type in results and path.is_file():
            status = "ok"
            reason = (
                "collector produced a non-empty artifact"
                if path.stat().st_size
                else "collector produced an empty artifact"
            )
            if path.stat().st_size == 0:
                status = "empty"
        elif error_key in results and Path(results[error_key]).is_file():
            status, reason = _classify_error(Path(results[error_key]))
        elif artifact_type == "hprof" and skip_hprof:
            status = "skipped"
            reason = "user selected --skip-hprof"
        elif needs_process and process_status != "running":
            status = "not_applicable"
            reason = "target process was not running"
        else:
            status = "not_collected"
            reason = "collector returned no artifact; inspect permissions, command support, and process state"

        item = {
            "artifact_type": artifact_type,
            "status": status,
            "path": _relative_or_name(root, path),
            "accounting_domain": accounting_domain,
            "perturbation": perturbation,
            "command_template": command,
            "reason": reason,
        }
        if path.is_file():
            item["size_bytes"] = path.stat().st_size
        if error_key in results and Path(results[error_key]).is_file():
            error_path = Path(results[error_key])
            item["error_path"] = _relative_or_name(root, error_path)
            item["error_size_bytes"] = error_path.stat().st_size
            item["error_sha256"] = _sha256(error_path)
        artifacts.append(item)

    return {
        "schema_version": CAPTURE_SCHEMA_VERSION,
        "manifest_type": "android-memory-capture-manifest",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "subject": {
            "package": package_name,
            "pid": pid,
            "timestamp": timestamp,
            "process_status": process_status,
            "phase": "single-diagnostic",
            "collection_mode": "detailed-diagnostic",
            "device": {
                "android_release": _read_value(files.get("android_release")),
                "android_sdk": _read_value(files.get("android_sdk")),
                "build_fingerprint": _read_value(files.get("build_fingerprint")),
                "page_size": _read_value(files.get("page_size")),
            },
        },
        "collection": {
            "hprof_requested": not skip_hprof,
            "natural_baseline": False,
            "limitations": [
                "Detailed dumpsys meminfo and optional HPROF make this a diagnostic snapshot, not a low-perturbation baseline.",
                "not_collected does not mean the memory category is absent.",
            ],
        },
        "artifacts": artifacts,
    }


def write_capture_manifest(path: Path, manifest: Dict[str, Any]) -> None:
    Path(path).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _classify_error(path: Path) -> Tuple[str, str]:
    content = path.read_text(encoding="utf-8", errors="replace").lower()
    if "permission denied" in content or "avc: denied" in content:
        return "permission_denied", "collector archived a permission-denied error"
    if "unknown command" in content or "not found" in content:
        return "not_supported", "collector archived an unsupported-command error"
    return "command_failed", "collector archived a command failure"


def _read_value(path_value: Optional[str]) -> Optional[str]:
    if not path_value:
        return None
    path = Path(path_value)
    if not path.is_file():
        return None
    value = path.read_text(encoding="utf-8", errors="replace").strip()
    return value or None


def _relative_or_name(root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(root))
    except ValueError:
        return path.name


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
