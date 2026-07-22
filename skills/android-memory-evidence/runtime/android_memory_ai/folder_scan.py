"""Bounded recursive inventory for user-supplied QA evidence folders."""

import os
from pathlib import Path
from typing import Any, Dict, List, Tuple


MAX_INDEXED_FILES = 2048
EXCLUDED_DIRECTORY_NAMES = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    "node_modules",
}
EXCLUDED_FILE_NAMES = {".DS_Store"}


def scan_evidence_tree(root: Path) -> Tuple[List[Path], Dict[str, Any]]:
    """Return a deterministic file list and explicit scan-boundary metadata."""
    root = Path(root).resolve()
    indexed: List[Path] = []
    total_files = 0
    total_bytes = 0
    skipped_symlinks = 0
    unreadable_entries = 0
    excluded_directories = 0
    extension_counts: Dict[str, int] = {}

    def record_walk_error(_error: OSError) -> None:
        nonlocal unreadable_entries
        unreadable_entries += 1

    for directory, directory_names, file_names in os.walk(
        str(root), followlinks=False, onerror=record_walk_error
    ):
        directory_names.sort()
        file_names.sort()
        kept_directories = []
        for name in directory_names:
            path = Path(directory) / name
            if name in EXCLUDED_DIRECTORY_NAMES:
                excluded_directories += 1
            elif path.is_symlink():
                skipped_symlinks += 1
            else:
                kept_directories.append(name)
        directory_names[:] = kept_directories

        for name in file_names:
            if name in EXCLUDED_FILE_NAMES:
                continue
            path = Path(directory) / name
            if path.is_symlink():
                skipped_symlinks += 1
                continue
            try:
                if not path.is_file():
                    continue
                size = path.stat().st_size
            except OSError:
                unreadable_entries += 1
                continue
            total_files += 1
            total_bytes += size
            extension = _extension(path)
            extension_counts[extension] = extension_counts.get(extension, 0) + 1
            if len(indexed) < MAX_INDEXED_FILES:
                indexed.append(path)

    return indexed, {
        "scan_mode": "recursive-content-aware",
        "total_files": total_files,
        "indexed_files": len(indexed),
        "total_bytes": total_bytes,
        "file_limit": MAX_INDEXED_FILES,
        "index_truncated": total_files > len(indexed),
        "skipped_symlinks": skipped_symlinks,
        "unreadable_entries": unreadable_entries,
        "excluded_directories": excluded_directories,
        "excluded_directory_names": sorted(EXCLUDED_DIRECTORY_NAMES),
        "extension_counts": {
            key: extension_counts[key] for key in sorted(extension_counts)
        },
    }


def summarize_inventory(
    scan: Dict[str, Any],
    artifacts: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Add classification outcomes without exposing raw file contents."""
    unclassified = [
        artifact for artifact in artifacts
        if artifact.get("artifact_type") == "unclassified_file"
    ]
    represented = {}
    for artifact in artifacts:
        path = artifact.get("path")
        if (
            not path
            or str(path).startswith("<external>/")
            or artifact.get("status") == "missing"
        ):
            continue
        current = represented.setdefault(path, {"hashed": False, "size_bytes": 0})
        current["hashed"] = current["hashed"] or bool(artifact.get("sha256"))
        current["size_bytes"] = max(
            current["size_bytes"], artifact.get("size_bytes") or 0
        )
    return {
        **scan,
        "represented_paths": len(represented),
        "unclassified_files": len(unclassified),
        "hashed_files": sum(1 for item in represented.values() if item["hashed"]),
        "unhashed_files": sum(1 for item in represented.values() if not item["hashed"]),
        "hashed_bytes": sum(
            item["size_bytes"] for item in represented.values() if item["hashed"]
        ),
        "all_indexed_files_represented": (
            not scan["index_truncated"]
            and len(represented) >= scan["indexed_files"]
        ),
    }


def _extension(path: Path) -> str:
    suffixes = "".join(path.suffixes).lower()
    return suffixes or "<none>"
