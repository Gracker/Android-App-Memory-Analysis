#!/usr/bin/env python3
# -*- coding:utf-8 -*-
"""
HPROF + smaps 联合内存分析工具

将 Java 堆分析 (HPROF) 与 Native 内存分析 (smaps) 结合，提供完整的内存视图。

功能:
- 关联 Java 堆和 Native 内存
- 识别 Native 内存泄漏（HPROF 中有 Bitmap 但 smaps 中 Graphics 内存异常）
- 分析 Java/Native 内存比例
- 检测内存碎片化
- 提供综合优化建议
"""

import argparse
import os
import sys
from datetime import datetime
from collections import defaultdict

# Import parsers
from hprof_parser import HprofParser

# smaps parser uses global variables, we need to import them
import smaps_parser


class CombinedAnalyzer:
    """HPROF + smaps 联合分析器"""

    def __init__(self, hprof_file, smaps_file):
        self.hprof_file = hprof_file
        self.smaps_file = smaps_file
        self.hprof_data = None
        self.smaps_data = None

    def parse_hprof(self):
        """解析 HPROF 文件"""
        print(f"\n{'='*60}")
        print(f"正在解析 HPROF 文件: {self.hprof_file}")
        print('='*60)

        parser = HprofParser(self.hprof_file)
        parser.parse(simple_mode=True, deep_analysis=True)

        self.hprof_data = {
            'total_instances': parser.total_instances,
            'total_instance_size': parser.total_instance_size,
            'total_arrays': parser.total_arrays,
            'total_array_size': parser.total_array_size,
            'total_java_heap': (parser.total_instance_size + parser.total_array_size) / 1024 / 1024,
            'bitmap_info': parser.bitmap_info,
            'class_stats': parser.class_stats,
            'package_stats': parser.package_stats,
            'string_stats': parser.string_stats,
            'primitive_stats': parser.primitive_stats,
            'leak_suspects': parser.leak_suspects,
            'app_package': parser.app_package,
            'large_byte_arrays': getattr(parser, 'large_byte_arrays', []),
            'lru_cache_analysis': getattr(parser, 'lru_cache_analysis', []),
            'empty_collections': getattr(parser, 'empty_collections', []),
            'large_collections': getattr(parser, 'large_collections', []),
        }

        return self.hprof_data

    def parse_smaps(self):
        """解析 smaps 文件"""
        print(f"\n{'='*60}")
        print(f"正在解析 smaps 文件: {self.smaps_file}")
        print('='*60)

        # Reset global counters
        smaps_parser.pss_count = [0] * smaps_parser.type_length
        smaps_parser.pssSum_count = [0] * smaps_parser.type_length
        smaps_parser.swapPss_count = [0] * smaps_parser.type_length

        # Reset type lists
        for i in range(smaps_parser.type_length):
            smaps_parser.pss_type_list[i] = {}
            smaps_parser.swap_type_list[i] = {}

        # Parse smaps
        smaps_parser.parse_smaps(self.smaps_file)

        # Extract data
        self.smaps_data = {
            'total_pss_kb': sum(smaps_parser.pssSum_count),
            'total_swap_kb': sum(smaps_parser.swapPss_count),

            # Major categories (KB)
            'dalvik_heap_kb': smaps_parser.pss_count[smaps_parser.HEAP_DALVIK],
            'native_heap_kb': smaps_parser.pss_count[smaps_parser.HEAP_NATIVE],
            'dalvik_other_kb': smaps_parser.pss_count[smaps_parser.HEAP_DALVIK_OTHER],
            'stack_kb': smaps_parser.pss_count[smaps_parser.HEAP_STACK],
            'so_kb': smaps_parser.pss_count[smaps_parser.HEAP_SO],
            'dex_kb': smaps_parser.pss_count[smaps_parser.HEAP_DEX],
            'oat_kb': smaps_parser.pss_count[smaps_parser.HEAP_OAT],
            'art_kb': smaps_parser.pss_count[smaps_parser.HEAP_ART],
            'graphics_kb': smaps_parser.pss_count[smaps_parser.HEAP_GRAPHICS],
            'gl_kb': smaps_parser.pss_count[smaps_parser.HEAP_GL],
            'apk_kb': smaps_parser.pss_count[smaps_parser.HEAP_APK],
            'ttf_kb': smaps_parser.pss_count[smaps_parser.HEAP_TTF],
            'ashmem_kb': smaps_parser.pss_count[smaps_parser.HEAP_ASHMEM],
            'unknown_kb': smaps_parser.pss_count[smaps_parser.HEAP_UNKNOWN],

            # Dalvik subdivisions
            'dalvik_normal_kb': smaps_parser.pss_count[smaps_parser.HEAP_DALVIK_NORMAL],
            'dalvik_large_kb': smaps_parser.pss_count[smaps_parser.HEAP_DALVIK_LARGE],
            'dalvik_zygote_kb': smaps_parser.pss_count[smaps_parser.HEAP_DALVIK_ZYGOTE],
            'dalvik_non_moving_kb': smaps_parser.pss_count[smaps_parser.HEAP_DALVIK_NON_MOVING],

            # Raw data for detailed analysis
            'pss_count': list(smaps_parser.pss_count),
            'pss_type_list': [dict(d) for d in smaps_parser.pss_type_list],
        }

        return self.smaps_data

    def analyze(self):
        """执行联合分析"""
        if not self.hprof_data:
            self.parse_hprof()
        if not self.smaps_data:
            self.parse_smaps()

        results = {
            'memory_overview': self._analyze_memory_overview(),
            'java_native_correlation': self._analyze_java_native_correlation(),
            'bitmap_graphics_analysis': self._analyze_bitmap_graphics(),
            'memory_distribution': self._analyze_memory_distribution(),
            'anomalies': self._detect_anomalies(),
            'recommendations': self._generate_recommendations(),
        }

        return results

    def _analyze_memory_overview(self):
        """内存概览分析"""
        java_heap_mb = self.hprof_data['total_java_heap']
        total_pss_mb = self.smaps_data['total_pss_kb'] / 1024
        native_heap_mb = self.smaps_data['native_heap_kb'] / 1024
        dalvik_heap_mb = self.smaps_data['dalvik_heap_kb'] / 1024

        return {
            'java_heap_mb': java_heap_mb,
            'dalvik_heap_smaps_mb': dalvik_heap_mb,
            'native_heap_mb': native_heap_mb,
            'total_pss_mb': total_pss_mb,
            'java_native_ratio': java_heap_mb / native_heap_mb if native_heap_mb > 0 else 0,
            'heap_diff_mb': abs(java_heap_mb - dalvik_heap_mb),
            'heap_diff_pct': abs(java_heap_mb - dalvik_heap_mb) / dalvik_heap_mb * 100 if dalvik_heap_mb > 0 else 0,
        }

    def _analyze_java_native_correlation(self):
        """Java/Native 内存关联分析"""
        # Estimate native memory from Java objects
        bitmap_native_estimate = 0
        if self.hprof_data['bitmap_info']:
            for bitmap_id, info in self.hprof_data['bitmap_info'].items():
                # Native pixel data
                bitmap_native_estimate += info.get('estimated_size', 0)

        # byte[] that might be native-backed
        byte_array_size = self.hprof_data['primitive_stats'].get('byte[]', {}).get('size', 0) / 1024

        # Actual native heap from smaps
        native_heap_kb = self.smaps_data['native_heap_kb']

        return {
            'estimated_bitmap_native_kb': bitmap_native_estimate / 1024,
            'byte_array_size_kb': byte_array_size,
            'actual_native_heap_kb': native_heap_kb,
            'unaccounted_native_kb': native_heap_kb - (bitmap_native_estimate / 1024) - byte_array_size,
        }

    def _analyze_bitmap_graphics(self):
        """Bitmap 与 Graphics 内存关联分析"""
        # HPROF: Bitmap statistics
        bitmap_count = len(self.hprof_data['bitmap_info'])
        bitmap_total_size = sum(info.get('estimated_size', 0)
                               for info in self.hprof_data['bitmap_info'].values())

        # smaps: Graphics memory
        graphics_kb = self.smaps_data['graphics_kb']
        gl_kb = self.smaps_data['gl_kb']

        return {
            'bitmap_count': bitmap_count,
            'bitmap_java_size_mb': bitmap_total_size / 1024 / 1024,
            'graphics_memory_mb': graphics_kb / 1024,
            'gl_memory_mb': gl_kb / 1024,
            'total_graphics_mb': (graphics_kb + gl_kb) / 1024,
            'bitmap_per_graphics_ratio': (bitmap_total_size / 1024) / (graphics_kb + gl_kb) if (graphics_kb + gl_kb) > 0 else 0,
        }

    def _analyze_memory_distribution(self):
        """内存分布分析"""
        total_pss = self.smaps_data['total_pss_kb']
        if total_pss == 0:
            return {}

        distribution = {
            'dalvik_heap_pct': self.smaps_data['dalvik_heap_kb'] / total_pss * 100,
            'native_heap_pct': self.smaps_data['native_heap_kb'] / total_pss * 100,
            'code_pct': (self.smaps_data['so_kb'] + self.smaps_data['dex_kb'] +
                        self.smaps_data['oat_kb'] + self.smaps_data['art_kb']) / total_pss * 100,
            'graphics_pct': (self.smaps_data['graphics_kb'] + self.smaps_data['gl_kb']) / total_pss * 100,
            'stack_pct': self.smaps_data['stack_kb'] / total_pss * 100,
            'other_pct': self.smaps_data['unknown_kb'] / total_pss * 100,
        }

        # Detailed code breakdown
        distribution['code_breakdown'] = {
            'so_mb': self.smaps_data['so_kb'] / 1024,
            'dex_mb': self.smaps_data['dex_kb'] / 1024,
            'oat_mb': self.smaps_data['oat_kb'] / 1024,
            'art_mb': self.smaps_data['art_kb'] / 1024,
        }

        return distribution

    def _detect_anomalies(self):
        """检测异常"""
        anomalies = []

        overview = self._analyze_memory_overview()
        correlation = self._analyze_java_native_correlation()
        bitmap_analysis = self._analyze_bitmap_graphics()

        # 1. Java heap vs Dalvik heap mismatch
        if overview['heap_diff_pct'] > 20:
            anomalies.append({
                'type': 'HEAP_MISMATCH',
                'severity': 'MEDIUM',
                'description': f"Java 堆 ({overview['java_heap_mb']:.1f} MB) 与 smaps Dalvik 堆 "
                              f"({overview['dalvik_heap_smaps_mb']:.1f} MB) 差异超过 20%",
                'suggestion': '可能存在堆外内存使用或 GC 后未释放的区域'
            })

        # 2. Large unaccounted native memory
        unaccounted = correlation['unaccounted_native_kb']
        if unaccounted > 10 * 1024:  # > 10MB
            anomalies.append({
                'type': 'UNACCOUNTED_NATIVE',
                'severity': 'HIGH',
                'description': f"发现 {unaccounted/1024:.1f} MB 无法追踪的 Native 内存",
                'suggestion': '检查 C/C++ 代码中的内存分配，可能存在 Native 泄漏'
            })

        # 3. Graphics memory anomaly
        if bitmap_analysis['bitmap_count'] == 0 and bitmap_analysis['total_graphics_mb'] > 50:
            anomalies.append({
                'type': 'GRAPHICS_WITHOUT_BITMAP',
                'severity': 'MEDIUM',
                'description': f"无 Bitmap 对象但 Graphics 内存高达 {bitmap_analysis['total_graphics_mb']:.1f} MB",
                'suggestion': '可能使用了 SurfaceView、TextureView 或 OpenGL 直接渲染'
            })

        # 4. High native/java ratio
        if overview['java_native_ratio'] < 0.5:
            anomalies.append({
                'type': 'HIGH_NATIVE_RATIO',
                'severity': 'INFO',
                'description': f"Native 内存 ({overview['native_heap_mb']:.1f} MB) 远超 Java 堆 "
                              f"({overview['java_heap_mb']:.1f} MB)",
                'suggestion': '应用可能大量使用 NDK 或第三方 Native 库'
            })

        # 5. Large stack memory (too many threads)
        stack_mb = self.smaps_data['stack_kb'] / 1024
        if stack_mb > 20:  # > 20MB
            estimated_threads = int(stack_mb / 1)  # ~1MB per thread
            anomalies.append({
                'type': 'HIGH_STACK_MEMORY',
                'severity': 'MEDIUM',
                'description': f"栈内存 {stack_mb:.1f} MB，估计约 {estimated_threads} 个线程",
                'suggestion': '检查是否创建了过多线程，考虑使用线程池'
            })

        # 6. High swap usage
        swap_mb = self.smaps_data['total_swap_kb'] / 1024
        if swap_mb > 50:
            anomalies.append({
                'type': 'HIGH_SWAP_USAGE',
                'severity': 'HIGH',
                'description': f"Swap 使用量 {swap_mb:.1f} MB",
                'suggestion': '应用内存压力大，部分内存被交换到磁盘，会影响性能'
            })

        return anomalies

    def _generate_recommendations(self):
        """生成综合优化建议"""
        recommendations = []
        anomalies = self._detect_anomalies()

        # Based on anomalies
        for anomaly in anomalies:
            if anomaly['severity'] in ['HIGH', 'MEDIUM']:
                recommendations.append({
                    'priority': anomaly['severity'],
                    'area': anomaly['type'],
                    'suggestion': anomaly['suggestion']
                })

        # Based on HPROF analysis
        if self.hprof_data['leak_suspects']:
            recommendations.append({
                'priority': 'HIGH',
                'area': 'MEMORY_LEAK',
                'suggestion': f"检测到 {len(self.hprof_data['leak_suspects'])} 个泄漏嫌疑，优先处理"
            })

        # Based on distribution
        distribution = self._analyze_memory_distribution()
        if distribution.get('code_pct', 0) > 40:
            recommendations.append({
                'priority': 'MEDIUM',
                'area': 'CODE_SIZE',
                'suggestion': '代码占用内存过大，考虑使用动态加载或 App Bundle'
            })

        # Empty collections
        if self.hprof_data['empty_collections']:
            total_empty = sum(count for _, count in self.hprof_data['empty_collections'])
            if total_empty > 500:
                recommendations.append({
                    'priority': 'LOW',
                    'area': 'EMPTY_COLLECTIONS',
                    'suggestion': f'{total_empty} 个空集合，使用 Collections.emptyXxx() 或延迟初始化'
                })

        return recommendations

    def print_report(self):
        """打印分析报告"""
        results = self.analyze()

        print("\n" + "="*80)
        print("=== HPROF + smaps 联合内存分析报告 ===")
        print("="*80)

        # Overview
        overview = results['memory_overview']
        print("\n--- 内存概览 ---")
        print(f"{'指标':<30} {'值':>15}")
        print("-" * 50)
        print(f"{'Java 堆 (HPROF)':<30} {overview['java_heap_mb']:>12.2f} MB")
        print(f"{'Dalvik 堆 (smaps)':<30} {overview['dalvik_heap_smaps_mb']:>12.2f} MB")
        print(f"{'Native 堆 (smaps)':<30} {overview['native_heap_mb']:>12.2f} MB")
        print(f"{'总 PSS (smaps)':<30} {overview['total_pss_mb']:>12.2f} MB")
        print(f"{'Java/Native 比例':<30} {overview['java_native_ratio']:>12.2f}")

        # Distribution
        dist = results['memory_distribution']
        if dist:
            print("\n--- 内存分布 (smaps) ---")
            print(f"{'区域':<20} {'占比':>10} {'说明':<30}")
            print("-" * 60)
            print(f"{'Dalvik 堆':<20} {dist['dalvik_heap_pct']:>8.1f}% {'Java 对象':<30}")
            print(f"{'Native 堆':<20} {dist['native_heap_pct']:>8.1f}% {'C/C++ 分配的内存':<30}")
            print(f"{'代码':<20} {dist['code_pct']:>8.1f}% {'.so/.dex/.oat/.art':<30}")
            print(f"{'图形':<20} {dist['graphics_pct']:>8.1f}% {'GPU 相关内存':<30}")
            print(f"{'栈':<20} {dist['stack_pct']:>8.1f}% {'线程栈':<30}")

        # Bitmap/Graphics correlation
        bitmap = results['bitmap_graphics_analysis']
        if bitmap['bitmap_count'] > 0 or bitmap['total_graphics_mb'] > 0:
            print("\n--- Bitmap/Graphics 关联分析 ---")
            print(f"HPROF Bitmap 对象数: {bitmap['bitmap_count']}")
            print(f"HPROF Bitmap 估算大小: {bitmap['bitmap_java_size_mb']:.2f} MB")
            print(f"smaps Graphics 内存: {bitmap['graphics_memory_mb']:.2f} MB")
            print(f"smaps GL 内存: {bitmap['gl_memory_mb']:.2f} MB")

        # Java/Native correlation
        corr = results['java_native_correlation']
        print("\n--- Java/Native 内存关联 ---")
        print(f"估算 Bitmap Native 内存: {corr['estimated_bitmap_native_kb']/1024:.2f} MB")
        print(f"byte[] 数组大小: {corr['byte_array_size_kb']/1024:.2f} MB")
        print(f"实际 Native 堆: {corr['actual_native_heap_kb']/1024:.2f} MB")
        if corr['unaccounted_native_kb'] > 0:
            print(f"⚠️  未追踪 Native 内存: {corr['unaccounted_native_kb']/1024:.2f} MB")

        # Anomalies
        anomalies = results['anomalies']
        if anomalies:
            print("\n--- 检测到的异常 ---")
            severity_icons = {'HIGH': '🔴', 'MEDIUM': '🟡', 'INFO': '🔵', 'LOW': '🟢'}
            for i, anomaly in enumerate(anomalies, 1):
                icon = severity_icons.get(anomaly['severity'], '⚪')
                print(f"\n{icon} [{i}] {anomaly['type']}")
                print(f"   {anomaly['description']}")
                print(f"   💡 {anomaly['suggestion']}")

        # Recommendations
        recommendations = results['recommendations']
        if recommendations:
            print("\n--- 优化建议 ---")
            for i, rec in enumerate(recommendations, 1):
                priority = rec['priority']
                icon = '🔴' if priority == 'HIGH' else ('🟡' if priority == 'MEDIUM' else '🟢')
                print(f"{icon} [{rec['area']}] {rec['suggestion']}")

        print("\n" + "="*80)

    def export_markdown(self, output_file):
        """导出 Markdown 格式报告"""
        results = self.analyze()

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("# HPROF + smaps 联合内存分析报告\n\n")
            f.write(f"**分析时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  \n")
            f.write(f"**HPROF 文件**: `{os.path.basename(self.hprof_file)}`  \n")
            f.write(f"**smaps 文件**: `{os.path.basename(self.smaps_file)}`\n\n")

            if self.hprof_data.get('app_package'):
                f.write(f"**App 包名**: `{self.hprof_data['app_package']}`\n\n")

            f.write("---\n\n")

            # Overview
            overview = results['memory_overview']
            f.write("## 内存概览\n\n")
            f.write("| 指标 | 值 | 说明 |\n")
            f.write("|------|-----|------|\n")
            f.write(f"| Java 堆 (HPROF) | **{overview['java_heap_mb']:.2f} MB** | HPROF 中的对象总大小 |\n")
            f.write(f"| Dalvik 堆 (smaps) | {overview['dalvik_heap_smaps_mb']:.2f} MB | smaps 中的 Dalvik 堆 |\n")
            f.write(f"| Native 堆 (smaps) | {overview['native_heap_mb']:.2f} MB | C/C++ 分配的内存 |\n")
            f.write(f"| 总 PSS | **{overview['total_pss_mb']:.2f} MB** | 进程实际物理内存占用 |\n")
            f.write(f"| Java/Native 比例 | {overview['java_native_ratio']:.2f} | >1 表示 Java 为主 |\n\n")

            # Distribution pie chart (text representation)
            dist = results['memory_distribution']
            if dist:
                f.write("## 内存分布\n\n")
                f.write("```\n")
                f.write(f"Dalvik 堆: {'█' * int(dist['dalvik_heap_pct']/5)} {dist['dalvik_heap_pct']:.1f}%\n")
                f.write(f"Native 堆: {'█' * int(dist['native_heap_pct']/5)} {dist['native_heap_pct']:.1f}%\n")
                f.write(f"代码:      {'█' * int(dist['code_pct']/5)} {dist['code_pct']:.1f}%\n")
                f.write(f"图形:      {'█' * int(dist['graphics_pct']/5)} {dist['graphics_pct']:.1f}%\n")
                f.write(f"栈:        {'█' * int(dist['stack_pct']/5)} {dist['stack_pct']:.1f}%\n")
                f.write("```\n\n")

            # Anomalies
            anomalies = results['anomalies']
            if anomalies:
                f.write("## 检测到的异常\n\n")
                for anomaly in anomalies:
                    severity = anomaly['severity']
                    icon = '🔴' if severity == 'HIGH' else ('🟡' if severity == 'MEDIUM' else '🔵')
                    f.write(f"### {icon} {anomaly['type']}\n\n")
                    f.write(f"> {anomaly['description']}\n\n")
                    f.write(f"**建议**: {anomaly['suggestion']}\n\n")

            # Recommendations
            recommendations = results['recommendations']
            if recommendations:
                f.write("## 优化建议\n\n")
                for rec in recommendations:
                    priority = rec['priority']
                    icon = '🔴' if priority == 'HIGH' else ('🟡' if priority == 'MEDIUM' else '🟢')
                    f.write(f"- {icon} **[{rec['area']}]** {rec['suggestion']}\n")
                f.write("\n")

            f.write("---\n\n")
            f.write("*报告由 Android-App-Memory-Analysis 联合分析工具生成*\n")

        print(f"\n报告已导出到: {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description="HPROF + smaps 联合内存分析工具",
        epilog="示例:\n"
               "  python3 combined_analyzer.py -H dump.hprof -S smaps.txt\n"
               "  python3 combined_analyzer.py -H dump.hprof -S smaps.txt --markdown",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument('-H', '--hprof', required=True, help="HPROF 文件路径")
    parser.add_argument('-S', '--smaps', required=True, help="smaps 文件路径")
    parser.add_argument('-o', '--output', help="输出文件路径")
    parser.add_argument('--markdown', action='store_true', help="输出 Markdown 格式")

    args = parser.parse_args()

    if not os.path.exists(args.hprof):
        print(f"错误: HPROF 文件不存在: {args.hprof}")
        sys.exit(1)

    if not os.path.exists(args.smaps):
        print(f"错误: smaps 文件不存在: {args.smaps}")
        sys.exit(1)

    analyzer = CombinedAnalyzer(args.hprof, args.smaps)
    analyzer.print_report()

    if args.markdown or args.output:
        output_file = args.output or "combined_analysis.md"
        if not output_file.endswith('.md'):
            output_file += '.md'
        analyzer.export_markdown(output_file)


if __name__ == '__main__':
    main()
