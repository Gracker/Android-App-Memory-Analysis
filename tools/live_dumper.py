#!/usr/bin/env python3
# -*- coding:utf-8 -*-
"""
Android 内存全景 Dump 工具

一键从手机采集所有内存相关数据：
- hprof: Java 堆快照
- smaps: 进程内存映射
- showmap: 进程内存映射摘要
- meminfo: dumpsys meminfo 输出（含 Native Allocations）
- gfxinfo: dumpsys gfxinfo 输出（GPU/Graphics）
- Android 17: exit-info 与 memory-limiter raw evidence

确保所有数据在同一时间点采集，便于关联分析。
"""

import argparse
import os
import subprocess
import sys
import time
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.android_shell_utils import (
    parse_ps_processes,
    read_dmabuf_with_shell,
    read_smaps_with_shell,
    resolve_pid_with_shell,
)


class LiveDumper:
    """一键内存数据采集器"""

    def __init__(self, adb_path=None):
        self.adb = adb_path or self._find_adb()
        self.device_connected = self._check_device()

    def _find_adb(self):
        """查找 adb 路径"""
        # 优先使用同目录下的 adb
        script_dir = os.path.dirname(os.path.abspath(__file__))
        local_adb = os.path.join(script_dir, 'adb')
        if os.path.exists(local_adb):
            return local_adb

        # 尝试系统 PATH
        try:
            result = subprocess.run(['which', 'adb'], capture_output=True, text=True)
            if result.returncode == 0:
                return result.stdout.strip()
        except:
            pass

        # 默认
        return 'adb'

    def _check_device(self):
        """检查设备连接状态"""
        try:
            result = subprocess.run(
                [self.adb, 'devices'],
                capture_output=True, text=True, timeout=10
            )
            lines = result.stdout.strip().split('\n')
            # 跳过第一行 "List of devices attached"
            devices = [l for l in lines[1:] if l.strip() and 'device' in l]
            return len(devices) > 0
        except Exception as e:
            print(f"检查设备连接失败: {e}")
            return False

    def _adb_shell(self, cmd, timeout=30):
        """执行 adb shell 命令"""
        try:
            result = subprocess.run(
                [self.adb, 'shell', cmd],
                capture_output=True, text=True, timeout=timeout
            )
            return result.stdout, result.returncode
        except subprocess.TimeoutExpired:
            return "", -1
        except Exception as e:
            return str(e), -1

    def _adb_shell_full(self, cmd, timeout=30):
        """执行 adb shell 命令并保留 stderr，适合归档 raw evidence。"""
        try:
            result = subprocess.run(
                [self.adb, 'shell', cmd],
                capture_output=True, text=True, timeout=timeout
            )
            return result.stdout or "", result.returncode, result.stderr or ""
        except subprocess.TimeoutExpired:
            return "", -1, f"timeout ({timeout}s)"
        except Exception as e:
            return "", -1, str(e)

    def _adb_pull(self, remote_path, local_path, timeout=60):
        """拉取文件到本地"""
        try:
            result = subprocess.run(
                [self.adb, 'pull', remote_path, local_path],
                capture_output=True, text=True, timeout=timeout
            )
            return result.returncode == 0
        except Exception as e:
            print(f"拉取文件失败: {e}")
            return False

    def get_pid(self, package_name):
        """获取应用 PID"""
        return resolve_pid_with_shell(self._adb_shell, package_name)

    def _write_artifact(self, output_path, content):
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)

    def _read_artifact_value(self, path):
        if not path or not os.path.exists(path):
            return ""
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read().strip()
        except OSError:
            return ""

    def dump_shell_artifact(self, command, output_path, timeout=30, error_path=None):
        """Dump raw shell output. Failures are archived but do not stop collection."""
        output, ret, stderr = self._adb_shell_full(command, timeout=timeout)
        if output.strip() or ret == 0:
            self._write_artifact(output_path, output)
        if ret != 0 and error_path:
            error = stderr.strip() or output.strip() or f"command failed: {command}"
            self._write_artifact(error_path, error + "\n")
        return ret == 0 and bool(output.strip())

    def dump_device_context(self, files):
        """Collect stable device context before PID-dependent artifacts."""
        results = {}
        context_commands = {
            'build_fingerprint': 'getprop ro.build.fingerprint',
            'android_release': 'getprop ro.build.version.release',
            'android_sdk': 'getprop ro.build.version.sdk',
            'page_size': 'getconf PAGE_SIZE',
        }
        for name, command in context_commands.items():
            if self.dump_shell_artifact(command, files[name]):
                results[name] = files[name]
        return results

    def dump_package_context(self, package_name, files):
        """Collect package/process context even if the target process is gone."""
        results = {}
        package_commands = {
            'package_uid': f'cmd package list packages -U {package_name}',
            'processes': 'ps -A',
            'activity_processes': 'dumpsys activity processes',
            'exit_info': f'dumpsys activity exit-info {package_name}',
            'memory_limiter_status': 'am memory-limiter status',
        }
        for name, command in package_commands.items():
            error_path = files.get(f'{name}_error')
            if self.dump_shell_artifact(command, files[name], timeout=30, error_path=error_path):
                results[name] = files[name]
            elif error_path and os.path.exists(error_path):
                results[f'{name}_error'] = error_path
        return results

    def list_running_apps(self):
        """列出正在运行的应用"""
        if not self.device_connected:
            print("错误: 未检测到已连接的设备")
            return []

        output, ret = self._adb_shell('ps -A')
        if ret != 0 or not output.strip():
            output, ret = self._adb_shell('ps')
        if ret != 0:
            print("获取进程列表失败")
            return []

        apps = []
        system_apps = []
        for pid, user, process_name in parse_ps_processes(output):
            if process_name.startswith('[') or process_name.startswith('/'):
                continue
            if 'android.hardware.' in process_name:
                continue
            if process_name.startswith('.'):
                continue
            if '.' not in process_name:
                continue

            is_user_app = user.startswith('u0_a') or user.startswith('u10_a')
            if is_user_app:
                apps.append((pid, process_name))
            else:
                system_apps.append((pid, process_name))

        return sorted(apps, key=lambda x: x[1]) + sorted(system_apps, key=lambda x: x[1])

    def dump_showmap(self, pid, output_path):
        """Dump showmap when available."""
        output, ret = self._adb_shell(f'showmap {pid}', timeout=60)
        if ret == 0 and output.strip():
            self._write_artifact(output_path, output)
            return True
        return False

    def dump_smaps(self, pid, output_path):
        """Dump smaps"""
        output, _ = read_smaps_with_shell(self._adb_shell, pid, timeout=60)
        if output:
            self._write_artifact(output_path, output)
            return True
        return False

    def dump_meminfo(self, package_name, output_path):
        """Dump detailed dumpsys meminfo."""
        output, ret = self._adb_shell(f'dumpsys meminfo -d {package_name}', timeout=30)
        if ret == 0 and output.strip():
            self._write_artifact(output_path, output)
            return True
        return False

    def dump_gfxinfo(self, package_name, output_path):
        """Dump dumpsys gfxinfo"""
        output, ret = self._adb_shell(f'dumpsys gfxinfo {package_name}', timeout=30)
        if ret == 0 and output.strip():
            self._write_artifact(output_path, output)
            return True
        return False

    def dump_zram_swap(self, output_path):
        """
        Dump zRAM/Swap 信息
        
        采集:
        - /proc/swaps
        - /sys/block/zram*/disksize
        - /sys/block/zram*/mm_stat
        - /sys/block/zram*/stat
        """
        lines = []
        
        # 采集 /proc/swaps
        lines.append("===== /proc/swaps =====")
        output, ret = self._adb_shell('cat /proc/swaps')
        if ret == 0:
            lines.append(output.strip())
        else:
            lines.append("# 无法读取 /proc/swaps")
        lines.append("")
        
        # 查找 zRAM 设备
        output, ret = self._adb_shell('ls -d /sys/block/zram* 2>/dev/null')
        if ret == 0 and output.strip():
            zram_devices = [line.strip().split('/')[-1] for line in output.strip().split('\n') if 'zram' in line]
            
            for device in sorted(zram_devices):
                lines.append(f"===== {device} =====")
                
                # disksize
                ds_output, ds_ret = self._adb_shell(f'cat /sys/block/{device}/disksize')
                if ds_ret == 0:
                    lines.append(f"disksize: {ds_output.strip()}")
                
                # mm_stat (新版本内核)
                mm_output, mm_ret = self._adb_shell(f'cat /sys/block/{device}/mm_stat 2>/dev/null')
                if mm_ret == 0 and mm_output.strip():
                    lines.append(f"mm_stat: {mm_output.strip()}")
                else:
                    # 旧版字段 (兼容)
                    for field in ['orig_data_size', 'compr_data_size', 'mem_used_total']:
                        f_output, f_ret = self._adb_shell(f'cat /sys/block/{device}/{field} 2>/dev/null')
                        if f_ret == 0 and f_output.strip():
                            lines.append(f"{field}: {f_output.strip()}")
                
                # stat (I/O 统计)
                stat_output, stat_ret = self._adb_shell(f'cat /sys/block/{device}/stat 2>/dev/null')
                if stat_ret == 0 and stat_output.strip():
                    lines.append(f"stat: {stat_output.strip()}")
                
                lines.append("")
        else:
            lines.append("# 未检测到 zRAM 设备")
        
        # 写入文件
        content = '\n'.join(lines)
        self._write_artifact(output_path, content)
        
        return bool(content.strip())

    def dump_dmabuf(self, output_path):
        """Dump DMA-BUF debugfs information when the device exposes it."""
        output, _ = read_dmabuf_with_shell(self._adb_shell, timeout=60)
        if output:
            self._write_artifact(output_path, output)
            return True
        return False

    def dump_proc_meminfo(self, output_path):
        """Dump /proc/meminfo (系统内存信息)"""
        output, ret = self._adb_shell('cat /proc/meminfo')
        if ret == 0 and output.strip():
            self._write_artifact(output_path, output)
            return True
        return False

    def write_meta(self, meta_path, package_name, pid, timestamp, results, files, process_status):
        """Save a compact index of evidence files and device/runtime context."""
        with open(meta_path, 'w', encoding='utf-8') as f:
            f.write(f"Package: {package_name}\n")
            f.write(f"PID: {pid or ''}\n")
            f.write(f"ProcessStatus: {process_status}\n")
            f.write(f"Timestamp: {timestamp}\n")
            f.write(f"PageSize: {self._read_artifact_value(files.get('page_size'))}\n")
            f.write(f"AndroidRelease: {self._read_artifact_value(files.get('android_release'))}\n")
            f.write(f"AndroidSdk: {self._read_artifact_value(files.get('android_sdk'))}\n")
            f.write(f"BuildFingerprint: {self._read_artifact_value(files.get('build_fingerprint'))}\n")
            f.write("Files:\n")
            for name, path in results.items():
                if name in ('meta', 'dump_dir', 'package', 'pid', 'process_status'):
                    continue
                size = os.path.getsize(path) if os.path.exists(path) else 0
                f.write(f"  {name}: {os.path.basename(path)} ({size} bytes)\n")

    def dump_hprof(self, package_name, output_path, timeout=120):
        """Dump hprof (Java 堆)"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        device_path = f'/data/local/tmp/dump_{timestamp}.hprof'

        # 执行 dumpheap
        _, ret = self._adb_shell(f'am dumpheap {package_name} {device_path}', timeout=timeout)

        # 等待文件生成
        print("  等待 hprof 文件生成...")
        time.sleep(5)

        # 检查文件是否存在
        output, ret = self._adb_shell(f'ls -la {device_path}')
        if ret != 0 or 'No such file' in output:
            print("  hprof 文件生成失败")
            return False

        # 拉取文件
        if not self._adb_pull(device_path, output_path, timeout=120):
            print("  拉取 hprof 文件失败")
            return False

        # 清理设备文件
        self._adb_shell(f'rm {device_path}')
        return True

    def dump_all(self, package_name, output_dir, skip_hprof=False):
        """
        一键 Dump 所有内存数据

        Args:
            package_name: 应用包名
            output_dir: 输出目录
            skip_hprof: 是否跳过 hprof（hprof dump 较慢）

        Returns:
            dict: 各数据文件的路径
        """
        if not self.device_connected:
            print("错误: 未检测到已连接的设备")
            return None

        # 创建输出目录
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dump_dir = os.path.join(output_dir, f"{package_name}_{timestamp}")
        os.makedirs(dump_dir, exist_ok=True)

        # 定义输出文件路径
        files = {
            'build_fingerprint': os.path.join(dump_dir, 'build_fingerprint.txt'),
            'android_release': os.path.join(dump_dir, 'android_release.txt'),
            'android_sdk': os.path.join(dump_dir, 'android_sdk.txt'),
            'page_size': os.path.join(dump_dir, 'page_size.txt'),
            'package_uid': os.path.join(dump_dir, 'package_uid.txt'),
            'processes': os.path.join(dump_dir, 'processes.txt'),
            'activity_processes': os.path.join(dump_dir, 'activity_processes.txt'),
            'exit_info': os.path.join(dump_dir, 'exit_info.txt'),
            'exit_info_error': os.path.join(dump_dir, 'exit_info.err'),
            'memory_limiter_status': os.path.join(dump_dir, 'memory_limiter_status.txt'),
            'memory_limiter_status_error': os.path.join(dump_dir, 'memory_limiter_status.err'),
            'showmap': os.path.join(dump_dir, 'showmap.txt'),
            'smaps': os.path.join(dump_dir, 'smaps.txt'),
            'meminfo': os.path.join(dump_dir, 'meminfo.txt'),
            'gfxinfo': os.path.join(dump_dir, 'gfxinfo.txt'),
            'hprof': os.path.join(dump_dir, 'heap.hprof'),
            'proc_meminfo': os.path.join(dump_dir, 'proc_meminfo.txt'),
            'zram_swap': os.path.join(dump_dir, 'zram_swap.txt'),
            'dmabuf': os.path.join(dump_dir, 'dmabuf_debug.txt'),
        }

        results = {}
        print(f"\n开始采集内存数据 -> {dump_dir}")
        print("=" * 50)

        print("\n[context] Dumping device metadata...")
        results.update(self.dump_device_context(files))

        print("\n[context] Dumping package and Android 17 memory-limiter evidence...")
        results.update(self.dump_package_context(package_name, files))

        # 获取 PID
        pid = self.get_pid(package_name)
        if not pid:
            print(f"\n警告: 应用 {package_name} 当前未运行")
            print("已保留设备元信息、进程列表、exit-info 和 memory-limiter 状态用于排查最近一次退出。")
            meta_path = os.path.join(dump_dir, 'meta.txt')
            self.write_meta(meta_path, package_name, None, timestamp, results, files, 'not_running')
            results['meta'] = meta_path
            results['dump_dir'] = dump_dir
            results['package'] = package_name
            results['pid'] = None
            results['process_status'] = 'not_running'
            return results

        print(f"\n找到应用 {package_name} (PID: {pid})")

        # 先快速采集轻量数据（确保时间点接近）
        print("\n[1/8] Dumping showmap...")
        if self.dump_showmap(pid, files['showmap']):
            results['showmap'] = files['showmap']
            print(f"  -> {os.path.basename(files['showmap'])}")
        else:
            print("  -> 失败或无权限")

        print("\n[2/8] Dumping smaps...")
        if self.dump_smaps(pid, files['smaps']):
            results['smaps'] = files['smaps']
            print(f"  -> {os.path.basename(files['smaps'])}")
        else:
            print("  -> 失败")

        print("\n[3/8] Dumping meminfo -d...")
        if self.dump_meminfo(package_name, files['meminfo']):
            results['meminfo'] = files['meminfo']
            print(f"  -> {os.path.basename(files['meminfo'])}")
        else:
            print("  -> 失败")

        print("\n[4/8] Dumping gfxinfo...")
        if self.dump_gfxinfo(package_name, files['gfxinfo']):
            results['gfxinfo'] = files['gfxinfo']
            print(f"  -> {os.path.basename(files['gfxinfo'])}")
        else:
            print("  -> 失败")

        print("\n[5/8] Dumping /proc/meminfo (系统内存)...")
        if self.dump_proc_meminfo(files['proc_meminfo']):
            results['proc_meminfo'] = files['proc_meminfo']
            print(f"  -> {os.path.basename(files['proc_meminfo'])}")
        else:
            print("  -> 失败")

        print("\n[6/8] Dumping zRAM/Swap...")
        if self.dump_zram_swap(files['zram_swap']):
            results['zram_swap'] = files['zram_swap']
            print(f"  -> {os.path.basename(files['zram_swap'])}")
        else:
            print("  -> 失败或无 zRAM")

        print("\n[7/8] Dumping DMA-BUF...")
        if self.dump_dmabuf(files['dmabuf']):
            results['dmabuf'] = files['dmabuf']
            print(f"  -> {os.path.basename(files['dmabuf'])}")
        else:
            print("  -> 失败或无权限")

        # hprof 最后 dump（耗时较长）
        if not skip_hprof:
            print("\n[8/8] Dumping hprof (这可能需要较长时间)...")
            if self.dump_hprof(package_name, files['hprof']):
                results['hprof'] = files['hprof']
                print(f"  -> {os.path.basename(files['hprof'])}")
            else:
                print("  -> 失败 (可能需要 debuggable 应用或 root 权限)")
        else:
            print("\n[8/8] 跳过 hprof dump")

        print("\n" + "=" * 50)
        print(f"采集完成! 文件保存在: {dump_dir}")
        primary_keys = ['showmap', 'smaps', 'meminfo', 'gfxinfo', 'proc_meminfo', 'zram_swap', 'dmabuf']
        if not skip_hprof:
            primary_keys.append('hprof')
        primary_successes = sum(1 for key in primary_keys if key in results)
        print(f"核心采集成功: {primary_successes}/{len(primary_keys)}")
        print(f"证据文件总数: {len(results)}")

        # 保存元信息
        meta_path = os.path.join(dump_dir, 'meta.txt')
        self.write_meta(meta_path, package_name, pid, timestamp, results, files, 'running')
        results['meta'] = meta_path
        results['dump_dir'] = dump_dir
        results['package'] = package_name
        results['pid'] = pid
        results['process_status'] = 'running'

        return results


def main():
    parser = argparse.ArgumentParser(
        description="Android 内存全景 Dump 工具",
        epilog="""
示例:
  # 列出运行中的应用
  python3 live_dumper.py --list

  # Dump 指定应用的所有内存数据
  python3 live_dumper.py --package com.example.app

  # 指定输出目录
  python3 live_dumper.py --package com.example.app -o ./dumps

  # 跳过 hprof（更快）
  python3 live_dumper.py --package com.example.app --skip-hprof
        """,
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument('-l', '--list', action='store_true',
                        help='列出正在运行的应用')
    parser.add_argument('-p', '--package', type=str,
                        help='目标应用包名')
    parser.add_argument('-o', '--output', type=str, default='.',
                        help='输出目录 (默认: 当前目录)')
    parser.add_argument('--skip-hprof', action='store_true',
                        help='跳过 hprof dump（更快，但无 Java 堆详情）')
    parser.add_argument('--adb', type=str,
                        help='指定 adb 路径')

    args = parser.parse_args()

    dumper = LiveDumper(adb_path=args.adb)

    if not dumper.device_connected:
        print("错误: 未检测到已连接的 Android 设备")
        print("请确保:")
        print("  1. 设备已通过 USB 连接")
        print("  2. 已开启 USB 调试")
        print("  3. 已授权此计算机调试")
        sys.exit(1)

    if args.list:
        apps = dumper.list_running_apps()
        if not apps:
            print("未找到正在运行的应用")
            return

        print(f"\n正在运行的应用 ({len(apps)} 个):")
        print("-" * 60)
        print(f"{'PID':<10} {'包名'}")
        print("-" * 60)
        for pid, name in apps:
            print(f"{pid:<10} {name}")
        return

    if not args.package:
        print("请指定包名 (-p/--package) 或使用 --list 查看运行中的应用")
        parser.print_help()
        sys.exit(1)

    results = dumper.dump_all(
        args.package,
        args.output,
        skip_hprof=args.skip_hprof
    )

    if results:
        print("\n可以使用以下命令进行分析:")
        if 'hprof' in results and 'smaps' in results:
            print(f"  python3 analyze.py combined -H {results['hprof']} -S {results['smaps']}")
        elif 'smaps' in results:
            print(f"  python3 analyze.py smaps {results['smaps']}")


if __name__ == '__main__':
    main()
