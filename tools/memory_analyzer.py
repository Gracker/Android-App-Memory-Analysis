#!/usr/bin/env python
# -*- coding:utf-8 -*-
# Android Memory Comprehensive Analysis Tool
# 综合分析工具：结合HPROF和SMAPS分析

import argparse
import os
import sys
import json
import re
from datetime import datetime
import subprocess

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.android_shell_utils import read_smaps_with_adb

# 导入现有的解析器
from hprof_parser import HprofParser
import smaps_parser

class MemoryAnalyzer:
    def __init__(self):
        self.hprof_data = None
        self.smaps_data = None
        self.meminfo_data = None
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
            smaps_parser.parse_smaps(smaps_file)
            
            self.smaps_data = {
                'pss_by_type': {},
                'swap_pss_by_type': {},
                'total_pss': {},
                'total_memory_kb': sum(smaps_parser.pssSum_count),
                'native_heap_kb': smaps_parser.pssSum_count[35] if len(smaps_parser.pssSum_count) > 35 else 0,  # HEAP_NATIVE_HEAP
                'dalvik_heap_kb': smaps_parser.pssSum_count[1] if len(smaps_parser.pssSum_count) > 1 else 0,    # HEAP_DALVIK
                'native_code_kb': smaps_parser.pssSum_count[2] if len(smaps_parser.pssSum_count) > 2 else 0     # HEAP_NATIVE
            }
            
            # 详细分类数据
            for type_name, pss_val, swap_val, total_val in zip(
                smaps_parser.pss_type,
                smaps_parser.pss_count,
                smaps_parser.swapPss_count,
                smaps_parser.pssSum_count,
            ):
                if total_val > 0:
                    self.smaps_data['pss_by_type'][type_name] = pss_val
                    self.smaps_data['swap_pss_by_type'][type_name] = swap_val
                    self.smaps_data['total_pss'][type_name] = total_val
            
            print("✓ SMAPS文件分析完成")
            return True
            
        except Exception as e:
            print(f"✗ SMAPS文件分析失败: {e}")
            return False

    def analyze_meminfo(self, meminfo_file):
        """分析dumpsys meminfo输出文件"""
        print(f"正在分析meminfo文件: {meminfo_file}")

        pattern = re.compile(
            r'^\s*(Native Heap|Dalvik Heap|Dalvik Other|Stack|Ashmem|Gfx dev|Other dev|'
            r'\.so mmap|\.jar mmap|\.apk mmap|\.ttf mmap|\.dex mmap|\.oat mmap|\.art mmap|'
            r'Other mmap|EGL mtrack|GL mtrack|Unknown|TOTAL)\s+(\d+)'
        )

        category_pss_kb = {}
        try:
            with open(meminfo_file, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    match = pattern.match(line)
                    if match:
                        category_pss_kb[match.group(1)] = int(match.group(2))

            if not category_pss_kb:
                print("✗ meminfo文件中未解析到有效内存数据")
                return False

            memtrack_egl_kb = category_pss_kb.get('EGL mtrack', 0)
            memtrack_gl_kb = category_pss_kb.get('GL mtrack', 0)

            self.meminfo_data = {
                'category_pss_kb': category_pss_kb,
                'total_pss_kb': category_pss_kb.get('TOTAL', 0),
                'native_heap_kb': category_pss_kb.get('Native Heap', 0),
                'dalvik_heap_kb': category_pss_kb.get('Dalvik Heap', 0),
                'gfx_dev_kb': category_pss_kb.get('Gfx dev', 0),
                'memtrack_egl_kb': memtrack_egl_kb,
                'memtrack_gl_kb': memtrack_gl_kb,
                'memtrack_total_kb': memtrack_egl_kb + memtrack_gl_kb,
            }
            print("✓ meminfo文件分析完成")
            return True

        except Exception as e:
            print(f"✗ meminfo文件分析失败: {e}")
            return False

    def _sum_smaps_types(self, *type_names):
        """按分类名汇总SMAPS中的PSS(kB)"""
        if not self.smaps_data:
            return 0
        total_pss = self.smaps_data.get('total_pss', {})
        return sum(total_pss.get(type_name, 0) for type_name in type_names)

    def _build_smaps_metrics(self):
        """构建更贴近dumpsys meminfo口径的SMAPS聚合指标"""
        if not self.smaps_data:
            return {}

        scudo_heap_kb = self._sum_smaps_types('scudo heap (Scudo安全内存分配器)')
        native_heap_map_kb = self._sum_smaps_types('native heap (本地堆内存)')
        legacy_native_kb = self._sum_smaps_types('Native (本地C/C++代码内存)')
        native_heap_total_kb = scudo_heap_kb + native_heap_map_kb + legacy_native_kb

        gfx_dev_kb = self._sum_smaps_types('Gfx dev (图形设备内存)')
        graphics_kb = self._sum_smaps_types('graphics (图形相关内存)')
        gl_kb = self._sum_smaps_types('gl (OpenGL图形内存)')
        dmabuf_kb = self._sum_smaps_types('dmabuf (直接内存缓冲区)')
        other_memtrack_kb = self._sum_smaps_types('other memtrack (其他内存追踪)')
        graphics_smaps_total_kb = gfx_dev_kb + graphics_kb + gl_kb + dmabuf_kb + other_memtrack_kb

        return {
            'total_memory_kb': self.smaps_data['total_memory_kb'],
            'dalvik_heap_kb': self.smaps_data['dalvik_heap_kb'],
            'native_code_kb': self._sum_smaps_types('.so mmap (动态链接库映射内存)'),
            'native_heap_total_kb': native_heap_total_kb,
            'native_heap_map_kb': native_heap_map_kb,
            'scudo_heap_kb': scudo_heap_kb,
            'legacy_native_kb': legacy_native_kb,
            'gfx_dev_kb': gfx_dev_kb,
            'graphics_kb': graphics_kb,
            'gl_kb': gl_kb,
            'dmabuf_kb': dmabuf_kb,
            'other_memtrack_kb': other_memtrack_kb,
            'graphics_smaps_total_kb': graphics_smaps_total_kb,
        }
    
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
        smaps_metrics = self._build_smaps_metrics()

        total_memory_kb = smaps_metrics['total_memory_kb']
        memtrack_total_kb = self.meminfo_data['memtrack_total_kb'] if self.meminfo_data else 0
        total_with_memtrack_kb = total_memory_kb + memtrack_total_kb
        if self.meminfo_data and self.meminfo_data.get('total_pss_kb', 0) > 0:
            total_with_memtrack_kb = self.meminfo_data['total_pss_kb']

        effective_native_heap_kb = smaps_metrics['native_heap_total_kb']
        if self.meminfo_data and self.meminfo_data.get('native_heap_kb', 0) > 0:
            effective_native_heap_kb = self.meminfo_data['native_heap_kb']

        graphics_total_kb = smaps_metrics['graphics_smaps_total_kb'] + memtrack_total_kb
        total_memory_mb = total_memory_kb / 1024
        total_with_memtrack_mb = total_with_memtrack_kb / 1024
        native_heap_mb = effective_native_heap_kb / 1024
        dalvik_heap_mb = smaps_metrics['dalvik_heap_kb'] / 1024
        native_code_mb = smaps_metrics['native_code_kb'] / 1024
        graphics_mb = graphics_total_kb / 1024
        
        self.analysis_result['summary'] = {
            'total_memory_mb': round(total_memory_mb, 2),
            'total_memory_with_memtrack_mb': round(total_with_memtrack_mb, 2),
            'java_heap_mb': round(java_heap_mb, 2),
            'native_heap_mb': round(native_heap_mb, 2),
            'dalvik_runtime_mb': round(dalvik_heap_mb, 2),
            'native_code_mb': round(native_code_mb, 2),
            'graphics_mb': round(graphics_mb, 2),
            'memtrack_mb': round(memtrack_total_kb / 1024, 2),
            'java_heap_percentage': round((java_heap_mb / total_with_memtrack_mb) * 100, 1) if total_with_memtrack_mb > 0 else 0
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
            'native_heap_smaps_mb': round(smaps_metrics['native_heap_total_kb'] / 1024, 2),
            'scudo_heap_mb': round(smaps_metrics['scudo_heap_kb'] / 1024, 2),
            'native_heap_map_mb': round(smaps_metrics['native_heap_map_kb'] / 1024, 2),
            'legacy_native_mb': round(smaps_metrics['legacy_native_kb'] / 1024, 2),
            'native_code_mb': round(native_code_mb, 2),
            'gfx_dev_mb': round(smaps_metrics['gfx_dev_kb'] / 1024, 2),
            'graphics_mb': round(graphics_mb, 2),
            'gl_mb': round(smaps_metrics['gl_kb'] / 1024, 2),
            'dmabuf_mb': round(smaps_metrics['dmabuf_kb'] / 1024, 2),
            'memtrack_mb': round(memtrack_total_kb / 1024, 2),
            'memtrack_egl_mb': round((self.meminfo_data['memtrack_egl_kb'] if self.meminfo_data else 0) / 1024, 2),
            'memtrack_gl_mb': round((self.meminfo_data['memtrack_gl_kb'] if self.meminfo_data else 0) / 1024, 2),
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
        smaps_metrics = self._build_smaps_metrics()
        total_memory_kb = smaps_metrics['total_memory_kb']
        memtrack_total_kb = self.meminfo_data['memtrack_total_kb'] if self.meminfo_data else 0
        total_with_memtrack_kb = total_memory_kb + memtrack_total_kb
        if self.meminfo_data and self.meminfo_data.get('total_pss_kb', 0) > 0:
            total_with_memtrack_kb = self.meminfo_data['total_pss_kb']

        effective_native_heap_kb = smaps_metrics['native_heap_total_kb']
        if self.meminfo_data and self.meminfo_data.get('native_heap_kb', 0) > 0:
            effective_native_heap_kb = self.meminfo_data['native_heap_kb']
        
        total_memory_mb = total_memory_kb / 1024
        
        self.analysis_result['summary'] = {
            'total_memory_mb': round(total_memory_mb, 2),
            'total_memory_with_memtrack_mb': round(total_with_memtrack_kb / 1024, 2),
            'native_heap_mb': round(effective_native_heap_kb / 1024, 2),
            'dalvik_runtime_mb': round(smaps_metrics['dalvik_heap_kb'] / 1024, 2),
            'native_code_mb': round(smaps_metrics['native_code_kb'] / 1024, 2),
            'graphics_mb': round((smaps_metrics['graphics_smaps_total_kb'] + memtrack_total_kb) / 1024, 2),
            'memtrack_mb': round(memtrack_total_kb / 1024, 2),
        }

        self.analysis_result['native_memory'] = {
            'native_heap_mb': round(effective_native_heap_kb / 1024, 2),
            'native_heap_smaps_mb': round(smaps_metrics['native_heap_total_kb'] / 1024, 2),
            'scudo_heap_mb': round(smaps_metrics['scudo_heap_kb'] / 1024, 2),
            'native_heap_map_mb': round(smaps_metrics['native_heap_map_kb'] / 1024, 2),
            'legacy_native_mb': round(smaps_metrics['legacy_native_kb'] / 1024, 2),
            'native_code_mb': round(smaps_metrics['native_code_kb'] / 1024, 2),
            'gfx_dev_mb': round(smaps_metrics['gfx_dev_kb'] / 1024, 2),
            'graphics_mb': round((smaps_metrics['graphics_smaps_total_kb'] + memtrack_total_kb) / 1024, 2),
            'gl_mb': round(smaps_metrics['gl_kb'] / 1024, 2),
            'dmabuf_mb': round(smaps_metrics['dmabuf_kb'] / 1024, 2),
            'memtrack_mb': round(memtrack_total_kb / 1024, 2),
            'memtrack_egl_mb': round((self.meminfo_data['memtrack_egl_kb'] if self.meminfo_data else 0) / 1024, 2),
            'memtrack_gl_mb': round((self.meminfo_data['memtrack_gl_kb'] if self.meminfo_data else 0) / 1024, 2),
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
            smaps_metrics = self._build_smaps_metrics()
            memtrack_total_kb = self.meminfo_data['memtrack_total_kb'] if self.meminfo_data else 0

            total_kb = smaps_metrics['total_memory_kb'] + memtrack_total_kb
            if self.meminfo_data and self.meminfo_data.get('total_pss_kb', 0) > 0:
                total_kb = self.meminfo_data['total_pss_kb']
            total_mb = total_kb / 1024

            native_heap_kb = smaps_metrics['native_heap_total_kb']
            if self.meminfo_data and self.meminfo_data.get('native_heap_kb', 0) > 0:
                native_heap_kb = self.meminfo_data['native_heap_kb']
            native_heap_mb = native_heap_kb / 1024
            
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
            graphics_mb = (smaps_metrics['graphics_smaps_total_kb'] + memtrack_total_kb) / 1024
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

        smaps_metrics = self._build_smaps_metrics()
        memtrack_total_kb = self.meminfo_data['memtrack_total_kb'] if self.meminfo_data else 0

        total_kb = smaps_metrics['total_memory_kb'] + memtrack_total_kb
        if self.meminfo_data and self.meminfo_data.get('total_pss_kb', 0) > 0:
            total_kb = self.meminfo_data['total_pss_kb']
        total_mb = total_kb / 1024

        native_heap_kb = smaps_metrics['native_heap_total_kb']
        if self.meminfo_data and self.meminfo_data.get('native_heap_kb', 0) > 0:
            native_heap_kb = self.meminfo_data['native_heap_kb']
        native_heap_mb = native_heap_kb / 1024
        
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

        graphics_mb = (smaps_metrics['graphics_smaps_total_kb'] + memtrack_total_kb) / 1024
        if graphics_mb > 30:
            recommendations.append({
                'type': 'INFO',
                'category': '图形内存',
                'message': f'图形内存使用较高 ({graphics_mb:.1f}MB)'
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
            'total_memory_with_memtrack_mb': '总内存(含mtrack)',
            'java_heap_mb': 'Java堆内存',
            'native_heap_mb': 'Native堆内存',
            'native_heap_smaps_mb': 'Native堆内存(SMAPS口径)',
            'scudo_heap_mb': 'Scudo堆内存',
            'native_heap_map_mb': 'Native Heap映射内存',
            'legacy_native_mb': 'Native传统分类内存',
            'dalvik_runtime_mb': 'Dalvik运行时',
            'native_code_mb': 'Native代码',
            'java_heap_percentage': 'Java堆占比',
            'total_objects': '总对象数',
            'total_arrays': '总数组数',
            'string_objects': '字符串对象数',
            'string_memory_mb': '字符串内存',
            'gfx_dev_mb': 'Gfx dev图形设备内存',
            'graphics_mb': '图形内存',
            'gl_mb': 'OpenGL内存',
            'dmabuf_mb': 'DMA-BUF内存',
            'memtrack_mb': 'Memtrack内存',
            'memtrack_egl_mb': 'EGL Memtrack内存',
            'memtrack_gl_mb': 'GL Memtrack内存',
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

    def export_json_report(self, output_file):
        """导出纯JSON格式分析报告"""
        if not self.analysis_result:
            print("没有分析结果可导出")
            return False

        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(self.analysis_result, f, ensure_ascii=False, indent=2)
            print(f"✓ JSON分析报告已导出到: {output_file}")
            return True
        except Exception as e:
            print(f"✗ 导出JSON报告失败: {e}")
            return False

def main():
    parser = argparse.ArgumentParser(description="Android内存综合分析工具")
    parser.add_argument('--hprof', help="HPROF文件路径")
    parser.add_argument('--smaps', help="SMAPS文件路径") 
    parser.add_argument('--meminfo', help="dumpsys meminfo输出文件路径(可选，用于补充mtrack数据)")
    parser.add_argument('-p', '--pid', help="进程PID (自动获取smaps，且尽量自动获取meminfo)")
    parser.add_argument('-o', '--output', help="分析结果输出文件")
    parser.add_argument('--json-output', help="JSON格式输出文件(纯JSON)")
    
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
    auto_meminfo_file = None
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
            print(f"获取进程 {pid} 的smaps数据...")

            smaps_content, smaps_error = read_smaps_with_adb('adb', pid, timeout=60)

            if not smaps_content:
                print(f"✗ 获取smaps数据失败: {smaps_error or '无详细错误信息'}")
                return

            with open(smaps_file, 'w', encoding='utf-8') as f:
                f.write(smaps_content)
            print(f"✓ smaps数据已保存到: {smaps_file}")

            # 在PID模式下自动尝试获取meminfo（失败不阻断）
            auto_meminfo_file = f"{pid}_meminfo_file.txt"
            meminfo_cmd = ['adb', 'shell', 'dumpsys', 'meminfo', '-d', str(pid)]
            print(f"尝试获取进程 {pid} 的meminfo数据...")
            meminfo_result = subprocess.run(meminfo_cmd, capture_output=True, text=True)
            if meminfo_result.returncode == 0 and meminfo_result.stdout.strip():
                with open(auto_meminfo_file, 'w', encoding='utf-8') as f:
                    f.write(meminfo_result.stdout)
                print(f"✓ meminfo数据已保存到: {auto_meminfo_file}")
            else:
                auto_meminfo_file = None
                error_msg = meminfo_result.stderr.strip() if meminfo_result.stderr else "无详细错误信息"
                print(f"⚠️ 获取meminfo数据失败，将继续仅基于SMAPS分析: {error_msg}")
                
        except ValueError:
            print("错误: 请提供有效的PID")
            return
        except Exception as e:
            print(f"获取smaps数据时出错: {e}")
            return
    
    if smaps_file:
        if not analyzer.analyze_smaps(smaps_file):
            return

    meminfo_file = args.meminfo if args.meminfo else auto_meminfo_file
    if meminfo_file:
        if not os.path.exists(meminfo_file):
            print(f"错误: meminfo文件不存在: {meminfo_file}")
            return
        if not analyzer.analyze_meminfo(meminfo_file):
            if args.meminfo:
                return
            print("⚠️ 自动获取的meminfo文件解析失败，将继续使用现有数据生成报告")
    
    # 生成综合分析
    analyzer.generate_comprehensive_analysis()
    
    # 显示分析报告
    analyzer.print_analysis_report()
    
    # 导出报告
    exported = False
    if args.output:
        analyzer.export_report(args.output)
        exported = True
    if args.json_output:
        analyzer.export_json_report(args.json_output)
        exported = True
    if not exported:
        # 默认输出文件
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_output = f"memory_analysis_{timestamp}.txt"
        analyzer.export_report(default_output)

if __name__ == "__main__":
    main()
