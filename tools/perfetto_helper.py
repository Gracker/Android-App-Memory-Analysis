#!/usr/bin/env python3
# -*- coding:utf-8 -*-
"""
Perfetto 追踪助手

提供 Perfetto 配置生成、追踪启动/停止、基础分析功能。

功能:
1. 生成内存追踪配置 (heapprofd, process_stats, memory counters)
2. 启动/停止追踪
3. 拉取 trace 文件
4. 使用 trace_processor 进行基础分析
"""

import argparse
import base64
import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.android_shell_utils import run_adb_command

# Perfetto 工具路径
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PERFETTO_TOOLS_DIR = os.path.join(SCRIPT_DIR, 'perfetto-mac-arm64')
TRACE_PROCESSOR = os.path.join(PERFETTO_TOOLS_DIR, 'trace_processor_shell')


@dataclass
class PerfettoConfig:
    """Perfetto 配置"""
    package: str = ""
    duration_ms: int = 30000
    buffer_size_kb: int = 64000

    # 启用的数据源
    enable_heapprofd: bool = True
    enable_process_stats: bool = True
    enable_memory_counters: bool = True
    enable_ftrace: bool = False

    # Heapprofd 配置
    heapprofd_sampling_interval: int = 4096  # 采样间隔 (bytes)
    heapprofd_all_heaps: bool = True

    # Process stats 配置
    process_stats_poll_ms: int = 1000


def generate_config(config: PerfettoConfig) -> str:
    """生成 Perfetto 配置文件内容 (protobuf text format)"""
    lines = []

    # Buffer 配置
    lines.append("buffers {")
    lines.append(f"  size_kb: {config.buffer_size_kb}")
    lines.append("  fill_policy: RING_BUFFER")
    lines.append("}")
    lines.append("")

    # 持续时间
    lines.append(f"duration_ms: {config.duration_ms}")
    lines.append("")

    # Heapprofd 数据源
    if config.enable_heapprofd and config.package:
        lines.append("# Heapprofd - Native 堆内存追踪")
        lines.append("data_sources {")
        lines.append('  config {')
        lines.append('    name: "android.heapprofd"')
        lines.append('    target_buffer: 0')
        lines.append('    heapprofd_config {')
        lines.append(f'      sampling_interval_bytes: {config.heapprofd_sampling_interval}')
        lines.append(f'      process_cmdline: "{config.package}"')
        if config.heapprofd_all_heaps:
            lines.append('      all_heaps: true')
        lines.append('      shmem_size_bytes: 8388608')
        lines.append('      block_client: true')
        lines.append('    }')
        lines.append('  }')
        lines.append('}')
        lines.append("")

    # Process stats 数据源
    if config.enable_process_stats:
        lines.append("# Process Stats - 进程统计信息")
        lines.append("data_sources {")
        lines.append('  config {')
        lines.append('    name: "linux.process_stats"')
        lines.append('    target_buffer: 0')
        lines.append('    process_stats_config {')
        lines.append(f'      proc_stats_poll_ms: {config.process_stats_poll_ms}')
        lines.append('      scan_all_processes_on_start: true')
        lines.append('    }')
        lines.append('  }')
        lines.append('}')
        lines.append("")

    # Memory counters 数据源 (sys.mem)
    if config.enable_memory_counters:
        lines.append("# Memory Counters - 系统内存计数器")
        lines.append("data_sources {")
        lines.append('  config {')
        lines.append('    name: "linux.sys_stats"')
        lines.append('    target_buffer: 0')
        lines.append('    sys_stats_config {')
        lines.append('      meminfo_period_ms: 1000')
        lines.append('      meminfo_counters: MEMINFO_MEM_TOTAL')
        lines.append('      meminfo_counters: MEMINFO_MEM_FREE')
        lines.append('      meminfo_counters: MEMINFO_MEM_AVAILABLE')
        lines.append('      meminfo_counters: MEMINFO_BUFFERS')
        lines.append('      meminfo_counters: MEMINFO_CACHED')
        lines.append('      meminfo_counters: MEMINFO_SWAP_CACHED')
        lines.append('      meminfo_counters: MEMINFO_ACTIVE')
        lines.append('      meminfo_counters: MEMINFO_INACTIVE')
        lines.append('      vmstat_period_ms: 1000')
        lines.append('      vmstat_counters: VMSTAT_NR_FREE_PAGES')
        lines.append('      vmstat_counters: VMSTAT_NR_SLAB_RECLAIMABLE')
        lines.append('      vmstat_counters: VMSTAT_NR_SLAB_UNRECLAIMABLE')
        lines.append('    }')
        lines.append('  }')
        lines.append('}')
        lines.append("")

    # Ftrace 数据源 (可选，用于更详细的追踪)
    if config.enable_ftrace:
        lines.append("# Ftrace - 内核追踪事件")
        lines.append("data_sources {")
        lines.append('  config {')
        lines.append('    name: "linux.ftrace"')
        lines.append('    target_buffer: 0')
        lines.append('    ftrace_config {')
        lines.append('      ftrace_events: "mm_event/mm_event_record"')
        lines.append('      ftrace_events: "kmem/rss_stat"')
        lines.append('      ftrace_events: "ion/ion_heap_grow"')
        lines.append('      ftrace_events: "ion/ion_heap_shrink"')
        lines.append('    }')
        lines.append('  }')
        lines.append('}')
        lines.append("")

    return "\n".join(lines)


def run_adb(args: List[str], timeout: int = 60) -> tuple[str, int, str]:
    return run_adb_command('adb', args, timeout=timeout)


def check_device():
    """检查设备连接"""
    output, return_code, error = run_adb(['devices'], timeout=15)
    if return_code != 0:
        print(f"错误: adb devices 执行失败: {error or '无详细错误信息'}")
        return False
    lines = output.strip().split('\n')
    devices = [l for l in lines[1:] if l.strip() and 'device' in l]
    if not devices:
        print("错误: 没有检测到 Android 设备")
        print("请确保设备已连接并启用 USB 调试")
        return False
    return True


def push_config(config_content: str, remote_path: str = '/data/local/tmp/perfetto_config.pbtxt') -> bool:
    """推送配置文件到设备"""
    local_path = '/tmp/perfetto_config.pbtxt'
    with open(local_path, 'w') as f:
        f.write(config_content)

    _, return_code, error = run_adb(['push', local_path, remote_path], timeout=30)
    if return_code != 0:
        print(f"错误: 推送配置文件失败: {error or '无详细错误信息'}")
        return False

    run_adb(['shell', f'chmod 644 {remote_path}'], timeout=15)
    return True


def start_trace(config: PerfettoConfig, output_path: str = '/data/misc/perfetto-traces/trace.perfetto', use_root: bool = True) -> bool:
    """启动 Perfetto 追踪"""
    print(f"正在启动 Perfetto 追踪...")
    print(f"  目标进程: {config.package or '全部'}")
    print(f"  持续时间: {config.duration_ms / 1000:.0f} 秒")

    duration_sec = config.duration_ms // 1000

    # 构建简单命令行参数 (避免配置文件权限问题)
    # 对于基本的内存追踪，使用预设的 atrace 类别
    categories = []

    if config.enable_process_stats:
        categories.append('am')  # Activity Manager
        categories.append('pm')  # Package Manager

    if config.enable_memory_counters:
        categories.append('ss')  # System stats

    # 构建 perfetto 命令
    root_prefix = 'su 0 ' if use_root else ''

    if categories:
        categories_str = ' '.join(categories)
        cmd_str = f'{root_prefix}perfetto -o {output_path} -t {duration_sec}s {categories_str}'
    else:
        # 只使用 sched 作为最小追踪
        cmd_str = f'{root_prefix}perfetto -o {output_path} -t {duration_sec}s sched'

    # 如果需要 heapprofd，需要使用配置文件方式
    if config.enable_heapprofd and config.package:
        print("注意: heapprofd 需要配置文件方式，尝试使用完整配置...")
        config_content = generate_config(config)

        # 使用 base64 编码传递配置，避免文件权限问题
        config_b64 = base64.b64encode(config_content.encode()).decode()

        cmd_str = f'{root_prefix}sh -c \'echo "{config_b64}" | base64 -d | perfetto -c - -o {output_path}\''

    print(f"  命令: {cmd_str}")
    timeout = max(duration_sec + 60, 90)
    stdout, return_code, stderr = run_adb(['shell', cmd_str], timeout=timeout)
    output = stderr or stdout

    if return_code != 0:
        if use_root:
            print("尝试不使用 root...")
            return start_trace(config, output_path, use_root=False)

        print(f"错误: 启动追踪失败")
        print(f"  输出: {output}")
        return False

    # 检查输出中是否有成功信息
    if 'Wrote' in output:
        # 解析写入的字节数
        match = re.search(r'Wrote (\d+) bytes', output)
        if match:
            bytes_written = int(match.group(1))
            print(f"追踪完成，写入 {bytes_written / 1024:.1f} KB")
        else:
            print(f"追踪完成")
    elif 'Connected' in output:
        print(f"追踪已启动，等待完成...")
    else:
        print(f"追踪命令已执行")

    print(f"追踪文件: {output_path}")
    return True


def stop_trace() -> bool:
    """停止 Perfetto 追踪"""
    print("正在停止 Perfetto 追踪...")

    run_adb(['shell', 'pkill -SIGINT perfetto'], timeout=15)

    time.sleep(2)

    output, _, _ = run_adb(['shell', 'pgrep perfetto'], timeout=15)
    if output.strip():
        print("警告: Perfetto 进程仍在运行，尝试强制停止...")
        run_adb(['shell', 'pkill -9 perfetto'], timeout=15)

    print("追踪已停止")
    return True


def pull_trace(remote_path: str = '/data/local/tmp/trace.perfetto',
               local_path: Optional[str] = None) -> Optional[str]:
    """从设备拉取 trace 文件"""
    if local_path is None:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        local_path = f'trace_{timestamp}.perfetto'

    print(f"正在拉取追踪文件...")
    _, return_code, error = run_adb(['pull', remote_path, local_path], timeout=180)

    if return_code != 0:
        print(f"错误: 拉取追踪文件失败: {error or '无详细错误信息'}")
        return None

    # 获取文件大小
    size = os.path.getsize(local_path)
    print(f"追踪文件已保存: {local_path} ({size / 1024 / 1024:.1f} MB)")
    return local_path


def run_trace_query(trace_path: str, sql: str) -> tuple[bool, str]:
    """执行 trace_processor SQL 查询"""
    # 使用 -q 参数传递 SQL 查询
    # 创建临时 SQL 文件
    with tempfile.NamedTemporaryFile(mode='w', suffix='.sql', delete=False) as f:
        f.write(sql.strip() + '\n')
        sql_file = f.name

    try:
        cmd = [TRACE_PROCESSOR, trace_path, '-q', sql_file]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.returncode == 0, result.stdout.strip()
    finally:
        os.unlink(sql_file)


def analyze_trace(trace_path: str, query: Optional[str] = None) -> bool:
    """使用 trace_processor 分析 trace 文件"""
    if not os.path.exists(TRACE_PROCESSOR):
        print(f"错误: trace_processor 未找到: {TRACE_PROCESSOR}")
        print("请确保 perfetto-mac-arm64 目录包含 trace_processor_shell")
        return False

    if not os.path.exists(trace_path):
        print(f"错误: trace 文件不存在: {trace_path}")
        return False

    # 确保 trace_processor 可执行
    os.chmod(TRACE_PROCESSOR, 0o755)

    if query:
        # 执行指定的 SQL 查询
        success, output = run_trace_query(trace_path, query)
        if success:
            print(output)
        else:
            print(f"查询失败")
        return success

    # 默认查询: 各种可用数据
    default_queries = [
        ("追踪概览", """
SELECT
    'Duration' as metric,
    CAST((SELECT MAX(ts) - MIN(ts) FROM slice) / 1000000000.0 AS TEXT) || ' seconds' as value
UNION ALL
SELECT
    'Processes' as metric,
    CAST(COUNT(*) AS TEXT) as value
FROM process WHERE pid > 0
UNION ALL
SELECT
    'Threads' as metric,
    CAST(COUNT(*) AS TEXT) as value
FROM thread WHERE tid > 0;
        """),
        ("进程信息", """
SELECT
    pid,
    name
FROM process
WHERE pid > 0 AND name IS NOT NULL
ORDER BY pid
LIMIT 20;
        """),
        ("可用计数器类型", """
SELECT DISTINCT name FROM counter_track
ORDER BY name
LIMIT 20;
        """),
        ("进程内存统计 (如有)", """
SELECT
    process.name as process_name,
    process.pid,
    CAST(MAX(counter.value) / 1024 / 1024 AS INT) as max_rss_mb
FROM counter
JOIN process_counter_track ON counter.track_id = process_counter_track.id
JOIN process ON process_counter_track.upid = process.upid
WHERE process_counter_track.name = 'mem.rss'
GROUP BY process.name, process.pid
ORDER BY max_rss_mb DESC
LIMIT 20;
        """),
    ]

    print(f"\n分析追踪文件: {trace_path}")
    print(f"文件大小: {os.path.getsize(trace_path) / 1024:.1f} KB")
    print("=" * 60)

    for title, sql in default_queries:
        print(f"\n{title}:")
        print("-" * 40)
        success, output = run_trace_query(trace_path, sql)
        if success and output:
            # 过滤掉 trace_processor 的日志信息
            lines = [l for l in output.split('\n') if not l.startswith('[') and not l.startswith('Loading')]
            output = '\n'.join(lines).strip()
            if output:
                print(output)
            else:
                print("(无数据)")
        else:
            print("(无数据)")

    return True


def interactive_shell(trace_path: str):
    """启动交互式 trace_processor shell"""
    if not os.path.exists(TRACE_PROCESSOR):
        print(f"错误: trace_processor 未找到: {TRACE_PROCESSOR}")
        return

    os.chmod(TRACE_PROCESSOR, 0o755)
    print(f"启动交互式分析: {trace_path}")
    print("输入 SQL 查询进行分析，输入 .quit 退出")
    os.execv(TRACE_PROCESSOR, [TRACE_PROCESSOR, trace_path])


def parse_duration(duration_str: str) -> int:
    """解析持续时间字符串，返回毫秒"""
    duration_str = duration_str.lower().strip()
    if duration_str.endswith('ms'):
        return int(duration_str[:-2])
    elif duration_str.endswith('s'):
        return int(float(duration_str[:-1]) * 1000)
    elif duration_str.endswith('m'):
        return int(float(duration_str[:-1]) * 60 * 1000)
    else:
        # 默认秒
        return int(float(duration_str) * 1000)


def main():
    parser = argparse.ArgumentParser(
        description="Perfetto 追踪助手 - 内存追踪配置、启动和分析",
        epilog="""
示例:
  # 生成配置文件
  python3 perfetto_helper.py config -p com.example.app -d 30s -o config.pbtxt

  # 启动追踪
  python3 perfetto_helper.py start -p com.example.app -d 30s

  # 停止追踪
  python3 perfetto_helper.py stop

  # 拉取追踪文件
  python3 perfetto_helper.py pull -o trace.perfetto

  # 分析追踪文件
  python3 perfetto_helper.py analyze trace.perfetto

  # 完整流程
  python3 perfetto_helper.py record -p com.example.app -d 30s -o trace.perfetto
        """,
        formatter_class=argparse.RawTextHelpFormatter
    )

    subparsers = parser.add_subparsers(dest='command', help='可用命令')

    # config 子命令
    config_parser = subparsers.add_parser('config', help='生成 Perfetto 配置文件')
    config_parser.add_argument('-p', '--package', help='目标应用包名')
    config_parser.add_argument('-d', '--duration', default='30s', help='追踪持续时间 (如: 30s, 1m)')
    config_parser.add_argument('-o', '--output', help='输出配置文件路径')
    config_parser.add_argument('--no-heapprofd', action='store_true', help='禁用 heapprofd')
    config_parser.add_argument('--no-process-stats', action='store_true', help='禁用进程统计')
    config_parser.add_argument('--no-memory-counters', action='store_true', help='禁用内存计数器')
    config_parser.add_argument('--enable-ftrace', action='store_true', help='启用 ftrace 追踪')
    config_parser.add_argument('--sampling-interval', type=int, default=4096,
                               help='Heapprofd 采样间隔 (bytes)')

    # start 子命令
    start_parser = subparsers.add_parser('start', help='启动 Perfetto 追踪')
    start_parser.add_argument('-p', '--package', help='目标应用包名')
    start_parser.add_argument('-d', '--duration', default='30s', help='追踪持续时间')
    start_parser.add_argument('-o', '--output', default='/data/misc/perfetto-traces/trace.perfetto',
                              help='设备上的输出路径')

    # stop 子命令
    subparsers.add_parser('stop', help='停止 Perfetto 追踪')

    # pull 子命令
    pull_parser = subparsers.add_parser('pull', help='从设备拉取追踪文件')
    pull_parser.add_argument('-r', '--remote', default='/data/misc/perfetto-traces/trace.perfetto',
                             help='设备上的追踪文件路径')
    pull_parser.add_argument('-o', '--output', help='本地输出路径')

    # analyze 子命令
    analyze_parser = subparsers.add_parser('analyze', help='分析追踪文件')
    analyze_parser.add_argument('trace_file', help='追踪文件路径')
    analyze_parser.add_argument('-q', '--query', help='自定义 SQL 查询')
    analyze_parser.add_argument('-i', '--interactive', action='store_true',
                                help='启动交互式 shell')

    # record 子命令 (完整流程)
    record_parser = subparsers.add_parser('record', help='录制追踪 (启动->等待->停止->拉取)')
    record_parser.add_argument('-p', '--package', help='目标应用包名')
    record_parser.add_argument('-d', '--duration', default='30s', help='追踪持续时间')
    record_parser.add_argument('-o', '--output', help='本地输出路径')
    record_parser.add_argument('--analyze', action='store_true', help='录制后自动分析')
    record_parser.add_argument('--no-heapprofd', action='store_true', help='禁用 heapprofd')
    record_parser.add_argument('--no-process-stats', action='store_true', help='禁用进程统计')
    record_parser.add_argument('--no-memory-counters', action='store_true', help='禁用内存计数器')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # 处理 config 命令
    if args.command == 'config':
        config = PerfettoConfig(
            package=args.package or "",
            duration_ms=parse_duration(args.duration),
            enable_heapprofd=not args.no_heapprofd,
            enable_process_stats=not args.no_process_stats,
            enable_memory_counters=not args.no_memory_counters,
            enable_ftrace=args.enable_ftrace,
            heapprofd_sampling_interval=args.sampling_interval,
        )
        content = generate_config(config)
        if args.output:
            with open(args.output, 'w') as f:
                f.write(content)
            print(f"配置已保存到: {args.output}")
        else:
            print(content)

    # 处理 start 命令
    elif args.command == 'start':
        if not check_device():
            sys.exit(1)
        config = PerfettoConfig(
            package=args.package or "",
            duration_ms=parse_duration(args.duration),
        )
        if not start_trace(config, args.output):
            sys.exit(1)

    # 处理 stop 命令
    elif args.command == 'stop':
        if not check_device():
            sys.exit(1)
        if not stop_trace():
            sys.exit(1)

    # 处理 pull 命令
    elif args.command == 'pull':
        if not check_device():
            sys.exit(1)
        result = pull_trace(args.remote, args.output)
        if not result:
            sys.exit(1)

    # 处理 analyze 命令
    elif args.command == 'analyze':
        if args.interactive:
            interactive_shell(args.trace_file)
        else:
            if not analyze_trace(args.trace_file, args.query):
                sys.exit(1)

    # 处理 record 命令
    elif args.command == 'record':
        if not check_device():
            sys.exit(1)

        config = PerfettoConfig(
            package=args.package or "",
            duration_ms=parse_duration(args.duration),
            enable_heapprofd=not getattr(args, 'no_heapprofd', False),
            enable_process_stats=not getattr(args, 'no_process_stats', False),
            enable_memory_counters=not getattr(args, 'no_memory_counters', False),
        )

        # 启动追踪 (perfetto 同步运行，会等待 duration 后自动完成)
        remote_path = '/data/misc/perfetto-traces/trace.perfetto'
        if not start_trace(config, remote_path):
            sys.exit(1)

        # 拉取文件
        local_path = pull_trace(remote_path, args.output)
        if not local_path:
            sys.exit(1)

        # 可选分析
        if args.analyze and local_path:
            print()
            analyze_trace(local_path)


if __name__ == '__main__':
    main()
