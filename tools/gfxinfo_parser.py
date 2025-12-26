#!/usr/bin/env python3
# -*- coding:utf-8 -*-
"""
dumpsys gfxinfo 解析器

解析 Android dumpsys gfxinfo 输出，提取关键图形指标：
- 帧率统计（Janky frames、各百分位延迟）
- CPU/GPU 缓存使用
- GraphicBuffer 分配详情
- 渲染管线类型
"""

import re
import argparse
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class FrameStats:
    """帧率统计"""
    total_frames: int = 0
    janky_frames: int = 0
    janky_frames_legacy: int = 0
    janky_percent: float = 0.0
    p50_ms: int = 0
    p90_ms: int = 0
    p95_ms: int = 0
    p99_ms: int = 0
    missed_vsync: int = 0
    high_input_latency: int = 0
    slow_ui_thread: int = 0
    slow_bitmap_uploads: int = 0
    slow_draw_commands: int = 0
    frame_deadline_missed: int = 0


@dataclass
class GpuStats:
    """GPU 统计"""
    p50_ms: int = 0
    p90_ms: int = 0
    p95_ms: int = 0
    p99_ms: int = 0


@dataclass
class CacheEntry:
    """缓存条目"""
    name: str
    size_bytes: int = 0
    entries: int = 0


@dataclass
class GraphicBuffer:
    """GraphicBuffer 信息"""
    handle: str = ""
    size_kb: float = 0
    width: int = 0
    stride: int = 0
    height: int = 0
    layers: int = 0
    format: str = ""
    usage: str = ""
    requestor: str = ""


@dataclass
class GfxinfoData:
    """完整的 gfxinfo 数据"""
    package_name: str = ""
    pid: int = 0
    uptime: int = 0
    realtime: int = 0

    # 帧率统计
    frame_stats: FrameStats = field(default_factory=FrameStats)

    # GPU 统计
    gpu_stats: GpuStats = field(default_factory=GpuStats)

    # 渲染管线
    pipeline: str = ""  # e.g., "Skia (Vulkan)"

    # 内存策略
    max_surface_area: int = 0
    max_resource_usage_mb: float = 0

    # CPU 缓存
    cpu_glyph_cache_kb: float = 0
    cpu_glyph_count: int = 0
    cpu_total_bytes: int = 0

    # GPU 缓存
    gpu_caches: List[CacheEntry] = field(default_factory=list)
    gpu_total_bytes: int = 0
    gpu_purgeable_bytes: int = 0

    # GraphicBuffer
    graphic_buffers: List[GraphicBuffer] = field(default_factory=list)
    graphic_buffers_total_kb: float = 0

    # 上下文
    contexts: int = 0
    contexts_stopped: int = 0


class GfxinfoParser:
    """dumpsys gfxinfo 解析器"""

    def __init__(self, content: str):
        self.content = content
        self.data = GfxinfoData()

    def parse(self) -> GfxinfoData:
        """解析 gfxinfo 内容"""
        self._parse_header()
        self._parse_frame_stats()
        self._parse_gpu_stats()
        self._parse_pipeline()
        self._parse_memory_policy()
        self._parse_cpu_caches()
        self._parse_gpu_caches()
        self._parse_graphic_buffers()
        return self.data

    def _parse_header(self):
        """解析头部信息"""
        # Uptime: 545135 Realtime: 545135
        m = re.search(r'Uptime:\s*(\d+)\s+Realtime:\s*(\d+)', self.content)
        if m:
            self.data.uptime = int(m.group(1))
            self.data.realtime = int(m.group(2))

        # ** Graphics info for pid 2137 [com.android.systemui] **
        m = re.search(r'Graphics info for pid (\d+) \[([^\]]+)\]', self.content)
        if m:
            self.data.pid = int(m.group(1))
            self.data.package_name = m.group(2)

    def _parse_frame_stats(self):
        """解析帧率统计"""
        stats = self.data.frame_stats

        # Total frames rendered: 635
        m = re.search(r'Total frames rendered:\s*(\d+)', self.content)
        if m:
            stats.total_frames = int(m.group(1))

        # Janky frames: 44 (6.93%)
        m = re.search(r'Janky frames:\s*(\d+)\s*\((\d+\.?\d*)%\)', self.content)
        if m:
            stats.janky_frames = int(m.group(1))
            stats.janky_percent = float(m.group(2))

        # Janky frames (legacy): 84 (13.23%)
        m = re.search(r'Janky frames \(legacy\):\s*(\d+)', self.content)
        if m:
            stats.janky_frames_legacy = int(m.group(1))

        # Percentiles
        for pct, attr in [('50th', 'p50_ms'), ('90th', 'p90_ms'),
                          ('95th', 'p95_ms'), ('99th', 'p99_ms')]:
            m = re.search(rf'{pct} percentile:\s*(\d+)ms', self.content)
            if m:
                setattr(stats, attr, int(m.group(1)))

        # Other stats
        patterns = [
            (r'Number Missed Vsync:\s*(\d+)', 'missed_vsync'),
            (r'Number High input latency:\s*(\d+)', 'high_input_latency'),
            (r'Number Slow UI thread:\s*(\d+)', 'slow_ui_thread'),
            (r'Number Slow bitmap uploads:\s*(\d+)', 'slow_bitmap_uploads'),
            (r'Number Slow issue draw commands:\s*(\d+)', 'slow_draw_commands'),
            (r'Number Frame deadline missed:\s*(\d+)', 'frame_deadline_missed'),
        ]
        for pattern, attr in patterns:
            m = re.search(pattern, self.content)
            if m:
                setattr(stats, attr, int(m.group(1)))

    def _parse_gpu_stats(self):
        """解析 GPU 统计"""
        gpu = self.data.gpu_stats

        for pct, attr in [('50th gpu', 'p50_ms'), ('90th gpu', 'p90_ms'),
                          ('95th gpu', 'p95_ms'), ('99th gpu', 'p99_ms')]:
            m = re.search(rf'{pct} percentile:\s*(\d+)ms', self.content)
            if m:
                setattr(gpu, attr, int(m.group(1)))

    def _parse_pipeline(self):
        """解析渲染管线类型"""
        # Pipeline=Skia (Vulkan)
        m = re.search(r'Pipeline=(.+)', self.content)
        if m:
            self.data.pipeline = m.group(1).strip()

        # Contexts: 6 (stopped = 3)
        m = re.search(r'Contexts:\s*(\d+)\s*\(stopped\s*=\s*(\d+)\)', self.content)
        if m:
            self.data.contexts = int(m.group(1))
            self.data.contexts_stopped = int(m.group(2))

    def _parse_memory_policy(self):
        """解析内存策略"""
        # Max surface area: 8090160
        m = re.search(r'Max surface area:\s*(\d+)', self.content)
        if m:
            self.data.max_surface_area = int(m.group(1))

        # Max resource usage: 388.33MB
        m = re.search(r'Max resource usage:\s*([\d.]+)MB', self.content)
        if m:
            self.data.max_resource_usage_mb = float(m.group(1))

    def _parse_cpu_caches(self):
        """解析 CPU 缓存"""
        # Glyph Cache: 173.82 KB (1 entry)
        m = re.search(r'Glyph Cache:\s*([\d.]+)\s*KB\s*\((\d+)', self.content)
        if m:
            self.data.cpu_glyph_cache_kb = float(m.group(1))

        # Glyph Count: 47
        m = re.search(r'Glyph Count:\s*(\d+)', self.content)
        if m:
            self.data.cpu_glyph_count = int(m.group(1))

        # Total CPU memory usage: 177995 bytes
        m = re.search(r'Total CPU memory usage:\s*(\d+)\s*bytes', self.content)
        if m:
            self.data.cpu_total_bytes = int(m.group(1))

    def _parse_gpu_caches(self):
        """解析 GPU 缓存"""
        # 查找 GPU Caches 部分
        gpu_section = re.search(
            r'GPU Caches:(.+?)(?:Total GPU memory usage:|GraphicBufferAllocator)',
            self.content, re.DOTALL
        )
        if not gpu_section:
            return

        section = gpu_section.group(1)

        # 匹配行如: "    Surface: 17.75 MB (43 entries)"
        pattern = r'([A-Za-z]+):\s*([\d.]+)\s*(KB|MB|bytes)\s*\((\d+)\s*entr'
        for m in re.finditer(pattern, section):
            name = m.group(1)
            size = float(m.group(2))
            unit = m.group(3)
            entries = int(m.group(4))

            # 转换为字节
            if unit == 'KB':
                size_bytes = int(size * 1024)
            elif unit == 'MB':
                size_bytes = int(size * 1024 * 1024)
            else:
                size_bytes = int(size)

            self.data.gpu_caches.append(CacheEntry(
                name=name, size_bytes=size_bytes, entries=entries
            ))

        # Total GPU memory usage: 18914048 bytes, 18.04 MB (113.58 KB is purgeable)
        m = re.search(r'Total GPU memory usage:\s*(\d+)\s*bytes', self.content)
        if m:
            self.data.gpu_total_bytes = int(m.group(1))

        m = re.search(r'\(([\d.]+)\s*KB is purgeable\)', self.content)
        if m:
            self.data.gpu_purgeable_bytes = int(float(m.group(1)) * 1024)

    def _parse_graphic_buffers(self):
        """解析 GraphicBuffer 分配"""
        # 查找 GraphicBufferAllocator 部分
        buffers_section = re.search(
            r'GraphicBufferAllocator buffers:(.+?)(?:\n\n|\Z)',
            self.content, re.DOTALL
        )
        if not buffers_section:
            return

        section = buffers_section.group(1)

        # 匹配行如:
        # 0xb4000074bdc62130 |   815.62 KiB | 1440 (1440) x  145 |      1 |        1 | 0x     b00 | VRI[StatusBar]#3(BLAST Consumer)3
        pattern = r'(0x[a-fA-F0-9]+)\s*\|\s*([\d.]+)\s*KiB\s*\|\s*(\d+)\s*\(\s*(\d+)\)\s*x\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(\S+)\s*\|\s*(0x\s*[a-fA-F0-9]+)\s*\|\s*(.+)'

        total_kb = 0
        for m in re.finditer(pattern, section):
            buf = GraphicBuffer(
                handle=m.group(1),
                size_kb=float(m.group(2)),
                width=int(m.group(3)),
                stride=int(m.group(4)),
                height=int(m.group(5)),
                layers=int(m.group(6)),
                format=m.group(7),
                usage=m.group(8).strip(),
                requestor=m.group(9).strip()
            )
            self.data.graphic_buffers.append(buf)
            total_kb += buf.size_kb

        self.data.graphic_buffers_total_kb = total_kb

    def get_summary(self) -> Dict:
        """获取汇总信息"""
        return {
            'package_name': self.data.package_name,
            'pid': self.data.pid,
            'pipeline': self.data.pipeline,
            'total_frames': self.data.frame_stats.total_frames,
            'janky_percent': self.data.frame_stats.janky_percent,
            'p50_ms': self.data.frame_stats.p50_ms,
            'p90_ms': self.data.frame_stats.p90_ms,
            'cpu_cache_kb': self.data.cpu_total_bytes / 1024,
            'gpu_cache_mb': self.data.gpu_total_bytes / 1024 / 1024,
            'graphic_buffers_mb': self.data.graphic_buffers_total_kb / 1024,
        }


def parse_gfxinfo_file(file_path: str) -> GfxinfoData:
    """解析 gfxinfo 文件"""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    parser = GfxinfoParser(content)
    return parser.parse()


def print_gfxinfo_report(data: GfxinfoData):
    """打印 gfxinfo 分析报告"""
    print("\n" + "=" * 70)
    print(f"=== dumpsys gfxinfo 分析报告 ===")
    print("=" * 70)

    print(f"\n包名: {data.package_name}")
    print(f"PID: {data.pid}")
    print(f"渲染管线: {data.pipeline}")
    print(f"Contexts: {data.contexts} (stopped: {data.contexts_stopped})")

    # 帧率统计
    stats = data.frame_stats
    print(f"\n--- 帧率统计 ---")
    print(f"总帧数: {stats.total_frames}")
    print(f"卡顿帧: {stats.janky_frames} ({stats.janky_percent:.2f}%)")
    print(f"帧延迟: p50={stats.p50_ms}ms | p90={stats.p90_ms}ms | p95={stats.p95_ms}ms | p99={stats.p99_ms}ms")
    print(f"Missed Vsync: {stats.missed_vsync} | Slow UI: {stats.slow_ui_thread} | Slow Draw: {stats.slow_draw_commands}")

    # GPU 统计
    gpu = data.gpu_stats
    print(f"\n--- GPU 统计 ---")
    print(f"GPU 延迟: p50={gpu.p50_ms}ms | p90={gpu.p90_ms}ms | p95={gpu.p95_ms}ms | p99={gpu.p99_ms}ms")

    # 内存使用
    print(f"\n--- 内存使用 ---")
    print(f"Max Resource Usage: {data.max_resource_usage_mb:.2f} MB")
    print(f"CPU 缓存: {data.cpu_total_bytes / 1024:.2f} KB (Glyph: {data.cpu_glyph_count} 个字符)")
    print(f"GPU 缓存: {data.gpu_total_bytes / 1024 / 1024:.2f} MB (可回收: {data.gpu_purgeable_bytes / 1024:.2f} KB)")

    if data.gpu_caches:
        print(f"\n  GPU 缓存详情:")
        for cache in data.gpu_caches:
            size_str = f"{cache.size_bytes / 1024:.2f} KB" if cache.size_bytes < 1024 * 1024 else f"{cache.size_bytes / 1024 / 1024:.2f} MB"
            print(f"    {cache.name}: {size_str} ({cache.entries} entries)")

    # GraphicBuffer
    if data.graphic_buffers:
        print(f"\n--- GraphicBuffer ({len(data.graphic_buffers)} 个, 共 {data.graphic_buffers_total_kb:.2f} KB) ---")
        for buf in data.graphic_buffers[:10]:  # 只显示前10个
            print(f"  {buf.width}x{buf.height} ({buf.size_kb:.2f} KB) - {buf.requestor}")
        if len(data.graphic_buffers) > 10:
            print(f"  ... 还有 {len(data.graphic_buffers) - 10} 个")

    print("\n" + "=" * 70)


def main():
    parser = argparse.ArgumentParser(
        description="dumpsys gfxinfo 解析器",
        epilog="""
示例:
  python3 gfxinfo_parser.py gfxinfo.txt
  python3 gfxinfo_parser.py -f gfxinfo.txt --json
        """,
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument('file', nargs='?', help='gfxinfo 文件路径')
    parser.add_argument('-f', '--file', dest='file_alt', help='gfxinfo 文件路径 (备选)')
    parser.add_argument('--json', action='store_true', help='输出 JSON 格式')

    args = parser.parse_args()

    file_path = args.file or args.file_alt
    if not file_path:
        print("请指定 gfxinfo 文件路径")
        parser.print_help()
        return

    if not os.path.exists(file_path):
        print(f"错误: 文件不存在: {file_path}")
        return

    data = parse_gfxinfo_file(file_path)

    if args.json:
        import json
        parser_obj = GfxinfoParser("")
        parser_obj.data = data
        output = parser_obj.get_summary()
        print(json.dumps(output, indent=2))
    else:
        print_gfxinfo_report(data)


if __name__ == '__main__':
    main()
