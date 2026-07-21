#!/usr/bin/env python3
"""Build an AI context with the bundled runtime or an explicit source checkout."""

import argparse
import subprocess
import sys
from pathlib import Path


def _validate_repo(candidate, source):
    resolved = Path(candidate).expanduser().resolve()
    if (resolved / "analyze.py").is_file() and (resolved / "android_memory_ai").is_dir():
        return resolved
    raise ValueError(
        "{} does not contain analyze.py and android_memory_ai: {}".format(source, resolved)
    )


def _source_checkout(explicit):
    if explicit:
        return _validate_repo(explicit, "--repo")
    return None


def _bundled_entrypoint():
    runtime = Path(__file__).resolve().parents[1] / "runtime"
    entrypoint = runtime / "run_ai_context.py"
    manifest = runtime / "runtime-manifest.json"
    catalog = runtime / "knowledge" / "android_memory_catalog.json"
    if not entrypoint.is_file() or not manifest.is_file() or not catalog.is_file():
        raise ValueError(
            "android-memory-evidence is incomplete: bundled runtime files are missing"
        )
    return entrypoint


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", help="Path to Android-App-Memory-Analysis")
    parser.add_argument("--dump-dir", required=True)
    parser.add_argument("--question", default="")
    parser.add_argument("--intent", default="auto")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    parser.add_argument("--lang", choices=("zh", "en"), default="zh")
    parser.add_argument("--output")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument(
        "--include-local-paths",
        action="store_true",
        help="Expose absolute paths to an authorized local AI",
    )
    args, passthrough = parser.parse_known_args(argv)

    try:
        repo = _source_checkout(args.repo)
        command = [sys.executable]
        if repo:
            command.extend([str(repo / "analyze.py"), "ai-context"])
        else:
            command.append(str(_bundled_entrypoint()))
    except ValueError as exc:
        print("build_context error: {}".format(exc), file=sys.stderr)
        return 1

    command.extend([
        "--dump-dir",
        str(Path(args.dump_dir).expanduser().resolve()),
        "--question",
        args.question,
        "--intent",
        args.intent,
        "--format",
        args.format,
        "--lang",
        args.lang,
    ])
    if args.output:
        command.extend(["--output", str(Path(args.output).expanduser().resolve())])
    if args.strict:
        command.append("--strict")
    if args.include_local_paths:
        command.append("--include-local-paths")
    command.extend(passthrough)
    return subprocess.run(command, check=False).returncode


if __name__ == "__main__":
    sys.exit(main())
