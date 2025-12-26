#!/usr/bin/env python3
# -*- coding:utf-8 -*-
"""
/proc/meminfo 解析器

解析系统级内存信息，提供内存压力分析。
数据来源: adb shell cat /proc/meminfo
"""

import argparse
import os
import sys
from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class ProcMeminfoData:
    """系统内存信息"""
    # 基础内存
    mem_total_kb: int = 0
    mem_free_kb: int = 0
    mem_available_kb: int = 0
    buffers_kb: int = 0
    cached_kb: int = 0

    # Swap
    swap_total_kb: int = 0
    swap_free_kb: int = 0
    swap_cached_kb: int = 0

    # 活跃/非活跃
    active_kb: int = 0
    inactive_kb: int = 0
    active_anon_kb: int = 0
    inactive_anon_kb: int = 0
    active_file_kb: int = 0
    inactive_file_kb: int = 0

    # 内核相关
    slab_kb: int = 0
    sreclaimable_kb: int = 0
    sunreclaim_kb: int = 0
    kernel_stack_kb: int = 0
    page_tables_kb: int = 0

    # ION/GPU (Android specific)
    ion_heap_kb: int = 0
    ion_page_pool_kb: int = 0

    # CMA (连续内存分配)
    cma_total_kb: int = 0
    cma_free_kb: int = 0

    # 其他
    dirty_kb: int = 0
    writeback_kb: int = 0
    anon_pages_kb: int = 0
    mapped_kb: int = 0
    shmem_kb: int = 0
    unevictable_kb: int = 0
    mlocked_kb: int = 0

    # 原始数据
    raw_data: Dict[str, int] = field(default_factory=dict)

    @property
    def mem_total_mb(self) -> float:
        return self.mem_total_kb / 1024

    @property
    def mem_available_mb(self) -> float:
        return self.mem_available_kb / 1024

    @property
    def mem_used_kb(self) -> int:
        return self.mem_total_kb - self.mem_available_kb

    @property
    def mem_used_mb(self) -> float:
        return self.mem_used_kb / 1024

    @property
    def available_percent(self) -> float:
        if self.mem_total_kb == 0:
            return 0
        return (self.mem_available_kb / self.mem_total_kb) * 100

    @property
    def swap_used_kb(self) -> int:
        return self.swap_total_kb - self.swap_free_kb

    @property
    def swap_used_percent(self) -> float:
        if self.swap_total_kb == 0:
            return 0
        return (self.swap_used_kb / self.swap_total_kb) * 100

    @property
    def memory_pressure(self) -> str:
        """
        计算内存压力等级
        - LOW: 可用内存 > 40%
        - MEDIUM: 可用内存 20-40%
        - HIGH: 可用内存 10-20%
        - CRITICAL: 可用内存 < 10%
        """
        avail = self.available_percent
        if avail > 40:
            return "LOW"
        elif avail > 20:
            return "MEDIUM"
        elif avail > 10:
            return "HIGH"
        else:
            return "CRITICAL"

    @property
    def memory_pressure_cn(self) -> str:
        """内存压力中文描述"""
        mapping = {
            "LOW": "低",
            "MEDIUM": "中等",
            "HIGH": "高",
            "CRITICAL": "危急"
        }
        return mapping.get(self.memory_pressure, "未知")


def parse_proc_meminfo(content: str) -> ProcMeminfoData:
    """解析 /proc/meminfo 内容"""
    data = ProcMeminfoData()

    for line in content.strip().split('\n'):
        if ':' not in line:
            continue

        parts = line.split(':')
        if len(parts) != 2:
            continue

        key = parts[0].strip()
        value_str = parts[1].strip().replace(' kB', '').replace('kB', '')

        try:
            value = int(value_str)
        except ValueError:
            continue

        # 存储原始数据
        data.raw_data[key] = value

        # 映射到字段
        key_lower = key.lower().replace('(', '_').replace(')', '')

        if key == 'MemTotal':
            data.mem_total_kb = value
        elif key == 'MemFree':
            data.mem_free_kb = value
        elif key == 'MemAvailable':
            data.mem_available_kb = value
        elif key == 'Buffers':
            data.buffers_kb = value
        elif key == 'Cached':
            data.cached_kb = value
        elif key == 'SwapTotal':
            data.swap_total_kb = value
        elif key == 'SwapFree':
            data.swap_free_kb = value
        elif key == 'SwapCached':
            data.swap_cached_kb = value
        elif key == 'Active':
            data.active_kb = value
        elif key == 'Inactive':
            data.inactive_kb = value
        elif key == 'Active(anon)':
            data.active_anon_kb = value
        elif key == 'Inactive(anon)':
            data.inactive_anon_kb = value
        elif key == 'Active(file)':
            data.active_file_kb = value
        elif key == 'Inactive(file)':
            data.inactive_file_kb = value
        elif key == 'Slab':
            data.slab_kb = value
        elif key == 'SReclaimable':
            data.sreclaimable_kb = value
        elif key == 'SUnreclaim':
            data.sunreclaim_kb = value
        elif key == 'KernelStack':
            data.kernel_stack_kb = value
        elif key == 'PageTables':
            data.page_tables_kb = value
        elif key == 'ION_heap':
            data.ion_heap_kb = value
        elif key == 'ION_page_pool':
            data.ion_page_pool_kb = value
        elif key == 'CmaTotal':
            data.cma_total_kb = value
        elif key == 'CmaFree':
            data.cma_free_kb = value
        elif key == 'Dirty':
            data.dirty_kb = value
        elif key == 'Writeback':
            data.writeback_kb = value
        elif key == 'AnonPages':
            data.anon_pages_kb = value
        elif key == 'Mapped':
            data.mapped_kb = value
        elif key == 'Shmem':
            data.shmem_kb = value
        elif key == 'Unevictable':
            data.unevictable_kb = value
        elif key == 'Mlocked':
            data.mlocked_kb = value

    return data


def parse_proc_meminfo_file(filepath: str) -> ProcMeminfoData:
    """从文件解析 /proc/meminfo"""
    with open(filepath, 'r') as f:
        content = f.read()
    return parse_proc_meminfo(content)


def print_report(data: ProcMeminfoData):
    """打印系统内存报告"""
    pressure_icons = {
        "LOW": "🟢",
        "MEDIUM": "🟡",
        "HIGH": "🟠",
        "CRITICAL": "🔴"
    }

    print("\n" + "=" * 60)
    print("系统内存状态 (/proc/meminfo)")
    print("=" * 60)

    # 内存概览
    print(f"\n{'─' * 40}")
    print("[ 内存概览 ]")
    print(f"{'─' * 40}")
    print(f"总内存:     {data.mem_total_mb:>10.1f} MB ({data.mem_total_kb / 1024 / 1024:.2f} GB)")
    print(f"可用内存:   {data.mem_available_mb:>10.1f} MB ({data.available_percent:.1f}%)")
    print(f"已用内存:   {data.mem_used_mb:>10.1f} MB")
    print(f"空闲内存:   {data.mem_free_kb / 1024:>10.1f} MB")
    print(f"缓存:       {data.cached_kb / 1024:>10.1f} MB")
    print(f"缓冲区:     {data.buffers_kb / 1024:>10.1f} MB")

    # 内存压力
    icon = pressure_icons.get(data.memory_pressure, "⚪")
    print(f"\n内存压力: {icon} {data.memory_pressure_cn} ({data.memory_pressure})")

    # Swap
    if data.swap_total_kb > 0:
        print(f"\n{'─' * 40}")
        print("[ Swap ]")
        print(f"{'─' * 40}")
        print(f"总 Swap:    {data.swap_total_kb / 1024:>10.1f} MB")
        print(f"已用 Swap:  {data.swap_used_kb / 1024:>10.1f} MB ({data.swap_used_percent:.1f}%)")
        print(f"空闲 Swap:  {data.swap_free_kb / 1024:>10.1f} MB")

    # ION (Android GPU memory)
    if data.ion_heap_kb > 0:
        print(f"\n{'─' * 40}")
        print("[ ION 内存 (GPU/Camera) ]")
        print(f"{'─' * 40}")
        print(f"ION Heap:   {data.ion_heap_kb / 1024:>10.1f} MB")
        if data.ion_page_pool_kb > 0:
            print(f"ION Pool:   {data.ion_page_pool_kb / 1024:>10.1f} MB")

    # CMA
    if data.cma_total_kb > 0:
        print(f"\n{'─' * 40}")
        print("[ CMA (连续内存分配) ]")
        print(f"{'─' * 40}")
        print(f"CMA 总量:   {data.cma_total_kb / 1024:>10.1f} MB")
        print(f"CMA 空闲:   {data.cma_free_kb / 1024:>10.1f} MB")

    # 内核内存
    print(f"\n{'─' * 40}")
    print("[ 内核内存 ]")
    print(f"{'─' * 40}")
    print(f"Slab:       {data.slab_kb / 1024:>10.1f} MB")
    print(f"  可回收:   {data.sreclaimable_kb / 1024:>10.1f} MB")
    print(f"  不可回收: {data.sunreclaim_kb / 1024:>10.1f} MB")
    print(f"内核栈:     {data.kernel_stack_kb / 1024:>10.1f} MB")
    print(f"页表:       {data.page_tables_kb / 1024:>10.1f} MB")

    print("\n" + "=" * 60)


def to_json(data: ProcMeminfoData) -> dict:
    """转换为 JSON 格式"""
    return {
        'memory': {
            'total_mb': round(data.mem_total_mb, 1),
            'available_mb': round(data.mem_available_mb, 1),
            'used_mb': round(data.mem_used_mb, 1),
            'free_mb': round(data.mem_free_kb / 1024, 1),
            'available_percent': round(data.available_percent, 1),
            'cached_mb': round(data.cached_kb / 1024, 1),
            'buffers_mb': round(data.buffers_kb / 1024, 1),
        },
        'swap': {
            'total_mb': round(data.swap_total_kb / 1024, 1),
            'used_mb': round(data.swap_used_kb / 1024, 1),
            'free_mb': round(data.swap_free_kb / 1024, 1),
            'used_percent': round(data.swap_used_percent, 1),
        },
        'pressure': {
            'level': data.memory_pressure,
            'level_cn': data.memory_pressure_cn,
        },
        'ion': {
            'heap_mb': round(data.ion_heap_kb / 1024, 1),
            'pool_mb': round(data.ion_page_pool_kb / 1024, 1),
        } if data.ion_heap_kb > 0 else None,
        'cma': {
            'total_mb': round(data.cma_total_kb / 1024, 1),
            'free_mb': round(data.cma_free_kb / 1024, 1),
        } if data.cma_total_kb > 0 else None,
        'kernel': {
            'slab_mb': round(data.slab_kb / 1024, 1),
            'sreclaimable_mb': round(data.sreclaimable_kb / 1024, 1),
            'sunreclaim_mb': round(data.sunreclaim_kb / 1024, 1),
            'kernel_stack_mb': round(data.kernel_stack_kb / 1024, 1),
            'page_tables_mb': round(data.page_tables_kb / 1024, 1),
        },
    }


def main():
    parser = argparse.ArgumentParser(
        description="/proc/meminfo 系统内存分析",
        epilog="""
示例:
  python3 proc_meminfo_parser.py -f proc_meminfo.txt
  adb shell cat /proc/meminfo | python3 proc_meminfo_parser.py
        """,
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument('-f', '--file', help='/proc/meminfo 文件路径')
    parser.add_argument('--json', action='store_true', help='输出 JSON 格式')

    args = parser.parse_args()

    if args.file:
        if not os.path.exists(args.file):
            print(f"错误: 文件不存在: {args.file}")
            sys.exit(1)
        data = parse_proc_meminfo_file(args.file)
    else:
        # 从 stdin 读取
        content = sys.stdin.read()
        if not content.strip():
            print("错误: 请提供 -f 参数或通过管道输入数据")
            sys.exit(1)
        data = parse_proc_meminfo(content)

    if args.json:
        import json
        print(json.dumps(to_json(data), indent=2, ensure_ascii=False))
    else:
        print_report(data)


if __name__ == '__main__':
    main()
