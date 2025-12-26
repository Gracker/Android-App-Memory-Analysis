#!/usr/bin/env python3
# -*- coding:utf-8 -*-
"""
DMA-BUF 解析器

解析 /sys/kernel/debug/dma_buf/bufinfo 输出，分析图形/相机/音频/视频内存使用。
数据来源: adb shell su 0 cat /sys/kernel/debug/dma_buf/bufinfo (需要 root)

DMA-BUF 是 Android 中用于在不同硬件组件间共享内存的机制，
常用于 GPU、Display、Camera、Video 等场景。
"""

import argparse
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class DmaBufEntry:
    """单个 DMA-BUF 条目"""
    size_bytes: int = 0
    flags: int = 0
    mode: int = 0
    ref_count: int = 0
    exporter: str = ""
    inode: int = 0
    attached_devices: List[str] = field(default_factory=list)


@dataclass
class DmaBufCategory:
    """DMA-BUF 分类统计"""
    name: str = ""
    name_cn: str = ""
    total_bytes: int = 0
    count: int = 0
    entries: List[DmaBufEntry] = field(default_factory=list)

    @property
    def total_mb(self) -> float:
        return self.total_bytes / 1024 / 1024


@dataclass
class DmaBufData:
    """DMA-BUF 解析结果"""
    total_bytes: int = 0
    total_count: int = 0

    # 按类型分类
    gpu: DmaBufCategory = field(default_factory=lambda: DmaBufCategory(name="GPU", name_cn="GPU 图形"))
    display: DmaBufCategory = field(default_factory=lambda: DmaBufCategory(name="Display", name_cn="显示"))
    camera: DmaBufCategory = field(default_factory=lambda: DmaBufCategory(name="Camera", name_cn="相机"))
    video: DmaBufCategory = field(default_factory=lambda: DmaBufCategory(name="Video", name_cn="视频"))
    audio: DmaBufCategory = field(default_factory=lambda: DmaBufCategory(name="Audio", name_cn="音频"))
    other: DmaBufCategory = field(default_factory=lambda: DmaBufCategory(name="Other", name_cn="其他"))

    # 所有条目
    entries: List[DmaBufEntry] = field(default_factory=list)

    # 解析警告/错误
    warnings: List[str] = field(default_factory=list)

    @property
    def total_mb(self) -> float:
        return self.total_bytes / 1024 / 1024

    def get_categories(self) -> List[DmaBufCategory]:
        """返回所有非空分类"""
        categories = [self.gpu, self.display, self.camera, self.video, self.audio, self.other]
        return [c for c in categories if c.count > 0]


def categorize_device(device_name: str) -> str:
    """
    根据设备名称判断 DMA-BUF 类型

    常见设备名称模式:
    - GPU: kgsl-3d0, adreno, mali, pvr
    - Display: mdss_mdp, drm, fb
    - Camera: cam_smmu, msm_camera
    - Video: vidc, venus, v4l2
    - Audio: msm-audio-ion, audio
    """
    device_lower = device_name.lower()

    # GPU 相关
    if any(x in device_lower for x in ['kgsl', 'adreno', 'mali', 'gpu', 'pvr']):
        return 'gpu'

    # 显示相关
    if any(x in device_lower for x in ['mdss', 'mdp', 'drm', 'fb', 'display', 'dpu']):
        return 'display'

    # 相机相关
    if any(x in device_lower for x in ['cam', 'camera', 'isp']):
        return 'camera'

    # 视频编解码
    if any(x in device_lower for x in ['vidc', 'venus', 'v4l2', 'video', 'codec']):
        return 'video'

    # 音频相关
    if any(x in device_lower for x in ['audio', 'sound', 'adsp']):
        return 'audio'

    return 'other'


def parse_dmabuf_bufinfo(content: str) -> DmaBufData:
    """
    解析 /sys/kernel/debug/dma_buf/bufinfo 输出

    格式示例:
    Dma-buf Objects:
    size	flags	mode	count	exp_name
    size    	flags   	mode    	count   	exp_name	ino
    00032768	00000002	00000007	00000002	ion	00075971
        Attached Devices:
    Total 0 devices attached

    00057344	00000002	00000007	00000003	ion	00065435
        Attached Devices:
        kgsl-3d0
    Total 1 devices attached

    Total 172 objects, 120500224 bytes
    """
    data = DmaBufData()
    lines = content.strip().split('\n')

    current_entry: Optional[DmaBufEntry] = None
    reading_devices = False

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # 跳过头部
        if line.startswith('Dma-buf') or line.startswith('size'):
            continue

        # 解析总结行
        if line.startswith('Total') and 'objects' in line:
            match = re.search(r'Total\s+(\d+)\s+objects,\s+(\d+)\s+bytes', line)
            if match:
                data.total_count = int(match.group(1))
                data.total_bytes = int(match.group(2))
            continue

        # 设备附加列表
        if 'Attached Devices' in line:
            reading_devices = True
            continue

        if line.startswith('Total') and 'devices attached' in line:
            reading_devices = False
            if current_entry:
                data.entries.append(current_entry)
                _categorize_entry(data, current_entry)
            continue

        if reading_devices and current_entry:
            # 这是一个设备名称
            current_entry.attached_devices.append(line)
            continue

        # 尝试解析 DMA-BUF 条目行
        # 格式: size flags mode count exp_name [ino]
        parts = line.split()
        if len(parts) >= 5:
            try:
                entry = DmaBufEntry()
                # 尝试解析 size (可能是十进制或十六进制)
                size_str = parts[0]
                if size_str.startswith('0x') or size_str.startswith('0X'):
                    entry.size_bytes = int(size_str, 16)
                elif all(c in '0123456789abcdefABCDEF' for c in size_str) and len(size_str) == 8:
                    # 8位数字，可能是十进制也可能是无前缀十六进制
                    # 尝试十进制优先
                    entry.size_bytes = int(size_str)
                else:
                    entry.size_bytes = int(size_str)

                entry.flags = int(parts[1], 16) if len(parts[1]) == 8 else int(parts[1])
                entry.mode = int(parts[2], 16) if len(parts[2]) == 8 else int(parts[2])
                entry.ref_count = int(parts[3], 16) if len(parts[3]) == 8 else int(parts[3])
                entry.exporter = parts[4]
                if len(parts) > 5:
                    entry.inode = int(parts[5])

                current_entry = entry
            except (ValueError, IndexError) as e:
                data.warnings.append(f"Failed to parse line: {line[:50]}... ({e})")
                continue

    return data


def _categorize_entry(data: DmaBufData, entry: DmaBufEntry):
    """将 DMA-BUF 条目分类到对应类别"""
    categories_hit = set()

    for device in entry.attached_devices:
        cat = categorize_device(device)
        categories_hit.add(cat)

    # 如果没有附加设备，归类为 other
    if not categories_hit:
        categories_hit.add('other')

    # 根据优先级选择主类别 (GPU > Display > Camera > Video > Audio > Other)
    if 'gpu' in categories_hit:
        primary_cat = 'gpu'
    elif 'display' in categories_hit:
        primary_cat = 'display'
    elif 'camera' in categories_hit:
        primary_cat = 'camera'
    elif 'video' in categories_hit:
        primary_cat = 'video'
    elif 'audio' in categories_hit:
        primary_cat = 'audio'
    else:
        primary_cat = 'other'

    # 添加到对应类别
    cat_obj = getattr(data, primary_cat)
    cat_obj.count += 1
    cat_obj.total_bytes += entry.size_bytes
    cat_obj.entries.append(entry)


def parse_dmabuf_file(filepath: str) -> DmaBufData:
    """从文件解析 DMA-BUF 信息"""
    with open(filepath, 'r') as f:
        content = f.read()
    return parse_dmabuf_bufinfo(content)


def print_report(data: DmaBufData):
    """打印 DMA-BUF 分析报告"""
    print("\n" + "=" * 60)
    print("DMA-BUF 内存分析")
    print("=" * 60)

    # 概览
    print(f"\n{'─' * 40}")
    print("[ 概览 ]")
    print(f"{'─' * 40}")
    print(f"总 DMA-BUF 内存: {data.total_mb:>10.2f} MB")
    print(f"总 Buffer 数量:  {data.total_count:>10}")

    # 分类统计
    print(f"\n{'─' * 40}")
    print("[ 分类统计 ]")
    print(f"{'─' * 40}")

    categories = data.get_categories()
    if categories:
        for cat in sorted(categories, key=lambda x: x.total_bytes, reverse=True):
            pct = (cat.total_bytes / data.total_bytes * 100) if data.total_bytes > 0 else 0
            print(f"  {cat.name_cn:12}: {cat.total_mb:>8.2f} MB ({cat.count:>3} buffers, {pct:>5.1f}%)")
    else:
        print("  无分类数据")

    # 大内存块 TOP 5
    print(f"\n{'─' * 40}")
    print("[ TOP 5 大内存块 ]")
    print(f"{'─' * 40}")

    sorted_entries = sorted(data.entries, key=lambda x: x.size_bytes, reverse=True)[:5]
    for i, entry in enumerate(sorted_entries, 1):
        size_mb = entry.size_bytes / 1024 / 1024
        devices = ', '.join(entry.attached_devices) if entry.attached_devices else '(无附加设备)'
        print(f"  {i}. {size_mb:>8.2f} MB - {devices}")

    # 警告
    if data.warnings:
        print(f"\n{'─' * 40}")
        print("[ 解析警告 ]")
        print(f"{'─' * 40}")
        for w in data.warnings[:5]:
            print(f"  - {w}")
        if len(data.warnings) > 5:
            print(f"  ... 还有 {len(data.warnings) - 5} 条警告")

    print("\n" + "=" * 60)


def to_json(data: DmaBufData) -> dict:
    """转换为 JSON 格式"""
    categories = {}
    for cat in data.get_categories():
        categories[cat.name.lower()] = {
            'name': cat.name,
            'name_cn': cat.name_cn,
            'total_mb': round(cat.total_mb, 2),
            'count': cat.count,
        }

    top_entries = []
    sorted_entries = sorted(data.entries, key=lambda x: x.size_bytes, reverse=True)[:10]
    for entry in sorted_entries:
        top_entries.append({
            'size_mb': round(entry.size_bytes / 1024 / 1024, 2),
            'size_bytes': entry.size_bytes,
            'exporter': entry.exporter,
            'ref_count': entry.ref_count,
            'devices': entry.attached_devices,
        })

    return {
        'total_mb': round(data.total_mb, 2),
        'total_count': data.total_count,
        'categories': categories,
        'top_entries': top_entries,
    }


def main():
    parser = argparse.ArgumentParser(
        description="DMA-BUF 内存分析",
        epilog="""
示例:
  python3 dmabuf_parser.py -f dmabuf_debug.txt
  adb shell su 0 cat /sys/kernel/debug/dma_buf/bufinfo | python3 dmabuf_parser.py
        """,
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument('-f', '--file', help='DMA-BUF debug 文件路径')
    parser.add_argument('--json', action='store_true', help='输出 JSON 格式')

    args = parser.parse_args()

    if args.file:
        if not os.path.exists(args.file):
            print(f"错误: 文件不存在: {args.file}")
            sys.exit(1)
        data = parse_dmabuf_file(args.file)
    else:
        # 从 stdin 读取
        content = sys.stdin.read()
        if not content.strip():
            print("错误: 请提供 -f 参数或通过管道输入数据")
            sys.exit(1)
        data = parse_dmabuf_bufinfo(content)

    if args.json:
        import json
        print(json.dumps(to_json(data), indent=2, ensure_ascii=False))
    else:
        print_report(data)


if __name__ == '__main__':
    main()
