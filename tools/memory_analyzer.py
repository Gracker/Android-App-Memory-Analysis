#!/usr/bin/env python
# -*- coding:utf-8 -*-
# Android Memory Comprehensive Analysis Tool
# 综合分析工具：结合HPROF和SMAPS分析

import argparse
import os
import sys
import json
from datetime import datetime
import subprocess

# 导入现有的解析器
from hprof_parser import HprofParser
from smaps_parser import parse_smaps, pss_type, type_list, pss_count, swapPss_count, pssSum_count

class MemoryAnalyzer:
    def __init__(self):
        self.hprof_data = None
        self.smaps_data = None
        self.analysis_result = {}
        
    def analyze_hprof(self, hprof_file):
        """分析HPROF文件"""
        print(f"正在分析HPROF文件: {hprof_file}")
        
        parser = HprofParser(hprof_file)
        if parser.parse():
            self.hprof_data = {
                'total_instances': parser.total_instances,
                'total_instance_size': parser.total_instance_size,
                'total_arrays': parser.total_arrays,
                'total_array_size': parser.total_array_size,
                'class_stats': dict(parser.class_stats),
                'primitive_stats': dict(parser.primitive_stats),
                'string_stats': parser.string_stats,
                'java_heap_size': parser.total_instance_size + parser.total_array_size
            }
            print("✓ HPROF文件分析完成")
            return True
        else:
            print("✗ HPROF文件分析失败")
            return False
    
    def analyze_smaps(self, smaps_file):
        """分析SMAPS文件"""
        print(f"正在分析SMAPS文件: {smaps_file}")
        
        try:
            # 重置全局变量
            global pss_count, swapPss_count, pssSum_count, type_list
            pss_count = [0] * 40
            swapPss_count = [0] * 40
            pssSum_count = [0] * 40
            type_list = []
            for i in range(40):
                type_list.append({})
            
            parse_smaps(smaps_file)
            
            self.smaps_data = {
                'pss_by_type': {},
                'swap_pss_by_type': {},
                'total_pss': {},
                'total_memory_kb': sum(pssSum_count),
                'native_heap_kb': pssSum_count[35] if len(pssSum_count) > 35 else 0,  # HEAP_NATIVE_HEAP
                'dalvik_heap_kb': pssSum_count[1] if len(pssSum_count) > 1 else 0,    # HEAP_DALVIK
                'native_code_kb': pssSum_count[2] if len(pssSum_count) > 2 else 0     # HEAP_NATIVE
            }
            
            # 详细分类数据
            for i, (type_name, pss_val, swap_val, total_val) in enumerate(zip(pss_type, pss_count, swapPss_count, pssSum_count)):
                if total_val > 0:
                    self.smaps_data['pss_by_type'][type_name] = pss_val
                    self.smaps_data['swap_pss_by_type'][type_name] = swap_val
                    self.smaps_data['total_pss'][type_name] = total_val
            
            print("✓ SMAPS文件分析完成")
            return True
            
        except Exception as e:
            print(f"✗ SMAPS文件分析失败: {e}")
            return False
    
    def generate_comprehensive_analysis(self):
        """生成综合分析报告"""
        if not self.hprof_data and not self.smaps_data:
            print("错误: 没有可分析的数据")
            return None
        
        self.analysis_result = {
            'timestamp': datetime.now().isoformat(),
            'summary': {},
            'java_heap': {},
            'native_memory': {},
            'memory_breakdown': {},
            'recommendations': []
        }
        
        # 生成总结
        if self.hprof_data and self.smaps_data:
            self._generate_combined_summary()
        elif self.hprof_data:
            self._generate_hprof_only_summary()
        elif self.smaps_data:
            self._generate_smaps_only_summary()
        
        return self.analysis_result
    
    def _generate_combined_summary(self):
        """生成HPROF+SMAPS综合分析"""
        java_heap_mb = self.hprof_data['java_heap_size'] / 1024 / 1024
        total_memory_mb = self.smaps_data['total_memory_kb'] / 1024
        native_heap_mb = self.smaps_data['native_heap_kb'] / 1024
        dalvik_heap_mb = self.smaps_data['dalvik_heap_kb'] / 1024
        native_code_mb = self.smaps_data['native_code_kb'] / 1024
        
        self.analysis_result['summary'] = {
            'total_memory_mb': round(total_memory_mb, 2),
            'java_heap_mb': round(java_heap_mb, 2),
            'native_heap_mb': round(native_heap_mb, 2),
            'dalvik_runtime_mb': round(dalvik_heap_mb, 2),
            'native_code_mb': round(native_code_mb, 2),
            'java_heap_percentage': round((java_heap_mb / total_memory_mb) * 100, 1) if total_memory_mb > 0 else 0
        }
        
        # Java堆详细分析
        self.analysis_result['java_heap'] = {
            'total_objects': self.hprof_data['total_instances'],
            'total_arrays': self.hprof_data['total_arrays'],
            'string_objects': self.hprof_data['string_stats']['count'],
            'string_memory_mb': round(self.hprof_data['string_stats']['size'] / 1024 / 1024, 2),
            'top_classes': self._get_top_classes(10)
        }
        
        # 本地内存详细分析
        self.analysis_result['native_memory'] = {
            'native_heap_mb': round(native_heap_mb, 2),
            'native_code_mb': round(native_code_mb, 2),
            'graphics_mb': round(self.smaps_data['total_pss'].get('graphics (图形相关内存)', 0) / 1024, 2),
            'gl_mb': round(self.smaps_data['total_pss'].get('gl (OpenGL图形内存)', 0) / 1024, 2)
        }
        
        # 内存分解
        self.analysis_result['memory_breakdown'] = {}
        for type_name, size_kb in self.smaps_data['total_pss'].items():
            if size_kb > 1024:  # 只显示大于1MB的项目
                self.analysis_result['memory_breakdown'][type_name] = round(size_kb / 1024, 2)
        
        # 生成建议
        self._generate_recommendations()
    
    def _generate_hprof_only_summary(self):
        """仅HPROF文件的分析"""
        java_heap_mb = self.hprof_data['java_heap_size'] / 1024 / 1024
        
        self.analysis_result['summary'] = {
            'java_heap_mb': round(java_heap_mb, 2),
            'total_objects': self.hprof_data['total_instances'],
            'total_arrays': self.hprof_data['total_arrays']
        }
        
        self.analysis_result['java_heap'] = {
            'total_objects': self.hprof_data['total_instances'],
            'total_arrays': self.hprof_data['total_arrays'],
            'string_objects': self.hprof_data['string_stats']['count'],
            'string_memory_mb': round(self.hprof_data['string_stats']['size'] / 1024 / 1024, 2),
            'top_classes': self._get_top_classes(15)
        }
        
        self._generate_java_heap_recommendations()
    
    def _generate_smaps_only_summary(self):
        """仅SMAPS文件的分析"""
        total_memory_mb = self.smaps_data['total_memory_kb'] / 1024
        
        self.analysis_result['summary'] = {
            'total_memory_mb': round(total_memory_mb, 2),
            'native_heap_mb': round(self.smaps_data['native_heap_kb'] / 1024, 2),
            'dalvik_runtime_mb': round(self.smaps_data['dalvik_heap_kb'] / 1024, 2)
        }
        
        self.analysis_result['memory_breakdown'] = {}
        for type_name, size_kb in self.smaps_data['total_pss'].items():
            if size_kb > 1024:
                self.analysis_result['memory_breakdown'][type_name] = round(size_kb / 1024, 2)
        
        self._generate_native_memory_recommendations()
    
    def _get_top_classes(self, top_n):
        """获取TOP N内存占用类"""
        if not self.hprof_data:
            return []
        
        sorted_classes = sorted(self.hprof_data['class_stats'].items(), 
                              key=lambda x: x[1]['size'], reverse=True)
        
        result = []
        for class_name, stats in sorted_classes[:top_n]:
            result.append({
                'class_name': class_name,
                'instance_count': stats['count'],
                'total_size_mb': round(stats['size'] / 1024 / 1024, 2),
                'avg_size_kb': round(stats['size'] / stats['count'] / 1024, 2) if stats['count'] > 0 else 0
            })
        
        return result
    
    def _generate_recommendations(self):
        """生成优化建议"""
        recommendations = []
        
        # Java堆分析建议
        if self.hprof_data:
            java_heap_mb = self.hprof_data['java_heap_size'] / 1024 / 1024
            string_mb = self.hprof_data['string_stats']['size'] / 1024 / 1024
            
            if java_heap_mb > 100:
                recommendations.append({
                    'type': 'WARNING',
                    'category': 'Java堆内存',
                    'message': f'Java堆内存使用量较大 ({java_heap_mb:.1f}MB)，建议检查内存泄漏'
                })
            
            if string_mb > 10:
                recommendations.append({
                    'type': 'INFO',
                    'category': '字符串优化',
                    'message': f'字符串占用 {string_mb:.1f}MB，建议优化字符串使用，考虑使用StringBuilder或字符串常量池'
                })
            
            # 检查大对象
            if self.hprof_data['class_stats']:
                largest_class = max(self.hprof_data['class_stats'].items(), key=lambda x: x[1]['size'])
                largest_size_mb = largest_class[1]['size'] / 1024 / 1024
                if largest_size_mb > 20:
                    recommendations.append({
                        'type': 'WARNING',
                        'category': '大对象检测',
                        'message': f'类 {largest_class[0]} 占用内存过大 ({largest_size_mb:.1f}MB)，请检查是否存在内存泄漏'
                    })
        
        # SMAPS分析建议
        if self.smaps_data:
            total_mb = self.smaps_data['total_memory_kb'] / 1024
            native_heap_mb = self.smaps_data['native_heap_kb'] / 1024
            
            if total_mb > 200:
                recommendations.append({
                    'type': 'WARNING',
                    'category': '总内存使用',
                    'message': f'应用总内存使用量过高 ({total_mb:.1f}MB)，可能影响系统性能'
                })
            
            if native_heap_mb > 50:
                recommendations.append({
                    'type': 'INFO',
                    'category': 'Native内存',
                    'message': f'Native堆内存使用较高 ({native_heap_mb:.1f}MB)，检查JNI代码和第三方库'
                })
            
            # 检查图形内存
            graphics_mb = self.smaps_data['total_pss'].get('graphics (图形相关内存)', 0) / 1024
            if graphics_mb > 30:
                recommendations.append({
                    'type': 'INFO',
                    'category': '图形内存',
                    'message': f'图形内存使用较高 ({graphics_mb:.1f}MB)，检查位图缓存和GPU内存使用'
                })
        
        self.analysis_result['recommendations'] = recommendations
    
    def _generate_java_heap_recommendations(self):
        """生成Java堆相关建议"""
        recommendations = []
        
        java_heap_mb = self.hprof_data['java_heap_size'] / 1024 / 1024
        string_mb = self.hprof_data['string_stats']['size'] / 1024 / 1024
        
        if java_heap_mb > 80:
            recommendations.append({
                'type': 'WARNING',
                'category': 'Java堆内存',
                'message': f'Java堆内存使用量较大 ({java_heap_mb:.1f}MB)'
            })
        
        if string_mb > 5:
            recommendations.append({
                'type': 'INFO',
                'category': '字符串优化',
                'message': f'字符串占用 {string_mb:.1f}MB，考虑优化字符串使用'
            })
        
        self.analysis_result['recommendations'] = recommendations
    
    def _generate_native_memory_recommendations(self):
        """生成Native内存相关建议"""
        recommendations = []
        
        total_mb = self.smaps_data['total_memory_kb'] / 1024
        native_heap_mb = self.smaps_data['native_heap_kb'] / 1024
        
        if total_mb > 150:
            recommendations.append({
                'type': 'WARNING',
                'category': '总内存使用',
                'message': f'应用总内存使用量较高 ({total_mb:.1f}MB)'
            })
        
        if native_heap_mb > 30:
            recommendations.append({
                'type': 'INFO',
                'category': 'Native内存',
                'message': f'Native堆内存使用较高 ({native_heap_mb:.1f}MB)'
            })
        
        self.analysis_result['recommendations'] = recommendations
    
    def print_analysis_report(self):
        """打印分析报告"""
        if not self.analysis_result:
            print("没有分析结果可显示")
            return
        
        print("\n" + "="*60)
        print("          Android 应用内存综合分析报告")
        print("="*60)
        
        # 总结信息
        print("\n📊 内存使用总结:")
        print("-" * 30)
        for key, value in self.analysis_result['summary'].items():
            key_cn = self._translate_key(key)
            if isinstance(value, (int, float)):
                if 'mb' in key.lower():
                    print(f"{key_cn}: {value} MB")
                elif 'percentage' in key.lower():
                    print(f"{key_cn}: {value}%")
                else:
                    print(f"{key_cn}: {value:,}")
            else:
                print(f"{key_cn}: {value}")
        
        # Java堆分析
        if 'java_heap' in self.analysis_result and self.analysis_result['java_heap']:
            print("\n☕ Java堆内存详情:")
            print("-" * 30)
            java_heap = self.analysis_result['java_heap']
            for key, value in java_heap.items():
                if key != 'top_classes':
                    key_cn = self._translate_key(key)
                    if isinstance(value, (int, float)):
                        if 'mb' in key.lower():
                            print(f"{key_cn}: {value} MB")
                        else:
                            print(f"{key_cn}: {value:,}")
                    else:
                        print(f"{key_cn}: {value}")
            
            # TOP类
            if 'top_classes' in java_heap and java_heap['top_classes']:
                print(f"\n🏆 TOP {len(java_heap['top_classes'])} 内存占用类:")
                print(f"{'类名':<40} {'实例数':<8} {'总大小(MB)':<12} {'平均大小(KB)':<12}")
                print("-" * 80)
                for cls in java_heap['top_classes']:
                    print(f"{cls['class_name']:<40} {cls['instance_count']:<8,} {cls['total_size_mb']:<12.2f} {cls['avg_size_kb']:<12.2f}")
        
        # Native内存分析
        if 'native_memory' in self.analysis_result and self.analysis_result['native_memory']:
            print("\n🔧 Native内存详情:")
            print("-" * 30)
            for key, value in self.analysis_result['native_memory'].items():
                key_cn = self._translate_key(key)
                print(f"{key_cn}: {value} MB")
        
        # 内存分解
        if 'memory_breakdown' in self.analysis_result and self.analysis_result['memory_breakdown']:
            print("\n📈 内存分类占用 (>1MB):")
            print("-" * 30)
            sorted_breakdown = sorted(self.analysis_result['memory_breakdown'].items(), 
                                    key=lambda x: x[1], reverse=True)
            for category, size_mb in sorted_breakdown[:15]:  # 显示前15项
                print(f"{category}: {size_mb} MB")
        
        # 优化建议
        if 'recommendations' in self.analysis_result and self.analysis_result['recommendations']:
            print("\n💡 优化建议:")
            print("-" * 30)
            for rec in self.analysis_result['recommendations']:
                icon = "⚠️" if rec['type'] == 'WARNING' else "ℹ️"
                print(f"{icon} [{rec['category']}] {rec['message']}")
        
        # Educational Resources Section
        print("\n" + "="*60)
        print("📚 深入学习指南 / Educational Resources")
        print("="*60)
        print("\n为了更好地理解综合分析结果，建议阅读以下详细指南：")
        print("For better understanding of comprehensive analysis results, please refer to these detailed guides:\n")
        
        print("🔍 基础内存分析 / Basic Memory Analysis:")
        print("  • dumpsys meminfo 输出详解指南 / dumpsys meminfo Interpretation Guide:")
        print("    ./meminfo_interpretation_guide.md")
        print("    应用级内存使用分析，理解应用内存分布和使用状况\n")
        
        print("  • /proc/meminfo 输出详解指南 / /proc/meminfo Interpretation Guide:")
        print("    ./proc_meminfo_interpretation_guide.md")
        print("    系统级内存使用分析，理解设备整体内存状况\n")
        
        print("  • showmap 输出详解指南 / showmap Interpretation Guide:")
        print("    ./showmap_interpretation_guide.md")
        print("    进程级内存映射概览，快速识别内存使用模式\n")
        
        print("🗺️ 详细内存分析 / Detailed Memory Analysis:")
        print("  • smaps 输出详解指南 / smaps Interpretation Guide:")
        print("    ./smaps_interpretation_guide.md")
        print("    最详细的内存映射分析，深入理解每个内存区域\n")
        
        print("📊 解析结果理解 / Understanding Analysis Results:")
        print("  • 分析结果详解指南 / Analysis Results Interpretation Guide:")
        print("    ./analysis_results_interpretation_guide.md")
        print("    理解本工具输出的每一项数据和优化建议\n")
        
        print("🔄 综合分析最佳实践 / Comprehensive Analysis Best Practices:")
        print("   • 结合 SMAPS 和 HPROF 数据进行完整内存分析")
        print("   • 重点关注 Java 堆和 Native 内存的平衡")
        print("   • 使用趋势分析识别内存泄漏模式")
        print("   • 基于分析结果制定针对性优化策略\n")
        
        print("\n" + "="*60)
    
    def _translate_key(self, key):
        """翻译字段名"""
        translations = {
            'total_memory_mb': '总内存使用',
            'java_heap_mb': 'Java堆内存',
            'native_heap_mb': 'Native堆内存',
            'dalvik_runtime_mb': 'Dalvik运行时',
            'native_code_mb': 'Native代码',
            'java_heap_percentage': 'Java堆占比',
            'total_objects': '总对象数',
            'total_arrays': '总数组数',
            'string_objects': '字符串对象数',
            'string_memory_mb': '字符串内存',
            'graphics_mb': '图形内存',
            'gl_mb': 'OpenGL内存'
        }
        return translations.get(key, key)
    
    def export_report(self, output_file):
        """导出分析报告"""
        if not self.analysis_result:
            print("没有分析结果可导出")
            return False
        
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write("Android 应用内存综合分析报告\n")
                f.write("=" * 50 + "\n\n")
                f.write(f"分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                
                # 以JSON格式导出详细数据
                f.write("详细分析数据 (JSON格式):\n")
                f.write("-" * 30 + "\n")
                json.dump(self.analysis_result, f, ensure_ascii=False, indent=2)
                
                # Educational Resources Section
                f.write("\n\n" + "="*60 + "\n")
                f.write("📚 深入学习指南 / Educational Resources\n")
                f.write("="*60 + "\n\n")
                f.write("为了更好地理解综合分析结果，建议阅读以下详细指南：\n")
                f.write("For better understanding of comprehensive analysis results, please refer to these detailed guides:\n\n")
                
                f.write("🔍 基础内存分析 / Basic Memory Analysis:\n")
                f.write("  • dumpsys meminfo 输出详解指南 / dumpsys meminfo Interpretation Guide:\n")
                f.write("    ./meminfo_interpretation_guide.md\n")
                f.write("    应用级内存使用分析，理解应用内存分布和使用状况\n\n")
                
                f.write("  • /proc/meminfo 输出详解指南 / /proc/meminfo Interpretation Guide:\n")
                f.write("    ./proc_meminfo_interpretation_guide.md\n")
                f.write("    系统级内存使用分析，理解设备整体内存状况\n\n")
                
                f.write("  • showmap 输出详解指南 / showmap Interpretation Guide:\n")
                f.write("    ./showmap_interpretation_guide.md\n")
                f.write("    进程级内存映射概览，快速识别内存使用模式\n\n")
                
                f.write("🗺️ 详细内存分析 / Detailed Memory Analysis:\n")
                f.write("  • smaps 输出详解指南 / smaps Interpretation Guide:\n")
                f.write("    ./smaps_interpretation_guide.md\n")
                f.write("    最详细的内存映射分析，深入理解每个内存区域\n\n")
                
                f.write("📊 解析结果理解 / Understanding Analysis Results:\n")
                f.write("  • 分析结果详解指南 / Analysis Results Interpretation Guide:\n")
                f.write("    ./analysis_results_interpretation_guide.md\n")
                f.write("    理解本工具输出的每一项数据和优化建议\n\n")
                
                f.write("🔄 综合分析最佳实践 / Comprehensive Analysis Best Practices:\n")
                f.write("   • 结合 SMAPS 和 HPROF 数据进行完整内存分析\n")
                f.write("   • 重点关注 Java 堆和 Native 内存的平衡\n")
                f.write("   • 使用趋势分析识别内存泄漏模式\n")
                f.write("   • 基于分析结果制定针对性优化策略\n\n")
                
            print(f"✓ 分析报告已导出到: {output_file}")
            return True
            
        except Exception as e:
            print(f"✗ 导出报告失败: {e}")
            return False

def main():
    parser = argparse.ArgumentParser(description="Android内存综合分析工具")
    parser.add_argument('--hprof', help="HPROF文件路径")
    parser.add_argument('--smaps', help="SMAPS文件路径") 
    parser.add_argument('-p', '--pid', help="进程PID (自动获取smaps)")
    parser.add_argument('-o', '--output', help="分析结果输出文件")
    parser.add_argument('--json-output', help="JSON格式输出文件")
    
    args = parser.parse_args()
    
    if not args.hprof and not args.smaps and not args.pid:
        print("请提供HPROF文件 (--hprof) 或 SMAPS文件 (--smaps) 或 进程PID (-p)")
        return
    
    analyzer = MemoryAnalyzer()
    
    # 分析HPROF文件
    if args.hprof:
        if not os.path.exists(args.hprof):
            print(f"错误: HPROF文件不存在: {args.hprof}")
            return
        if not analyzer.analyze_hprof(args.hprof):
            return
    
    # 分析SMAPS文件
    smaps_file = None
    if args.smaps:
        if not os.path.exists(args.smaps):
            print(f"错误: SMAPS文件不存在: {args.smaps}")
            return
        smaps_file = args.smaps
    elif args.pid:
        # 通过PID获取smaps
        try:
            pid = int(args.pid)
            smaps_file = f"{pid}_smaps_file.txt"
            cmd = f"adb shell su root cat /proc/{pid}/smaps"
            print(f"获取进程 {pid} 的smaps数据...")
            
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            if result.returncode == 0:
                with open(smaps_file, 'w') as f:
                    f.write(result.stdout)
                print(f"✓ smaps数据已保存到: {smaps_file}")
            else:
                print(f"✗ 获取smaps数据失败: {result.stderr}")
                return
                
        except ValueError:
            print("错误: 请提供有效的PID")
            return
        except Exception as e:
            print(f"获取smaps数据时出错: {e}")
            return
    
    if smaps_file:
        if not analyzer.analyze_smaps(smaps_file):
            return
    
    # 生成综合分析
    analyzer.generate_comprehensive_analysis()
    
    # 显示分析报告
    analyzer.print_analysis_report()
    
    # 导出报告
    if args.output:
        analyzer.export_report(args.output)
    elif args.json_output:
        analyzer.export_report(args.json_output)
    else:
        # 默认输出文件
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_output = f"memory_analysis_{timestamp}.txt"
        analyzer.export_report(default_output)

if __name__ == "__main__":
    main()