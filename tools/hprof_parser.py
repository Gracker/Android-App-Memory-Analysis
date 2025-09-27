
import sys
import os
from datetime import datetime
from collections import defaultdict
import argparse
import struct

class HprofParser:
    def __init__(self, filename):
        self.filename = filename
        self.hprof = None
        self.size_of_identifier = 4
        self.strings = {}
        self.classes = {}
        self.total_instances = 0
        self.total_instance_size = 0
        self.total_arrays = 0
        self.total_array_size = 0
        self.class_stats = defaultdict(lambda: {'count': 0, 'size': 0})
        self.string_stats = {'count': 0, 'size': 0}
        self.primitive_stats = defaultdict(lambda: {'count': 0, 'size': 0})
        self.package_stats = defaultdict(lambda: {'count': 0, 'size': 0})

        self.notes = {
            'java.lang': 'Java语言的核心包，包含Object, String, Integer等基础类。实例数多是正常的，但如果某个特定类的实例过多，可能存在问题。',
            'java.util': 'Java的工具包，包含集合框架(List, Map, Set)等。关注HashMap, ArrayList等集合类的大小，可能存在内存泄漏。',
            'byte[]': '字节数组，通常用于存储图片、网络数据、文件等二进制数据。如果总大小过大，需要分析这些数据是否被及时释放。',
            'java.lang.String': '字符串类。实例数过多或总大小过大，可能存在字符串重复创建或未及时释放的问题。',
        }

        self.TAG_STRING = 0x01
        self.TAG_LOAD_CLASS = 0x02
        self.TAG_UNLOAD_CLASS = 0x03
        self.TAG_STACK_FRAME = 0x04
        self.TAG_STACK_TRACE = 0x05
        self.TAG_ALLOC_SITES = 0x06
        self.TAG_HEAP_SUMMARY = 0x07
        self.TAG_START_THREAD = 0x0A
        self.TAG_END_THREAD = 0x0B
        self.TAG_HEAP_DUMP = 0x0C
        self.TAG_HEAP_DUMP_SEGMENT = 0x1C
        self.TAG_HEAP_DUMP_END = 0x2C
        self.TAG_CPU_SAMPLES = 0x0D
        self.TAG_CONTROL_SETTINGS = 0x0E

        self.HEAP_TAG_ROOT_UNKNOWN = 0xFF
        self.HEAP_TAG_ROOT_JNI_GLOBAL = 0x01
        self.HEAP_TAG_ROOT_JNI_LOCAL = 0x02
        self.HEAP_TAG_ROOT_JAVA_FRAME = 0x03
        self.HEAP_TAG_ROOT_NATIVE_STACK = 0x04
        self.HEAP_TAG_ROOT_STICKY_CLASS = 0x05
        self.HEAP_TAG_ROOT_THREAD_BLOCK = 0x06
        self.HEAP_TAG_ROOT_MONITOR_USED = 0x07
        self.HEAP_TAG_ROOT_THREAD_OBJECT = 0x08
        self.HEAP_TAG_CLASS_DUMP = 0x20
        self.HEAP_TAG_INSTANCE_DUMP = 0x21
        self.HEAP_TAG_OBJECT_ARRAY_DUMP = 0x22
        self.HEAP_TAG_PRIMITIVE_ARRAY_DUMP = 0x23
        self.HEAP_TAG_HEAP_DUMP_INFO = 0xfe
        self.HEAP_TAG_ROOT_INTERNED_STRING = 0x89
        self.HEAP_TAG_ROOT_FINALIZING = 0x8a
        self.HEAP_TAG_ROOT_DEBUGGER = 0x8b
        self.HEAP_TAG_ROOT_REFERENCE_CLEANUP = 0x8c
        self.HEAP_TAG_ROOT_VM_INTERNAL = 0x8d
        self.HEAP_TAG_ROOT_JNI_MONITOR = 0x8e
        self.HEAP_TAG_ROOT_UNREACHABLE = 0x90
        self.HEAP_TAG_PRIMITIVE_ARRAY_NODATA = 0xc3

        self.TYPE_OBJECT = 2
        self.TYPE_BOOLEAN = 4
        self.TYPE_CHAR = 5
        self.TYPE_FLOAT = 6
        self.TYPE_DOUBLE = 7
        self.TYPE_BYTE = 8
        self.TYPE_SHORT = 9
        self.TYPE_INT = 10
        self.TYPE_LONG = 11

        self.BASIC_TYPES = {
            self.TYPE_BOOLEAN: (1, 'boolean'),
            self.TYPE_CHAR: (2, 'char'),
            self.TYPE_FLOAT: (4, 'float'),
            self.TYPE_DOUBLE: (8, 'double'),
            self.TYPE_BYTE: (1, 'byte'),
            self.TYPE_SHORT: (2, 'short'),
            self.TYPE_INT: (4, 'int'),
            self.TYPE_LONG: (8, 'long'),
        }

    def parse(self, simple_mode=False, top_n=20, min_size_mb=0.1, output_file=None):
        try:
            self.openHprof(self.filename)
            self.readHead()
            self.readRecords()
            if not simple_mode:
                self.print_package_statistics(top_n)
                self.print_class_statistics(top_n, min_size_mb)
                self.print_primitive_statistics()
                self.print_string_statistics()
            if output_file:
                self.export_analysis(output_file)
            else:
                base_name = os.path.splitext(os.path.basename(self.filename))[0]
                default_output = f"{base_name}_analysis.txt"
                self.export_analysis(default_output)
                print(f"\n分析结果已导出到: {default_output}")
            return True
        except Exception as e:
            print(f"解析HPROF文件失败: {e}")
            return False
        finally:
            if self.hprof:
                self.hprof.close()

    def readRecords(self):
        file_length = os.path.getsize(self.hprof.name)
        while self.hprof.tell() < file_length:
            tag = self.readInt(1)
            self.readInt(4) # time
            length = self.readInt(4)
            if tag == self.TAG_STRING:
                self.readString(length)
            elif tag == self.TAG_LOAD_CLASS:
                self.readLoadClass(length)
            elif tag in [self.TAG_HEAP_DUMP, self.TAG_HEAP_DUMP_SEGMENT]:
                self.readHeapDumpInternal(length)
            elif tag in [self.TAG_UNLOAD_CLASS, self.TAG_STACK_FRAME, self.TAG_STACK_TRACE, self.TAG_ALLOC_SITES, self.TAG_HEAP_SUMMARY, self.TAG_START_THREAD, self.TAG_END_THREAD, self.TAG_HEAP_DUMP_END, self.TAG_CPU_SAMPLES, self.TAG_CONTROL_SETTINGS]:
                self.seek(length)
            else:
                raise Exception('Not supported tag: %d, position: %d' % (tag, self.hprof.tell()))

    def readHead(self):
        version_bytes = []
        while True:
            b = self.read(1)
            if not b or b == b'\x00':
                break
            version_bytes.append(b)
        version = b''.join(version_bytes).decode('utf-8')
        self.size_of_identifier = self.readInt(4)
        timestamp = self.readInt(8) / 1000
        print("HPROF版本: %s" % (version))
        print("标识符大小: %d" % (self.size_of_identifier))
        print("时间戳: %s" % (datetime.fromtimestamp(timestamp)))
        self.BASIC_TYPES[self.TYPE_OBJECT] = (self.size_of_identifier, 'object')

    def readString(self, length):
        string_id = self.readId()
        self.strings[string_id] = self.read(length - self.size_of_identifier).decode('utf-8', 'ignore')

    def readLoadClass(self, length):
        class_serial = self.readInt(4)
        class_id = self.readId()
        stack_trace_serial = self.readInt(4)
        class_name_id = self.readId()
        self.classes[class_id] = {'name': self.strings.get(class_name_id, 'unknown')}

    def readHeapDumpInternal(self, length):
        available = length
        while available > 0:
            start = self.hprof.tell()
            tag = self.readInt(1)
            if not tag:
                break
            if tag == self.HEAP_TAG_CLASS_DUMP:
                self.readClassDump()
            elif tag == self.HEAP_TAG_INSTANCE_DUMP:
                self.readInstanceDump()
            elif tag == self.HEAP_TAG_OBJECT_ARRAY_DUMP:
                self.readObjectArrayDump()
            elif tag == self.HEAP_TAG_PRIMITIVE_ARRAY_DUMP:
                self.readPrimitiveArrayDump()
            else:
                self.seek(self.get_heap_subrecord_length(tag))
            end = self.hprof.tell()
            available -= end - start

    def get_heap_subrecord_length(self, tag):
        if tag in [self.HEAP_TAG_ROOT_UNKNOWN, self.HEAP_TAG_ROOT_STICKY_CLASS, self.HEAP_TAG_ROOT_MONITOR_USED, self.HEAP_TAG_ROOT_INTERNED_STRING, self.HEAP_TAG_ROOT_FINALIZING, self.HEAP_TAG_ROOT_DEBUGGER, self.HEAP_TAG_ROOT_REFERENCE_CLEANUP, self.HEAP_TAG_ROOT_VM_INTERNAL, self.HEAP_TAG_ROOT_UNREACHABLE]:
            return self.size_of_identifier
        elif tag == self.HEAP_TAG_ROOT_JNI_GLOBAL:
            return 2 * self.size_of_identifier
        elif tag in [self.HEAP_TAG_ROOT_JNI_LOCAL, self.HEAP_TAG_ROOT_JAVA_FRAME, self.HEAP_TAG_ROOT_THREAD_OBJECT, self.HEAP_TAG_ROOT_JNI_MONITOR]:
            return self.size_of_identifier + 8
        elif tag == self.HEAP_TAG_ROOT_NATIVE_STACK or tag == self.HEAP_TAG_ROOT_THREAD_BLOCK:
            return self.size_of_identifier + 4
        elif tag == self.HEAP_TAG_HEAP_DUMP_INFO:
            return 4 + self.size_of_identifier
        return 0

    def readClassDump(self):
        class_id = self.readId()
        self.readInt(4)
        super_class_id = self.readId()
        self.readId()
        self.readId()
        self.readId()
        self.seek(self.size_of_identifier * 2)
        instance_size = self.readInt(4)
        if class_id in self.classes:
            self.classes[class_id]['instance_size'] = instance_size
        self.readClassConstantFields()
        self.readClassStaticFields()
        self.readInstanceFields()

    def readClassConstantFields(self):
        count = self.readInt(2)
        for _ in range(count):
            self.seek(2)
            type = self.readInt(1)
            size, _ = self.BASIC_TYPES.get(type, (0, ''))
            if size > 0:
                self.seek(size)

    def readClassStaticFields(self):
        count = self.readInt(2)
        for _ in range(count):
            self.readId()
            type = self.readInt(1)
            size, _ = self.BASIC_TYPES.get(type, (0, ''))
            if size > 0:
                self.seek(size)

    def readInstanceFields(self):
        count = self.readInt(2)
        self.seek(count * (self.size_of_identifier + 1))

    def readInstanceDump(self):
        instance_id = self.readId()
        self.readInt(4)
        class_id = self.readId()
        fields_byte_size = self.readInt(4)
        self.seek(fields_byte_size)
        self.total_instances += 1
        self.total_instance_size += fields_byte_size
        class_name = self.classes.get(class_id, {}).get('name', 'unknown')
        self.class_stats[class_name]['count'] += 1
        self.class_stats[class_name]['size'] += fields_byte_size
        if 'java.lang.String' in class_name:
            self.string_stats['count'] += 1
            self.string_stats['size'] += fields_byte_size
        
        parts = class_name.split('.')
        if len(parts) > 1:
            package_name = '.'.join(parts[:-1])
            self.package_stats[package_name]['count'] += 1
            self.package_stats[package_name]['size'] += fields_byte_size

    def readObjectArrayDump(self):
        self.readId()
        self.readInt(4)
        length = self.readInt(4)
        array_class_id = self.readId()
        element_size = self.size_of_identifier * length
        self.seek(element_size)
        self.total_arrays += 1
        self.total_array_size += element_size
        class_name = self.classes.get(array_class_id, {}).get('name', 'unknown') + '[]'
        self.class_stats[class_name]['count'] += 1
        self.class_stats[class_name]['size'] += element_size

    def readPrimitiveArrayDump(self):
        self.readId()
        self.readInt(4)
        length = self.readInt(4)
        type = self.readInt(1)
        size, type_name = self.BASIC_TYPES.get(type, (0, 'unknown'))
        if size > 0:
            element_size = size * length
            self.seek(element_size)
            self.total_arrays += 1
            self.total_array_size += element_size
            self.primitive_stats[f'{type_name}[]']['count'] += 1
            self.primitive_stats[f'{type_name}[]']['size'] += element_size

    def openHprof(self, file):
        self.hprof = open(file, 'rb')

    def readInt(self, length):
        return int.from_bytes(self.read(length), byteorder='big', signed=False)

    def readId(self):
        return self.readInt(self.size_of_identifier)

    def read(self, length):
        return self.hprof.read(length)

    def seek(self, length):
        self.hprof.seek(length, 1)

    def print_package_statistics(self, top_n=20):
        print(f"\n=== TOP {top_n} 内存占用包 ===")
        print(f"{'包名':<50} {'实例数':<10} {'总大小(MB)':<12} {'说明'}")
        print("-" * 80)
        sorted_packages = sorted(self.package_stats.items(), 
                               key=lambda x: x[1]['size'], reverse=True)
        count = 0
        for package_name, stats in sorted_packages:
            size_mb = stats['size'] / 1024 / 1024
            note = self.notes.get(package_name, '')
            print(f"{package_name:<50} {stats['count']:<10,} {size_mb:<12.2f} {note}")
            count += 1
            if count >= top_n:
                break

    def print_class_statistics(self, top_n=20, min_size_mb=0.1):
        print(f"\n=== TOP {top_n} 内存占用类 (最小 {min_size_mb}MB) ===")
        print(f"{'类名':<50} {'实例数':<10} {'总大小(MB)':<12} {'平均大小(KB)':<12} {'说明'}")
        print("-" * 100)
        sorted_classes = sorted(self.class_stats.items(), 
                              key=lambda x: x[1]['size'], reverse=True)
        count = 0
        for class_name, stats in sorted_classes:
            size_mb = stats['size'] / 1024 / 1024
            if size_mb < min_size_mb:
                continue
            avg_size_kb = stats['size'] / stats['count'] / 1024 if stats['count'] > 0 else 0
            note = self.notes.get(class_name, '')
            print(f"{class_name:<50} {stats['count']:<10,} {size_mb:<12.2f} {avg_size_kb:<12.2f} {note}")
            count += 1
            if count >= top_n:
                break

    def print_primitive_statistics(self, top_n=10):
        print(f"\n=== TOP {top_n} 基本类型数组内存占用 ===")
        print(f"{'数组类型':<20} {'数组数量':<10} {'总大小(MB)':<12} {'平均大小(KB)':<12} {'说明'}")
        print("-" * 70)
        sorted_primitives = sorted(self.primitive_stats.items(), 
                                 key=lambda x: x[1]['size'], reverse=True)
        for i, (array_type, stats) in enumerate(sorted_primitives[:top_n]):
            size_mb = stats['size'] / 1024 / 1024
            avg_size_kb = stats['size'] / stats['count'] / 1024 if stats['count'] > 0 else 0
            note = self.notes.get(array_type, '')
            print(f"{array_type:<20} {stats['count']:<10,} {size_mb:<12.2f} {avg_size_kb:<12.2f} {note}")

    def print_string_statistics(self):
        print(f"\n=== 字符串内存统计 ===")
        print(f"字符串实例数: {self.string_stats['count']:,}")
        print(f"字符串总大小: {self.string_stats['size'] / 1024 / 1024:.2f} MB")
        if self.string_stats['count'] > 0:
            avg_size = self.string_stats['size'] / self.string_stats['count']
            print(f"平均字符串大小: {avg_size:.2f} bytes")

    def export_analysis(self, output_file):
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("Android HPROF内存分析报告\n")
            f.write("=" * 50 + "\n\n")
            f.write(f"分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"HPROF文件: {self.filename}\n\n")
            f.write("总体内存统计:\n")
            f.write("-" * 30 + "\n")
            f.write(f"总实例数: {self.total_instances:,}\n")
            f.write(f"实例总大小: {self.total_instance_size / 1024 / 1024:.2f} MB\n")
            f.write(f"总数组数: {self.total_arrays:,}\n")
            f.write(f"数组总大小: {self.total_array_size / 1024 / 1024:.2f} MB\n")
            f.write(f"总内存使用: {(self.total_instance_size + self.total_array_size) / 1024 / 1024:.2f} MB\n\n")
            f.write("TOP 20 内存占用包:\n")
            f.write("-" * 30 + "\n")
            f.write(f" {'包名':<50} {'实例数':<10} {'总大小(MB)':<12}")
            f.write("-" * 80 + "\n")
            sorted_packages = sorted(self.package_stats.items(), 
                               key=lambda x: x[1]['size'], reverse=True)
            count = 0
            for package_name, stats in sorted_packages:
                size_mb = stats['size'] / 1024 / 1024
                if size_mb < 0.1:
                    continue
                f.write(f"{package_name:<50} {stats['count']:<10,} {size_mb:<12.2f}\n")
                count += 1
                if count >= 20:
                    break

            f.write("\nTOP 50 内存占用类:\n")
            f.write("-" * 30 + "\n")
            f.write(f" {'类名':<60} {'实例数':<12} {'总大小(MB)':<15} {'平均大小(KB)':<15}")
            f.write("-" * 110 + "\n")
            sorted_classes = sorted(self.class_stats.items(), 
                                  key=lambda x: x[1]['size'], reverse=True)
            for class_name, stats in sorted_classes[:50]:
                size_mb = stats['size'] / 1024 / 1024
                avg_size_kb = stats['size'] / stats['count'] / 1024 if stats['count'] > 0 else 0
                f.write(f"{class_name:<60} {stats['count']:<12,} {size_mb:<15.2f} {avg_size_kb:<15.2f}\n")
            f.write(f"\n基本类型数组统计:\n")
            f.write("-" * 30 + "\n")
            f.write(f" {'数组类型':<20} {'数组数量':<12} {'总大小(MB)':<15} {'平均大小(KB)':<15}")
            f.write("-" * 70 + "\n")
            sorted_primitives = sorted(self.primitive_stats.items(), 
                                     key=lambda x: x[1]['size'], reverse=True)
            for array_type, stats in sorted_primitives:
                size_mb = stats['size'] / 1024 / 1024
                avg_size_kb = stats['size'] / stats['count'] / 1024 if stats['count'] > 0 else 0
                f.write(f"{array_type:<20} {stats['count']:<12,} {size_mb:<15.2f} {avg_size_kb:<15.2f}\n")
            f.write(f"\n字符串统计:\n")
            f.write("-" * 30 + "\n")
            f.write(f"字符串实例数: {self.string_stats['count']:,}\n")
            f.write(f"字符串总大小: {self.string_stats['size'] / 1024 / 1024:.2f} MB\n")
            if self.string_stats['count'] > 0:
                avg_size = self.string_stats['size'] / self.string_stats['count']
                f.write(f"平均字符串大小: {avg_size:.2f} bytes\n")

if __name__ == '__main__':
    arg_parser = argparse.ArgumentParser(description="Android HPROF内存分析工具")
    arg_parser.add_argument('-f', '--file', required=True, help="HPROF文件路径")
    arg_parser.add_argument('-o', '--output', help="分析结果输出文件")
    arg_parser.add_argument('-t', '--top', type=int, default=20, help="显示TOP N个内存占用类 (默认20)")
    arg_parser.add_argument('-m', '--min-size', type=float, default=0.1, help="最小显示大小(MB) (默认0.1)")
    arg_parser.add_argument('-s', '--simple', action='store_true', help="简单输出模式")
    args = arg_parser.parse_args()
    parser = HprofParser(args.file)
    parser.parse(args.simple, args.top, args.min_size, args.output)
