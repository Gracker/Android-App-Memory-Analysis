#!/usr/bin/env python3
# -*- coding:utf-8 -*-
"""
dumpsys meminfo 解析器

解析 Android dumpsys meminfo 输出，提取关键内存指标：
- 内存分类（Native/Dalvik/Code/Graphics/Stack）
- Objects 统计（Views/Activities/Binders）
- Native Allocations（Bitmap malloced/nonmalloced）
- SQL 内存使用
"""

import re
import argparse
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class MemoryCategory:
    """内存分类"""
    name: str
    pss_total: int = 0          # KB
    private_dirty: int = 0       # KB
    private_clean: int = 0       # KB
    swap_dirty: int = 0          # KB
    rss_total: int = 0           # KB
    heap_size: int = 0           # KB (仅 Native/Dalvik Heap)
    heap_alloc: int = 0          # KB
    heap_free: int = 0           # KB


@dataclass
class ObjectsInfo:
    """对象统计"""
    views: int = 0
    view_root_impl: int = 0
    app_contexts: int = 0
    activities: int = 0
    assets: int = 0
    asset_managers: int = 0
    local_binders: int = 0
    proxy_binders: int = 0
    parcel_memory: int = 0       # KB
    parcel_count: int = 0
    death_recipients: int = 0
    webviews: int = 0


@dataclass
class NativeAllocation:
    """Native 分配统计"""
    name: str
    count: int = 0
    size_kb: float = 0


@dataclass
class MeminfoData:
    """完整的 meminfo 数据"""
    package_name: str = ""
    pid: int = 0
    uptime: int = 0
    realtime: int = 0

    # 内存分类
    categories: Dict[str, MemoryCategory] = field(default_factory=dict)

    # 汇总
    total_pss: int = 0           # KB
    total_private_dirty: int = 0
    total_rss: int = 0
    total_swap: int = 0

    # App Summary
    java_heap_pss: int = 0
    java_heap_rss: int = 0
    native_heap_pss: int = 0
    native_heap_rss: int = 0
    code_pss: int = 0
    code_rss: int = 0
    stack_pss: int = 0
    stack_rss: int = 0
    graphics_pss: int = 0
    graphics_rss: int = 0
    private_other: int = 0
    system: int = 0

    # Objects
    objects: ObjectsInfo = field(default_factory=ObjectsInfo)

    # Native Allocations
    native_allocations: List[NativeAllocation] = field(default_factory=list)

    # SQL
    sql_memory_used: int = 0
    sql_pagecache_overflow: int = 0


class MeminfoParser:
    """dumpsys meminfo 解析器"""

    def __init__(self, content: str):
        self.content = content
        self.data = MeminfoData()

    def parse(self) -> MeminfoData:
        """解析 meminfo 内容"""
        self._parse_header()
        self._parse_memory_table()
        self._parse_app_summary()
        self._parse_objects()
        self._parse_native_allocations()
        self._parse_sql()
        return self.data

    def _parse_header(self):
        """解析头部信息"""
        # Uptime: 544084 Realtime: 544084
        m = re.search(r'Uptime:\s*(\d+)\s+Realtime:\s*(\d+)', self.content)
        if m:
            self.data.uptime = int(m.group(1))
            self.data.realtime = int(m.group(2))

        # ** MEMINFO in pid 2137 [com.android.systemui] **
        m = re.search(r'MEMINFO in pid (\d+) \[([^\]]+)\]', self.content)
        if m:
            self.data.pid = int(m.group(1))
            self.data.package_name = m.group(2)

    def _parse_memory_table(self):
        """解析内存分类表格"""
        # 查找表格开始
        lines = self.content.split('\n')
        in_table = False
        header_found = False

        for line in lines:
            # 检测表头
            if 'Pss' in line and 'Private' in line and 'Dirty' in line:
                header_found = True
                continue

            if header_found and '------' in line:
                in_table = True
                continue

            if in_table:
                # 表格结束
                if line.strip() == '' or 'App Summary' in line:
                    break

                # 解析行: "  Native Heap    33897    33888        0        0    38348    47348    35473     7316"
                parts = line.split()
                if len(parts) >= 6:
                    # 处理多词名称（如 "Native Heap", "Dalvik Other"）
                    try:
                        # 找到第一个数字的位置
                        num_start = 0
                        for i, p in enumerate(parts):
                            try:
                                int(p)
                                num_start = i
                                break
                            except ValueError:
                                continue

                        if num_start > 0:
                            name = ' '.join(parts[:num_start])
                            values = parts[num_start:]

                            cat = MemoryCategory(name=name)
                            if len(values) >= 1:
                                cat.pss_total = int(values[0])
                            if len(values) >= 2:
                                cat.private_dirty = int(values[1])
                            if len(values) >= 3:
                                cat.private_clean = int(values[2])
                            if len(values) >= 4:
                                cat.swap_dirty = int(values[3])
                            if len(values) >= 5:
                                cat.rss_total = int(values[4])
                            if len(values) >= 6:
                                cat.heap_size = int(values[5])
                            if len(values) >= 7:
                                cat.heap_alloc = int(values[6])
                            if len(values) >= 8:
                                cat.heap_free = int(values[7])

                            self.data.categories[name] = cat
                    except (ValueError, IndexError):
                        continue

        # 解析汇总行: "TOTAL PSS:   155992            TOTAL RSS:   399256      TOTAL SWAP (KB):      152"
        m = re.search(r'TOTAL PSS:\s*(\d+)', self.content)
        if m:
            self.data.total_pss = int(m.group(1))

        m = re.search(r'TOTAL RSS:\s*(\d+)', self.content)
        if m:
            self.data.total_rss = int(m.group(1))

        m = re.search(r'TOTAL SWAP.*?:\s*(\d+)', self.content)
        if m:
            self.data.total_swap = int(m.group(1))

    def _parse_app_summary(self):
        """解析 App Summary 部分"""
        # Java Heap:    32532                          71748
        patterns = [
            (r'Java Heap:\s*(\d+)\s+(\d+)', 'java_heap'),
            (r'Native Heap:\s*(\d+)\s+(\d+)', 'native_heap'),
            (r'Code:\s*(\d+)\s+(\d+)', 'code'),
            (r'Stack:\s*(\d+)\s+(\d+)', 'stack'),
            (r'Graphics:\s*(\d+)\s+(\d+)', 'graphics'),
            (r'Private Other:\s*(\d+)', 'private_other'),
            (r'System:\s*(\d+)', 'system'),
        ]

        for pattern, attr in patterns:
            m = re.search(pattern, self.content)
            if m:
                if attr == 'private_other':
                    self.data.private_other = int(m.group(1))
                elif attr == 'system':
                    self.data.system = int(m.group(1))
                else:
                    setattr(self.data, f'{attr}_pss', int(m.group(1)))
                    setattr(self.data, f'{attr}_rss', int(m.group(2)))

    def _parse_objects(self):
        """解析 Objects 部分"""
        obj = self.data.objects

        patterns = [
            (r'Views:\s*(\d+)', 'views'),
            (r'ViewRootImpl:\s*(\d+)', 'view_root_impl'),
            (r'AppContexts:\s*(\d+)', 'app_contexts'),
            (r'Activities:\s*(\d+)', 'activities'),
            (r'Assets:\s*(\d+)', 'assets'),
            (r'AssetManagers:\s*(\d+)', 'asset_managers'),
            (r'Local Binders:\s*(\d+)', 'local_binders'),
            (r'Proxy Binders:\s*(\d+)', 'proxy_binders'),
            (r'Parcel memory:\s*(\d+)', 'parcel_memory'),
            (r'Parcel count:\s*(\d+)', 'parcel_count'),
            (r'Death Recipients:\s*(\d+)', 'death_recipients'),
            (r'WebViews:\s*(\d+)', 'webviews'),
        ]

        for pattern, attr in patterns:
            m = re.search(pattern, self.content)
            if m:
                setattr(obj, attr, int(m.group(1)))

    def _parse_native_allocations(self):
        """解析 Native Allocations 部分"""
        # 查找 Native Allocations 部分
        native_section = re.search(
            r'Native Allocations.*?(?=\n\s*SQL|\n\s*$|\Z)',
            self.content,
            re.DOTALL
        )
        if not native_section:
            return

        section = native_section.group(0)

        # 匹配行如: "   Bitmap (malloced):       20                           6185"
        pattern = r'([A-Za-z]+)\s*\(([^)]+)\):\s*(\d+)\s+(\d+(?:\.\d+)?)'
        for m in re.finditer(pattern, section):
            name = f"{m.group(1)} ({m.group(2)})"
            count = int(m.group(3))
            size_kb = float(m.group(4))
            self.data.native_allocations.append(
                NativeAllocation(name=name, count=count, size_kb=size_kb)
            )

    def _parse_sql(self):
        """解析 SQL 部分"""
        m = re.search(r'MEMORY_USED:\s*(\d+)', self.content)
        if m:
            self.data.sql_memory_used = int(m.group(1))

        m = re.search(r'PAGECACHE_OVERFLOW:\s*(\d+)', self.content)
        if m:
            self.data.sql_pagecache_overflow = int(m.group(1))

    def get_bitmap_stats(self) -> Dict[str, Dict[str, float]]:
        """获取 Bitmap 统计"""
        result = {
            'malloced': {'count': 0, 'size_kb': 0},
            'nonmalloced': {'count': 0, 'size_kb': 0},
            'total': {'count': 0, 'size_kb': 0}
        }

        for alloc in self.data.native_allocations:
            if 'Bitmap' in alloc.name:
                if 'malloced' in alloc.name and 'non' not in alloc.name:
                    result['malloced']['count'] = alloc.count
                    result['malloced']['size_kb'] = alloc.size_kb
                elif 'nonmalloced' in alloc.name:
                    result['nonmalloced']['count'] = alloc.count
                    result['nonmalloced']['size_kb'] = alloc.size_kb

        result['total']['count'] = result['malloced']['count'] + result['nonmalloced']['count']
        result['total']['size_kb'] = result['malloced']['size_kb'] + result['nonmalloced']['size_kb']
        return result


def parse_meminfo_file(file_path: str) -> MeminfoData:
    """解析 meminfo 文件"""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    parser = MeminfoParser(content)
    return parser.parse()


def print_meminfo_report(data: MeminfoData):
    """打印 meminfo 分析报告"""
    print("\n" + "=" * 70)
    print(f"=== dumpsys meminfo 分析报告 ===")
    print("=" * 70)

    print(f"\n包名: {data.package_name}")
    print(f"PID: {data.pid}")
    print(f"Uptime: {data.uptime}ms")

    # 汇总
    print(f"\n--- 内存汇总 ---")
    print(f"{'指标':<20} {'值':>15}")
    print("-" * 40)
    print(f"{'Total PSS':<20} {data.total_pss / 1024:>12.2f} MB")
    print(f"{'Total RSS':<20} {data.total_rss / 1024:>12.2f} MB")
    print(f"{'Total Swap':<20} {data.total_swap / 1024:>12.2f} MB")

    # App Summary
    print(f"\n--- App Summary ---")
    print(f"{'分类':<20} {'PSS (KB)':>12} {'RSS (KB)':>12}")
    print("-" * 50)
    print(f"{'Java Heap':<20} {data.java_heap_pss:>12} {data.java_heap_rss:>12}")
    print(f"{'Native Heap':<20} {data.native_heap_pss:>12} {data.native_heap_rss:>12}")
    print(f"{'Code':<20} {data.code_pss:>12} {data.code_rss:>12}")
    print(f"{'Stack':<20} {data.stack_pss:>12} {data.stack_rss:>12}")
    print(f"{'Graphics':<20} {data.graphics_pss:>12} {data.graphics_rss:>12}")
    print(f"{'Private Other':<20} {data.private_other:>12} {'-':>12}")
    print(f"{'System':<20} {data.system:>12} {'-':>12}")

    # Objects
    obj = data.objects
    print(f"\n--- Objects ---")
    print(f"Views: {obj.views}  |  ViewRootImpl: {obj.view_root_impl}  |  Activities: {obj.activities}")
    print(f"Local Binders: {obj.local_binders}  |  Proxy Binders: {obj.proxy_binders}")
    print(f"WebViews: {obj.webviews}  |  Assets: {obj.assets}")

    # Native Allocations
    if data.native_allocations:
        print(f"\n--- Native Allocations ---")
        print(f"{'类型':<25} {'数量':>10} {'大小 (KB)':>15}")
        print("-" * 55)
        for alloc in data.native_allocations:
            print(f"{alloc.name:<25} {alloc.count:>10} {alloc.size_kb:>15.2f}")

        # Bitmap 汇总
        parser = MeminfoParser("")
        parser.data = data
        bitmap = parser.get_bitmap_stats()
        if bitmap['total']['count'] > 0:
            print(f"\n{'Bitmap 总计':<25} {int(bitmap['total']['count']):>10} {bitmap['total']['size_kb']:>15.2f}")
            print(f"  -> malloced (Java 管理): {int(bitmap['malloced']['count'])} 个, {bitmap['malloced']['size_kb']:.2f} KB")
            print(f"  -> nonmalloced (Native 管理): {int(bitmap['nonmalloced']['count'])} 个, {bitmap['nonmalloced']['size_kb']:.2f} KB")

    print("\n" + "=" * 70)


def main():
    parser = argparse.ArgumentParser(
        description="dumpsys meminfo 解析器",
        epilog="""
示例:
  python3 meminfo_parser.py meminfo.txt
  python3 meminfo_parser.py -f meminfo.txt --json
        """,
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument('file', nargs='?', help='meminfo 文件路径')
    parser.add_argument('-f', '--file', dest='file_alt', help='meminfo 文件路径 (备选)')
    parser.add_argument('--json', action='store_true', help='输出 JSON 格式')

    args = parser.parse_args()

    file_path = args.file or args.file_alt
    if not file_path:
        print("请指定 meminfo 文件路径")
        parser.print_help()
        return

    if not os.path.exists(file_path):
        print(f"错误: 文件不存在: {file_path}")
        return

    data = parse_meminfo_file(file_path)

    if args.json:
        import json
        # 简化输出
        output = {
            'package_name': data.package_name,
            'pid': data.pid,
            'total_pss_kb': data.total_pss,
            'total_rss_kb': data.total_rss,
            'java_heap_pss_kb': data.java_heap_pss,
            'native_heap_pss_kb': data.native_heap_pss,
            'graphics_pss_kb': data.graphics_pss,
            'objects': {
                'views': data.objects.views,
                'activities': data.objects.activities,
                'webviews': data.objects.webviews,
            },
            'bitmap': MeminfoParser("").get_bitmap_stats() if data.native_allocations else None
        }
        # 重新解析获取 bitmap stats
        parser_temp = MeminfoParser("")
        parser_temp.data = data
        output['bitmap'] = parser_temp.get_bitmap_stats()
        print(json.dumps(output, indent=2))
    else:
        print_meminfo_report(data)


if __name__ == '__main__':
    main()
