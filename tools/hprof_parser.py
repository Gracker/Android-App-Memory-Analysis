
import sys
import os
from datetime import datetime
from collections import defaultdict, deque
import argparse
import struct

class HprofParser:
    """
    Enhanced HPROF Parser with:
    - GC Root analysis
    - Reference graph building
    - Dominator tree calculation
    - Retained size computation
    - Memory leak detection
    - String/Bitmap/Collection analysis
    """

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

        # Phase 1: Enhanced data structures
        self.gc_roots = {}  # object_id -> {'type': root_type, 'thread_serial': ..., 'frame_num': ...}
        self.gc_root_types = defaultdict(list)  # root_type -> [object_ids]

        # Class field definitions: class_id -> {'fields': [(name_id, type), ...], 'super_class_id': id, 'instance_size': size}
        self.class_fields = {}

        # Instance data: object_id -> {'class_id': id, 'fields_data': bytes, 'size': size}
        self.instances = {}

        # Object arrays: array_id -> {'class_id': id, 'elements': [object_ids], 'size': size}
        self.object_arrays = {}

        # Primitive arrays: array_id -> {'type': type, 'length': len, 'data': bytes, 'size': size}
        self.primitive_arrays = {}

        # Phase 2: Reference graphs
        self.outgoing_refs = defaultdict(set)  # object_id -> set of referenced object_ids
        self.incoming_refs = defaultdict(set)  # object_id -> set of referencing object_ids

        # Phase 3: Dominator tree and retained size
        self.dominators = {}  # object_id -> immediate dominator id
        self.dominated_by = defaultdict(set)  # object_id -> set of objects it dominates
        self.retained_sizes = {}  # object_id -> retained size
        self.shallow_sizes = {}  # object_id -> shallow size

        # Phase 4: Leak detection
        self.leak_suspects = []

        # Phase 5: Advanced analysis
        self.string_contents = {}  # string_object_id -> actual string content
        self.duplicate_strings = defaultdict(list)  # string_content -> [object_ids]
        self.bitmap_info = {}  # bitmap_id -> {'width': w, 'height': h, 'size': size}

        # GC Root type names
        self.GC_ROOT_NAMES = {
            0xFF: 'UNKNOWN',
            0x01: 'JNI_GLOBAL',
            0x02: 'JNI_LOCAL',
            0x03: 'JAVA_FRAME',
            0x04: 'NATIVE_STACK',
            0x05: 'STICKY_CLASS',
            0x06: 'THREAD_BLOCK',
            0x07: 'MONITOR_USED',
            0x08: 'THREAD_OBJ',
            0x89: 'INTERNED_STRING',
            0x8a: 'FINALIZING',
            0x8b: 'DEBUGGER',
            0x8c: 'REFERENCE_CLEANUP',
            0x8d: 'VM_INTERNAL',
            0x8e: 'JNI_MONITOR',
            0x90: 'UNREACHABLE',
        }

        self.notes = {
            'java.lang': 'Java核心包，包含Object, String, Integer等。',
            'java.util': 'Java工具包，包含集合框架。关注HashMap, ArrayList等。',
            'byte[]': '字节数组，用于图片、网络数据等。',
            'java.lang.String': '字符串类。过多可能存在重复创建问题。',
        }

        # HPROF Tags
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

        # Heap Dump Sub-record Tags
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

        # Type constants
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

    # ==================== Phase 1: Enhanced Data Collection ====================

    def parse(self, simple_mode=False, top_n=20, min_size_mb=0.1, output_file=None, deep_analysis=True):
        """Main parsing method with optional deep analysis"""
        try:
            self.openHprof(self.filename)
            self.readHead()
            print("正在解析HPROF记录...")
            self.readRecords()

            if deep_analysis:
                print("正在构建引用图...")
                self.build_reference_graph()
                print("正在计算支配树和Retained Size...")
                self.compute_dominator_tree()
                self.calculate_retained_sizes()
                print("正在检测内存泄漏...")
                self.detect_memory_leaks()
                print("正在分析字符串...")
                self.analyze_strings()
                print("正在分析Bitmap...")
                self.analyze_bitmaps()
                print("正在分析集合类...")
                self.analyze_collections()

            if not simple_mode:
                self.print_gc_root_statistics()
                self.print_package_statistics(top_n)
                self.print_class_statistics(top_n, min_size_mb)
                self.print_primitive_statistics()
                self.print_string_statistics()
                if deep_analysis:
                    self.print_dominator_tree_top(top_n)
                    self.print_leak_suspects()
                    self.print_duplicate_strings()
                    self.print_bitmap_analysis()
                    self.print_collection_analysis()

            if output_file:
                self.export_analysis(output_file, deep_analysis)
            else:
                base_name = os.path.splitext(os.path.basename(self.filename))[0]
                default_output = f"{base_name}_analysis.txt"
                self.export_analysis(default_output, deep_analysis)
                print(f"\n分析结果已导出到: {default_output}")
            return True
        except Exception as e:
            import traceback
            print(f"解析HPROF文件失败: {e}")
            traceback.print_exc()
            return False
        finally:
            if self.hprof:
                self.hprof.close()

    def readRecords(self):
        """Read all HPROF records"""
        file_length = os.path.getsize(self.hprof.name)
        while self.hprof.tell() < file_length:
            tag = self.readInt(1)
            self.readInt(4)  # time
            length = self.readInt(4)
            if tag == self.TAG_STRING:
                self.readString(length)
            elif tag == self.TAG_LOAD_CLASS:
                self.readLoadClass(length)
            elif tag in [self.TAG_HEAP_DUMP, self.TAG_HEAP_DUMP_SEGMENT]:
                self.readHeapDumpInternal(length)
            elif tag in [self.TAG_UNLOAD_CLASS, self.TAG_STACK_FRAME, self.TAG_STACK_TRACE,
                        self.TAG_ALLOC_SITES, self.TAG_HEAP_SUMMARY, self.TAG_START_THREAD,
                        self.TAG_END_THREAD, self.TAG_HEAP_DUMP_END, self.TAG_CPU_SAMPLES,
                        self.TAG_CONTROL_SETTINGS]:
                self.seek(length)
            else:
                raise Exception('Not supported tag: %d, position: %d' % (tag, self.hprof.tell()))

    def readHead(self):
        """Read HPROF file header"""
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
        """Read UTF8 string record"""
        string_id = self.readId()
        self.strings[string_id] = self.read(length - self.size_of_identifier).decode('utf-8', 'ignore')

    def readLoadClass(self, length):
        """Read class load record"""
        class_serial = self.readInt(4)
        class_id = self.readId()
        stack_trace_serial = self.readInt(4)
        class_name_id = self.readId()
        self.classes[class_id] = {
            'name': self.strings.get(class_name_id, 'unknown'),
            'serial': class_serial
        }

    def readHeapDumpInternal(self, length):
        """Read heap dump segment with GC roots and objects"""
        available = length
        while available > 0:
            start = self.hprof.tell()
            tag = self.readInt(1)
            if not tag:
                break

            # GC Root records - Phase 1.1
            if tag == self.HEAP_TAG_ROOT_UNKNOWN:
                self.readGcRootUnknown()
            elif tag == self.HEAP_TAG_ROOT_JNI_GLOBAL:
                self.readGcRootJniGlobal()
            elif tag == self.HEAP_TAG_ROOT_JNI_LOCAL:
                self.readGcRootJniLocal()
            elif tag == self.HEAP_TAG_ROOT_JAVA_FRAME:
                self.readGcRootJavaFrame()
            elif tag == self.HEAP_TAG_ROOT_NATIVE_STACK:
                self.readGcRootNativeStack()
            elif tag == self.HEAP_TAG_ROOT_STICKY_CLASS:
                self.readGcRootStickyClass()
            elif tag == self.HEAP_TAG_ROOT_THREAD_BLOCK:
                self.readGcRootThreadBlock()
            elif tag == self.HEAP_TAG_ROOT_MONITOR_USED:
                self.readGcRootMonitorUsed()
            elif tag == self.HEAP_TAG_ROOT_THREAD_OBJECT:
                self.readGcRootThreadObject()
            elif tag == self.HEAP_TAG_ROOT_INTERNED_STRING:
                self.readGcRootInternedString()
            elif tag == self.HEAP_TAG_ROOT_FINALIZING:
                self.readGcRootFinalizing()
            elif tag == self.HEAP_TAG_ROOT_DEBUGGER:
                self.readGcRootDebugger()
            elif tag == self.HEAP_TAG_ROOT_REFERENCE_CLEANUP:
                self.readGcRootReferenceCleanup()
            elif tag == self.HEAP_TAG_ROOT_VM_INTERNAL:
                self.readGcRootVmInternal()
            elif tag == self.HEAP_TAG_ROOT_JNI_MONITOR:
                self.readGcRootJniMonitor()
            elif tag == self.HEAP_TAG_ROOT_UNREACHABLE:
                self.readGcRootUnreachable()
            # Object records
            elif tag == self.HEAP_TAG_CLASS_DUMP:
                self.readClassDump()
            elif tag == self.HEAP_TAG_INSTANCE_DUMP:
                self.readInstanceDump()
            elif tag == self.HEAP_TAG_OBJECT_ARRAY_DUMP:
                self.readObjectArrayDump()
            elif tag == self.HEAP_TAG_PRIMITIVE_ARRAY_DUMP:
                self.readPrimitiveArrayDump()
            elif tag == self.HEAP_TAG_HEAP_DUMP_INFO:
                self.seek(4 + self.size_of_identifier)
            elif tag == self.HEAP_TAG_PRIMITIVE_ARRAY_NODATA:
                self.readPrimitiveArrayNoData()
            else:
                # Unknown tag, try to skip based on known patterns
                self.seek(self.get_heap_subrecord_length(tag))

            end = self.hprof.tell()
            available -= end - start

    # ==================== GC Root Parsing Methods (Phase 1.1) ====================

    def readGcRootUnknown(self):
        """ROOT_UNKNOWN: id"""
        obj_id = self.readId()
        self.add_gc_root(obj_id, self.HEAP_TAG_ROOT_UNKNOWN)

    def readGcRootJniGlobal(self):
        """ROOT_JNI_GLOBAL: id, jni_global_ref_id"""
        obj_id = self.readId()
        jni_ref_id = self.readId()
        self.add_gc_root(obj_id, self.HEAP_TAG_ROOT_JNI_GLOBAL, jni_ref_id=jni_ref_id)

    def readGcRootJniLocal(self):
        """ROOT_JNI_LOCAL: id, thread_serial, frame_num"""
        obj_id = self.readId()
        thread_serial = self.readInt(4)
        frame_num = self.readInt(4)
        self.add_gc_root(obj_id, self.HEAP_TAG_ROOT_JNI_LOCAL,
                        thread_serial=thread_serial, frame_num=frame_num)

    def readGcRootJavaFrame(self):
        """ROOT_JAVA_FRAME: id, thread_serial, frame_num"""
        obj_id = self.readId()
        thread_serial = self.readInt(4)
        frame_num = self.readInt(4)
        self.add_gc_root(obj_id, self.HEAP_TAG_ROOT_JAVA_FRAME,
                        thread_serial=thread_serial, frame_num=frame_num)

    def readGcRootNativeStack(self):
        """ROOT_NATIVE_STACK: id, thread_serial"""
        obj_id = self.readId()
        thread_serial = self.readInt(4)
        self.add_gc_root(obj_id, self.HEAP_TAG_ROOT_NATIVE_STACK, thread_serial=thread_serial)

    def readGcRootStickyClass(self):
        """ROOT_STICKY_CLASS: id"""
        obj_id = self.readId()
        self.add_gc_root(obj_id, self.HEAP_TAG_ROOT_STICKY_CLASS)

    def readGcRootThreadBlock(self):
        """ROOT_THREAD_BLOCK: id, thread_serial"""
        obj_id = self.readId()
        thread_serial = self.readInt(4)
        self.add_gc_root(obj_id, self.HEAP_TAG_ROOT_THREAD_BLOCK, thread_serial=thread_serial)

    def readGcRootMonitorUsed(self):
        """ROOT_MONITOR_USED: id"""
        obj_id = self.readId()
        self.add_gc_root(obj_id, self.HEAP_TAG_ROOT_MONITOR_USED)

    def readGcRootThreadObject(self):
        """ROOT_THREAD_OBJ: id, thread_serial, stack_trace_serial"""
        obj_id = self.readId()
        thread_serial = self.readInt(4)
        stack_trace_serial = self.readInt(4)
        self.add_gc_root(obj_id, self.HEAP_TAG_ROOT_THREAD_OBJECT,
                        thread_serial=thread_serial, stack_trace_serial=stack_trace_serial)

    def readGcRootInternedString(self):
        """ROOT_INTERNED_STRING: id"""
        obj_id = self.readId()
        self.add_gc_root(obj_id, self.HEAP_TAG_ROOT_INTERNED_STRING)

    def readGcRootFinalizing(self):
        """ROOT_FINALIZING: id"""
        obj_id = self.readId()
        self.add_gc_root(obj_id, self.HEAP_TAG_ROOT_FINALIZING)

    def readGcRootDebugger(self):
        """ROOT_DEBUGGER: id"""
        obj_id = self.readId()
        self.add_gc_root(obj_id, self.HEAP_TAG_ROOT_DEBUGGER)

    def readGcRootReferenceCleanup(self):
        """ROOT_REFERENCE_CLEANUP: id"""
        obj_id = self.readId()
        self.add_gc_root(obj_id, self.HEAP_TAG_ROOT_REFERENCE_CLEANUP)

    def readGcRootVmInternal(self):
        """ROOT_VM_INTERNAL: id"""
        obj_id = self.readId()
        self.add_gc_root(obj_id, self.HEAP_TAG_ROOT_VM_INTERNAL)

    def readGcRootJniMonitor(self):
        """ROOT_JNI_MONITOR: id, thread_serial, frame_num"""
        obj_id = self.readId()
        thread_serial = self.readInt(4)
        frame_num = self.readInt(4)
        self.add_gc_root(obj_id, self.HEAP_TAG_ROOT_JNI_MONITOR,
                        thread_serial=thread_serial, frame_num=frame_num)

    def readGcRootUnreachable(self):
        """ROOT_UNREACHABLE: id"""
        obj_id = self.readId()
        self.add_gc_root(obj_id, self.HEAP_TAG_ROOT_UNREACHABLE)

    def add_gc_root(self, obj_id, root_type, **kwargs):
        """Add a GC root with type information"""
        if obj_id == 0:
            return
        self.gc_roots[obj_id] = {'type': root_type, **kwargs}
        self.gc_root_types[root_type].append(obj_id)

    # ==================== Class and Object Parsing (Phase 1.2, 1.3, 1.4) ====================

    def get_heap_subrecord_length(self, tag):
        """Get length of unknown heap sub-records"""
        if tag in [self.HEAP_TAG_ROOT_UNKNOWN, self.HEAP_TAG_ROOT_STICKY_CLASS,
                   self.HEAP_TAG_ROOT_MONITOR_USED, self.HEAP_TAG_ROOT_INTERNED_STRING,
                   self.HEAP_TAG_ROOT_FINALIZING, self.HEAP_TAG_ROOT_DEBUGGER,
                   self.HEAP_TAG_ROOT_REFERENCE_CLEANUP, self.HEAP_TAG_ROOT_VM_INTERNAL,
                   self.HEAP_TAG_ROOT_UNREACHABLE]:
            return self.size_of_identifier
        elif tag == self.HEAP_TAG_ROOT_JNI_GLOBAL:
            return 2 * self.size_of_identifier
        elif tag in [self.HEAP_TAG_ROOT_JNI_LOCAL, self.HEAP_TAG_ROOT_JAVA_FRAME,
                     self.HEAP_TAG_ROOT_THREAD_OBJECT, self.HEAP_TAG_ROOT_JNI_MONITOR]:
            return self.size_of_identifier + 8
        elif tag == self.HEAP_TAG_ROOT_NATIVE_STACK or tag == self.HEAP_TAG_ROOT_THREAD_BLOCK:
            return self.size_of_identifier + 4
        elif tag == self.HEAP_TAG_HEAP_DUMP_INFO:
            return 4 + self.size_of_identifier
        return 0

    def readClassDump(self):
        """Read class dump with field definitions (Phase 1.2)"""
        class_id = self.readId()
        self.readInt(4)  # stack trace serial
        super_class_id = self.readId()
        class_loader_id = self.readId()
        signers_id = self.readId()
        protection_domain_id = self.readId()
        self.readId()  # reserved
        self.readId()  # reserved
        instance_size = self.readInt(4)

        # Read constant pool
        const_pool = self.readClassConstantFields()

        # Read static fields
        static_fields = self.readClassStaticFieldsWithValues()

        # Read instance field definitions (Phase 1.2)
        instance_fields = self.readInstanceFieldDefinitions()

        # Store class info with field definitions
        if class_id in self.classes:
            self.classes[class_id]['instance_size'] = instance_size
            self.classes[class_id]['super_class_id'] = super_class_id
            self.classes[class_id]['instance_fields'] = instance_fields
            self.classes[class_id]['static_fields'] = static_fields

        self.class_fields[class_id] = {
            'instance_size': instance_size,
            'super_class_id': super_class_id,
            'instance_fields': instance_fields,
            'static_fields': static_fields
        }

    def readClassConstantFields(self):
        """Read class constant pool"""
        count = self.readInt(2)
        constants = []
        for _ in range(count):
            idx = self.readInt(2)
            type_id = self.readInt(1)
            size, _ = self.BASIC_TYPES.get(type_id, (0, ''))
            if size > 0:
                value = self.read(size)
                constants.append((idx, type_id, value))
        return constants

    def readClassStaticFieldsWithValues(self):
        """Read static fields with their values"""
        count = self.readInt(2)
        static_fields = []
        for _ in range(count):
            name_id = self.readId()
            type_id = self.readInt(1)
            size, _ = self.BASIC_TYPES.get(type_id, (0, ''))
            if size > 0:
                value = self.read(size)
                static_fields.append({
                    'name_id': name_id,
                    'type': type_id,
                    'value': value
                })
        return static_fields

    def readInstanceFieldDefinitions(self):
        """Read instance field definitions (Phase 1.2)"""
        count = self.readInt(2)
        fields = []
        for _ in range(count):
            name_id = self.readId()
            type_id = self.readInt(1)
            fields.append({
                'name_id': name_id,
                'type': type_id
            })
        return fields

    def get_all_instance_fields(self, class_id):
        """Get all instance fields including inherited ones"""
        fields = []
        current_class_id = class_id
        while current_class_id != 0 and current_class_id in self.class_fields:
            class_info = self.class_fields[current_class_id]
            fields = class_info.get('instance_fields', []) + fields
            current_class_id = class_info.get('super_class_id', 0)
        return fields

    def readInstanceDump(self):
        """Read instance dump with field values (Phase 1.3)"""
        instance_id = self.readId()
        self.readInt(4)  # stack trace serial
        class_id = self.readId()
        fields_byte_size = self.readInt(4)

        # Read field data instead of skipping
        fields_data = self.read(fields_byte_size)

        self.total_instances += 1
        self.total_instance_size += fields_byte_size

        # Calculate shallow size (object header + fields)
        shallow_size = 8 + fields_byte_size  # 8 bytes for object header
        if self.size_of_identifier == 8:
            shallow_size = 16 + fields_byte_size  # 64-bit header

        # Store instance data
        self.instances[instance_id] = {
            'class_id': class_id,
            'fields_data': fields_data,
            'size': shallow_size
        }
        self.shallow_sizes[instance_id] = shallow_size

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
        """Read object array with elements (Phase 1.4)"""
        array_id = self.readId()
        self.readInt(4)  # stack trace serial
        length = self.readInt(4)
        array_class_id = self.readId()

        # Read element references instead of skipping
        elements = []
        for _ in range(length):
            elem_id = self.readId()
            elements.append(elem_id)

        element_size = self.size_of_identifier * length
        shallow_size = 12 + element_size  # array header + elements
        if self.size_of_identifier == 8:
            shallow_size = 24 + element_size

        self.object_arrays[array_id] = {
            'class_id': array_class_id,
            'elements': elements,
            'length': length,
            'size': shallow_size
        }
        self.shallow_sizes[array_id] = shallow_size

        self.total_arrays += 1
        self.total_array_size += element_size
        class_name = self.classes.get(array_class_id, {}).get('name', 'unknown') + '[]'
        self.class_stats[class_name]['count'] += 1
        self.class_stats[class_name]['size'] += element_size

    def readPrimitiveArrayDump(self):
        """Read primitive array with data"""
        array_id = self.readId()
        self.readInt(4)  # stack trace serial
        length = self.readInt(4)
        type_id = self.readInt(1)
        size, type_name = self.BASIC_TYPES.get(type_id, (0, 'unknown'))

        if size > 0:
            element_size = size * length
            data = self.read(element_size)

            shallow_size = 12 + element_size
            if self.size_of_identifier == 8:
                shallow_size = 24 + element_size

            self.primitive_arrays[array_id] = {
                'type': type_id,
                'type_name': type_name,
                'length': length,
                'data': data,
                'size': shallow_size
            }
            self.shallow_sizes[array_id] = shallow_size

            self.total_arrays += 1
            self.total_array_size += element_size
            self.primitive_stats[f'{type_name}[]']['count'] += 1
            self.primitive_stats[f'{type_name}[]']['size'] += element_size

    def readPrimitiveArrayNoData(self):
        """Read primitive array without data (Android specific)"""
        array_id = self.readId()
        self.readInt(4)  # stack trace serial
        length = self.readInt(4)
        type_id = self.readInt(1)
        size, type_name = self.BASIC_TYPES.get(type_id, (0, 'unknown'))
        if size > 0:
            element_size = size * length
            self.primitive_arrays[array_id] = {
                'type': type_id,
                'type_name': type_name,
                'length': length,
                'data': None,
                'size': element_size
            }
            self.shallow_sizes[array_id] = element_size

    # ==================== Phase 2: Reference Graph Building ====================

    def build_reference_graph(self):
        """Build outgoing and incoming reference graphs (Phase 2.1, 2.2)"""
        # Extract references from instances
        for obj_id, instance in self.instances.items():
            class_id = instance['class_id']
            fields_data = instance['fields_data']
            refs = self.extract_references_from_instance(class_id, fields_data)
            for ref in refs:
                if ref != 0:
                    self.outgoing_refs[obj_id].add(ref)
                    self.incoming_refs[ref].add(obj_id)

        # Extract references from object arrays
        for array_id, array in self.object_arrays.items():
            for elem_id in array['elements']:
                if elem_id != 0:
                    self.outgoing_refs[array_id].add(elem_id)
                    self.incoming_refs[elem_id].add(array_id)

        # Extract references from static fields
        for class_id, class_info in self.class_fields.items():
            for field in class_info.get('static_fields', []):
                if field['type'] == self.TYPE_OBJECT:
                    ref_id = int.from_bytes(field['value'], byteorder='big')
                    if ref_id != 0:
                        self.outgoing_refs[class_id].add(ref_id)
                        self.incoming_refs[ref_id].add(class_id)

    def extract_references_from_instance(self, class_id, fields_data):
        """Extract object references from instance field data"""
        refs = []
        fields = self.get_all_instance_fields(class_id)
        offset = 0

        for field in fields:
            type_id = field['type']
            size, _ = self.BASIC_TYPES.get(type_id, (0, ''))
            if size == 0:
                continue

            if offset + size > len(fields_data):
                break

            if type_id == self.TYPE_OBJECT:
                ref_id = int.from_bytes(fields_data[offset:offset+size], byteorder='big')
                refs.append(ref_id)

            offset += size

        return refs

    def find_path_to_gc_root(self, obj_id, max_depth=50, exclude_weak_refs=True):
        """Find shortest path from object to GC root (Phase 2.3)"""
        if obj_id in self.gc_roots:
            return [obj_id]

        visited = set()
        queue = deque([(obj_id, [obj_id])])

        while queue:
            current_id, path = queue.popleft()

            if len(path) > max_depth:
                continue

            if current_id in visited:
                continue
            visited.add(current_id)

            # Check if current is a GC root
            if current_id in self.gc_roots:
                return path

            # Check incoming references
            for ref_id in self.incoming_refs.get(current_id, []):
                if ref_id not in visited:
                    # Skip weak/soft references if requested
                    if exclude_weak_refs:
                        ref_class_id = self.instances.get(ref_id, {}).get('class_id')
                        if ref_class_id:
                            class_name = self.classes.get(ref_class_id, {}).get('name', '')
                            if 'WeakReference' in class_name or 'SoftReference' in class_name:
                                continue
                    queue.append((ref_id, path + [ref_id]))

        return None  # No path found

    # ==================== Phase 3: Dominator Tree and Retained Size ====================

    def compute_dominator_tree(self):
        """Compute dominator tree using simplified algorithm (Phase 3.1, 3.2)"""
        # Create a virtual super root that connects all GC roots
        SUPER_ROOT = -1

        # Find all reachable objects from GC roots
        reachable = set()
        queue = deque(self.gc_roots.keys())

        while queue:
            obj_id = queue.popleft()
            if obj_id in reachable:
                continue
            reachable.add(obj_id)
            for ref in self.outgoing_refs.get(obj_id, []):
                if ref not in reachable:
                    queue.append(ref)

        # For GC roots, the dominator is the super root
        for root_id in self.gc_roots:
            self.dominators[root_id] = SUPER_ROOT

        # Simple dominator calculation for non-root objects
        # For each reachable object, find common dominator of all incoming refs
        changed = True
        iterations = 0
        max_iterations = 10  # Limit iterations for performance

        while changed and iterations < max_iterations:
            changed = False
            iterations += 1

            for obj_id in reachable:
                if obj_id in self.gc_roots:
                    continue

                incoming = [ref for ref in self.incoming_refs.get(obj_id, []) if ref in reachable]
                if not incoming:
                    continue

                # Find common dominator of all incoming references
                new_dom = None
                for ref in incoming:
                    if ref in self.dominators or ref in self.gc_roots:
                        if new_dom is None:
                            new_dom = ref
                        else:
                            # Find common ancestor
                            new_dom = self.find_common_dominator(new_dom, ref)

                if new_dom is not None and self.dominators.get(obj_id) != new_dom:
                    self.dominators[obj_id] = new_dom
                    changed = True

        # Build dominated_by map
        for obj_id, dom_id in self.dominators.items():
            if dom_id != SUPER_ROOT:
                self.dominated_by[dom_id].add(obj_id)

    def find_common_dominator(self, a, b):
        """Find common dominator of two objects"""
        SUPER_ROOT = -1
        path_a = set()
        current = a
        while current != SUPER_ROOT and current is not None:
            path_a.add(current)
            current = self.dominators.get(current)

        current = b
        while current != SUPER_ROOT and current is not None:
            if current in path_a:
                return current
            current = self.dominators.get(current)

        return a  # Fallback

    def calculate_retained_sizes(self):
        """Calculate retained size for each object (Phase 3.3)"""
        # Post-order traversal of dominator tree
        visited = set()

        def compute_retained(obj_id):
            if obj_id in visited:
                return self.retained_sizes.get(obj_id, 0)
            visited.add(obj_id)

            # Start with shallow size
            retained = self.shallow_sizes.get(obj_id, 0)

            # Add retained sizes of all dominated objects
            for dominated_id in self.dominated_by.get(obj_id, []):
                retained += compute_retained(dominated_id)

            self.retained_sizes[obj_id] = retained
            return retained

        # Compute for all objects
        for obj_id in self.shallow_sizes:
            if obj_id not in visited:
                compute_retained(obj_id)

    # ==================== Phase 4: Memory Leak Detection ====================

    def detect_memory_leaks(self):
        """Detect potential memory leaks (Phase 4.1, 4.2, 4.3)"""
        self.leak_suspects = []

        # Phase 4.1: Detect duplicate Activity/Fragment instances
        self.detect_duplicate_instances()

        # Phase 4.2: Detect accumulation points
        self.detect_accumulation_points()

        # Sort by severity (retained size)
        self.leak_suspects.sort(key=lambda x: x.get('retained_size', 0), reverse=True)

    def detect_duplicate_instances(self):
        """Detect multiple instances of Activity/Fragment (Phase 4.1)"""
        # Count instances by class
        class_instances = defaultdict(list)
        for obj_id, instance in self.instances.items():
            class_id = instance['class_id']
            class_name = self.classes.get(class_id, {}).get('name', '')
            class_instances[class_name].append(obj_id)

        # Check for suspicious duplicates
        suspicious_classes = ['Activity', 'Fragment', 'Service', 'BroadcastReceiver']

        for class_name, obj_ids in class_instances.items():
            for suspicious in suspicious_classes:
                if suspicious in class_name and len(obj_ids) > 1:
                    # Check if they're reachable
                    reachable_count = sum(1 for oid in obj_ids if oid in self.dominators or oid in self.gc_roots)
                    if reachable_count > 1:
                        total_retained = sum(self.retained_sizes.get(oid, 0) for oid in obj_ids)
                        self.leak_suspects.append({
                            'type': 'DUPLICATE_INSTANCE',
                            'class_name': class_name,
                            'count': len(obj_ids),
                            'reachable_count': reachable_count,
                            'object_ids': obj_ids,
                            'retained_size': total_retained,
                            'description': f"检测到 {reachable_count} 个 {class_name} 实例（应该只有1个）"
                        })

    def detect_accumulation_points(self):
        """Detect memory accumulation points (Phase 4.2)"""
        # Find objects with large retained/shallow ratio
        for obj_id in self.retained_sizes:
            retained = self.retained_sizes.get(obj_id, 0)
            shallow = self.shallow_sizes.get(obj_id, 0)

            if shallow == 0:
                continue

            ratio = retained / shallow

            # Large retained size with high ratio indicates accumulation
            if retained > 1024 * 1024 and ratio > 10:  # > 1MB and ratio > 10
                class_id = self.instances.get(obj_id, {}).get('class_id')
                if not class_id:
                    array_info = self.object_arrays.get(obj_id)
                    if array_info:
                        class_id = array_info.get('class_id')

                class_name = self.classes.get(class_id, {}).get('name', 'unknown') if class_id else 'unknown'

                # Check if dominated objects are mostly same type
                dominated = self.dominated_by.get(obj_id, set())

                self.leak_suspects.append({
                    'type': 'ACCUMULATION_POINT',
                    'class_name': class_name,
                    'object_id': obj_id,
                    'shallow_size': shallow,
                    'retained_size': retained,
                    'ratio': ratio,
                    'dominated_count': len(dominated),
                    'description': f"{class_name} 持有 {retained/1024/1024:.2f}MB 内存（{len(dominated)}个对象）"
                })

    # ==================== Phase 5: Advanced Analysis ====================

    def analyze_strings(self):
        """Analyze string contents for duplicates (Phase 5.1)"""
        # Find String class
        string_class_id = None
        for class_id, class_info in self.classes.items():
            if class_info.get('name') == 'java.lang.String':
                string_class_id = class_id
                break

        if not string_class_id:
            return

        # Find char[] or byte[] arrays referenced by strings
        char_array_class_id = None
        for class_id, class_info in self.classes.items():
            if class_info.get('name') == 'char[]' or class_info.get('name') == '[C':
                char_array_class_id = class_id
                break

        # Analyze each string instance
        for obj_id, instance in self.instances.items():
            if instance['class_id'] != string_class_id:
                continue

            # Try to find the value array reference
            refs = list(self.outgoing_refs.get(obj_id, []))
            for ref in refs:
                if ref in self.primitive_arrays:
                    array = self.primitive_arrays[ref]
                    if array['type'] == self.TYPE_CHAR and array.get('data'):
                        try:
                            # Decode char array to string
                            content = array['data'].decode('utf-16-be', errors='ignore')
                            if len(content) > 0 and len(content) < 1000:  # Reasonable string length
                                self.string_contents[obj_id] = content
                                self.duplicate_strings[content].append(obj_id)
                        except:
                            pass
                    elif array['type'] == self.TYPE_BYTE and array.get('data'):
                        try:
                            content = array['data'].decode('utf-8', errors='ignore')
                            if len(content) > 0 and len(content) < 1000:
                                self.string_contents[obj_id] = content
                                self.duplicate_strings[content].append(obj_id)
                        except:
                            pass

    def analyze_bitmaps(self):
        """Analyze Bitmap objects for memory usage (Phase 5.2)"""
        # Find Bitmap class
        bitmap_class_id = None
        for class_id, class_info in self.classes.items():
            if class_info.get('name') == 'android.graphics.Bitmap':
                bitmap_class_id = class_id
                break

        if not bitmap_class_id:
            return

        # Get field definitions for Bitmap class
        bitmap_fields = self.get_all_instance_fields(bitmap_class_id)

        # Build field name to index mapping
        field_offsets = {}
        offset = 0
        for i, field in enumerate(bitmap_fields):
            type_id = field['type']
            size, _ = self.BASIC_TYPES.get(type_id, (0, ''))
            if size == 0:
                continue
            name_id = field.get('name_id')
            if name_id and name_id in self.strings:
                field_name = self.strings[name_id]
                field_offsets[field_name] = (offset, type_id, size)
            offset += size

        # Analyze each Bitmap instance
        for obj_id, instance in self.instances.items():
            if instance['class_id'] != bitmap_class_id:
                continue

            fields_data = instance['fields_data']
            width = 0
            height = 0

            # Extract mWidth
            if 'mWidth' in field_offsets:
                off, type_id, size = field_offsets['mWidth']
                if off + size <= len(fields_data) and type_id == self.TYPE_INT:
                    width = int.from_bytes(fields_data[off:off+size], byteorder='big', signed=True)

            # Extract mHeight
            if 'mHeight' in field_offsets:
                off, type_id, size = field_offsets['mHeight']
                if off + size <= len(fields_data) and type_id == self.TYPE_INT:
                    height = int.from_bytes(fields_data[off:off+size], byteorder='big', signed=True)

            # Sanity check - valid bitmap dimensions
            if width > 0 and height > 0 and width < 10000 and height < 10000:
                # Assume ARGB_8888 format (4 bytes per pixel)
                estimated_size = width * height * 4
                self.bitmap_info[obj_id] = {
                    'width': width,
                    'height': height,
                    'estimated_size': estimated_size
                }

    def analyze_collections(self):
        """Analyze collection classes for capacity issues (Phase 5.3)"""
        self.collection_analysis = []

        # Find HashMap and ArrayList classes
        collection_classes = {}
        for class_id, class_info in self.classes.items():
            name = class_info.get('name', '')
            if name in ['java.util.HashMap', 'java.util.ArrayList',
                       'java.util.HashSet', 'java.util.LinkedList',
                       'java.util.concurrent.ConcurrentHashMap']:
                collection_classes[class_id] = name

        for obj_id, instance in self.instances.items():
            class_id = instance['class_id']
            if class_id not in collection_classes:
                continue

            class_name = collection_classes[class_id]
            fields_data = instance['fields_data']
            fields = self.get_all_instance_fields(class_id)

            # Build field offsets
            field_offsets = {}
            offset = 0
            for field in fields:
                type_id = field['type']
                field_size, _ = self.BASIC_TYPES.get(type_id, (0, ''))
                if field_size == 0:
                    continue
                name_id = field.get('name_id')
                if name_id and name_id in self.strings:
                    field_name = self.strings[name_id]
                    field_offsets[field_name] = (offset, type_id, field_size)
                offset += field_size

            size = 0
            capacity = 0

            # Extract size field
            if 'size' in field_offsets:
                off, type_id, field_size = field_offsets['size']
                if off + field_size <= len(fields_data) and type_id == self.TYPE_INT:
                    size = int.from_bytes(fields_data[off:off+field_size], byteorder='big', signed=True)

            # Extract threshold for HashMap (capacity = threshold / 0.75)
            if 'threshold' in field_offsets:
                off, type_id, field_size = field_offsets['threshold']
                if off + field_size <= len(fields_data) and type_id == self.TYPE_INT:
                    threshold = int.from_bytes(fields_data[off:off+field_size], byteorder='big', signed=True)
                    if threshold > 0 and threshold < 10000000:  # Sanity check
                        capacity = int(threshold / 0.75)

            # Check for over-allocated collections with reasonable values
            if capacity > 0 and size >= 0 and capacity < 10000000 and size < capacity:
                utilization = size / capacity if capacity > 0 else 0
                wasted_slots = capacity - size
                if wasted_slots > 100 and utilization < 0.5:
                    self.collection_analysis.append({
                        'object_id': obj_id,
                        'class_name': class_name,
                        'size': size,
                        'capacity': capacity,
                        'utilization': utilization,
                        'wasted_slots': wasted_slots
                    })

        # Sort by wasted slots
        self.collection_analysis.sort(key=lambda x: x['wasted_slots'], reverse=True)

    def print_bitmap_analysis(self, top_n=10):
        """Print Bitmap analysis results"""
        if not self.bitmap_info:
            return

        print(f"\n=== Bitmap 分析 TOP {top_n} ===")
        print(f"{'尺寸':<20} {'估算内存':<15} {'对象ID'}")
        print("-" * 50)

        sorted_bitmaps = sorted(self.bitmap_info.items(),
                               key=lambda x: x[1]['estimated_size'], reverse=True)

        for obj_id, info in sorted_bitmaps[:top_n]:
            size_str = f"{info['width']}x{info['height']}"
            mem_str = f"{info['estimated_size']/1024/1024:.2f} MB"
            print(f"{size_str:<20} {mem_str:<15} 0x{obj_id:x}")

    def print_collection_analysis(self, top_n=10):
        """Print collection analysis results"""
        if not hasattr(self, 'collection_analysis') or not self.collection_analysis:
            return

        print(f"\n=== 集合类容量分析 TOP {top_n} ===")
        print(f"{'类名':<35} {'大小':<10} {'容量':<10} {'利用率':<10} {'浪费槽位'}")
        print("-" * 80)

        for item in self.collection_analysis[:top_n]:
            print(f"{item['class_name']:<35} {item['size']:<10} {item['capacity']:<10} "
                  f"{item['utilization']*100:.1f}%     {item['wasted_slots']}")

    # ==================== Output Methods ====================

    def print_gc_root_statistics(self):
        """Print GC root statistics"""
        print(f"\n=== GC Root 统计 ===")
        print(f"{'类型':<25} {'数量':<10}")
        print("-" * 40)

        for root_type, obj_ids in sorted(self.gc_root_types.items(),
                                         key=lambda x: len(x[1]), reverse=True):
            type_name = self.GC_ROOT_NAMES.get(root_type, f'UNKNOWN_{root_type}')
            print(f"{type_name:<25} {len(obj_ids):<10,}")

        print(f"\n总计 GC Root: {len(self.gc_roots):,}")

    def print_dominator_tree_top(self, top_n=20):
        """Print top objects by retained size"""
        print(f"\n=== TOP {top_n} Retained Size ===")
        print(f"{'类名':<50} {'Shallow(KB)':<12} {'Retained(MB)':<12} {'支配对象数'}")
        print("-" * 90)

        sorted_objects = sorted(self.retained_sizes.items(),
                               key=lambda x: x[1], reverse=True)[:top_n]

        for obj_id, retained in sorted_objects:
            shallow = self.shallow_sizes.get(obj_id, 0)
            dominated_count = len(self.dominated_by.get(obj_id, []))

            # Get class name
            class_name = 'unknown'
            if obj_id in self.instances:
                class_id = self.instances[obj_id]['class_id']
                class_name = self.classes.get(class_id, {}).get('name', 'unknown')
            elif obj_id in self.object_arrays:
                class_id = self.object_arrays[obj_id]['class_id']
                class_name = self.classes.get(class_id, {}).get('name', 'unknown') + '[]'
            elif obj_id in self.primitive_arrays:
                type_name = self.primitive_arrays[obj_id].get('type_name', 'unknown')
                class_name = f'{type_name}[]'

            print(f"{class_name:<50} {shallow/1024:<12.2f} {retained/1024/1024:<12.2f} {dominated_count}")

    def print_leak_suspects(self):
        """Print memory leak suspects"""
        if not self.leak_suspects:
            print("\n=== 内存泄漏检测 ===")
            print("未检测到明显的内存泄漏嫌疑")
            return

        print(f"\n=== 内存泄漏嫌疑 ({len(self.leak_suspects)} 个) ===")
        print("-" * 80)

        for i, suspect in enumerate(self.leak_suspects[:10], 1):
            print(f"\n[{i}] {suspect['type']}")
            print(f"    {suspect['description']}")
            if suspect['type'] == 'DUPLICATE_INSTANCE':
                print(f"    类名: {suspect['class_name']}")
                print(f"    实例数: {suspect['count']} (可达: {suspect['reachable_count']})")
            elif suspect['type'] == 'ACCUMULATION_POINT':
                print(f"    Shallow: {suspect['shallow_size']/1024:.2f} KB")
                print(f"    Retained: {suspect['retained_size']/1024/1024:.2f} MB")

    def print_duplicate_strings(self, top_n=10):
        """Print duplicate strings analysis"""
        duplicates = [(content, ids) for content, ids in self.duplicate_strings.items()
                     if len(ids) > 1 and len(content) > 0]

        if not duplicates:
            return

        # Sort by wasted memory (count-1) * size
        duplicates.sort(key=lambda x: (len(x[1])-1) * len(x[0]) * 2, reverse=True)

        print(f"\n=== 重复字符串 TOP {top_n} ===")
        print(f"{'字符串内容':<40} {'重复次数':<10} {'浪费内存':<12}")
        print("-" * 70)

        for content, ids in duplicates[:top_n]:
            wasted = (len(ids) - 1) * len(content) * 2  # char = 2 bytes
            display_content = content[:37] + '...' if len(content) > 40 else content
            display_content = display_content.replace('\n', '\\n').replace('\r', '\\r')
            print(f"{display_content:<40} {len(ids):<10} {wasted/1024:.2f} KB")

    def print_package_statistics(self, top_n=20):
        """Print memory usage by package"""
        print(f"\n=== TOP {top_n} 内存占用包 ===")
        print(f"{'包名':<50} {'实例数':<10} {'总大小(MB)':<12}")
        print("-" * 80)
        sorted_packages = sorted(self.package_stats.items(),
                               key=lambda x: x[1]['size'], reverse=True)
        count = 0
        for package_name, stats in sorted_packages:
            size_mb = stats['size'] / 1024 / 1024
            print(f"{package_name:<50} {stats['count']:<10,} {size_mb:<12.2f}")
            count += 1
            if count >= top_n:
                break

    def print_class_statistics(self, top_n=20, min_size_mb=0.1):
        """Print memory usage by class"""
        print(f"\n=== TOP {top_n} 内存占用类 (最小 {min_size_mb}MB) ===")
        print(f"{'类名':<50} {'实例数':<10} {'总大小(MB)':<12} {'平均大小(KB)':<12}")
        print("-" * 100)
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
        """Print primitive array statistics"""
        print(f"\n=== TOP {top_n} 基本类型数组内存占用 ===")
        print(f"{'数组类型':<20} {'数组数量':<10} {'总大小(MB)':<12} {'平均大小(KB)':<12}")
        print("-" * 70)
        sorted_primitives = sorted(self.primitive_stats.items(),
                                 key=lambda x: x[1]['size'], reverse=True)
        for i, (array_type, stats) in enumerate(sorted_primitives[:top_n]):
            size_mb = stats['size'] / 1024 / 1024
            avg_size_kb = stats['size'] / stats['count'] / 1024 if stats['count'] > 0 else 0
            print(f"{array_type:<20} {stats['count']:<10,} {size_mb:<12.2f} {avg_size_kb:<12.2f}")

    def print_string_statistics(self):
        """Print string memory statistics"""
        print(f"\n=== 字符串内存统计 ===")
        print(f"字符串实例数: {self.string_stats['count']:,}")
        print(f"字符串总大小: {self.string_stats['size'] / 1024 / 1024:.2f} MB")
        if self.string_stats['count'] > 0:
            avg_size = self.string_stats['size'] / self.string_stats['count']
            print(f"平均字符串大小: {avg_size:.2f} bytes")

    def export_analysis(self, output_file, deep_analysis=True):
        """Export analysis results to file"""
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("Android HPROF 深度内存分析报告\n")
            f.write("=" * 60 + "\n\n")
            f.write(f"分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"HPROF文件: {self.filename}\n\n")

            # GC Root Statistics
            f.write("GC Root 统计:\n")
            f.write("-" * 40 + "\n")
            for root_type, obj_ids in sorted(self.gc_root_types.items(),
                                             key=lambda x: len(x[1]), reverse=True):
                type_name = self.GC_ROOT_NAMES.get(root_type, f'UNKNOWN_{root_type}')
                f.write(f"{type_name:<25} {len(obj_ids):,}\n")
            f.write(f"\n总计 GC Root: {len(self.gc_roots):,}\n\n")

            # Overall Statistics
            f.write("总体内存统计:\n")
            f.write("-" * 40 + "\n")
            f.write(f"总实例数: {self.total_instances:,}\n")
            f.write(f"实例总大小: {self.total_instance_size / 1024 / 1024:.2f} MB\n")
            f.write(f"总数组数: {self.total_arrays:,}\n")
            f.write(f"数组总大小: {self.total_array_size / 1024 / 1024:.2f} MB\n")
            f.write(f"总内存使用: {(self.total_instance_size + self.total_array_size) / 1024 / 1024:.2f} MB\n\n")

            if deep_analysis:
                # Dominator Tree Top
                f.write("TOP 30 Retained Size:\n")
                f.write("-" * 40 + "\n")
                f.write(f"{'类名':<50} {'Shallow(KB)':<12} {'Retained(MB)':<12}\n")

                sorted_objects = sorted(self.retained_sizes.items(),
                                       key=lambda x: x[1], reverse=True)[:30]
                for obj_id, retained in sorted_objects:
                    shallow = self.shallow_sizes.get(obj_id, 0)
                    class_name = 'unknown'
                    if obj_id in self.instances:
                        class_id = self.instances[obj_id]['class_id']
                        class_name = self.classes.get(class_id, {}).get('name', 'unknown')
                    elif obj_id in self.object_arrays:
                        class_id = self.object_arrays[obj_id]['class_id']
                        class_name = self.classes.get(class_id, {}).get('name', 'unknown') + '[]'
                    elif obj_id in self.primitive_arrays:
                        type_name = self.primitive_arrays[obj_id].get('type_name', 'unknown')
                        class_name = f'{type_name}[]'
                    f.write(f"{class_name:<50} {shallow/1024:<12.2f} {retained/1024/1024:<12.2f}\n")
                f.write("\n")

                # Leak Suspects
                if self.leak_suspects:
                    f.write(f"内存泄漏嫌疑 ({len(self.leak_suspects)} 个):\n")
                    f.write("-" * 40 + "\n")
                    for i, suspect in enumerate(self.leak_suspects[:20], 1):
                        f.write(f"\n[{i}] {suspect['type']}\n")
                        f.write(f"    {suspect['description']}\n")
                        if 'retained_size' in suspect:
                            f.write(f"    Retained: {suspect['retained_size']/1024/1024:.2f} MB\n")
                    f.write("\n")

                # Duplicate Strings
                duplicates = [(c, ids) for c, ids in self.duplicate_strings.items()
                             if len(ids) > 1 and len(c) > 0]
                if duplicates:
                    duplicates.sort(key=lambda x: (len(x[1])-1) * len(x[0]) * 2, reverse=True)
                    f.write("重复字符串 TOP 20:\n")
                    f.write("-" * 40 + "\n")
                    for content, ids in duplicates[:20]:
                        wasted = (len(ids) - 1) * len(content) * 2
                        display = content[:50].replace('\n', '\\n').replace('\r', '\\r')
                        f.write(f"'{display}' x{len(ids)} = {wasted/1024:.2f} KB wasted\n")
                    f.write("\n")

                # Bitmap Analysis
                if self.bitmap_info:
                    f.write("Bitmap 分析 TOP 20:\n")
                    f.write("-" * 40 + "\n")
                    sorted_bitmaps = sorted(self.bitmap_info.items(),
                                           key=lambda x: x[1]['estimated_size'], reverse=True)
                    for obj_id, info in sorted_bitmaps[:20]:
                        size_str = f"{info['width']}x{info['height']}"
                        mem_mb = info['estimated_size']/1024/1024
                        f.write(f"{size_str:<20} {mem_mb:.2f} MB\n")
                    f.write("\n")

                # Collection Analysis
                if hasattr(self, 'collection_analysis') and self.collection_analysis:
                    f.write("集合类容量分析 TOP 20:\n")
                    f.write("-" * 40 + "\n")
                    for item in self.collection_analysis[:20]:
                        f.write(f"{item['class_name']:<35} size={item['size']} "
                               f"capacity={item['capacity']} utilization={item['utilization']*100:.1f}%\n")
                    f.write("\n")

            # Package Statistics
            f.write("TOP 30 内存占用包:\n")
            f.write("-" * 40 + "\n")
            sorted_packages = sorted(self.package_stats.items(),
                               key=lambda x: x[1]['size'], reverse=True)
            for package_name, stats in sorted_packages[:30]:
                size_mb = stats['size'] / 1024 / 1024
                if size_mb < 0.1:
                    continue
                f.write(f"{package_name:<50} {stats['count']:<10,} {size_mb:.2f} MB\n")
            f.write("\n")

            # Class Statistics
            f.write("TOP 50 内存占用类:\n")
            f.write("-" * 40 + "\n")
            sorted_classes = sorted(self.class_stats.items(),
                                  key=lambda x: x[1]['size'], reverse=True)
            for class_name, stats in sorted_classes[:50]:
                size_mb = stats['size'] / 1024 / 1024
                avg_size_kb = stats['size'] / stats['count'] / 1024 if stats['count'] > 0 else 0
                f.write(f"{class_name:<60} {stats['count']:<12,} {size_mb:.2f} MB\n")
            f.write("\n")

            # Primitive Array Statistics
            f.write("基本类型数组统计:\n")
            f.write("-" * 40 + "\n")
            sorted_primitives = sorted(self.primitive_stats.items(),
                                     key=lambda x: x[1]['size'], reverse=True)
            for array_type, stats in sorted_primitives:
                size_mb = stats['size'] / 1024 / 1024
                avg_size_kb = stats['size'] / stats['count'] / 1024 if stats['count'] > 0 else 0
                f.write(f"{array_type:<20} {stats['count']:<12,} {size_mb:.2f} MB\n")

    # ==================== Utility Methods ====================

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


if __name__ == '__main__':
    arg_parser = argparse.ArgumentParser(description="Android HPROF 深度内存分析工具")
    arg_parser.add_argument('-f', '--file', required=True, help="HPROF文件路径")
    arg_parser.add_argument('-o', '--output', help="分析结果输出文件")
    arg_parser.add_argument('-t', '--top', type=int, default=20, help="显示TOP N个内存占用类 (默认20)")
    arg_parser.add_argument('-m', '--min-size', type=float, default=0.1, help="最小显示大小(MB) (默认0.1)")
    arg_parser.add_argument('-s', '--simple', action='store_true', help="简单输出模式")
    arg_parser.add_argument('--no-deep', action='store_true', help="禁用深度分析(更快但功能较少)")
    args = arg_parser.parse_args()

    parser = HprofParser(args.file)
    parser.parse(args.simple, args.top, args.min_size, args.output, deep_analysis=not args.no_deep)
