"""Command-line interface for the provider-neutral Android memory AI context."""

import argparse
import sys
from pathlib import Path

from .context import build_ai_context
from .contracts import RUNTIME_NAME, RUNTIME_VERSION
from .guidance import INTENT_PROFILES
from .render import render_json, render_markdown


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a validated Android memory evidence context for AI analysis.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="{} {}".format(RUNTIME_NAME, RUNTIME_VERSION),
    )
    parser.add_argument("-d", "--dump-dir", required=True, help="Dump/evidence directory")
    parser.add_argument(
        "--intent",
        default="auto",
        choices=["auto"] + sorted(INTENT_PROFILES),
        help="Analysis intent; auto infers from --question",
    )
    parser.add_argument("--question", default="", help="User question or symptom description")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    parser.add_argument("--lang", choices=("zh", "en"), default="zh")
    parser.add_argument("-o", "--output", help="Output path; defaults to stdout")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit 2 when required evidence is incomplete",
    )
    parser.add_argument(
        "--hash-large-files",
        action="store_true",
        help="Hash artifacts larger than 512 MiB (can be slow)",
    )
    parser.add_argument(
        "--include-local-paths",
        action="store_true",
        help="Include absolute local artifact paths; use only for an authorized local AI",
    )

    artifact_group = parser.add_argument_group("explicit artifact overrides")
    artifact_group.add_argument("-m", "--meminfo")
    artifact_group.add_argument("-S", "--smaps")
    artifact_group.add_argument("--showmap")
    artifact_group.add_argument("-H", "--hprof")
    artifact_group.add_argument("-g", "--gfxinfo")
    artifact_group.add_argument("-P", "--proc-meminfo")
    artifact_group.add_argument("--pressure-memory")
    artifact_group.add_argument("-Z", "--zram")
    artifact_group.add_argument("-D", "--dmabuf")
    artifact_group.add_argument("--exit-info")
    artifact_group.add_argument("--analysis-report")
    artifact_group.add_argument("--comparison-report")
    artifact_group.add_argument("--perfetto-trace")
    artifact_group.add_argument("--native-heap-profile")
    artifact_group.add_argument("--phase-metadata")
    artifact_group.add_argument("--device-context")

    subject_group = parser.add_argument_group("subject overrides")
    subject_group.add_argument("--package")
    subject_group.add_argument("--pid")
    subject_group.add_argument("--android-release")
    subject_group.add_argument("--android-sdk")
    subject_group.add_argument("--build-fingerprint")
    subject_group.add_argument("--page-size")
    subject_group.add_argument("--phase")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    artifact_overrides = {
        "meminfo": args.meminfo,
        "smaps": args.smaps,
        "showmap": args.showmap,
        "hprof": args.hprof,
        "gfxinfo": args.gfxinfo,
        "proc_meminfo": args.proc_meminfo,
        "pressure_memory": args.pressure_memory,
        "zram": args.zram,
        "dmabuf": args.dmabuf,
        "exit_info": args.exit_info,
        "analysis_report": args.analysis_report,
        "comparison_report": args.comparison_report,
        "perfetto_trace": args.perfetto_trace,
        "native_heap_profile": args.native_heap_profile,
        "phase_metadata": args.phase_metadata,
        "device_context": args.device_context,
    }
    artifact_overrides = {key: value for key, value in artifact_overrides.items() if value}
    subject_overrides = {
        "package": args.package,
        "pid": args.pid,
        "android_release": args.android_release,
        "android_sdk": args.android_sdk,
        "build_fingerprint": args.build_fingerprint,
        "page_size": args.page_size,
        "phase": args.phase,
    }
    subject_overrides = {
        key: value for key, value in subject_overrides.items() if value not in (None, "")
    }

    try:
        context = build_ai_context(
            root=Path(args.dump_dir),
            intent=args.intent,
            question=args.question,
            artifact_overrides=artifact_overrides,
            subject_overrides=subject_overrides,
            hash_large_files=args.hash_large_files,
            include_local_paths=args.include_local_paths,
        )
    except (OSError, ValueError) as exc:
        print("ai-context error: {}".format(exc), file=sys.stderr)
        return 1

    output = render_json(context) if args.format == "json" else render_markdown(context, args.lang)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output, encoding="utf-8")
    else:
        sys.stdout.write(output)

    if args.strict and context["analysis_contract"]["support_level"] == "insufficient":
        return 2
    return 0
