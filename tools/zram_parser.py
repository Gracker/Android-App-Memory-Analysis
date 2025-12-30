#!/usr/bin/env python3
# -*- coding:utf-8 -*-
"""
zRAM/Swap 解析器

解析 Android 设备的 zRAM 压缩内存和 Swap 使用情况。

数据来源:
- /proc/swaps: Swap 设备列表
- /sys/block/zram*/mm_stat: zRAM 统计 (Android 4.4+)
- /sys/block/zram*/stat: 块设备 I/O 统计
- /sys/block/zram*/disksize: zRAM 磁盘大小
- /sys/block/zram*/mem_used_total: 总使用内存 (旧版)
- /sys/block/zram*/compr_data_size: 压缩后数据大小 (旧版)
- /sys/block/zram*/orig_data_size: 原始数据大小 (旧版)
"""

import argparse
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class ZramDevice:
    """单个 zRAM 设备信息"""
    name: str = ""                    # 设备名 (zram0, zram1, ...)
    disksize_kb: int = 0              # 磁盘大小 (KB)
    
    # mm_stat 字段 (新版本内核 3.15+)
    orig_data_size_bytes: int = 0     # 原始数据大小 (未压缩)
    compr_data_size_bytes: int = 0    # 压缩后数据大小
    mem_used_total_bytes: int = 0     # 实际使用的内存 (含元数据)
    mem_limit_bytes: int = 0          # 内存限制
    mem_used_max_bytes: int = 0       # 历史最大使用内存
    same_pages: int = 0               # 相同页面数 (零页优化)
    pages_compacted: int = 0          # 压缩的页面数
    huge_pages: int = 0               # 大页数 (仅部分内核支持)
    
    # 旧版字段 (兼容)
    num_reads: int = 0
    num_writes: int = 0
    invalid_io: int = 0
    notify_free: int = 0
    
    @property
    def disksize_mb(self) -> float:
        return self.disksize_kb / 1024
    
    @property
    def orig_data_mb(self) -> float:
        return self.orig_data_size_bytes / 1024 / 1024
    
    @property
    def compr_data_mb(self) -> float:
        return self.compr_data_size_bytes / 1024 / 1024
    
    @property
    def mem_used_mb(self) -> float:
        return self.mem_used_total_bytes / 1024 / 1024
    
    @property
    def compression_ratio(self) -> float:
        """压缩率 (原始大小 / 压缩后大小)"""
        if self.compr_data_size_bytes == 0:
            return 0
        return self.orig_data_size_bytes / self.compr_data_size_bytes
    
    @property
    def space_saving_percent(self) -> float:
        """空间节省百分比"""
        if self.orig_data_size_bytes == 0:
            return 0
        saved = self.orig_data_size_bytes - self.compr_data_size_bytes
        return (saved / self.orig_data_size_bytes) * 100
    
    @property
    def usage_percent(self) -> float:
        """使用率 (原始数据 / 磁盘大小)"""
        if self.disksize_kb == 0:
            return 0
        orig_kb = self.orig_data_size_bytes / 1024
        return (orig_kb / self.disksize_kb) * 100


@dataclass
class SwapDevice:
    """Swap 设备信息 (来自 /proc/swaps)"""
    name: str = ""          # 设备路径
    type: str = ""          # 类型 (partition, file, zram)
    size_kb: int = 0        # 总大小
    used_kb: int = 0        # 已使用
    priority: int = 0       # 优先级
    
    @property
    def size_mb(self) -> float:
        return self.size_kb / 1024
    
    @property
    def used_mb(self) -> float:
        return self.used_kb / 1024
    
    @property
    def used_percent(self) -> float:
        if self.size_kb == 0:
            return 0
        return (self.used_kb / self.size_kb) * 100
    
    @property
    def is_zram(self) -> bool:
        return 'zram' in self.name.lower()


@dataclass
class ZramSwapData:
    """zRAM/Swap 综合分析数据"""
    # Swap 设备列表
    swap_devices: List[SwapDevice] = field(default_factory=list)
    
    # zRAM 设备列表
    zram_devices: List[ZramDevice] = field(default_factory=list)
    
    # 汇总统计
    total_swap_kb: int = 0
    used_swap_kb: int = 0
    total_zram_disk_kb: int = 0
    total_zram_orig_bytes: int = 0
    total_zram_compr_bytes: int = 0
    total_zram_mem_used_bytes: int = 0
    
    # 原始内容 (用于调试)
    raw_swaps: str = ""
    raw_mm_stat: Dict[str, str] = field(default_factory=dict)
    
    @property
    def total_swap_mb(self) -> float:
        return self.total_swap_kb / 1024
    
    @property
    def used_swap_mb(self) -> float:
        return self.used_swap_kb / 1024
    
    @property
    def swap_used_percent(self) -> float:
        if self.total_swap_kb == 0:
            return 0
        return (self.used_swap_kb / self.total_swap_kb) * 100
    
    @property
    def total_zram_disk_mb(self) -> float:
        return self.total_zram_disk_kb / 1024
    
    @property
    def total_zram_orig_mb(self) -> float:
        return self.total_zram_orig_bytes / 1024 / 1024
    
    @property
    def total_zram_compr_mb(self) -> float:
        return self.total_zram_compr_bytes / 1024 / 1024
    
    @property
    def total_zram_mem_used_mb(self) -> float:
        return self.total_zram_mem_used_bytes / 1024 / 1024
    
    @property
    def overall_compression_ratio(self) -> float:
        """整体压缩率"""
        if self.total_zram_compr_bytes == 0:
            return 0
        return self.total_zram_orig_bytes / self.total_zram_compr_bytes
    
    @property
    def overall_space_saving_percent(self) -> float:
        """整体空间节省百分比"""
        if self.total_zram_orig_bytes == 0:
            return 0
        saved = self.total_zram_orig_bytes - self.total_zram_compr_bytes
        return (saved / self.total_zram_orig_bytes) * 100
    
    @property
    def has_zram(self) -> bool:
        return len(self.zram_devices) > 0
    
    @property
    def memory_saved_mb(self) -> float:
        """节省的内存 (MB)"""
        return self.total_zram_orig_mb - self.total_zram_mem_used_mb


def parse_proc_swaps(content: str) -> List[SwapDevice]:
    """
    解析 /proc/swaps 内容
    
    格式示例:
    Filename                Type        Size    Used    Priority
    /dev/block/zram0        partition   2097148 1234    5
    """
    devices = []
    lines = content.strip().split('\n')
    
    for line in lines[1:]:  # 跳过标题行
        if not line.strip():
            continue
        
        parts = line.split()
        if len(parts) >= 5:
            device = SwapDevice(
                name=parts[0],
                type=parts[1],
                size_kb=int(parts[2]),
                used_kb=int(parts[3]),
                priority=int(parts[4])
            )
            devices.append(device)
    
    return devices


def parse_mm_stat(content: str) -> Dict[str, int]:
    """
    解析 /sys/block/zram*/mm_stat 内容
    
    格式 (空格分隔的数字):
    orig_data_size  compr_data_size  mem_used_total  mem_limit  mem_used_max  same_pages  pages_compacted  huge_pages
    
    注: 字段数量可能因内核版本不同而变化 (5-8 个字段)
    """
    result = {}
    parts = content.strip().split()
    
    field_names = [
        'orig_data_size',
        'compr_data_size', 
        'mem_used_total',
        'mem_limit',
        'mem_used_max',
        'same_pages',
        'pages_compacted',
        'huge_pages'
    ]
    
    for i, value in enumerate(parts):
        if i < len(field_names):
            try:
                result[field_names[i]] = int(value)
            except ValueError:
                result[field_names[i]] = 0
    
    return result


def parse_zram_stat(content: str) -> Dict[str, int]:
    """
    解析 /sys/block/zram*/stat 内容 (块设备 I/O 统计)
    
    格式 (与 /sys/block/*/stat 相同):
    read_ios read_merges read_sectors read_ticks write_ios write_merges write_sectors write_ticks ...
    """
    result = {}
    parts = content.strip().split()
    
    field_names = [
        'read_ios', 'read_merges', 'read_sectors', 'read_ticks',
        'write_ios', 'write_merges', 'write_sectors', 'write_ticks',
        'in_flight', 'io_ticks', 'time_in_queue'
    ]
    
    for i, value in enumerate(parts):
        if i < len(field_names):
            try:
                result[field_names[i]] = int(value)
            except ValueError:
                result[field_names[i]] = 0
    
    return result


def parse_zram_device_from_files(device_data: Dict[str, str]) -> ZramDevice:
    """
    从采集的文件内容解析 zRAM 设备信息
    
    device_data 格式:
    {
        'name': 'zram0',
        'disksize': '2147483648',
        'mm_stat': '123456789 ...',
        'stat': '...',
        # 旧版字段 (可选)
        'orig_data_size': '...',
        'compr_data_size': '...',
        'mem_used_total': '...'
    }
    """
    device = ZramDevice(name=device_data.get('name', 'unknown'))
    
    # 解析 disksize
    if 'disksize' in device_data:
        try:
            device.disksize_kb = int(device_data['disksize'].strip()) // 1024
        except ValueError:
            pass
    
    # 解析 mm_stat (新版本内核)
    if 'mm_stat' in device_data and device_data['mm_stat'].strip():
        mm_stat = parse_mm_stat(device_data['mm_stat'])
        device.orig_data_size_bytes = mm_stat.get('orig_data_size', 0)
        device.compr_data_size_bytes = mm_stat.get('compr_data_size', 0)
        device.mem_used_total_bytes = mm_stat.get('mem_used_total', 0)
        device.mem_limit_bytes = mm_stat.get('mem_limit', 0)
        device.mem_used_max_bytes = mm_stat.get('mem_used_max', 0)
        device.same_pages = mm_stat.get('same_pages', 0)
        device.pages_compacted = mm_stat.get('pages_compacted', 0)
        device.huge_pages = mm_stat.get('huge_pages', 0)
    else:
        # 旧版字段 (兼容旧内核)
        if 'orig_data_size' in device_data:
            try:
                device.orig_data_size_bytes = int(device_data['orig_data_size'].strip())
            except ValueError:
                pass
        if 'compr_data_size' in device_data:
            try:
                device.compr_data_size_bytes = int(device_data['compr_data_size'].strip())
            except ValueError:
                pass
        if 'mem_used_total' in device_data:
            try:
                device.mem_used_total_bytes = int(device_data['mem_used_total'].strip())
            except ValueError:
                pass
    
    # 解析 stat (块设备统计)
    if 'stat' in device_data and device_data['stat'].strip():
        stat = parse_zram_stat(device_data['stat'])
        device.num_reads = stat.get('read_ios', 0)
        device.num_writes = stat.get('write_ios', 0)
    
    return device


def parse_zram_swap_data(swaps_content: str, zram_data: Dict[str, Dict[str, str]]) -> ZramSwapData:
    """
    解析 zRAM/Swap 数据
    
    Args:
        swaps_content: /proc/swaps 文件内容
        zram_data: zRAM 设备数据字典
            {
                'zram0': {
                    'disksize': '...',
                    'mm_stat': '...',
                    ...
                },
                'zram1': { ... }
            }
    
    Returns:
        ZramSwapData 对象
    """
    data = ZramSwapData()
    data.raw_swaps = swaps_content
    
    # 解析 Swap 设备
    if swaps_content.strip():
        data.swap_devices = parse_proc_swaps(swaps_content)
    
    # 计算 Swap 汇总
    for swap in data.swap_devices:
        data.total_swap_kb += swap.size_kb
        data.used_swap_kb += swap.used_kb
    
    # 解析 zRAM 设备
    for name, device_files in zram_data.items():
        device_files['name'] = name
        device = parse_zram_device_from_files(device_files)
        data.zram_devices.append(device)
        data.raw_mm_stat[name] = device_files.get('mm_stat', '')
        
        # 累加统计
        data.total_zram_disk_kb += device.disksize_kb
        data.total_zram_orig_bytes += device.orig_data_size_bytes
        data.total_zram_compr_bytes += device.compr_data_size_bytes
        data.total_zram_mem_used_bytes += device.mem_used_total_bytes
    
    return data


def parse_zram_swap_file(filepath: str) -> ZramSwapData:
    """
    从合并的文件解析 zRAM/Swap 数据
    
    文件格式:
    ===== /proc/swaps =====
    Filename                Type        Size    Used    Priority
    /dev/block/zram0        partition   2097148 1234    5
    
    ===== zram0 =====
    disksize: 2147483648
    mm_stat: 123456789 ...
    stat: ...
    
    ===== zram1 =====
    ...
    """
    with open(filepath, 'r') as f:
        content = f.read()
    
    return parse_zram_swap_content(content)


def parse_zram_swap_content(content: str) -> ZramSwapData:
    """解析合并的 zRAM/Swap 内容"""
    data = ZramSwapData()
    
    # 分割各个部分
    sections = re.split(r'={5,}\s*(.+?)\s*={5,}', content)
    
    swaps_content = ""
    zram_data = {}
    current_zram = None
    
    i = 0
    while i < len(sections):
        section = sections[i].strip()
        
        if section == '/proc/swaps' and i + 1 < len(sections):
            swaps_content = sections[i + 1].strip()
            i += 2
        elif section.startswith('zram'):
            device_name = section
            if i + 1 < len(sections):
                device_content = sections[i + 1].strip()
                zram_data[device_name] = _parse_zram_section(device_content)
            i += 2
        else:
            i += 1
    
    return parse_zram_swap_data(swaps_content, zram_data)


def _parse_zram_section(content: str) -> Dict[str, str]:
    """解析单个 zRAM 设备部分"""
    result = {}
    for line in content.split('\n'):
        if ':' in line:
            key, value = line.split(':', 1)
            result[key.strip()] = value.strip()
    return result


def print_report(data: ZramSwapData):
    """打印 zRAM/Swap 分析报告"""
    print("\n" + "=" * 60)
    print("zRAM/Swap 内存分析")
    print("=" * 60)
    
    # Swap 概览
    print(f"\n{'─' * 40}")
    print("[ Swap 概览 ]")
    print(f"{'─' * 40}")
    
    if data.swap_devices:
        print(f"总 Swap:   {data.total_swap_mb:>10.1f} MB")
        print(f"已使用:    {data.used_swap_mb:>10.1f} MB ({data.swap_used_percent:.1f}%)")
        print(f"空闲:      {data.total_swap_mb - data.used_swap_mb:>10.1f} MB")
        
        print(f"\nSwap 设备列表:")
        print(f"{'设备':<30} {'类型':<12} {'大小(MB)':<10} {'已用(MB)':<10} {'使用率':<8}")
        print("-" * 78)
        for swap in data.swap_devices:
            zram_mark = " [zRAM]" if swap.is_zram else ""
            print(f"{swap.name:<30} {swap.type:<12} {swap.size_mb:>8.1f}   {swap.used_mb:>8.1f}   {swap.used_percent:>6.1f}%{zram_mark}")
    else:
        print("未检测到 Swap 设备")
    
    # zRAM 详情
    if data.has_zram:
        print(f"\n{'─' * 40}")
        print("[ zRAM 压缩内存 ]")
        print(f"{'─' * 40}")
        
        print(f"zRAM 磁盘大小:  {data.total_zram_disk_mb:>10.1f} MB")
        print(f"原始数据:       {data.total_zram_orig_mb:>10.1f} MB")
        print(f"压缩后数据:     {data.total_zram_compr_mb:>10.1f} MB")
        print(f"实际内存占用:   {data.total_zram_mem_used_mb:>10.1f} MB")
        
        if data.overall_compression_ratio > 0:
            print(f"\n压缩率:        {data.overall_compression_ratio:>10.2f}x")
            print(f"空间节省:      {data.overall_space_saving_percent:>10.1f}%")
            print(f"内存节省:      {data.memory_saved_mb:>10.1f} MB")
        
        # 每个 zRAM 设备详情
        if len(data.zram_devices) > 1:
            print(f"\nzRAM 设备详情:")
            print(f"{'设备':<10} {'磁盘大小':<12} {'原始数据':<12} {'压缩后':<12} {'压缩率':<10} {'使用率':<8}")
            print("-" * 70)
            for dev in data.zram_devices:
                print(f"{dev.name:<10} {dev.disksize_mb:>10.1f}MB {dev.orig_data_mb:>10.1f}MB {dev.compr_data_mb:>10.1f}MB {dev.compression_ratio:>8.2f}x {dev.usage_percent:>6.1f}%")
        else:
            # 单个设备时显示更多详情
            dev = data.zram_devices[0]
            print(f"\n设备: {dev.name}")
            if dev.same_pages > 0:
                print(f"相同页面 (零页优化): {dev.same_pages:,} 页")
            if dev.pages_compacted > 0:
                print(f"已压缩页面: {dev.pages_compacted:,} 页")
            if dev.num_reads > 0 or dev.num_writes > 0:
                print(f"I/O 统计: 读 {dev.num_reads:,} 次, 写 {dev.num_writes:,} 次")
    
    # 分析建议
    print(f"\n{'─' * 40}")
    print("[ 分析 ]")
    print(f"{'─' * 40}")
    
    if data.swap_used_percent > 80:
        print("⚠️ Swap 使用率较高 (>80%)，系统可能存在内存压力")
    elif data.swap_used_percent > 50:
        print("⚠️ Swap 使用率中等 (>50%)，建议关注内存使用情况")
    elif data.has_zram and data.swap_used_percent > 0:
        print("✅ Swap/zRAM 使用率正常")
    
    if data.has_zram:
        if data.overall_compression_ratio < 1.5:
            print("⚠️ zRAM 压缩率较低 (<1.5x)，数据可能不太可压缩")
        elif data.overall_compression_ratio > 3:
            print("✅ zRAM 压缩效果很好 (>3x)")
        else:
            print(f"✅ zRAM 压缩率正常 ({data.overall_compression_ratio:.2f}x)")
    
    print("\n" + "=" * 60)


def to_json(data: ZramSwapData) -> dict:
    """转换为 JSON 格式"""
    return {
        'swap': {
            'total_mb': round(data.total_swap_mb, 1),
            'used_mb': round(data.used_swap_mb, 1),
            'used_percent': round(data.swap_used_percent, 1),
            'devices': [
                {
                    'name': d.name,
                    'type': d.type,
                    'size_mb': round(d.size_mb, 1),
                    'used_mb': round(d.used_mb, 1),
                    'used_percent': round(d.used_percent, 1),
                    'is_zram': d.is_zram,
                    'priority': d.priority
                }
                for d in data.swap_devices
            ]
        },
        'zram': {
            'disk_size_mb': round(data.total_zram_disk_mb, 1),
            'orig_data_mb': round(data.total_zram_orig_mb, 1),
            'compr_data_mb': round(data.total_zram_compr_mb, 1),
            'mem_used_mb': round(data.total_zram_mem_used_mb, 1),
            'compression_ratio': round(data.overall_compression_ratio, 2),
            'space_saving_percent': round(data.overall_space_saving_percent, 1),
            'memory_saved_mb': round(data.memory_saved_mb, 1),
            'devices': [
                {
                    'name': d.name,
                    'disksize_mb': round(d.disksize_mb, 1),
                    'orig_data_mb': round(d.orig_data_mb, 1),
                    'compr_data_mb': round(d.compr_data_mb, 1),
                    'mem_used_mb': round(d.mem_used_mb, 1),
                    'compression_ratio': round(d.compression_ratio, 2),
                    'usage_percent': round(d.usage_percent, 1),
                    'same_pages': d.same_pages,
                    'num_reads': d.num_reads,
                    'num_writes': d.num_writes
                }
                for d in data.zram_devices
            ]
        } if data.has_zram else None
    }


def main():
    parser = argparse.ArgumentParser(
        description="zRAM/Swap 内存分析",
        epilog="""
示例:
  # 分析采集的文件
  python3 zram_parser.py -f zram_swap.txt
  
  # 输出 JSON 格式
  python3 zram_parser.py -f zram_swap.txt --json
        """,
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument('-f', '--file', help='zRAM/Swap 数据文件')
    parser.add_argument('--json', action='store_true', help='输出 JSON 格式')
    
    args = parser.parse_args()
    
    if not args.file:
        print("错误: 请提供 -f 参数指定数据文件")
        parser.print_help()
        sys.exit(1)
    
    if not os.path.exists(args.file):
        print(f"错误: 文件不存在: {args.file}")
        sys.exit(1)
    
    data = parse_zram_swap_file(args.file)
    
    if args.json:
        import json
        print(json.dumps(to_json(data), indent=2, ensure_ascii=False))
    else:
        print_report(data)


if __name__ == '__main__':
    main()

