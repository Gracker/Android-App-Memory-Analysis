#!/usr/bin/env python3
# -*- coding:utf-8 -*-
"""
Android 内存对比分析器

对比两次 dump 的内存差异，发现内存增长和泄漏：
- meminfo 对比: PSS/Java Heap/Native 变化
- gfxinfo 对比: View 数量变化、帧率变化
- 高亮显示增长超过阈值的项目
"""

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# Import parsers
from meminfo_parser import parse_meminfo_file, MeminfoData
from gfxinfo_parser import parse_gfxinfo_file, GfxinfoData


@dataclass
class MemoryDiff:
    """内存差异数据"""
    name: str
    before: float
    after: float
    diff: float
    diff_percent: float
    unit: str = "MB"
    warning: bool = False


@dataclass
class DiffResult:
    """对比分析结果"""
    timestamp: str = ""
    package_name: str = ""

    # 内存差异
    memory_diffs: List[MemoryDiff] = field(default_factory=list)

    # Bitmap 差异
    bitmap_diffs: List[MemoryDiff] = field(default_factory=list)

    # UI 资源差异
    ui_diffs: List[MemoryDiff] = field(default_factory=list)

    # 帧率差异
    frame_diffs: List[MemoryDiff] = field(default_factory=list)

    # 警告
    warnings: List[str] = field(default_factory=list)

    # 总结
    summary: str = ""


class DiffAnalyzer:
    """对比分析器"""

    def __init__(self, before_dir: str = None, after_dir: str = None,
                 before_meminfo: str = None, after_meminfo: str = None,
                 before_gfxinfo: str = None, after_gfxinfo: str = None,
                 warning_threshold: float = 20.0):
        """
        初始化对比分析器

        Args:
            before_dir: 前一次 dump 目录
            after_dir: 后一次 dump 目录
            before_meminfo: 前一次 meminfo 文件
            after_meminfo: 后一次 meminfo 文件
            before_gfxinfo: 前一次 gfxinfo 文件
            after_gfxinfo: 后一次 gfxinfo 文件
            warning_threshold: 警告阈值（增长百分比）
        """
        self.warning_threshold = warning_threshold

        # 从目录自动查找文件
        if before_dir:
            before_meminfo = before_meminfo or os.path.join(before_dir, 'meminfo.txt')
            before_gfxinfo = before_gfxinfo or os.path.join(before_dir, 'gfxinfo.txt')
        if after_dir:
            after_meminfo = after_meminfo or os.path.join(after_dir, 'meminfo.txt')
            after_gfxinfo = after_gfxinfo or os.path.join(after_dir, 'gfxinfo.txt')

        self.before_meminfo_file = before_meminfo
        self.after_meminfo_file = after_meminfo
        self.before_gfxinfo_file = before_gfxinfo
        self.after_gfxinfo_file = after_gfxinfo

        self.before_meminfo: Optional[MeminfoData] = None
        self.after_meminfo: Optional[MeminfoData] = None
        self.before_gfxinfo: Optional[GfxinfoData] = None
        self.after_gfxinfo: Optional[GfxinfoData] = None

    def parse_all(self):
        """解析所有文件"""
        if self.before_meminfo_file and os.path.exists(self.before_meminfo_file):
            self.before_meminfo = parse_meminfo_file(self.before_meminfo_file)
        if self.after_meminfo_file and os.path.exists(self.after_meminfo_file):
            self.after_meminfo = parse_meminfo_file(self.after_meminfo_file)
        if self.before_gfxinfo_file and os.path.exists(self.before_gfxinfo_file):
            self.before_gfxinfo = parse_gfxinfo_file(self.before_gfxinfo_file)
        if self.after_gfxinfo_file and os.path.exists(self.after_gfxinfo_file):
            self.after_gfxinfo = parse_gfxinfo_file(self.after_gfxinfo_file)

    def _calc_diff(self, name: str, before: float, after: float, unit: str = "MB") -> MemoryDiff:
        """计算差异"""
        diff = after - before
        diff_percent = (diff / before * 100) if before > 0 else (100 if after > 0 else 0)
        warning = diff_percent > self.warning_threshold
        return MemoryDiff(
            name=name,
            before=before,
            after=after,
            diff=diff,
            diff_percent=diff_percent,
            unit=unit,
            warning=warning
        )

    def analyze(self) -> DiffResult:
        """执行对比分析"""
        self.parse_all()

        result = DiffResult(
            timestamp=datetime.now().isoformat(),
        )

        # 内存对比
        if self.before_meminfo and self.after_meminfo:
            result.package_name = self.after_meminfo.package_name

            # PSS 对比
            result.memory_diffs.append(
                self._calc_diff("Total PSS",
                                self.before_meminfo.total_pss / 1024,
                                self.after_meminfo.total_pss / 1024)
            )
            result.memory_diffs.append(
                self._calc_diff("Java Heap",
                                self.before_meminfo.java_heap_pss / 1024,
                                self.after_meminfo.java_heap_pss / 1024)
            )
            result.memory_diffs.append(
                self._calc_diff("Native Heap",
                                self.before_meminfo.native_heap_pss / 1024,
                                self.after_meminfo.native_heap_pss / 1024)
            )
            result.memory_diffs.append(
                self._calc_diff("Graphics",
                                self.before_meminfo.graphics_pss / 1024,
                                self.after_meminfo.graphics_pss / 1024)
            )
            result.memory_diffs.append(
                self._calc_diff("Code",
                                self.before_meminfo.code_pss / 1024,
                                self.after_meminfo.code_pss / 1024)
            )
            result.memory_diffs.append(
                self._calc_diff("Stack",
                                self.before_meminfo.stack_pss / 1024,
                                self.after_meminfo.stack_pss / 1024)
            )

            # Bitmap 对比
            before_bitmaps = self._get_bitmap_count(self.before_meminfo)
            after_bitmaps = self._get_bitmap_count(self.after_meminfo)
            result.bitmap_diffs.append(
                self._calc_diff("Bitmap 数量", before_bitmaps, after_bitmaps, unit="个")
            )

            before_bitmap_size = self._get_bitmap_size(self.before_meminfo)
            after_bitmap_size = self._get_bitmap_size(self.after_meminfo)
            result.bitmap_diffs.append(
                self._calc_diff("Bitmap 大小", before_bitmap_size, after_bitmap_size)
            )

            # UI 资源对比
            result.ui_diffs.append(
                self._calc_diff("Views",
                                self.before_meminfo.objects.views,
                                self.after_meminfo.objects.views, unit="个")
            )
            result.ui_diffs.append(
                self._calc_diff("Activities",
                                self.before_meminfo.objects.activities,
                                self.after_meminfo.objects.activities, unit="个")
            )
            result.ui_diffs.append(
                self._calc_diff("ViewRootImpl",
                                self.before_meminfo.objects.view_root_impl,
                                self.after_meminfo.objects.view_root_impl, unit="个")
            )

        # 帧率对比
        if self.before_gfxinfo and self.after_gfxinfo:
            result.frame_diffs.append(
                self._calc_diff("卡顿率",
                                self.before_gfxinfo.frame_stats.janky_percent,
                                self.after_gfxinfo.frame_stats.janky_percent, unit="%")
            )
            result.frame_diffs.append(
                self._calc_diff("P90 帧延迟",
                                self.before_gfxinfo.frame_stats.p90_ms,
                                self.after_gfxinfo.frame_stats.p90_ms, unit="ms")
            )

        # 生成警告
        self._generate_warnings(result)

        # 生成总结
        self._generate_summary(result)

        return result

    def _get_bitmap_count(self, meminfo: MeminfoData) -> int:
        """获取 Bitmap 数量"""
        count = 0
        for alloc in meminfo.native_allocations:
            if 'Bitmap' in alloc.name:
                count += int(alloc.count)
        return count

    def _get_bitmap_size(self, meminfo: MeminfoData) -> float:
        """获取 Bitmap 大小 (MB)"""
        size_kb = 0
        for alloc in meminfo.native_allocations:
            if 'Bitmap' in alloc.name:
                size_kb += alloc.size_kb
        return size_kb / 1024

    def _generate_warnings(self, result: DiffResult):
        """生成警告"""
        warnings = result.warnings

        # 检查内存增长
        for diff in result.memory_diffs:
            if diff.warning:
                warnings.append(f"{diff.name} 增长 {diff.diff_percent:.1f}% ({diff.diff:+.2f} {diff.unit})")

        # 检查 Bitmap 增长
        for diff in result.bitmap_diffs:
            if diff.warning:
                if diff.unit == "个":
                    warnings.append(f"{diff.name} 增加 {int(diff.diff):+d} 个 ({diff.diff_percent:.1f}%)")
                else:
                    warnings.append(f"{diff.name} 增长 {diff.diff_percent:.1f}% ({diff.diff:+.2f} {diff.unit})")

        # 检查 Activity 泄漏
        for diff in result.ui_diffs:
            if diff.name == "Activities" and diff.diff > 0:
                warnings.append(f"可能存在 Activity 泄漏: 增加了 {int(diff.diff)} 个 Activity")

        # 检查 View 增长
        for diff in result.ui_diffs:
            if diff.name == "Views" and diff.diff_percent > 50:
                warnings.append(f"View 数量大幅增长: {int(diff.diff):+d} 个 ({diff.diff_percent:.1f}%)")

    def _generate_summary(self, result: DiffResult):
        """生成总结"""
        total_diff = None
        for diff in result.memory_diffs:
            if diff.name == "Total PSS":
                total_diff = diff
                break

        if total_diff:
            if total_diff.diff > 0:
                result.summary = f"内存增长 {total_diff.diff:.2f} MB ({total_diff.diff_percent:.1f}%)"
                if total_diff.diff_percent > self.warning_threshold:
                    result.summary += " ⚠️ 需要关注"
            elif total_diff.diff < 0:
                result.summary = f"内存减少 {abs(total_diff.diff):.2f} MB ({abs(total_diff.diff_percent):.1f}%)"
            else:
                result.summary = "内存无明显变化"

    def print_report(self):
        """打印对比报告"""
        result = self.analyze()

        print("\n" + "=" * 80)
        print("=== Android 内存对比分析报告 ===")
        print("=" * 80)

        if result.package_name:
            print(f"\n包名: {result.package_name}")

        # 总结
        print(f"\n📊 总结: {result.summary}")

        # 内存对比
        if result.memory_diffs:
            print(f"\n{'─' * 60}")
            print("[ 内存对比 ]")
            print(f"{'─' * 60}")
            print(f"{'指标':<15} {'前':<12} {'后':<12} {'变化':<15} {'增长率'}")
            print("-" * 60)
            for diff in result.memory_diffs:
                arrow = "↑" if diff.diff > 0 else ("↓" if diff.diff < 0 else "→")
                warn = " ⚠️" if diff.warning else ""
                print(f"{diff.name:<15} {diff.before:>8.2f} {diff.unit:<3} {diff.after:>8.2f} {diff.unit:<3} "
                      f"{diff.diff:>+8.2f} {diff.unit:<3} {arrow} {diff.diff_percent:>+6.1f}%{warn}")

        # Bitmap 对比
        if result.bitmap_diffs:
            print(f"\n{'─' * 60}")
            print("[ Bitmap 对比 ]")
            print(f"{'─' * 60}")
            for diff in result.bitmap_diffs:
                arrow = "↑" if diff.diff > 0 else ("↓" if diff.diff < 0 else "→")
                warn = " ⚠️" if diff.warning else ""
                if diff.unit == "个":
                    print(f"{diff.name}: {int(diff.before)} → {int(diff.after)} ({int(diff.diff):+d}) {arrow}{warn}")
                else:
                    print(f"{diff.name}: {diff.before:.2f} → {diff.after:.2f} {diff.unit} "
                          f"({diff.diff:+.2f} {diff.unit}) {arrow}{warn}")

        # UI 资源对比
        if result.ui_diffs:
            print(f"\n{'─' * 60}")
            print("[ UI 资源对比 ]")
            print(f"{'─' * 60}")
            for diff in result.ui_diffs:
                arrow = "↑" if diff.diff > 0 else ("↓" if diff.diff < 0 else "→")
                warn = " ⚠️" if diff.warning or (diff.name == "Activities" and diff.diff > 0) else ""
                print(f"{diff.name}: {int(diff.before)} → {int(diff.after)} ({int(diff.diff):+d}) {arrow}{warn}")

        # 帧率对比
        if result.frame_diffs:
            print(f"\n{'─' * 60}")
            print("[ 帧率对比 ]")
            print(f"{'─' * 60}")
            for diff in result.frame_diffs:
                arrow = "↑" if diff.diff > 0 else ("↓" if diff.diff < 0 else "→")
                print(f"{diff.name}: {diff.before:.2f} → {diff.after:.2f} {diff.unit} "
                      f"({diff.diff:+.2f}) {arrow}")

        # 警告
        if result.warnings:
            print(f"\n{'─' * 60}")
            print("[ ⚠️ 警告 ]")
            print(f"{'─' * 60}")
            for warning in result.warnings:
                print(f"  • {warning}")

        print("\n" + "=" * 80)

    def to_json(self, indent=2) -> str:
        """输出 JSON 格式"""
        result = self.analyze()

        def diff_to_dict(diff: MemoryDiff) -> dict:
            return {
                'name': diff.name,
                'before': round(diff.before, 2),
                'after': round(diff.after, 2),
                'diff': round(diff.diff, 2),
                'diff_percent': round(diff.diff_percent, 1),
                'unit': diff.unit,
                'warning': diff.warning
            }

        data = {
            'timestamp': result.timestamp,
            'package_name': result.package_name,
            'summary': result.summary,
            'memory_diffs': [diff_to_dict(d) for d in result.memory_diffs],
            'bitmap_diffs': [diff_to_dict(d) for d in result.bitmap_diffs],
            'ui_diffs': [diff_to_dict(d) for d in result.ui_diffs],
            'frame_diffs': [diff_to_dict(d) for d in result.frame_diffs],
            'warnings': result.warnings
        }

        return json.dumps(data, indent=indent, ensure_ascii=False)


def main():
    parser = argparse.ArgumentParser(
        description="Android 内存对比分析器",
        epilog="""
示例:
  # 对比两个 dump 目录
  python3 diff_analyzer.py -b ./dump_before -a ./dump_after

  # 对比两个 meminfo 文件
  python3 diff_analyzer.py --before-meminfo before.txt --after-meminfo after.txt

  # 输出 JSON 格式
  python3 diff_analyzer.py -b ./dump_before -a ./dump_after --json
        """,
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument('-b', '--before', help='前一次 dump 目录')
    parser.add_argument('-a', '--after', help='后一次 dump 目录')
    parser.add_argument('--before-meminfo', help='前一次 meminfo 文件')
    parser.add_argument('--after-meminfo', help='后一次 meminfo 文件')
    parser.add_argument('--before-gfxinfo', help='前一次 gfxinfo 文件')
    parser.add_argument('--after-gfxinfo', help='后一次 gfxinfo 文件')
    parser.add_argument('--threshold', type=float, default=20.0,
                        help='警告阈值（增长百分比，默认 20%%）')
    parser.add_argument('--json', action='store_true', help='输出 JSON 格式')
    parser.add_argument('-o', '--output', help='输出文件路径')

    args = parser.parse_args()

    if not args.before and not args.before_meminfo:
        print("请提供前一次 dump 目录 (-b) 或 meminfo 文件 (--before-meminfo)")
        parser.print_help()
        sys.exit(1)

    if not args.after and not args.after_meminfo:
        print("请提供后一次 dump 目录 (-a) 或 meminfo 文件 (--after-meminfo)")
        parser.print_help()
        sys.exit(1)

    analyzer = DiffAnalyzer(
        before_dir=args.before,
        after_dir=args.after,
        before_meminfo=args.before_meminfo,
        after_meminfo=args.after_meminfo,
        before_gfxinfo=args.before_gfxinfo,
        after_gfxinfo=args.after_gfxinfo,
        warning_threshold=args.threshold
    )

    if args.json:
        output = analyzer.to_json()
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(output)
            print(f"JSON 报告已保存到: {args.output}")
        else:
            print(output)
    else:
        analyzer.print_report()


if __name__ == '__main__':
    main()
