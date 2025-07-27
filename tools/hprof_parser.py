#!/usr/bin/env python
# -*- coding:utf-8 -*-
# Android HPROF Memory Analysis Tool
# @Author: Android Memory Analysis Tool

import argparse
import struct
import os
import sys
from collections import defaultdict, Counter
from datetime import datetime

class HprofRecord:
    """HPROF记录类型"""
    UTF8 = 0x01
    LOAD_CLASS = 0x02
    UNLOAD_CLASS = 0x03
    STACK_FRAME = 0x04
    STACK_TRACE = 0x05
    ALLOC_SITES = 0x06
    HEAP_SUMMARY = 0x07
    START_THREAD = 0x0a
    END_THREAD = 0x0b
    HEAP_DUMP = 0x0c
    HEAP_DUMP_SEGMENT = 0x1c
    HEAP_DUMP_END = 0x2c
    CPU_SAMPLES = 0x0d
    CONTROL_SETTINGS = 0x0e

class HprofHeapDump:
    """堆dump子记录类型"""
    ROOT_UNKNOWN = 0xff
    ROOT_JNI_GLOBAL = 0x01
    ROOT_JNI_LOCAL = 0x02
    ROOT_JAVA_FRAME = 0x03
    ROOT_NATIVE_STACK = 0x04
    ROOT_STICKY_CLASS = 0x05
    ROOT_THREAD_BLOCK = 0x06
    ROOT_MONITOR_USED = 0x07
    ROOT_THREAD_OBJECT = 0x08
    CLASS_DUMP = 0x20
    INSTANCE_DUMP = 0x21
    OBJECT_ARRAY_DUMP = 0x22
    PRIMITIVE_ARRAY_DUMP = 0x23

class HprofParser:
    def __init__(self, filename):
        self.filename = filename
        self.file = None
        self.header = {}
        self.strings = {}  # id -> string
        self.classes = {}  # class_id -> class_info
        self.instances = {}  # object_id -> instance_info
        self.arrays = {}  # array_id -> array_info
        self.roots = []
        self.total_instances = 0
        self.total_instance_size = 0
        self.total_arrays = 0
        self.total_array_size = 0
        
        # 分类统计
        self.class_stats = defaultdict(lambda: {'count': 0, 'size': 0})
        self.string_stats = {'count': 0, 'size': 0}
        self.primitive_stats = defaultdict(lambda: {'count': 0, 'size': 0})
        
    def parse(self):
        """解析HPROF文件"""
        try:
            self.file = open(self.filename, 'rb')
            self._parse_header()
            self._parse_records()
            self._analyze_memory()
            return True
        except Exception as e:
            print(f"解析HPROF文件失败: {e}")
            return False
        finally:
            if self.file:
                self.file.close()
    
    def _parse_header(self):
        """解析文件头"""
        # 读取版本字符串 (以null结尾)
        version_bytes = []
        while True:
            byte = self.file.read(1)
            if not byte or byte == b'\x00':
                break
            version_bytes.append(byte)
        
        self.header['version'] = b''.join(version_bytes).decode('ascii')
        
        # 读取标识符大小（4字节）
        id_size_bytes = self.file.read(4)
        self.header['id_size'] = struct.unpack('>I', id_size_bytes)[0]
        
        # 读取时间戳（8字节）
        timestamp_bytes = self.file.read(8)
        self.header['timestamp'] = struct.unpack('>Q', timestamp_bytes)[0]
        
        print(f"HPROF版本: {self.header['version']}")
        print(f"标识符大小: {self.header['id_size']} bytes")
        print(f"时间戳: {datetime.fromtimestamp(self.header['timestamp']/1000)}")
    
    def _read_id(self):
        """读取ID"""
        id_bytes = self.file.read(self.header['id_size'])
        if len(id_bytes) != self.header['id_size']:
            return None
        if self.header['id_size'] == 4:
            return struct.unpack('>I', id_bytes)[0]
        elif self.header['id_size'] == 8:
            return struct.unpack('>Q', id_bytes)[0]
        else:
            return int.from_bytes(id_bytes, 'big')
    
    def _parse_records(self):
        """解析记录"""
        while True:
            # 读取记录头
            record_header = self.file.read(9)  # 1字节类型 + 4字节时间戳 + 4字节长度
            if len(record_header) != 9:
                break
                
            record_type = record_header[0]
            timestamp = struct.unpack('>I', record_header[1:5])[0]
            length = struct.unpack('>I', record_header[5:9])[0]
            
            # 根据记录类型处理
            if record_type == HprofRecord.UTF8:
                self._parse_utf8_record(length)
            elif record_type == HprofRecord.LOAD_CLASS:
                self._parse_load_class_record(length)
            elif record_type in [HprofRecord.HEAP_DUMP, HprofRecord.HEAP_DUMP_SEGMENT]:
                self._parse_heap_dump_record(length)
            else:
                # 跳过其他类型的记录
                self.file.seek(length, 1)
    
    def _parse_utf8_record(self, length):
        """解析UTF8字符串记录"""
        string_id = self._read_id()
        string_data = self.file.read(length - self.header['id_size'])
        try:
            string_value = string_data.decode('utf-8')
            self.strings[string_id] = string_value
        except UnicodeDecodeError:
            self.strings[string_id] = str(string_data)
    
    def _parse_load_class_record(self, length):
        """解析类加载记录"""
        class_serial = struct.unpack('>I', self.file.read(4))[0]
        class_id = self._read_id()
        stack_trace_serial = struct.unpack('>I', self.file.read(4))[0]
        class_name_id = self._read_id()
        
        self.classes[class_id] = {
            'serial': class_serial,
            'name_id': class_name_id,
            'name': self.strings.get(class_name_id, f"Unknown_{class_name_id}"),
            'stack_trace': stack_trace_serial
        }
    
    def _parse_heap_dump_record(self, length):
        """解析堆dump记录"""
        end_pos = self.file.tell() + length
        
        while self.file.tell() < end_pos:
            sub_record_type = self.file.read(1)
            if not sub_record_type:
                break
            sub_record_type = sub_record_type[0]
            
            if sub_record_type == HprofHeapDump.CLASS_DUMP:
                self._parse_class_dump()
            elif sub_record_type == HprofHeapDump.INSTANCE_DUMP:
                self._parse_instance_dump()
            elif sub_record_type == HprofHeapDump.OBJECT_ARRAY_DUMP:
                self._parse_object_array_dump()
            elif sub_record_type == HprofHeapDump.PRIMITIVE_ARRAY_DUMP:
                self._parse_primitive_array_dump()
            elif sub_record_type in [HprofHeapDump.ROOT_JNI_GLOBAL, HprofHeapDump.ROOT_JNI_LOCAL,
                                   HprofHeapDump.ROOT_JAVA_FRAME, HprofHeapDump.ROOT_NATIVE_STACK,
                                   HprofHeapDump.ROOT_STICKY_CLASS, HprofHeapDump.ROOT_THREAD_BLOCK,
                                   HprofHeapDump.ROOT_MONITOR_USED, HprofHeapDump.ROOT_THREAD_OBJECT]:
                self._parse_root_record(sub_record_type)
            else:
                # 跳过未知的子记录类型
                break
    
    def _parse_class_dump(self):
        """解析类dump"""
        class_id = self._read_id()
        stack_trace_serial = struct.unpack('>I', self.file.read(4))[0]
        super_class_id = self._read_id()
        class_loader_id = self._read_id()
        signers_id = self._read_id()
        protection_domain_id = self._read_id()
        reserved1 = self._read_id()
        reserved2 = self._read_id()
        instance_size = struct.unpack('>I', self.file.read(4))[0]
        
        # 读取常量池
        constant_pool_size = struct.unpack('>H', self.file.read(2))[0]
        for _ in range(constant_pool_size):
            index = struct.unpack('>H', self.file.read(2))[0]
            type_byte = self.file.read(1)[0]
            self._skip_value_by_type(type_byte)
        
        # 读取静态字段
        static_fields_count = struct.unpack('>H', self.file.read(2))[0]
        for _ in range(static_fields_count):
            name_id = self._read_id()
            type_byte = self.file.read(1)[0]
            self._skip_value_by_type(type_byte)
        
        # 读取实例字段
        instance_fields_count = struct.unpack('>H', self.file.read(2))[0]
        for _ in range(instance_fields_count):
            name_id = self._read_id()
            type_byte = self.file.read(1)[0]
        
        # 更新类信息
        if class_id in self.classes:
            self.classes[class_id]['instance_size'] = instance_size
    
    def _parse_instance_dump(self):
        """解析实例dump"""
        object_id = self._read_id()
        stack_trace_serial = struct.unpack('>I', self.file.read(4))[0]
        class_id = self._read_id()
        instance_data_length = struct.unpack('>I', self.file.read(4))[0]
        
        # 跳过实例数据
        self.file.seek(instance_data_length, 1)
        
        # 统计
        class_name = "Unknown"
        if class_id in self.classes:
            class_name = self.classes[class_id]['name']
        
        self.instances[object_id] = {
            'class_id': class_id,
            'class_name': class_name,
            'size': instance_data_length,
            'stack_trace': stack_trace_serial
        }
        
        self.total_instances += 1
        self.total_instance_size += instance_data_length
        self.class_stats[class_name]['count'] += 1
        self.class_stats[class_name]['size'] += instance_data_length
        
        # 特殊处理String对象
        if 'String' in class_name:
            self.string_stats['count'] += 1
            self.string_stats['size'] += instance_data_length
    
    def _parse_object_array_dump(self):
        """解析对象数组dump"""
        array_id = self._read_id()
        stack_trace_serial = struct.unpack('>I', self.file.read(4))[0]
        array_length = struct.unpack('>I', self.file.read(4))[0]
        element_class_id = self._read_id()
        
        # 跳过数组元素
        element_size = self.header['id_size']
        total_size = array_length * element_size
        self.file.seek(total_size, 1)
        
        # 获取元素类名
        element_class_name = "Unknown"
        if element_class_id in self.classes:
            element_class_name = self.classes[element_class_id]['name']
        
        array_name = f"{element_class_name}[]"
        
        self.arrays[array_id] = {
            'element_class_id': element_class_id,
            'element_class_name': element_class_name,
            'length': array_length,
            'size': total_size,
            'type': 'object'
        }
        
        self.total_arrays += 1
        self.total_array_size += total_size
        self.class_stats[array_name]['count'] += 1
        self.class_stats[array_name]['size'] += total_size
    
    def _parse_primitive_array_dump(self):
        """解析基本类型数组dump"""
        array_id = self._read_id()
        stack_trace_serial = struct.unpack('>I', self.file.read(4))[0]
        array_length = struct.unpack('>I', self.file.read(4))[0]
        element_type = self.file.read(1)[0]
        
        # 基本类型大小映射
        type_sizes = {
            4: 1,   # boolean
            5: 2,   # char
            6: 4,   # float
            7: 8,   # double
            8: 1,   # byte
            9: 2,   # short
            10: 4,  # int
            11: 8   # long
        }
        
        type_names = {
            4: 'boolean',
            5: 'char',
            6: 'float',
            7: 'double',
            8: 'byte',
            9: 'short',
            10: 'int',
            11: 'long'
        }
        
        element_size = type_sizes.get(element_type, 1)
        total_size = array_length * element_size
        type_name = type_names.get(element_type, f'type_{element_type}')
        array_name = f"{type_name}[]"
        
        # 跳过数组数据
        self.file.seek(total_size, 1)
        
        self.arrays[array_id] = {
            'element_type': element_type,
            'element_type_name': type_name,
            'length': array_length,
            'size': total_size,
            'type': 'primitive'
        }
        
        self.total_arrays += 1
        self.total_array_size += total_size
        self.primitive_stats[array_name]['count'] += 1
        self.primitive_stats[array_name]['size'] += total_size
    
    def _parse_root_record(self, root_type):
        """解析根对象记录"""
        object_id = self._read_id()
        
        root_info = {'type': root_type, 'object_id': object_id}
        
        # 根据根类型读取额外信息
        if root_type in [HprofHeapDump.ROOT_JNI_LOCAL, HprofHeapDump.ROOT_JAVA_FRAME]:
            thread_serial = struct.unpack('>I', self.file.read(4))[0]
            frame_number = struct.unpack('>I', self.file.read(4))[0]
            root_info['thread_serial'] = thread_serial
            root_info['frame_number'] = frame_number
        elif root_type == HprofHeapDump.ROOT_THREAD_OBJECT:
            thread_serial = struct.unpack('>I', self.file.read(4))[0]
            stack_trace_serial = struct.unpack('>I', self.file.read(4))[0]
            root_info['thread_serial'] = thread_serial
            root_info['stack_trace_serial'] = stack_trace_serial
        
        self.roots.append(root_info)
    
    def _skip_value_by_type(self, type_byte):
        """根据类型跳过值"""
        type_sizes = {
            2: self.header['id_size'],  # object
            4: 1,   # boolean
            5: 2,   # char
            6: 4,   # float
            7: 8,   # double
            8: 1,   # byte
            9: 2,   # short
            10: 4,  # int
            11: 8   # long
        }
        size = type_sizes.get(type_byte, 0)
        if size > 0:
            self.file.seek(size, 1)
    
    def _analyze_memory(self):
        """分析内存使用情况"""
        print("\n=== 内存分析完成 ===")
        print(f"总实例数: {self.total_instances:,}")
        print(f"实例总大小: {self.total_instance_size / 1024 / 1024:.2f} MB")
        print(f"总数组数: {self.total_arrays:,}")
        print(f"数组总大小: {self.total_array_size / 1024 / 1024:.2f} MB")
        print(f"总内存使用: {(self.total_instance_size + self.total_array_size) / 1024 / 1024:.2f} MB")
    
    def print_class_statistics(self, top_n=20, min_size_mb=0.1):
        """打印类统计信息"""
        print(f"\n=== TOP {top_n} 内存占用类 (最小 {min_size_mb}MB) ===")
        print(f"{'类名':<50} {'实例数':<10} {'总大小(MB)':<12} {'平均大小(KB)':<12}")
        print("-" * 90)
        
        # 按总大小排序
        sorted_classes = sorted(self.class_stats.items(), 
                              key=lambda x: x[1]['size'], reverse=True)
        
        count = 0
        for class_name, stats in sorted_classes:
            size_mb = stats['size'] / 1024 / 1024
            if size_mb < min_size_mb:
                continue
                
            avg_size_kb = stats['size'] / stats['count'] / 1024 if stats['count'] > 0 else 0
            print(f"{class_name:<50} {stats['count']:<10,} {size_mb:<12.2f} {avg_size_kb:<12.2f}")
            
            count += 1
            if count >= top_n:
                break
    
    def print_primitive_statistics(self, top_n=10):
        """打印基本类型数组统计"""
        print(f"\n=== TOP {top_n} 基本类型数组内存占用 ===")
        print(f"{'数组类型':<20} {'数组数量':<10} {'总大小(MB)':<12} {'平均大小(KB)':<12}")
        print("-" * 60)
        
        sorted_primitives = sorted(self.primitive_stats.items(), 
                                 key=lambda x: x[1]['size'], reverse=True)
        
        for i, (array_type, stats) in enumerate(sorted_primitives[:top_n]):
            size_mb = stats['size'] / 1024 / 1024
            avg_size_kb = stats['size'] / stats['count'] / 1024 if stats['count'] > 0 else 0
            print(f"{array_type:<20} {stats['count']:<10,} {size_mb:<12.2f} {avg_size_kb:<12.2f}")
    
    def print_string_statistics(self):
        """打印字符串统计"""
        print(f"\n=== 字符串内存统计 ===")
        print(f"字符串实例数: {self.string_stats['count']:,}")
        print(f"字符串总大小: {self.string_stats['size'] / 1024 / 1024:.2f} MB")
        if self.string_stats['count'] > 0:
            avg_size = self.string_stats['size'] / self.string_stats['count']
            print(f"平均字符串大小: {avg_size:.2f} bytes")
    
    def export_analysis(self, output_file):
        """导出分析结果"""
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("Android HPROF内存分析报告\n")
            f.write("=" * 50 + "\n\n")
            
            f.write(f"分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"HPROF文件: {self.filename}\n\n")
            
            # 总体统计
            f.write("总体内存统计:\n")
            f.write("-" * 30 + "\n")
            f.write(f"总实例数: {self.total_instances:,}\n")
            f.write(f"实例总大小: {self.total_instance_size / 1024 / 1024:.2f} MB\n")
            f.write(f"总数组数: {self.total_arrays:,}\n")
            f.write(f"数组总大小: {self.total_array_size / 1024 / 1024:.2f} MB\n")
            f.write(f"总内存使用: {(self.total_instance_size + self.total_array_size) / 1024 / 1024:.2f} MB\n\n")
            
            # 类统计
            f.write("TOP 50 内存占用类:\n")
            f.write("-" * 30 + "\n")
            f.write(f"{'类名':<60} {'实例数':<12} {'总大小(MB)':<15} {'平均大小(KB)':<15}\n")
            f.write("-" * 110 + "\n")
            
            sorted_classes = sorted(self.class_stats.items(), 
                                  key=lambda x: x[1]['size'], reverse=True)
            
            for class_name, stats in sorted_classes[:50]:
                size_mb = stats['size'] / 1024 / 1024
                avg_size_kb = stats['size'] / stats['count'] / 1024 if stats['count'] > 0 else 0
                f.write(f"{class_name:<60} {stats['count']:<12,} {size_mb:<15.2f} {avg_size_kb:<15.2f}\n")
            
            # 基本类型数组统计
            f.write(f"\n基本类型数组统计:\n")
            f.write("-" * 30 + "\n")
            f.write(f"{'数组类型':<20} {'数组数量':<12} {'总大小(MB)':<15} {'平均大小(KB)':<15}\n")
            f.write("-" * 70 + "\n")
            
            sorted_primitives = sorted(self.primitive_stats.items(), 
                                     key=lambda x: x[1]['size'], reverse=True)
            
            for array_type, stats in sorted_primitives:
                size_mb = stats['size'] / 1024 / 1024
                avg_size_kb = stats['size'] / stats['count'] / 1024 if stats['count'] > 0 else 0
                f.write(f"{array_type:<20} {stats['count']:<12,} {size_mb:<15.2f} {avg_size_kb:<15.2f}\n")
            
            # 字符串统计
            f.write(f"\n字符串统计:\n")
            f.write("-" * 30 + "\n")
            f.write(f"字符串实例数: {self.string_stats['count']:,}\n")
            f.write(f"字符串总大小: {self.string_stats['size'] / 1024 / 1024:.2f} MB\n")
            if self.string_stats['count'] > 0:
                avg_size = self.string_stats['size'] / self.string_stats['count']
                f.write(f"平均字符串大小: {avg_size:.2f} bytes\n")
            
            # Educational Resources Section
            f.write("\n" + "="*60 + "\n")
            f.write("📚 深入学习指南 / Educational Resources\n")
            f.write("="*60 + "\n\n")
            f.write("为了更好地理解 HPROF 分析结果，建议阅读以下详细指南：\n")
            f.write("For better understanding of HPROF analysis results, please refer to these detailed guides:\n\n")
            
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
            
            f.write("☕ Java 堆内存专项优化 / Java Heap Memory Optimization:\n")
            f.write("   • 结合 SMAPS 分析了解完整内存使用情况\n")
            f.write("   • 使用 MAT (Memory Analyzer Tool) 进行深度引用链分析\n")
            f.write("   • 配合 LeakCanary 自动检测内存泄漏\n")
            f.write("   • 关注大对象、重复字符串和集合类的使用\n\n")

def main():
    parser = argparse.ArgumentParser(description="Android HPROF内存分析工具")
    parser.add_argument('-f', '--file', required=True, help="HPROF文件路径")
    parser.add_argument('-o', '--output', help="分析结果输出文件")
    parser.add_argument('-t', '--top', type=int, default=20, help="显示TOP N个内存占用类 (默认20)")
    parser.add_argument('-m', '--min-size', type=float, default=0.1, help="最小显示大小(MB) (默认0.1)")
    parser.add_argument('-s', '--simple', action='store_true', help="简单输出模式")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.file):
        print(f"错误: HPROF文件不存在: {args.file}")
        return
    
    print(f"开始解析HPROF文件: {args.file}")
    
    parser = HprofParser(args.file)
    if parser.parse():
        if not args.simple:
            parser.print_class_statistics(args.top, args.min_size)
            parser.print_primitive_statistics()
            parser.print_string_statistics()
        
        if args.output:
            parser.export_analysis(args.output)
            print(f"\n分析结果已导出到: {args.output}")
        else:
            # 默认输出文件
            base_name = os.path.splitext(os.path.basename(args.file))[0]
            default_output = f"{base_name}_analysis.txt"
            parser.export_analysis(default_output)
            print(f"\n分析结果已导出到: {default_output}")
        
        # Educational Resources for Console Output
        print("\n" + "="*60)
        print("📚 深入学习指南 / Educational Resources")
        print("="*60)
        print("\n为了更好地理解 HPROF 分析结果，建议阅读以下详细指南：")
        print("For better understanding of HPROF analysis results, please refer to these detailed guides:\n")
        
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
        
        print("☕ Java 堆内存专项优化 / Java Heap Memory Optimization:")
        print("   • 结合 SMAPS 分析了解完整内存使用情况")
        print("   • 使用 MAT (Memory Analyzer Tool) 进行深度引用链分析")
        print("   • 配合 LeakCanary 自动检测内存泄漏")
        print("   • 关注大对象、重复字符串和集合类的使用\n")
    else:
        print("HPROF文件解析失败")

if __name__ == "__main__":
    main()