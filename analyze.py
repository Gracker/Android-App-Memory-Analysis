import argparse
import gzip
import os
import subprocess
import sys
import tempfile

# --- Configuration ---
TOOLS_DIR = os.path.join(os.path.dirname(__file__), 'tools')
HPROF_PARSER = os.path.join(TOOLS_DIR, 'hprof_parser.py')
SMAPS_PARSER = os.path.join(TOOLS_DIR, 'smaps_parser.py')
COMBINED_ANALYZER = os.path.join(TOOLS_DIR, 'combined_analyzer.py')
MEMORY_ANALYZER = os.path.join(TOOLS_DIR, 'memory_analyzer.py')
LIVE_DUMPER = os.path.join(TOOLS_DIR, 'live_dumper.py')
MEMINFO_PARSER = os.path.join(TOOLS_DIR, 'meminfo_parser.py')
GFXINFO_PARSER = os.path.join(TOOLS_DIR, 'gfxinfo_parser.py')
PANORAMA_ANALYZER = os.path.join(TOOLS_DIR, 'panorama_analyzer.py')
DIFF_ANALYZER = os.path.join(TOOLS_DIR, 'diff_analyzer.py')
DEMO_HPROF = os.path.join(os.path.dirname(__file__), 'demo', 'hprof_sample', 'heapdump_latest.hprof')
DEMO_HPROF_GZ = os.path.join(os.path.dirname(__file__), 'demo', 'hprof_sample', 'heapdump_latest.hprof.gz')
DEMO_SMAPS = os.path.join(os.path.dirname(__file__), 'demo', 'smaps_sample', 'smaps')
DEMO_MEMINFO = os.path.join(os.path.dirname(__file__), 'demo', 'smaps_sample', 'meminfo.txt')


def resolve_hprof_input(file_path, notice_stream=None):
    if not file_path:
        return None, None, None
    if notice_stream is None:
        notice_stream = sys.stdout

    if not os.path.exists(file_path) and file_path.endswith('.hprof'):
        compressed_path = f"{file_path}.gz"
        if os.path.exists(compressed_path):
            print(f"--- HPROF file not found, using packaged sample: {compressed_path} ---", file=notice_stream)
            file_path = compressed_path

    if file_path.endswith('.gz'):
        if not os.path.exists(file_path):
            print(f"Error: HPROF package not found at '{file_path}'")
            sys.exit(1)

        fd, temp_path = tempfile.mkstemp(prefix='hprof_', suffix='.hprof')
        os.close(fd)
        try:
            with gzip.open(file_path, 'rb') as source, open(temp_path, 'wb') as target:
                while True:
                    chunk = source.read(1024 * 1024)
                    if not chunk:
                        break
                    if isinstance(chunk, str):
                        chunk = chunk.encode('utf-8')
                    target.write(chunk)
        except OSError as error:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            print(f"Error: failed to extract HPROF package '{file_path}': {error}")
            sys.exit(1)

        print(f"--- Decompressed HPROF package: {file_path} ---", file=notice_stream)
        sidecar = f"{os.path.splitext(os.path.basename(temp_path))[0]}_analysis.txt"
        return temp_path, temp_path, sidecar

    return file_path, None, None


def cleanup_temp_hprof(temp_path, sidecar_path=None, remove_sidecar=False):
    if remove_sidecar and sidecar_path and os.path.exists(sidecar_path):
        os.remove(sidecar_path)
    if temp_path and os.path.exists(temp_path):
        os.remove(temp_path)


def default_demo_hprof_path():
    if os.path.exists(DEMO_HPROF_GZ):
        return DEMO_HPROF_GZ
    return DEMO_HPROF

def analyze_hprof(file_path, extra_args=None):
    """Calls the hprof parser script."""
    resolved_hprof, temp_hprof, temp_sidecar = resolve_hprof_input(file_path)
    if not resolved_hprof or not os.path.exists(resolved_hprof):
        print(f"Error: HPROF file not found at '{file_path}'")
        sys.exit(1)

    print(f"--- Analyzing HPROF file: {file_path} ---")
    command = [sys.executable, HPROF_PARSER, '-f', resolved_hprof]
    if extra_args:
        command.extend(extra_args)
    try:
        subprocess.run(command, check=True)
    finally:
        cleanup_temp_hprof(temp_hprof, temp_sidecar, remove_sidecar=True)

def analyze_smaps(file_path):
    """Calls the smaps parser script."""
    if not os.path.exists(file_path):
        print(f"Error: smaps file not found at '{file_path}'")
        sys.exit(1)

    print(f"--- Analyzing smaps file: {file_path} ---")
    command = [sys.executable, SMAPS_PARSER, '-f', file_path]
    subprocess.run(command, check=True)

def analyze_combined_legacy(hprof_file, smaps_file, markdown=False, output=None):
    """Calls the legacy combined analyzer for HPROF + smaps analysis."""
    resolved_hprof, temp_hprof, temp_sidecar = resolve_hprof_input(hprof_file)
    if not resolved_hprof or not os.path.exists(resolved_hprof):
        print(f"Error: HPROF file not found at '{hprof_file}'")
        sys.exit(1)
    if not os.path.exists(smaps_file):
        print(f"Error: smaps file not found at '{smaps_file}'")
        sys.exit(1)

    print(f"--- Combined Analysis: HPROF + smaps ---")
    command = [sys.executable, COMBINED_ANALYZER, '-H', resolved_hprof, '-S', smaps_file]
    if markdown:
        command.append('--markdown')
    if output:
        command.extend(['-o', output])
    try:
        subprocess.run(command, check=True)
    finally:
        cleanup_temp_hprof(temp_hprof, temp_sidecar, remove_sidecar=True)


def analyze_combined_modern(hprof_file=None, smaps_file=None, meminfo_file=None, pid=None,
                            output=None, json_output=None, demo=False):
    """Calls the enhanced combined analyzer (memory_analyzer.py)."""
    if demo:
        if pid:
            print("Error: --demo cannot be used together with -p/--pid")
            sys.exit(1)
        hprof_file = hprof_file or default_demo_hprof_path()
        smaps_file = smaps_file or DEMO_SMAPS
        meminfo_file = meminfo_file or DEMO_MEMINFO
        print("--- Using bundled demo dataset ---")

    resolved_hprof, temp_hprof, temp_sidecar = (None, None, None)
    if hprof_file:
        resolved_hprof, temp_hprof, temp_sidecar = resolve_hprof_input(hprof_file)
    if hprof_file and (not resolved_hprof or not os.path.exists(resolved_hprof)):
        print(f"Error: HPROF file not found at '{hprof_file}'")
        sys.exit(1)
    if smaps_file and not os.path.exists(smaps_file):
        print(f"Error: smaps file not found at '{smaps_file}'")
        sys.exit(1)
    if meminfo_file and not os.path.exists(meminfo_file):
        print(f"Error: meminfo file not found at '{meminfo_file}'")
        sys.exit(1)
    if not hprof_file and not smaps_file and not pid:
        print("Error: enhanced combined mode requires at least one of --hprof, --smaps, or -p/--pid")
        sys.exit(1)

    print("--- Enhanced Combined Analysis (meminfo-aware) ---")
    command = [sys.executable, MEMORY_ANALYZER]
    if resolved_hprof:
        command.extend(['--hprof', resolved_hprof])
    if smaps_file:
        command.extend(['--smaps', smaps_file])
    if meminfo_file:
        command.extend(['--meminfo', meminfo_file])
    if pid:
        command.extend(['-p', str(pid)])
    if output:
        command.extend(['-o', output])
    if json_output:
        command.extend(['--json-output', json_output])

    try:
        subprocess.run(command, check=True)
    finally:
        cleanup_temp_hprof(temp_hprof, temp_sidecar, remove_sidecar=True)


def live_dump(package=None, list_apps=False, output_dir='.', skip_hprof=False, analyze=True):
    """Live dump memory data from connected device."""
    command = [sys.executable, LIVE_DUMPER]

    if list_apps:
        command.append('--list')
        subprocess.run(command, check=True)
        return None

    if not package:
        print("Error: Please specify a package name with --package")
        sys.exit(1)

    command.extend(['--package', package, '-o', output_dir])
    if skip_hprof:
        command.append('--skip-hprof')

    result = subprocess.run(command, capture_output=True, text=True)
    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)

    if result.returncode != 0:
        print("Live dump failed")
        sys.exit(1)

    # 查找生成的目录
    import glob
    pattern = os.path.join(output_dir, f"{package}_*")
    dirs = sorted(glob.glob(pattern), reverse=True)
    if dirs:
        dump_dir = dirs[0]
        print(f"\n数据已保存到: {dump_dir}")

        if analyze:
            process_status = read_live_dump_process_status(dump_dir)
            if process_status == 'not_running':
                print("进程未运行，已跳过 panorama 分析；请查看 exit_info.txt、memory_limiter_status.txt 和 meta.txt。")
                return dump_dir

            # 使用全景分析器进行深度分析
            subprocess.run([sys.executable, PANORAMA_ANALYZER, '-d', dump_dir])

        return dump_dir
    return None


def read_live_dump_process_status(dump_dir):
    """Read ProcessStatus from a live dump meta file, if present."""
    meta_path = os.path.join(dump_dir, 'meta.txt')
    if not os.path.exists(meta_path):
        return None

    with open(meta_path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.startswith('ProcessStatus:'):
                return line.split(':', 1)[1].strip()
    return None


def analyze_meminfo(file_path):
    """Analyze meminfo file."""
    if not os.path.exists(file_path):
        print(f"Error: meminfo file not found at '{file_path}'")
        sys.exit(1)
    subprocess.run([sys.executable, MEMINFO_PARSER, file_path], check=True)


def analyze_gfxinfo(file_path):
    """Analyze gfxinfo file."""
    if not os.path.exists(file_path):
        print(f"Error: gfxinfo file not found at '{file_path}'")
        sys.exit(1)
    subprocess.run([sys.executable, GFXINFO_PARSER, file_path], check=True)


def analyze_panorama(dump_dir=None, meminfo=None, gfxinfo=None, hprof=None, smaps=None,
                     proc_meminfo=None, dmabuf=None, zram_swap=None,
                     output_json=False, output_markdown=False, output_file=None):
    """Full panorama analysis with multiple data sources."""
    command = [sys.executable, PANORAMA_ANALYZER]
    resolved_hprof, temp_hprof, temp_sidecar = (hprof, None, None)
    if hprof:
        notice_stream = sys.stderr if output_json and not output_file else sys.stdout
        resolved_hprof, temp_hprof, temp_sidecar = resolve_hprof_input(hprof, notice_stream=notice_stream)
        if not resolved_hprof or not os.path.exists(resolved_hprof):
            print(f"Error: HPROF file not found at '{hprof}'")
            sys.exit(1)

    if dump_dir:
        command.extend(['-d', dump_dir])
    if meminfo:
        command.extend(['-m', meminfo])
    if gfxinfo:
        command.extend(['-g', gfxinfo])
    if resolved_hprof:
        command.extend(['-H', resolved_hprof])
    if smaps:
        command.extend(['-S', smaps])
    if proc_meminfo:
        command.extend(['-P', proc_meminfo])
    if dmabuf:
        command.extend(['-D', dmabuf])
    if zram_swap:
        command.extend(['-Z', zram_swap])

    if output_json:
        command.append('--json')
    if output_markdown:
        command.append('--markdown')
    if output_file:
        command.extend(['-o', output_file])

    try:
        subprocess.run(command, check=True)
    finally:
        cleanup_temp_hprof(temp_hprof, temp_sidecar, remove_sidecar=True)


def analyze_diff(before_dir=None, after_dir=None, before_meminfo=None, after_meminfo=None,
                 threshold=20.0, output_json=False, output_file=None):
    """Compare two memory dumps."""
    command = [sys.executable, DIFF_ANALYZER]

    if before_dir:
        command.extend(['-b', before_dir])
    if after_dir:
        command.extend(['-a', after_dir])
    if before_meminfo:
        command.extend(['--before-meminfo', before_meminfo])
    if after_meminfo:
        command.extend(['--after-meminfo', after_meminfo])
    if threshold != 20.0:
        command.extend(['--threshold', str(threshold)])
    if output_json:
        command.append('--json')
    if output_file:
        command.extend(['-o', output_file])

    subprocess.run(command, check=True)


def build_ai_evidence_context(args):
    """Build the provider-neutral AI evidence context through the focused CLI."""
    command = [sys.executable, os.path.join(TOOLS_DIR, 'ai_context.py'), '-d', args.dump_dir]
    passthrough = {
        '--intent': args.intent,
        '--question': args.question,
        '--format': args.format,
        '--lang': args.lang,
        '--output': args.output,
        '--meminfo': args.meminfo,
        '--smaps': args.smaps,
        '--showmap': args.showmap,
        '--hprof': args.hprof,
        '--gfxinfo': args.gfxinfo,
        '--proc-meminfo': args.proc_meminfo,
        '--pressure-memory': args.pressure_memory,
        '--zram': args.zram,
        '--dmabuf': args.dmabuf,
        '--exit-info': args.exit_info,
        '--analysis-report': args.analysis_report,
        '--comparison-report': args.comparison_report,
        '--perfetto-trace': args.perfetto_trace,
        '--native-heap-profile': args.native_heap_profile,
        '--phase-metadata': args.phase_metadata,
        '--device-context': args.device_context,
        '--package': args.package,
        '--pid': args.pid,
        '--android-release': args.android_release,
        '--android-sdk': args.android_sdk,
        '--build-fingerprint': args.build_fingerprint,
        '--page-size': args.page_size,
        '--phase': args.phase,
    }
    for option, value in passthrough.items():
        if value not in (None, ''):
            command.extend([option, str(value)])
    if args.strict:
        command.append('--strict')
    if args.hash_large_files:
        command.append('--hash-large-files')
    if args.include_local_paths:
        command.append('--include-local-paths')
    result = subprocess.run(command, check=False)
    if result.returncode:
        sys.exit(result.returncode)


def main():
    """Main function to parse arguments and dispatch commands."""
    parser = argparse.ArgumentParser(
        description="Android 内存分析统一工具",
        epilog="""示例:
  # 从手机一键 dump 并分析
  python3 analyze.py live --list                          # 列出运行中的应用
  python3 analyze.py live --package com.example.app       # dump 并分析
  python3 analyze.py live --package com.example.app --skip-hprof  # 快速模式

  # 分析本地文件
  python3 analyze.py hprof demo/hprof_sample/heapdump_latest.hprof.gz
  python3 analyze.py smaps demo/smaps_sample/smaps
  python3 analyze.py meminfo dump/meminfo.txt
  python3 analyze.py gfxinfo dump/gfxinfo.txt

  # 全景分析（多数据源关联）
  python3 analyze.py panorama -d /tmp/com.example.app_20231225_120000
  python3 analyze.py panorama -m meminfo.txt -g gfxinfo.txt

  # 内存对比分析
  python3 analyze.py diff -b ./dump_before -a ./dump_after
  python3 analyze.py diff --before-meminfo m1.txt --after-meminfo m2.txt

  # 传统联合分析
  python3 analyze.py combined -H demo/hprof.hprof -S demo/smaps.txt

  # 增强联合分析（支持 meminfo/mtrack）
  python3 analyze.py combined --hprof demo/hprof_sample/heapdump_latest.hprof.gz --smaps demo/smaps_sample/smaps --meminfo demo/smaps_sample/meminfo.txt --json-output report.json
  python3 analyze.py combined --demo --json-output demo_report.json

  # 构建供 AI 项目使用的校验证据上下文（不调用外部模型）
  python3 analyze.py ai-context -d ./dump --question "Native memory keeps growing" --format markdown
""",
        formatter_class=argparse.RawTextHelpFormatter
    )

    subparsers = parser.add_subparsers(dest='command', required=True, help='可用命令')

    # Live dump command
    live_parser = subparsers.add_parser('live', help='从手机实时 dump 并分析内存数据')
    live_parser.add_argument('-l', '--list', action='store_true', help='列出运行中的应用')
    live_parser.add_argument('-p', '--package', type=str, help='目标应用包名')
    live_parser.add_argument('-o', '--output', type=str, default='.', help='输出目录')
    live_parser.add_argument('--skip-hprof', action='store_true', help='跳过 hprof dump（更快）')
    live_parser.add_argument('--dump-only', action='store_true', help='只 dump 不分析')

    # HPROF command
    hprof_parser = subparsers.add_parser('hprof', help='分析 .hprof 文件 (Java 堆)')
    hprof_parser.add_argument('file', type=str, help='HPROF 文件路径')
    hprof_parser.add_argument('--markdown', action='store_true', help='输出 Markdown 格式')
    hprof_parser.add_argument('--compare', metavar='FILE2', help='与另一个 HPROF 文件对比')

    # SMAPS command
    smaps_parser_cmd = subparsers.add_parser('smaps', help='分析 smaps 文件 (Native 内存)')
    smaps_parser_cmd.add_argument('file', type=str, help='smaps 文件路径')

    # Meminfo command
    meminfo_parser_cmd = subparsers.add_parser('meminfo', help='分析 dumpsys meminfo 输出')
    meminfo_parser_cmd.add_argument('file', type=str, help='meminfo 文件路径')

    # Gfxinfo command
    gfxinfo_parser_cmd = subparsers.add_parser('gfxinfo', help='分析 dumpsys gfxinfo 输出')
    gfxinfo_parser_cmd.add_argument('file', type=str, help='gfxinfo 文件路径')

    # Panorama command (multi-source deep analysis)
    panorama_parser = subparsers.add_parser('panorama', help='全景分析（多数据源深度关联）')
    panorama_parser.add_argument('-d', '--dump-dir', help='dump 目录（自动查找文件）')
    panorama_parser.add_argument('-m', '--meminfo', help='meminfo 文件路径')
    panorama_parser.add_argument('-g', '--gfxinfo', help='gfxinfo 文件路径')
    panorama_parser.add_argument('-H', '--hprof', help='HPROF 文件路径')
    panorama_parser.add_argument('-S', '--smaps', help='smaps 文件路径')
    panorama_parser.add_argument('-P', '--proc-meminfo', help='/proc/meminfo 文件路径')
    panorama_parser.add_argument('-D', '--dmabuf', help='DMA-BUF debug 文件路径')
    panorama_parser.add_argument('-Z', '--zram-swap', help='zRAM/Swap 数据文件路径')
    panorama_parser.add_argument('--json', action='store_true', help='输出 JSON 格式')
    panorama_parser.add_argument('--markdown', '-md', action='store_true', help='输出 Markdown 格式')
    panorama_parser.add_argument('-o', '--output', help='输出文件路径')

    # Diff command
    diff_parser = subparsers.add_parser('diff', help='内存对比分析（比较两次 dump）')
    diff_parser.add_argument('-b', '--before', help='前一次 dump 目录')
    diff_parser.add_argument('-a', '--after', help='后一次 dump 目录')
    diff_parser.add_argument('--before-meminfo', help='前一次 meminfo 文件')
    diff_parser.add_argument('--after-meminfo', help='后一次 meminfo 文件')
    diff_parser.add_argument('--threshold', type=float, default=20.0,
                             help='警告阈值（增长百分比，默认 20%%）')
    diff_parser.add_argument('--json', action='store_true', help='输出 JSON 格式')
    diff_parser.add_argument('-o', '--output', help='输出文件路径')

    # Combined command
    combined_parser = subparsers.add_parser(
        'combined',
        help='联合分析（传统 HPROF+smaps，或增强模式支持 meminfo/pid/demo）'
    )
    combined_parser.add_argument('-H', '--hprof', help='HPROF 文件路径')
    combined_parser.add_argument('-S', '--smaps', help='smaps 文件路径')
    combined_parser.add_argument('-m', '--meminfo', help='meminfo 文件路径（增强模式）')
    combined_parser.add_argument('-p', '--pid', help='进程 PID（增强模式，自动抓取 smaps/meminfo）')
    combined_parser.add_argument('--demo', action='store_true', help='使用内置 demo 数据（增强模式）')
    combined_parser.add_argument('--json-output', help='JSON 输出文件（增强模式）')
    combined_parser.add_argument('--modern', action='store_true', help='强制使用增强模式')
    combined_parser.add_argument('--markdown', action='store_true', help='输出 Markdown 格式（传统模式）')
    combined_parser.add_argument('-o', '--output', help='输出文件路径')

    # Provider-neutral AI evidence context
    ai_parser = subparsers.add_parser(
        'ai-context',
        help='构建可供 AI 使用的校验证据上下文（不调用外部模型）'
    )
    ai_parser.add_argument('-d', '--dump-dir', required=True, help='dump/证据目录')
    ai_parser.add_argument(
        '--intent',
        default='auto',
        help='分析意图；auto 根据问题推断，具体取值由 ai_context.py 的唯一注册表校验'
    )
    ai_parser.add_argument('--question', default='', help='用户问题或症状描述')
    ai_parser.add_argument('--format', choices=['json', 'markdown'], default='json')
    ai_parser.add_argument('--lang', choices=['zh', 'en'], default='zh')
    ai_parser.add_argument('-o', '--output', help='输出文件；默认 stdout')
    ai_parser.add_argument('--strict', action='store_true', help='必需证据不完整时返回 exit code 2')
    ai_parser.add_argument('--hash-large-files', action='store_true', help='计算超过 512 MiB 文件的 SHA-256')
    ai_parser.add_argument(
        '--include-local-paths',
        action='store_true',
        help='包含本机绝对路径；仅供已授权的本地 AI 使用'
    )
    ai_parser.add_argument('-m', '--meminfo')
    ai_parser.add_argument('-S', '--smaps')
    ai_parser.add_argument('--showmap')
    ai_parser.add_argument('-H', '--hprof')
    ai_parser.add_argument('-g', '--gfxinfo')
    ai_parser.add_argument('-P', '--proc-meminfo')
    ai_parser.add_argument('--pressure-memory')
    ai_parser.add_argument('-Z', '--zram')
    ai_parser.add_argument('-D', '--dmabuf')
    ai_parser.add_argument('--exit-info')
    ai_parser.add_argument('--analysis-report')
    ai_parser.add_argument('--comparison-report')
    ai_parser.add_argument('--perfetto-trace')
    ai_parser.add_argument('--native-heap-profile')
    ai_parser.add_argument('--phase-metadata')
    ai_parser.add_argument('--device-context')
    ai_parser.add_argument('--package')
    ai_parser.add_argument('--pid')
    ai_parser.add_argument('--android-release')
    ai_parser.add_argument('--android-sdk')
    ai_parser.add_argument('--build-fingerprint')
    ai_parser.add_argument('--page-size')
    ai_parser.add_argument('--phase')

    args = parser.parse_args()

    if args.command == 'live':
        live_dump(
            package=args.package,
            list_apps=args.list,
            output_dir=args.output,
            skip_hprof=args.skip_hprof,
            analyze=not args.dump_only
        )
    elif args.command == 'hprof':
        extra_args = []
        if args.markdown:
            extra_args.append('--markdown')
        if args.compare:
            extra_args.extend(['--compare', args.compare])
        analyze_hprof(args.file, extra_args if extra_args else None)
    elif args.command == 'smaps':
        analyze_smaps(args.file)
    elif args.command == 'meminfo':
        analyze_meminfo(args.file)
    elif args.command == 'gfxinfo':
        analyze_gfxinfo(args.file)
    elif args.command == 'panorama':
        analyze_panorama(
            dump_dir=args.dump_dir,
            meminfo=args.meminfo,
            gfxinfo=args.gfxinfo,
            hprof=args.hprof,
            smaps=args.smaps,
            proc_meminfo=args.proc_meminfo,
            dmabuf=args.dmabuf,
            zram_swap=args.zram_swap,
            output_json=args.json,
            output_markdown=args.markdown,
            output_file=args.output
        )
    elif args.command == 'diff':
        analyze_diff(
            before_dir=args.before,
            after_dir=args.after,
            before_meminfo=args.before_meminfo,
            after_meminfo=args.after_meminfo,
            threshold=args.threshold,
            output_json=args.json,
            output_file=args.output
        )
    elif args.command == 'combined':
        use_modern_mode = bool(
            args.modern or args.meminfo or args.pid or args.json_output or args.demo
        )
        if use_modern_mode:
            if args.markdown:
                print("Warning: --markdown is ignored in enhanced combined mode")
            analyze_combined_modern(
                hprof_file=args.hprof,
                smaps_file=args.smaps,
                meminfo_file=args.meminfo,
                pid=args.pid,
                output=args.output,
                json_output=args.json_output,
                demo=args.demo,
            )
        else:
            if not args.hprof or not args.smaps:
                print("Error: legacy combined mode requires both -H/--hprof and -S/--smaps")
                print("Hint: add --modern or provide --meminfo/--pid/--demo to use enhanced mode")
                sys.exit(1)
            analyze_combined_legacy(args.hprof, args.smaps, args.markdown, args.output)
    elif args.command == 'ai-context':
        build_ai_evidence_context(args)

    json_stdout = (
        (args.command == 'panorama' and args.json and not args.output) or
        (args.command == 'diff' and args.json and not args.output) or
        (args.command == 'ai-context' and not args.output)
    )
    if not json_stdout:
        print("\n--- Analysis complete. ---")

if __name__ == '__main__':
    try:
        main()
    except subprocess.CalledProcessError as e:
        print(f"An error occurred while running the analysis script: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        sys.exit(1)
