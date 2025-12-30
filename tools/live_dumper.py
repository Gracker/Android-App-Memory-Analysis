#!/usr/bin/env python3
# -*- coding:utf-8 -*-
"""
Android 内存全景 Dump 工具

一键从手机采集所有内存相关数据：
- hprof: Java 堆快照
- smaps: 进程内存映射
- meminfo: dumpsys meminfo 输出（含 Native Allocations）
- gfxinfo: dumpsys gfxinfo 输出（GPU/Graphics）

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
        # 方法1: pidof
        output, ret = self._adb_shell(f'pidof {package_name}')
        if ret == 0 and output.strip():
            try:
                return int(output.strip().split()[0])
            except:
                pass

        # 方法2: ps | grep
        output, ret = self._adb_shell(f'ps -A | grep {package_name}')
        if ret == 0 and output.strip():
            for line in output.strip().split('\n'):
                if package_name in line:
                    parts = line.split()
                    if len(parts) >= 2:
                        try:
                            return int(parts[1])
                        except:
                            continue
        return None

    def list_running_apps(self):
        """列出正在运行的应用"""
        if not self.device_connected:
            print("错误: 未检测到已连接的设备")
            return []

        output, ret = self._adb_shell('ps -A')
        if ret != 0:
            print("获取进程列表失败")
            return []

        apps = []
        system_apps = []
        for line in output.strip().split('\n')[1:]:  # 跳过标题行
            parts = line.split()
            if len(parts) >= 9:
                process_name = parts[-1]
                pid = parts[1]
                user = parts[0]

                # 排除内核进程
                if process_name.startswith('[') or process_name.startswith('/'):
                    continue

                # 排除 HAL 服务
                if 'android.hardware.' in process_name:
                    continue

                # 排除以 . 开头的进程
                if process_name.startswith('.'):
                    continue

                # 必须包含 . 才是有效包名
                if '.' not in process_name:
                    continue

                try:
                    pid_int = int(pid)
                except:
                    continue

                # 用户应用: u0_aXXX 或 u10_aXXX
                is_user_app = user.startswith('u0_a') or user.startswith('u10_a')

                if is_user_app:
                    apps.append((pid_int, process_name))
                else:
                    # 系统应用 (com.android.*, com.google.*)
                    system_apps.append((pid_int, process_name))

        # 用户应用优先，然后是系统应用
        return sorted(apps, key=lambda x: x[1]) + sorted(system_apps, key=lambda x: x[1])

    def dump_smaps(self, pid, output_path):
        """Dump smaps"""
        output, ret = self._adb_shell(f'cat /proc/{pid}/smaps', timeout=60)
        if ret == 0 and output.strip():
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(output)
            return True
        return False

    def dump_meminfo(self, package_name, output_path):
        """Dump dumpsys meminfo"""
        output, ret = self._adb_shell(f'dumpsys meminfo {package_name}', timeout=30)
        if ret == 0 and output.strip():
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(output)
            return True
        return False

    def dump_gfxinfo(self, package_name, output_path):
        """Dump dumpsys gfxinfo"""
        output, ret = self._adb_shell(f'dumpsys gfxinfo {package_name}', timeout=30)
        if ret == 0 and output.strip():
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(output)
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
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        return bool(content.strip())

    def dump_proc_meminfo(self, output_path):
        """Dump /proc/meminfo (系统内存信息)"""
        output, ret = self._adb_shell('cat /proc/meminfo')
        if ret == 0 and output.strip():
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(output)
            return True
        return False

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

        # 获取 PID
        pid = self.get_pid(package_name)
        if not pid:
            print(f"错误: 应用 {package_name} 未运行")
            return None

        print(f"找到应用 {package_name} (PID: {pid})")

        # 创建输出目录
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dump_dir = os.path.join(output_dir, f"{package_name}_{timestamp}")
        os.makedirs(dump_dir, exist_ok=True)

        # 定义输出文件路径
        files = {
            'smaps': os.path.join(dump_dir, 'smaps.txt'),
            'meminfo': os.path.join(dump_dir, 'meminfo.txt'),
            'gfxinfo': os.path.join(dump_dir, 'gfxinfo.txt'),
            'hprof': os.path.join(dump_dir, 'heap.hprof'),
            'proc_meminfo': os.path.join(dump_dir, 'proc_meminfo.txt'),
            'zram_swap': os.path.join(dump_dir, 'zram_swap.txt'),
        }

        results = {}
        print(f"\n开始采集内存数据 -> {dump_dir}")
        print("=" * 50)

        # 先快速采集轻量数据（确保时间点接近）
        print("\n[1/4] Dumping smaps...")
        if self.dump_smaps(pid, files['smaps']):
            results['smaps'] = files['smaps']
            print(f"  -> {os.path.basename(files['smaps'])}")
        else:
            print("  -> 失败")

        print("\n[2/4] Dumping meminfo...")
        if self.dump_meminfo(package_name, files['meminfo']):
            results['meminfo'] = files['meminfo']
            print(f"  -> {os.path.basename(files['meminfo'])}")
        else:
            print("  -> 失败")

        print("\n[3/6] Dumping gfxinfo...")
        if self.dump_gfxinfo(package_name, files['gfxinfo']):
            results['gfxinfo'] = files['gfxinfo']
            print(f"  -> {os.path.basename(files['gfxinfo'])}")
        else:
            print("  -> 失败")

        print("\n[4/6] Dumping /proc/meminfo (系统内存)...")
        if self.dump_proc_meminfo(files['proc_meminfo']):
            results['proc_meminfo'] = files['proc_meminfo']
            print(f"  -> {os.path.basename(files['proc_meminfo'])}")
        else:
            print("  -> 失败")

        print("\n[5/6] Dumping zRAM/Swap...")
        if self.dump_zram_swap(files['zram_swap']):
            results['zram_swap'] = files['zram_swap']
            print(f"  -> {os.path.basename(files['zram_swap'])}")
        else:
            print("  -> 失败或无 zRAM")

        # hprof 最后 dump（耗时较长）
        if not skip_hprof:
            print("\n[6/6] Dumping hprof (这可能需要较长时间)...")
            if self.dump_hprof(package_name, files['hprof']):
                results['hprof'] = files['hprof']
                print(f"  -> {os.path.basename(files['hprof'])}")
            else:
                print("  -> 失败 (可能需要 debuggable 应用或 root 权限)")
        else:
            print("\n[6/6] 跳过 hprof dump")

        print("\n" + "=" * 50)
        print(f"采集完成! 文件保存在: {dump_dir}")
        total_items = 6 if not skip_hprof else 5
        print(f"成功: {len(results)}/{total_items}")

        # 保存元信息
        meta_path = os.path.join(dump_dir, 'meta.txt')
        with open(meta_path, 'w') as f:
            f.write(f"Package: {package_name}\n")
            f.write(f"PID: {pid}\n")
            f.write(f"Timestamp: {timestamp}\n")
            f.write(f"Files:\n")
            for name, path in results.items():
                size = os.path.getsize(path) if os.path.exists(path) else 0
                f.write(f"  {name}: {os.path.basename(path)} ({size} bytes)\n")

        results['meta'] = meta_path
        results['dump_dir'] = dump_dir
        results['package'] = package_name
        results['pid'] = pid

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
