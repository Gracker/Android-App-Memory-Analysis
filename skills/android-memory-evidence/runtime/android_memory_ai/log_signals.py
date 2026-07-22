"""Extract bounded, privacy-safe Android memory signals from text logs."""

import gzip
import hashlib
import re
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


MAX_LOG_SCAN_BYTES = 32 * 1024 * 1024
MAX_SIGNAL_SAMPLES = 5
MAX_LINE_CHARS = 16 * 1024
MAX_ARCHIVE_MEMBERS = 256

_THREADTIME_RE = re.compile(
    r"^(?P<timestamp>\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+)\s+"
    r"\d+\s+\d+\s+[VDIWEFAS]\s+(?P<tag>[^:]{1,80})\s*:\s*"
)
_BRIEF_RE = re.compile(r"^[VDIWEFAS]/(?P<tag>[^(:]{1,80})(?:\(\s*\d+\))?:\s*")

_SIGNAL_DEFINITIONS: Tuple[Dict[str, Any], ...] = (
    {
        "signal_type": "leakcanary-retained-object",
        "category": "managed-leak-report",
        "strength": "diagnostic-report",
        "patterns": (
            r"\bAPPLICATION LEAKS\b",
            r"\bLeakCanary\b.*\b(?:retained|leak(?:ing|ed)?|heap analysis)\b",
            r"\bLeaking:\s*YES\b",
        ),
        "does_not_prove": "A retained-object or leak-trace marker still needs the complete trace, expected lifecycle, target identity, and reproduction phase before selecting the code owner.",
    },
    {
        "signal_type": "android-component-leak",
        "category": "managed-resource-leak",
        "strength": "runtime-warning",
        "patterns": (
            r"\bhas leaked window\b",
            r"\bhas leaked ServiceConnection\b",
            r"\bServiceConnectionLeaked\b",
            r"\bIntentReceiverLeaked\b",
        ),
        "does_not_prove": "The warning identifies a lifecycle cleanup failure, but the owning registration or window path must be bound to the matching component and source revision.",
    },
    {
        "signal_type": "strictmode-resource-leak",
        "category": "managed-resource-leak",
        "strength": "runtime-warning",
        "patterns": (
            r"\bLeakedClosableViolation\b",
            r"\bLeakedRegistrationViolation\b",
            r"\bSqliteObjectLeakedViolation\b",
            r"\bLeakedSqlLiteObjectViolation\b",
            r"\bSQLite(?:Connection|Closable)\b.*\bwas leaked\b",
            r"\bA resource was acquired at attached stack trace but never released\b",
        ),
        "does_not_prove": "A finalization-time resource warning identifies missing explicit cleanup, not the size or full process-memory impact of that resource.",
    },
    {
        "signal_type": "java-heap-oom",
        "category": "allocation-failure",
        "strength": "failure-symptom",
        "patterns": (
            r"\bjava\.lang\.OutOfMemoryError\b",
            r"\bFailed to allocate a \d+ byte allocation\b",
            r"\bGC overhead limit exceeded\b",
        ),
        "does_not_prove": "An OOM location is where allocation failed; it does not by itself identify the allocation growth or retained owner that exhausted the budget.",
    },
    {
        "signal_type": "native-allocation-failure",
        "category": "allocation-failure",
        "strength": "failure-symptom",
        "patterns": (
            r"\bscudo\b.*\b(?:out of memory|allocation.*failed|corrupted chunk|invalid chunk)\b",
            r"\b(?:malloc|calloc|realloc)\b.*\bfailed\b",
            r"\bAbort message:.*\b(?:scudo|jemalloc)\b",
        ),
        "does_not_prove": "Allocator failure or integrity output requires symbolized native stacks and matching process/page evidence before naming an allocation owner.",
    },
    {
        "signal_type": "lmkd-kill",
        "category": "system-pressure-event",
        "strength": "system-policy-event",
        "patterns": (
            r"\blmkd\b.*\b(?:kill|killing|killed)\b",
            r"\blowmemorykiller\b.*\b(?:kill|killing|select)\b",
            r"\blowmemory_kill\b",
        ),
        "does_not_prove": "An LMKD event supports a pressure-related exit, but it does not establish that the target app leaked or caused the device-wide pressure.",
    },
    {
        "signal_type": "kernel-oom-kill",
        "category": "system-pressure-event",
        "strength": "system-policy-event",
        "patterns": (
            r"\bOut of memory:\s*Kill process\b",
            r"\boom-kill:\b",
            r"\bKilled process \d+\b.*\b(?:total-vm|anon-rss|file-rss)\b",
        ),
        "does_not_prove": "A kernel OOM kill identifies a terminal pressure event, not the user-space owner or the earlier allocation timeline.",
    },
    {
        "signal_type": "jni-reference-table-overflow",
        "category": "native-reference-failure",
        "strength": "runtime-failure",
        "patterns": (
            r"\bJNI ERROR\b.*\breference table overflow\b",
            r"\b(?:local|global) reference table overflow\b",
        ),
        "does_not_prove": "A JNI reference-table overflow identifies reference-management failure, but the creating callsite and missing release still need a complete stack or instrumentation evidence.",
    },
    {
        "signal_type": "gc-pressure",
        "category": "runtime-pressure-symptom",
        "strength": "pressure-symptom",
        "patterns": (
            r"\bWaitForGcToComplete blocked\b",
            r"\bForcing collection of SoftReferences\b",
            r"\bClamp target GC heap\b",
        ),
        "does_not_prove": "GC delay or emergency collection indicates pressure, not a leak; correlate it with heap/page trends and the exact workload phase.",
    },
    {
        "signal_type": "binder-proxy-pressure",
        "category": "ipc-resource-pressure",
        "strength": "runtime-warning",
        "patterns": (
            r"\bToo many BinderProxy objects\b",
            r"\bBinderProxy\b.*\b(?:limit|high watermark|map growth)\b",
        ),
        "does_not_prove": "Binder proxy pressure points to IPC object growth; the producing interface, process pair, and lifecycle still need confirmation.",
    },
    {
        "signal_type": "cursor-window-allocation-failure",
        "category": "database-resource-pressure",
        "strength": "failure-symptom",
        "patterns": (
            r"\bCould not allocate CursorWindow\b",
            r"\bCursorWindow\b.*\b(?:allocation.*failed|failed to allocate)\b",
        ),
        "does_not_prove": "CursorWindow allocation failure does not distinguish an oversized query, unclosed cursor, process pressure, or platform limit without database and lifecycle evidence.",
    },
    {
        "signal_type": "graphics-allocation-failure",
        "category": "graphics-resource-pressure",
        "strength": "failure-symptom",
        "patterns": (
            r"\bUnable to create bitmap\b",
            r"\bbitmap size exceeds VM budget\b",
            r"\bCanvas: trying to draw too large\b",
            r"\bEGL_BAD_ALLOC\b",
            r"\bgralloc\b.*\b(?:alloc|allocation)\b.*\bfailed\b",
        ),
        "does_not_prove": "A graphics allocation failure needs buffer ownership, dimensions/formats, process roles, and Graphics/memtrack/DMA-BUF evidence before selecting a leak mechanism.",
    },
)


def scan_android_log(path: Path) -> Dict[str, Any]:
    """Scan one text or gzip log without returning raw log messages."""
    sources, truncated, compression, archive_metadata = _read_log_sources(path)
    compiled = [
        (
            definition,
            tuple(
                re.compile(pattern, re.IGNORECASE)
                for pattern in definition["patterns"]
            ),
        )
        for definition in _SIGNAL_DEFINITIONS
    ]
    matches: Dict[str, Dict[str, Any]] = {}
    format_hits = 0
    encodings = set()
    line_count = 0
    text_source_count = 0
    managed_owner_path_candidate = False

    for member, data in sources:
        if not _is_text_content(data):
            continue
        text_source_count += 1
        text, encoding = _decode_log(data)
        encodings.add(encoding)
        lines = text.splitlines()
        line_count += len(lines)
        managed_owner_path_candidate = (
            managed_owner_path_candidate or _has_managed_owner_path(text)
        )
        for line_number, raw_line in enumerate(lines, 1):
            line = raw_line[:MAX_LINE_CHARS]
            timestamp, tag, recognized = _line_context(line)
            if recognized:
                format_hits += 1
            for definition, patterns in compiled:
                if not any(pattern.search(line) for pattern in patterns):
                    continue
                signal_type = definition["signal_type"]
                signal = matches.setdefault(
                    signal_type,
                    {
                        "signal_type": signal_type,
                        "category": definition["category"],
                        "strength": definition["strength"],
                        "count": 0,
                        "samples": [],
                        "does_not_prove": definition["does_not_prove"],
                    },
                )
                signal["count"] += 1
                if len(signal["samples"]) < MAX_SIGNAL_SAMPLES:
                    sample = {
                        "line_number": line_number,
                        "line_sha256": hashlib.sha256(
                            raw_line.encode("utf-8", errors="replace")
                        ).hexdigest(),
                    }
                    if member:
                        sample["archive_member"] = member
                    if timestamp:
                        sample["timestamp"] = timestamp
                    if tag:
                        sample["tag"] = tag
                    signal["samples"].append(sample)

    signals = [matches[key] for key in sorted(matches)]
    result = {
        "format": "android-log-text",
        "encoding": encodings.pop() if len(encodings) == 1 else "mixed-or-unknown",
        "compression": compression,
        "bytes_scanned": sum(len(data) for _, data in sources),
        "scan_limit_bytes": MAX_LOG_SCAN_BYTES,
        "scan_truncated": truncated,
        "line_count": line_count,
        "text_content_recognized": text_source_count > 0,
        "android_format_recognized": format_hits > 0,
        "memory_signal_matches": sum(signal["count"] for signal in signals),
        "managed_owner_path_candidate": managed_owner_path_candidate,
        "signals": signals,
        "raw_lines_embedded": False,
    }
    result.update(archive_metadata)
    return result


def _read_log_sources(
    path: Path,
) -> Tuple[List[Tuple[Optional[str], bytes]], bool, str, Dict[str, Any]]:
    with path.open("rb") as source:
        prefix = source.read(4)
    if prefix in (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"):
        return _read_zip_sources(path)
    data, truncated, compression = _read_bounded(path)
    return [(None, data)], truncated, compression, {}


def _read_zip_sources(
    path: Path,
) -> Tuple[List[Tuple[Optional[str], bytes]], bool, str, Dict[str, Any]]:
    sources: List[Tuple[Optional[str], bytes]] = []
    scanned_bytes = 0
    scanned_members = 0
    examined_members = 0
    skipped_members = 0
    truncated = False
    try:
        with zipfile.ZipFile(str(path)) as archive:
            members = sorted(
                (item for item in archive.infolist() if not item.is_dir()),
                key=lambda item: (_archive_member_priority(item.filename), item.filename),
            )
            for index, item in enumerate(members):
                if examined_members >= MAX_ARCHIVE_MEMBERS:
                    skipped_members += len(members) - index
                    truncated = True
                    break
                examined_members += 1
                remaining = MAX_LOG_SCAN_BYTES - scanned_bytes
                if remaining <= 0:
                    skipped_members += 1
                    truncated = True
                    continue
                if item.flag_bits & 0x1:
                    skipped_members += 1
                    continue
                with archive.open(item, "r") as handle:
                    sample = handle.read(min(4096, remaining + 1))
                    if not _is_text_content(sample):
                        skipped_members += 1
                        continue
                    data = sample + handle.read(max(0, remaining - len(sample)) + 1)
                if len(data) > remaining:
                    data = data[:remaining]
                    truncated = True
                scanned_members += 1
                scanned_bytes += len(data)
                sources.append((item.filename, data))
    except zipfile.BadZipFile as exc:
        raise OSError("invalid ZIP log archive: {}".format(exc)) from exc
    return sources, truncated, "zip", {
        "archive_members_scanned": scanned_members,
        "archive_members_examined": examined_members,
        "archive_members_skipped": skipped_members,
        "archive_member_limit": MAX_ARCHIVE_MEMBERS,
    }


def _archive_member_priority(filename: str) -> int:
    lowered = filename.lower()
    if lowered.endswith((".txt", ".log", ".csv", ".json", ".xml")):
        return 0
    if any(marker in lowered for marker in ("bugreport", "dumpstate", "logcat", "anr", "tombstone")):
        return 0
    return 1


def _read_bounded(path: Path) -> Tuple[bytes, bool, str]:
    with path.open("rb") as source:
        is_gzip = source.read(2) == b"\x1f\x8b"
    opener = gzip.open if is_gzip else open
    compression = "gzip" if opener is gzip.open else "none"
    with opener(str(path), "rb") as handle:
        data = handle.read(MAX_LOG_SCAN_BYTES + 1)
    return data[:MAX_LOG_SCAN_BYTES], len(data) > MAX_LOG_SCAN_BYTES, compression


def _decode_log(data: bytes) -> Tuple[str, str]:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", errors="replace"), "utf-16"
    return data.decode("utf-8", errors="replace"), "utf-8"


def _is_text_content(data: bytes) -> bool:
    return (
        bool(data)
        and (
            data.startswith((b"\xff\xfe", b"\xfe\xff"))
            or data.count(b"\x00") <= max(4, len(data) // 100)
        )
    )


def _has_managed_owner_path(text: str) -> bool:
    for root_match in re.finditer(r"\bGC Root\s*:", text, re.IGNORECASE):
        report_window = text[root_match.start():root_match.start() + 256 * 1024]
        if (
            re.search(r"\bLeaking:\s*YES\b", report_window, re.IGNORECASE)
            and any(marker in report_window for marker in ("├─", "╰→", "↓"))
        ):
            return True
    return False


def _line_context(line: str) -> Tuple[str, str, bool]:
    threadtime = _THREADTIME_RE.match(line)
    if threadtime:
        return (
            threadtime.group("timestamp"),
            threadtime.group("tag").strip(),
            True,
        )
    brief = _BRIEF_RE.match(line)
    if brief:
        return "", brief.group("tag").strip(), True
    return "", "", False
