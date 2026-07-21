#!/usr/bin/env python3
"""Generate or verify the self-contained android-memory-evidence runtime bundle."""

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Dict, Iterable, Tuple


REPO_ROOT = Path(__file__).resolve().parent.parent
BUNDLE_ROOT = REPO_ROOT / "skills" / "android-memory-evidence" / "runtime"
SKILL_NAMES = (
    "android-memory-evidence",
    "android-memory-diagnose",
    "android-memory-remediate",
)

SOURCE_MAPPINGS: Tuple[Tuple[str, str], ...] = (
    ("android_memory_ai/__init__.py", "android_memory_ai/__init__.py"),
    ("android_memory_ai/catalog.py", "android_memory_ai/catalog.py"),
    ("android_memory_ai/cli.py", "android_memory_ai/cli.py"),
    ("android_memory_ai/context.py", "android_memory_ai/context.py"),
    ("android_memory_ai/contracts.py", "android_memory_ai/contracts.py"),
    ("android_memory_ai/evidence.py", "android_memory_ai/evidence.py"),
    ("android_memory_ai/guidance.py", "android_memory_ai/guidance.py"),
    ("android_memory_ai/render.py", "android_memory_ai/render.py"),
    ("knowledge/android_memory_catalog.json", "knowledge/android_memory_catalog.json"),
)

ENTRYPOINT = b'''#!/usr/bin/env python3
"""Run the bundled Android memory AI context CLI without repository dependencies."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from android_memory_ai.cli import main


if __name__ == "__main__":
    sys.exit(main())
'''


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _expected_assets() -> Dict[Path, bytes]:
    sys.path.insert(0, str(REPO_ROOT))
    from android_memory_ai.contracts import RUNTIME_NAME, RUNTIME_VERSION, SCHEMA_VERSION

    assets = {
        BUNDLE_ROOT / destination: (REPO_ROOT / source).read_bytes()
        for source, destination in SOURCE_MAPPINGS
    }
    assets[BUNDLE_ROOT / "run_ai_context.py"] = ENTRYPOINT

    catalog = json.loads(
        (REPO_ROOT / "knowledge" / "android_memory_catalog.json").read_text(
            encoding="utf-8"
        )
    )
    source_by_destination = {
        destination: source for source, destination in SOURCE_MAPPINGS
    }
    files = []
    for path, content in sorted(assets.items(), key=lambda item: str(item[0])):
        relative = path.relative_to(BUNDLE_ROOT).as_posix()
        entry = {
            "path": relative,
            "sha256": _sha256(content),
        }
        source = source_by_destination.get(relative)
        if source:
            entry["source"] = source
        else:
            entry["source"] = "generated-entrypoint"
        files.append(entry)
    manifest = {
        "bundle_schema_version": "1.0",
        "skill": "android-memory-evidence",
        "minimum_python": "3.8",
        "release_version": (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip(),
        "runtime_name": RUNTIME_NAME,
        "runtime_version": RUNTIME_VERSION,
        "context_schema_version": SCHEMA_VERSION,
        "catalog_id": catalog["catalog_id"],
        "catalog_version": catalog["catalog_version"],
        "files": files,
    }
    assets[BUNDLE_ROOT / "runtime-manifest.json"] = (
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    return assets


def _expected_license_assets() -> Dict[Path, bytes]:
    license_content = (REPO_ROOT / "LICENSE").read_bytes()
    return {
        REPO_ROOT / "skills" / skill_name / "LICENSE": license_content
        for skill_name in SKILL_NAMES
    }


def _unexpected_files(expected: Iterable[Path]) -> Tuple[Path, ...]:
    if not BUNDLE_ROOT.exists():
        return ()
    expected_set = set(expected)
    return tuple(
        path
        for path in BUNDLE_ROOT.rglob("*")
        if path.is_file()
        and path not in expected_set
        and path.suffix != ".pyc"
        and "__pycache__" not in path.parts
    )


def write_bundle() -> int:
    runtime_assets = _expected_assets()
    assets = dict(runtime_assets)
    assets.update(_expected_license_assets())
    for path, content in assets.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    (BUNDLE_ROOT / "run_ai_context.py").chmod(0o755)
    unexpected = _unexpected_files(runtime_assets)
    if unexpected:
        print("Bundle written, but unexpected files remain:", file=sys.stderr)
        for path in unexpected:
            print("  {}".format(path.relative_to(REPO_ROOT)), file=sys.stderr)
        return 1
    print(
        "Synchronized {} bundled runtime and Skill license files.".format(len(assets))
    )
    return 0


def check_bundle() -> int:
    runtime_assets = _expected_assets()
    assets = dict(runtime_assets)
    assets.update(_expected_license_assets())
    problems = []
    for path, expected in assets.items():
        if not path.is_file():
            problems.append("missing {}".format(path.relative_to(REPO_ROOT)))
            continue
        actual = path.read_bytes()
        if actual != expected:
            problems.append("stale {}".format(path.relative_to(REPO_ROOT)))
    for path in _unexpected_files(runtime_assets):
        problems.append("unexpected {}".format(path.relative_to(REPO_ROOT)))
    if problems:
        print("Bundled Skill runtime is not synchronized:", file=sys.stderr)
        for problem in problems:
            print("  {}".format(problem), file=sys.stderr)
        print(
            "Run: python3 scripts/sync_skill_runtime.py --write",
            file=sys.stderr,
        )
        return 1
    print("Bundled Skill runtime matches canonical sources.")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="Regenerate the bundle")
    mode.add_argument("--check", action="store_true", help="Fail when the bundle has drifted")
    args = parser.parse_args(argv)
    return write_bundle() if args.write else check_bundle()


if __name__ == "__main__":
    sys.exit(main())
