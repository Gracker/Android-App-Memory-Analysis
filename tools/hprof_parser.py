
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

    def __init__(self, filename, verbose=True):
        self.filename = filename
        self.verbose = verbose
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

        # Phase 6: Deep insight analysis
        self.large_byte_arrays = []  # [(array_id, size, holder_chain, inferred_usage)]
        self.large_strings = []  # [(string_id, size, content, holder_chain)]
        self.large_int_arrays = []  # [(array_id, size, holder_chain)]
        self.large_long_arrays = []  # [(array_id, size, holder_chain)]

        # Standard library classes to filter (noise)
        self.NOISE_CLASSES = {
            'sun.misc.Cleaner',
            'java.lang.ref.WeakReference',
            'java.lang.ref.SoftReference',
            'java.lang.ref.PhantomReference',
            'java.lang.ref.Finalizer',
            'java.lang.ref.FinalizerReference',
            'libcore.util.NativeAllocationRegistry$CleanerThunk',
            'java.security.Provider$ServiceKey',
            'java.security.Provider$Service',
            'sun.security.jca.ServiceId',
        }

        # Interesting holder patterns (business objects)
        self.INTERESTING_PATTERNS = [
            'Activity', 'Fragment', 'View', 'Adapter', 'Holder',
            'Manager', 'Service', 'Repository', 'Cache', 'Pool',
            'Controller', 'Presenter', 'ViewModel', 'Model',
            'Bitmap', 'Drawable', 'Image', 'Buffer',
        ]

        # App package name (to be detected)
        self.app_package = None

        # System/library prefixes (not App code)
        self.SYSTEM_PREFIXES = [
            'android.', 'androidx.', 'com.android.', 'com.google.android.',
            'java.', 'javax.', 'kotlin.', 'kotlinx.',
            'dalvik.', 'libcore.', 'sun.', 'org.apache.',
            'com.google.gson.', 'com.squareup.', 'okhttp3.', 'retrofit2.',
            'io.reactivex.', 'rx.', 'dagger.', 'org.greenrobot.',
        ]

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

    def parse(self, simple_mode=False, top_n=20, min_size_mb=0.1, output_file=None, deep_analysis=True, markdown=False):
        """Main parsing method with optional deep analysis"""
        try:
            self.openHprof(self.filename)
            self.readHead()
            print("正在解析HPROF记录...")
            self.readRecords()

            if deep_analysis:
                print("正在检测 App 包名...")
                self.detect_app_package()
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
                print("正在分析 LruCache...")
                self.analyze_lru_cache()
                # Phase 6: Deep insight analysis
                self.analyze_large_byte_arrays(top_n)
                self.analyze_large_strings(top_n)
                self.analyze_large_int_arrays(top_n)
                self.analyze_suspicious_holdings()

            if not simple_mode:
                self.print_gc_root_statistics()
                if deep_analysis:
                    # Print the most useful analysis first
                    self.print_optimization_suggestions()  # Suggestions first!
                    self.print_large_byte_arrays()
                    self.print_large_strings()
                    self.print_large_int_arrays()
                    self.print_bitmap_analysis()
                    self.print_collection_analysis()
                    self.print_lru_cache_analysis()
                    self.print_suspicious_holdings()
                    self.print_dominator_tree_top(top_n)
                    self.print_leak_suspects()
                    self.print_duplicate_strings()
                self.print_package_statistics(top_n)
                self.print_class_statistics(top_n, min_size_mb)
                self.print_primitive_statistics()
                self.print_string_statistics()

            if output_file:
                if markdown:
                    self.export_markdown(output_file, deep_analysis)
                else:
                    self.export_analysis(output_file, deep_analysis)
            else:
                base_name = os.path.splitext(os.path.basename(self.filename))[0]
                if markdown:
                    default_output = f"{base_name}_analysis.md"
                    self.export_markdown(default_output, deep_analysis)
                else:
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
        if self.verbose:
            print("HPROF版本: %s" % (version), file=sys.stderr)
            print("标识符大小: %d" % (self.size_of_identifier), file=sys.stderr)
            print("时间戳: %s" % (datetime.fromtimestamp(timestamp)), file=sys.stderr)
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
        """Analyze Bitmap objects with deep insights (Phase 5.2)"""
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

        # Bitmap config bytes per pixel mapping
        config_bpp = {
            'ALPHA_8': 1,
            'RGB_565': 2,
            'ARGB_4444': 2,
            'ARGB_8888': 4,
            'RGBA_F16': 8,
            'HARDWARE': 4,
        }

        # For detecting duplicate bitmaps
        size_to_bitmaps = defaultdict(list)

        # Analyze each Bitmap instance
        for obj_id, instance in self.instances.items():
            if instance['class_id'] != bitmap_class_id:
                continue

            fields_data = instance['fields_data']
            width = 0
            height = 0
            density = 0
            is_mutable = False
            is_recycled = False
            config_name = 'ARGB_8888'
            native_ptr = 0

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

            # Extract mDensity
            if 'mDensity' in field_offsets:
                off, type_id, size = field_offsets['mDensity']
                if off + size <= len(fields_data) and type_id == self.TYPE_INT:
                    density = int.from_bytes(fields_data[off:off+size], byteorder='big', signed=True)

            # Extract mIsMutable
            if 'mIsMutable' in field_offsets:
                off, type_id, size = field_offsets['mIsMutable']
                if off + size <= len(fields_data) and type_id == self.TYPE_BOOLEAN:
                    is_mutable = fields_data[off] != 0

            # Extract mRecycled
            if 'mRecycled' in field_offsets:
                off, type_id, size = field_offsets['mRecycled']
                if off + size <= len(fields_data) and type_id == self.TYPE_BOOLEAN:
                    is_recycled = fields_data[off] != 0

            # Extract mNativePtr
            if 'mNativePtr' in field_offsets:
                off, type_id, size = field_offsets['mNativePtr']
                if off + size <= len(fields_data) and type_id == self.TYPE_LONG:
                    native_ptr = int.from_bytes(fields_data[off:off+size], byteorder='big', signed=False)

            # Sanity check - valid bitmap dimensions
            if width > 0 and height > 0 and width < 20000 and height < 20000:
                bpp = config_bpp.get(config_name, 4)
                estimated_size = width * height * bpp

                bitmap_data = {
                    'width': width,
                    'height': height,
                    'density': density,
                    'config': config_name,
                    'bpp': bpp,
                    'is_mutable': is_mutable,
                    'is_recycled': is_recycled,
                    'native_ptr': native_ptr,
                    'estimated_size': estimated_size,
                    'holder_chain': None
                }

                self.bitmap_info[obj_id] = bitmap_data
                size_to_bitmaps[(width, height)].append(obj_id)

        # Detect duplicate bitmaps (same dimensions)
        self.duplicate_bitmaps = []
        for size_key, bitmap_ids in size_to_bitmaps.items():
            if len(bitmap_ids) > 1:
                width, height = size_key
                self.duplicate_bitmaps.append({
                    'size': size_key,
                    'count': len(bitmap_ids),
                    'bitmap_ids': bitmap_ids,
                    'total_wasted': (len(bitmap_ids) - 1) * width * height * 4
                })

        self.duplicate_bitmaps.sort(key=lambda x: x['total_wasted'], reverse=True)

        # Get holder chains for top bitmaps
        sorted_bitmaps = sorted(self.bitmap_info.items(),
                               key=lambda x: x[1]['estimated_size'], reverse=True)
        for obj_id, info in sorted_bitmaps[:20]:
            info['holder_chain'] = self.get_holder_chain(obj_id)

    # ==================== Phase 6: Deep Insight Analysis ====================

    def detect_app_package(self):
        """Detect the App's package name from Activity classes"""
        # Strategy 1: Find classes that extend Activity
        activity_classes = []
        for class_id, class_info in self.classes.items():
            name = class_info.get('name', '')
            # Look for Activity subclasses
            if 'Activity' in name and not name.startswith(tuple(self.SYSTEM_PREFIXES)):
                activity_classes.append(name)

        # Extract package name from Activity classes
        if activity_classes:
            # Find common package prefix
            packages = []
            for name in activity_classes:
                parts = name.rsplit('.', 1)
                if len(parts) > 1:
                    packages.append(parts[0])

            if packages:
                # Find most common package or shortest common prefix
                from collections import Counter
                pkg_counts = Counter(packages)
                most_common = pkg_counts.most_common(1)
                if most_common:
                    self.app_package = most_common[0][0]
                    print(f"检测到 App 包名: {self.app_package}")
                    return

        # Strategy 2: Find most common non-system package
        package_counts = defaultdict(int)
        for class_id, class_info in self.classes.items():
            name = class_info.get('name', '')
            if name.startswith(tuple(self.SYSTEM_PREFIXES)):
                continue
            parts = name.split('.')
            if len(parts) >= 2:
                pkg = '.'.join(parts[:2])  # e.g., com.example
                package_counts[pkg] += 1

        if package_counts:
            most_common = max(package_counts.items(), key=lambda x: x[1])
            self.app_package = most_common[0]
            print(f"推测 App 包名: {self.app_package}")

    def is_app_class(self, class_name):
        """Check if a class belongs to the App"""
        if not class_name or not self.app_package:
            return False
        return class_name.startswith(self.app_package)

    def is_system_class(self, class_name):
        """Check if a class is a system/library class"""
        if not class_name:
            return True
        return class_name.startswith(tuple(self.SYSTEM_PREFIXES))

    def analyze_large_byte_arrays(self, top_n=20):
        """Analyze largest byte[] arrays with their holder chains (Phase 6.1)"""
        print("正在分析大 byte[] 的持有者...")

        # Find all byte arrays sorted by size
        byte_arrays = []
        for array_id, array_info in self.primitive_arrays.items():
            if array_info.get('type_name') == 'byte':
                size = array_info.get('size', 0)
                byte_arrays.append((array_id, size))

        # Sort by size descending
        byte_arrays.sort(key=lambda x: x[1], reverse=True)

        # Analyze top N
        for array_id, size in byte_arrays[:top_n]:
            holder_chain = self.get_holder_chain(array_id)
            inferred_usage = self.infer_byte_array_usage(array_id, holder_chain)
            self.large_byte_arrays.append({
                'id': array_id,
                'size': size,
                'holder_chain': holder_chain,
                'usage': inferred_usage
            })

    def analyze_large_strings(self, top_n=20):
        """Analyze largest String objects with their content (Phase 6.2)"""
        print("正在分析大 String 的内容...")

        # Find String class
        string_class_id = None
        for class_id, class_info in self.classes.items():
            if class_info.get('name') == 'java.lang.String':
                string_class_id = class_id
                break

        if not string_class_id:
            return

        # Find all String instances with their backing array
        string_sizes = []
        for obj_id, instance in self.instances.items():
            if instance['class_id'] != string_class_id:
                continue

            total_size = instance['size']
            content = None
            fields_data = instance.get('fields_data', b'')

            # Android String layout varies by version.
            # Scan all possible offsets for object references to find the value array
            for offset in range(0, len(fields_data) - self.size_of_identifier + 1, self.size_of_identifier):
                ref = int.from_bytes(
                    fields_data[offset:offset + self.size_of_identifier],
                    byteorder='big'
                )
                if ref in self.primitive_arrays:
                    array = self.primitive_arrays[ref]
                    # Only consider byte[] or char[] as potential String value
                    if array.get('type') in [self.TYPE_BYTE, self.TYPE_CHAR]:
                        array_size = array.get('size', 0)
                        total_size += array_size
                        content = self.decode_string_array(array)
                        if content:
                            break

            string_sizes.append((obj_id, total_size, content))

        # Sort by size descending
        string_sizes.sort(key=lambda x: x[1], reverse=True)

        # Get top N with holder chains
        for obj_id, size, content in string_sizes[:top_n]:
            holder_chain = self.get_holder_chain(obj_id)
            self.large_strings.append({
                'id': obj_id,
                'size': size,
                'content': content,
                'holder_chain': holder_chain
            })

    def decode_string_array(self, array):
        """Decode a char[] or byte[] array to string content"""
        if not array.get('data'):
            return None

        data = array['data']
        array_type = array.get('type')

        # char[] - Java's native String storage (pre-Android 9)
        if array_type == self.TYPE_CHAR:
            try:
                return data.decode('utf-16-be', errors='ignore')
            except:
                pass

        # byte[] - Compact String storage (Android 9+)
        if array_type == self.TYPE_BYTE:
            # Try different encodings
            for encoding in ['utf-8', 'latin-1', 'utf-16-le', 'utf-16-be']:
                try:
                    decoded = data.decode(encoding, errors='ignore')
                    # Basic validity check - should be mostly printable
                    printable_ratio = sum(1 for c in decoded if c.isprintable() or c in '\n\r\t') / max(len(decoded), 1)
                    if printable_ratio > 0.7:
                        return decoded
                except:
                    pass

        return None

    def analyze_large_int_arrays(self, top_n=20):
        """Analyze largest int[] and long[] arrays (Phase 6.3)"""
        print("正在分析大 int[]/long[] 的持有者...")

        # Find int arrays
        int_arrays = []
        for array_id, array_info in self.primitive_arrays.items():
            if array_info.get('type_name') == 'int':
                size = array_info.get('size', 0)
                int_arrays.append((array_id, size, 'int'))
            elif array_info.get('type_name') == 'long':
                size = array_info.get('size', 0)
                int_arrays.append((array_id, size, 'long'))

        # Sort by size
        int_arrays.sort(key=lambda x: x[1], reverse=True)

        # Analyze top N
        for array_id, size, array_type in int_arrays[:top_n]:
            holder_chain = self.get_holder_chain(array_id)
            if array_type == 'int':
                self.large_int_arrays.append({
                    'id': array_id,
                    'size': size,
                    'holder_chain': holder_chain
                })
            else:
                self.large_long_arrays.append({
                    'id': array_id,
                    'size': size,
                    'holder_chain': holder_chain
                })

    def get_holder_chain(self, obj_id, max_depth=10):
        """Get the holder chain from object to interesting business object or GC root"""
        chain = []
        visited = set()
        current_id = obj_id

        for _ in range(max_depth):
            if current_id in visited:
                break
            visited.add(current_id)

            # Get object info
            obj_info = self.get_object_info(current_id)
            chain.append(obj_info)

            # Check if we've reached a GC root
            if current_id in self.gc_roots:
                root_type = self.gc_roots[current_id].get('type')
                obj_info['is_gc_root'] = True
                obj_info['gc_root_type'] = self.GC_ROOT_NAMES.get(root_type, 'UNKNOWN')
                break

            # Check if we've reached an interesting object
            class_name = obj_info.get('class_name', '')
            if self.is_interesting_class(class_name):
                obj_info['is_interesting'] = True
                # Continue a bit more to find the ultimate holder
                incoming = list(self.incoming_refs.get(current_id, []))
                if incoming:
                    # Pick the holder that's not a noise class
                    best_holder = None
                    for holder_id in incoming:
                        holder_info = self.get_object_info(holder_id)
                        holder_class = holder_info.get('class_name', '')
                        if not self.is_noise_class(holder_class):
                            best_holder = holder_id
                            break
                    if best_holder and best_holder not in visited:
                        current_id = best_holder
                        continue
                break

            # Find incoming references (who holds this object)
            incoming = list(self.incoming_refs.get(current_id, []))
            if not incoming:
                break

            # Prefer non-noise class holders
            best_holder = None
            for holder_id in incoming:
                if holder_id in visited:
                    continue
                holder_info = self.get_object_info(holder_id)
                holder_class = holder_info.get('class_name', '')
                if not self.is_noise_class(holder_class):
                    best_holder = holder_id
                    break

            if best_holder is None and incoming:
                # Fallback to first available
                for holder_id in incoming:
                    if holder_id not in visited:
                        best_holder = holder_id
                        break

            if best_holder is None:
                break

            current_id = best_holder

        return chain

    def get_object_info(self, obj_id):
        """Get detailed info about an object"""
        info = {
            'id': obj_id,
            'class_name': 'unknown',
            'type': 'unknown'
        }

        if obj_id in self.instances:
            instance = self.instances[obj_id]
            class_id = instance['class_id']
            class_name = self.classes.get(class_id, {}).get('name', 'unknown')
            info['class_name'] = class_name
            info['type'] = 'instance'
            info['size'] = instance.get('size', 0)
            info['is_app_class'] = self.is_app_class(class_name)

            # Try to find the field name that references this object
            info['field_names'] = self.get_field_names_for_class(class_id)

        elif obj_id in self.object_arrays:
            array = self.object_arrays[obj_id]
            class_id = array['class_id']
            class_name = self.classes.get(class_id, {}).get('name', 'unknown')
            info['class_name'] = class_name + '[]'
            info['type'] = 'object_array'
            info['length'] = array.get('length', 0)
            info['size'] = array.get('size', 0)
            info['is_app_class'] = self.is_app_class(class_name)

        elif obj_id in self.primitive_arrays:
            array = self.primitive_arrays[obj_id]
            info['class_name'] = f"{array.get('type_name', 'unknown')}[]"
            info['type'] = 'primitive_array'
            info['length'] = array.get('length', 0)
            info['size'] = array.get('size', 0)

        elif obj_id in self.classes:
            class_name = self.classes[obj_id].get('name', 'unknown')
            info['class_name'] = class_name + ' (class)'
            info['type'] = 'class'
            info['is_app_class'] = self.is_app_class(class_name)

        return info

    def get_field_names_for_class(self, class_id):
        """Get field names for a class"""
        field_names = []
        if class_id in self.class_fields:
            for field in self.class_fields[class_id].get('instance_fields', []):
                name_id = field.get('name_id')
                if name_id and name_id in self.strings:
                    field_names.append(self.strings[name_id])
        return field_names

    def is_noise_class(self, class_name):
        """Check if a class is a noise/standard library class"""
        if not class_name:
            return True

        # Check exact matches
        if class_name in self.NOISE_CLASSES:
            return True

        # Check prefixes that are usually noise
        noise_prefixes = [
            'sun.', 'java.lang.ref.', 'java.security.', 'libcore.',
            'dalvik.system.', 'android.icu.', 'com.android.org.bouncycastle.',
        ]
        for prefix in noise_prefixes:
            if class_name.startswith(prefix):
                return True

        return False

    def is_interesting_class(self, class_name):
        """Check if a class is an interesting business object"""
        if not class_name:
            return False

        for pattern in self.INTERESTING_PATTERNS:
            if pattern in class_name:
                return True

        # Also check if it's an app-specific class (not android.* or java.*)
        if not class_name.startswith(('android.', 'java.', 'kotlin.', 'com.android.', 'dalvik.')):
            # Likely an app class
            return True

        return False

    def infer_byte_array_usage(self, array_id, holder_chain):
        """Infer the usage of a byte[] based on its holder chain"""
        for obj in holder_chain:
            class_name = obj.get('class_name', '')

            # Check for Bitmap
            if 'Bitmap' in class_name:
                return 'Bitmap 像素数据'

            # Check for streams/buffers
            if 'InputStream' in class_name or 'OutputStream' in class_name:
                return 'IO 流缓冲区'
            if 'Buffer' in class_name:
                return '缓冲区'

            # Check for network
            if 'Socket' in class_name or 'Http' in class_name or 'Network' in class_name:
                return '网络数据'

            # Check for file operations
            if 'File' in class_name:
                return '文件数据'

            # Check for codec/media
            if 'Codec' in class_name or 'Media' in class_name or 'Audio' in class_name or 'Video' in class_name:
                return '多媒体数据'

            # Check for crypto
            if 'Cipher' in class_name or 'Crypto' in class_name or 'Encrypt' in class_name:
                return '加密数据'

            # Check for String
            if class_name == 'java.lang.String':
                return 'String 内部存储'

        # Check array size for hints
        array = self.primitive_arrays.get(array_id, {})
        size = array.get('size', 0)

        if size > 1024 * 1024:  # > 1MB
            return '大型数据块 (可能是图片/文件)'
        elif size > 100 * 1024:  # > 100KB
            return '中型数据块'
        else:
            return '小型数据块'

    def analyze_collections(self):
        """Analyze collection classes for capacity issues and problems (Phase 5.3)"""
        self.collection_analysis = []
        self.empty_collections = []
        self.large_collections = []

        # Find collection classes
        collection_classes = {}
        for class_id, class_info in self.classes.items():
            name = class_info.get('name', '')
            if name in ['java.util.HashMap', 'java.util.ArrayList',
                       'java.util.HashSet', 'java.util.LinkedList',
                       'java.util.concurrent.ConcurrentHashMap',
                       'java.util.LinkedHashMap', 'java.util.TreeMap',
                       'java.util.Vector', 'java.util.Stack',
                       'android.util.ArrayMap', 'android.util.SparseArray',
                       'android.util.LongSparseArray']:
                collection_classes[class_id] = name

        empty_count_by_type = defaultdict(int)

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

            # Extract mSize for Android collections
            if 'mSize' in field_offsets:
                off, type_id, field_size = field_offsets['mSize']
                if off + field_size <= len(fields_data) and type_id == self.TYPE_INT:
                    size = int.from_bytes(fields_data[off:off+field_size], byteorder='big', signed=True)

            # Extract threshold for HashMap (capacity = threshold / 0.75)
            if 'threshold' in field_offsets:
                off, type_id, field_size = field_offsets['threshold']
                if off + field_size <= len(fields_data) and type_id == self.TYPE_INT:
                    threshold = int.from_bytes(fields_data[off:off+field_size], byteorder='big', signed=True)
                    if threshold > 0 and threshold < 10000000:
                        capacity = int(threshold / 0.75)

            # Sanity check for size
            if size < 0 or size > 10000000:  # Invalid or unreasonably large
                continue

            # Detect empty collections
            if size == 0:
                empty_count_by_type[class_name] += 1

            # Detect large collections (>1000 elements)
            if size > 1000:
                self.large_collections.append({
                    'object_id': obj_id,
                    'class_name': class_name,
                    'size': size,
                    'holder_chain': None  # Will be filled later
                })

            # Check for over-allocated collections
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

        # Store empty collection stats
        self.empty_collections = [(name, count) for name, count in empty_count_by_type.items()]
        self.empty_collections.sort(key=lambda x: x[1], reverse=True)

        # Sort by wasted slots
        self.collection_analysis.sort(key=lambda x: x['wasted_slots'], reverse=True)

        # Sort large collections by size
        self.large_collections.sort(key=lambda x: x['size'], reverse=True)

        # Get holder chains for top large collections
        for item in self.large_collections[:10]:
            item['holder_chain'] = self.get_holder_chain(item['object_id'])

    def analyze_suspicious_holdings(self):
        """Detect suspicious memory holdings (Phase 6.4)"""
        print("正在检测不合理持有...")
        self.suspicious_holdings = []

        # 1. Find static fields holding large objects
        for class_id, class_info in self.classes.items():
            class_name = class_info.get('name', '')

            # Skip system classes
            if self.is_system_class(class_name):
                continue

            # Check static fields
            if class_id in self.class_fields:
                static_fields = self.class_fields[class_id].get('static_fields', [])
                for field in static_fields:
                    field_value = field.get('value')
                    if not field_value or field_value == 0:
                        continue

                    # Check if this static field points to a large object
                    retained = self.retained_sizes.get(field_value, 0)
                    if retained > 100 * 1024:  # > 100KB
                        field_name = self.strings.get(field.get('name_id'), 'unknown')
                        self.suspicious_holdings.append({
                            'type': 'STATIC_FIELD',
                            'class_name': class_name,
                            'field_name': field_name,
                            'retained_size': retained,
                            'object_id': field_value,
                            'description': f'静态字段 {class_name}.{field_name} 持有 {retained/1024/1024:.2f} MB'
                        })

        # 2. Detect singleton patterns holding too much
        singleton_patterns = ['$Companion', 'INSTANCE', 'sInstance', 'mInstance']
        for class_id, class_info in self.classes.items():
            class_name = class_info.get('name', '')

            if self.is_system_class(class_name):
                continue

            if class_id in self.class_fields:
                static_fields = self.class_fields[class_id].get('static_fields', [])
                for field in static_fields:
                    field_name_id = field.get('name_id')
                    if not field_name_id:
                        continue

                    field_name = self.strings.get(field_name_id, '')
                    is_singleton = any(pattern in field_name for pattern in singleton_patterns)

                    if is_singleton:
                        field_value = field.get('value')
                        if field_value and field_value != 0:
                            retained = self.retained_sizes.get(field_value, 0)
                            if retained > 500 * 1024:  # > 500KB for singleton
                                self.suspicious_holdings.append({
                                    'type': 'SINGLETON',
                                    'class_name': class_name,
                                    'field_name': field_name,
                                    'retained_size': retained,
                                    'object_id': field_value,
                                    'description': f'单例 {class_name} 持有 {retained/1024/1024:.2f} MB'
                                })

        # 3. Detect Activities/Fragments in static fields (potential leak)
        for holding in self.suspicious_holdings[:]:  # Copy list to modify during iteration
            obj_id = holding.get('object_id')
            if obj_id in self.instances:
                instance = self.instances[obj_id]
                class_id = instance['class_id']
                obj_class_name = self.classes.get(class_id, {}).get('name', '')

                if 'Activity' in obj_class_name or 'Fragment' in obj_class_name:
                    holding['type'] = 'LEAKED_COMPONENT'
                    holding['description'] = f'⚠️ 可能泄漏! {obj_class_name} 被静态字段持有'

        # Sort by retained size
        self.suspicious_holdings.sort(key=lambda x: x['retained_size'], reverse=True)

    def analyze_lru_cache(self):
        """Analyze LruCache usage (Phase 4.3)"""
        print("正在分析 LruCache...")
        self.lru_cache_analysis = []

        # Find LruCache and related cache classes (strict match)
        cache_class_names = [
            'android.util.LruCache',
            'androidx.collection.LruCache',
            'android.support.v4.util.LruCache',
        ]

        cache_classes = {}
        for class_id, class_info in self.classes.items():
            name = class_info.get('name', '')
            # Only match exact LruCache classes or subclasses (contain LruCache in name)
            for cache_name in cache_class_names:
                if name == cache_name or 'LruCache' in name:
                    cache_classes[class_id] = name
                    break

        for obj_id, instance in self.instances.items():
            class_id = instance['class_id']
            if class_id not in cache_classes:
                continue

            class_name = cache_classes[class_id]
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

            # Extract LruCache fields
            cache_info = {
                'object_id': obj_id,
                'class_name': class_name,
                'size': 0,
                'maxSize': 0,
                'putCount': 0,
                'hitCount': 0,
                'missCount': 0,
                'evictionCount': 0,
                'createCount': 0,
                'utilization': 0.0,
                'hit_rate': 0.0,
                'holder_chain': None
            }

            # Read size
            if 'size' in field_offsets:
                off, type_id, field_size = field_offsets['size']
                if off + field_size <= len(fields_data) and type_id == self.TYPE_INT:
                    cache_info['size'] = int.from_bytes(fields_data[off:off+field_size], byteorder='big', signed=True)

            # Read maxSize
            if 'maxSize' in field_offsets:
                off, type_id, field_size = field_offsets['maxSize']
                if off + field_size <= len(fields_data) and type_id == self.TYPE_INT:
                    cache_info['maxSize'] = int.from_bytes(fields_data[off:off+field_size], byteorder='big', signed=True)

            # Read putCount
            if 'putCount' in field_offsets:
                off, type_id, field_size = field_offsets['putCount']
                if off + field_size <= len(fields_data) and type_id == self.TYPE_INT:
                    cache_info['putCount'] = int.from_bytes(fields_data[off:off+field_size], byteorder='big', signed=True)

            # Read hitCount
            if 'hitCount' in field_offsets:
                off, type_id, field_size = field_offsets['hitCount']
                if off + field_size <= len(fields_data) and type_id == self.TYPE_INT:
                    cache_info['hitCount'] = int.from_bytes(fields_data[off:off+field_size], byteorder='big', signed=True)

            # Read missCount
            if 'missCount' in field_offsets:
                off, type_id, field_size = field_offsets['missCount']
                if off + field_size <= len(fields_data) and type_id == self.TYPE_INT:
                    cache_info['missCount'] = int.from_bytes(fields_data[off:off+field_size], byteorder='big', signed=True)

            # Read evictionCount
            if 'evictionCount' in field_offsets:
                off, type_id, field_size = field_offsets['evictionCount']
                if off + field_size <= len(fields_data) and type_id == self.TYPE_INT:
                    cache_info['evictionCount'] = int.from_bytes(fields_data[off:off+field_size], byteorder='big', signed=True)

            # Read createCount
            if 'createCount' in field_offsets:
                off, type_id, field_size = field_offsets['createCount']
                if off + field_size <= len(fields_data) and type_id == self.TYPE_INT:
                    cache_info['createCount'] = int.from_bytes(fields_data[off:off+field_size], byteorder='big', signed=True)

            # Calculate utilization
            if cache_info['maxSize'] > 0:
                cache_info['utilization'] = cache_info['size'] / cache_info['maxSize']

            # Calculate hit rate
            total_access = cache_info['hitCount'] + cache_info['missCount']
            if total_access > 0:
                cache_info['hit_rate'] = cache_info['hitCount'] / total_access

            # Get holder chain
            cache_info['holder_chain'] = self.get_holder_chain(obj_id)

            # Only add if we have valid data
            if cache_info['maxSize'] > 0 or cache_info['size'] > 0:
                self.lru_cache_analysis.append(cache_info)

        # Sort by size descending
        self.lru_cache_analysis.sort(key=lambda x: x['size'], reverse=True)

    def print_lru_cache_analysis(self):
        """Print LruCache analysis results"""
        if not hasattr(self, 'lru_cache_analysis') or not self.lru_cache_analysis:
            print("\n=== LruCache 分析 ===")
            print("未检测到 LruCache 实例")
            return

        print(f"\n{'='*80}")
        print(f"=== LruCache 缓存分析 (共 {len(self.lru_cache_analysis)} 个) ===")
        print(f"{'='*80}")

        for i, cache in enumerate(self.lru_cache_analysis[:20], 1):
            print(f"\n[{i}] {cache['class_name']}")
            print(f"    当前大小/最大容量: {cache['size']:,} / {cache['maxSize']:,}")
            print(f"    利用率: {cache['utilization']*100:.1f}%")

            if cache['hitCount'] > 0 or cache['missCount'] > 0:
                print(f"    命中率: {cache['hit_rate']*100:.1f}% (命中: {cache['hitCount']:,}, 未命中: {cache['missCount']:,})")

            if cache['evictionCount'] > 0:
                print(f"    淘汰次数: {cache['evictionCount']:,}")

            if cache['putCount'] > 0:
                print(f"    写入次数: {cache['putCount']:,}")

            # Print holder chain if available
            if cache['holder_chain']:
                print("    持有者链:")
                for j, holder_info in enumerate(cache['holder_chain'][:5]):
                    indent = "      " + "  " * j
                    holder_name = holder_info.get('class_name', 'unknown')
                    type_marker = ""
                    if holder_info.get('is_gc_root'):
                        type_marker = f" [GC Root: {holder_info.get('gc_root_type', 'UNKNOWN')}]"
                    elif holder_info.get('is_app_class'):
                        type_marker = " [★ 业务对象]"
                    print(f"{indent}└─ {holder_name}{type_marker}")

        # Print summary insights
        print(f"\n--- LruCache 使用建议 ---")

        # Check for low hit rates
        low_hit_caches = [c for c in self.lru_cache_analysis if c['hit_rate'] < 0.5 and (c['hitCount'] + c['missCount']) > 10]
        if low_hit_caches:
            print(f"⚠️  {len(low_hit_caches)} 个缓存命中率低于 50%，考虑:")
            print("   1. 增加缓存容量")
            print("   2. 优化缓存键策略")
            print("   3. 预加载常用数据")

        # Check for high eviction rates
        high_eviction = [c for c in self.lru_cache_analysis if c['evictionCount'] > c['putCount'] * 0.5 and c['putCount'] > 10]
        if high_eviction:
            print(f"⚠️  {len(high_eviction)} 个缓存淘汰频繁，建议增加 maxSize")

        # Check for underutilized caches
        underutilized = [c for c in self.lru_cache_analysis if c['utilization'] < 0.3 and c['maxSize'] > 0]
        if underutilized:
            print(f"💡 {len(underutilized)} 个缓存利用率低于 30%，可减小 maxSize 节省内存")

    def print_suspicious_holdings(self, top_n=10):
        """Print suspicious holdings analysis"""
        if not hasattr(self, 'suspicious_holdings') or not self.suspicious_holdings:
            return

        print(f"\n{'='*80}")
        print("=== 不合理持有检测 ===")
        print(f"{'='*80}")

        # Group by type
        leaked = [h for h in self.suspicious_holdings if h['type'] == 'LEAKED_COMPONENT']
        static = [h for h in self.suspicious_holdings if h['type'] == 'STATIC_FIELD']
        singleton = [h for h in self.suspicious_holdings if h['type'] == 'SINGLETON']

        if leaked:
            print(f"\n--- ⚠️ 可能的内存泄漏 ({len(leaked)} 个) ---")
            for item in leaked[:5]:
                print(f"  {item['description']}")
                print(f"    位置: {item['class_name']}.{item['field_name']}")

        if static:
            print(f"\n--- 静态字段持有大对象 ({len(static)} 个) ---")
            print("提示: 静态字段生命周期与进程相同，持有大对象会导致内存无法释放")
            for item in static[:top_n]:
                print(f"  {item['class_name']}.{item['field_name']}")
                print(f"    Retained: {item['retained_size']/1024/1024:.2f} MB")

        if singleton:
            print(f"\n--- 单例持有过多数据 ({len(singleton)} 个) ---")
            print("提示: 单例不会被回收，其持有的数据也不会释放")
            for item in singleton[:top_n]:
                print(f"  {item['class_name']}")
                print(f"    Retained: {item['retained_size']/1024/1024:.2f} MB")

    def print_optimization_suggestions(self):
        """Print optimization suggestions based on analysis"""
        print(f"\n{'='*80}")
        print("=== 内存优化建议 ===")
        print(f"{'='*80}")

        suggestions = []
        priority_high = []
        priority_medium = []
        priority_low = []

        # 1. Check for memory leaks
        if hasattr(self, 'suspicious_holdings'):
            leaked = [h for h in self.suspicious_holdings if h['type'] == 'LEAKED_COMPONENT']
            if leaked:
                priority_high.append({
                    'issue': '检测到可能的内存泄漏',
                    'detail': f'{len(leaked)} 个 Activity/Fragment 被静态字段持有',
                    'suggestion': '1. 检查是否有 static 变量持有 Activity/Fragment 引用\n'
                                  '2. 使用 WeakReference 替代强引用\n'
                                  '3. 在 onDestroy() 中清理引用'
                })

        # 2. Check for large bitmaps
        if self.bitmap_info:
            large_bitmaps = [b for b in self.bitmap_info.values() if b['estimated_size'] > 1024*1024]
            if large_bitmaps:
                total_mb = sum(b['estimated_size'] for b in large_bitmaps) / 1024 / 1024
                priority_medium.append({
                    'issue': '大尺寸 Bitmap',
                    'detail': f'{len(large_bitmaps)} 个 Bitmap 超过 1MB，共占用 {total_mb:.1f} MB',
                    'suggestion': '1. 使用 inSampleSize 降低图片分辨率\n'
                                  '2. 使用 RGB_565 替代 ARGB_8888（节省 50% 内存）\n'
                                  '3. 及时调用 recycle() 释放不用的 Bitmap'
                })

        # 3. Check for duplicate bitmaps
        if hasattr(self, 'duplicate_bitmaps') and self.duplicate_bitmaps:
            total_wasted = sum(d['total_wasted'] for d in self.duplicate_bitmaps) / 1024 / 1024
            if total_wasted > 1:
                priority_medium.append({
                    'issue': '重复加载 Bitmap',
                    'detail': f'相同尺寸 Bitmap 重复加载，浪费约 {total_wasted:.1f} MB',
                    'suggestion': '1. 使用 LruCache 或 Glide/Picasso 缓存图片\n'
                                  '2. 检查是否多次加载相同资源'
                })

        # 4. Check for empty collections
        if hasattr(self, 'empty_collections') and self.empty_collections:
            total_empty = sum(count for _, count in self.empty_collections)
            if total_empty > 100:
                priority_low.append({
                    'issue': '大量空集合',
                    'detail': f'{total_empty} 个空集合对象',
                    'suggestion': '1. 使用 Collections.emptyList()/emptyMap() 替代 new ArrayList()\n'
                                  '2. 延迟初始化：需要时再创建集合'
                })

        # 5. Check for large collections
        if hasattr(self, 'large_collections') and self.large_collections:
            priority_medium.append({
                'issue': '超大集合',
                'detail': f'{len(self.large_collections)} 个集合超过 1000 个元素',
                'suggestion': '1. 检查是否需要保存这么多数据\n'
                              '2. 考虑分页加载或使用数据库\n'
                              '3. 定期清理不需要的数据'
            })

        # 6. Check for static field holdings
        if hasattr(self, 'suspicious_holdings'):
            static = [h for h in self.suspicious_holdings if h['type'] == 'STATIC_FIELD']
            if static:
                total_mb = sum(h['retained_size'] for h in static) / 1024 / 1024
                priority_medium.append({
                    'issue': '静态字段持有大量数据',
                    'detail': f'{len(static)} 个静态字段共持有 {total_mb:.1f} MB',
                    'suggestion': '1. 评估是否需要静态持有\n'
                                  '2. 考虑使用软引用 SoftReference\n'
                                  '3. 在内存紧张时主动释放'
                })

        # 7. Check for LruCache issues
        if hasattr(self, 'lru_cache_analysis') and self.lru_cache_analysis:
            # Check for low hit rates
            low_hit = [c for c in self.lru_cache_analysis if c['hit_rate'] < 0.5 and (c['hitCount'] + c['missCount']) > 10]
            if low_hit:
                priority_medium.append({
                    'issue': 'LruCache 命中率低',
                    'detail': f'{len(low_hit)} 个缓存命中率低于 50%',
                    'suggestion': '1. 增加缓存容量 (maxSize)\n'
                                  '2. 优化缓存键策略\n'
                                  '3. 预加载常用数据'
                })

            # Check for underutilized caches
            underutilized = [c for c in self.lru_cache_analysis if c['utilization'] < 0.3 and c['maxSize'] > 0]
            if underutilized:
                priority_low.append({
                    'issue': 'LruCache 利用率低',
                    'detail': f'{len(underutilized)} 个缓存利用率低于 30%',
                    'suggestion': '1. 减小 maxSize 节省内存\n'
                                  '2. 检查缓存是否有必要'
                })

        # Print suggestions
        if priority_high:
            print("\n🔴 高优先级 (需立即处理)")
            for i, s in enumerate(priority_high, 1):
                print(f"\n  [{i}] {s['issue']}")
                print(f"      {s['detail']}")
                print(f"      建议:")
                for line in s['suggestion'].split('\n'):
                    print(f"        {line}")

        if priority_medium:
            print("\n🟡 中优先级 (建议优化)")
            for i, s in enumerate(priority_medium, 1):
                print(f"\n  [{i}] {s['issue']}")
                print(f"      {s['detail']}")
                print(f"      建议:")
                for line in s['suggestion'].split('\n'):
                    print(f"        {line}")

        if priority_low:
            print("\n🟢 低优先级 (可选优化)")
            for i, s in enumerate(priority_low, 1):
                print(f"\n  [{i}] {s['issue']}")
                print(f"      {s['detail']}")
                print(f"      建议:")
                for line in s['suggestion'].split('\n'):
                    print(f"        {line}")

        if not priority_high and not priority_medium and not priority_low:
            print("\n✅ 未发现明显的内存问题，继续保持！")

    def print_large_byte_arrays(self):
        """Print large byte[] analysis with holder chains"""
        if not self.large_byte_arrays:
            return

        print(f"\n{'='*80}")
        print("=== TOP 大 byte[] 分析 (谁持有了这些内存?) ===")
        if self.app_package:
            print(f"App 包名: {self.app_package}")
        print(f"{'='*80}")

        for i, item in enumerate(self.large_byte_arrays, 1):
            size_kb = item['size'] / 1024
            size_mb = item['size'] / 1024 / 1024

            if size_mb >= 1:
                size_str = f"{size_mb:.2f} MB"
            else:
                size_str = f"{size_kb:.2f} KB"

            print(f"\n[{i}] byte[{item.get('length', '?')}] - {size_str}")
            print(f"    推断用途: {item['usage']}")
            print(f"    持有者链:")

            chain = item['holder_chain']
            for j, obj in enumerate(chain):
                indent = "    " + "  " * j
                class_name = obj.get('class_name', 'unknown')
                markers = []
                if obj.get('is_gc_root'):
                    markers.append(f"GC Root: {obj.get('gc_root_type', 'UNKNOWN')}")
                if obj.get('is_app_class'):
                    markers.append("🔴 App")
                elif obj.get('is_interesting'):
                    markers.append("★ 业务对象")

                marker_str = f" [{', '.join(markers)}]" if markers else ""
                if j == 0:
                    print(f"{indent}└─ {class_name}{marker_str}")
                else:
                    print(f"{indent}└─ 被持有于: {class_name}{marker_str}")

    def print_large_strings(self):
        """Print large String analysis with content preview"""
        if not self.large_strings:
            return

        print(f"\n{'='*80}")
        print("=== TOP 大 String 分析 (实际内容是什么?) ===")
        print(f"{'='*80}")

        for i, item in enumerate(self.large_strings, 1):
            size_kb = item['size'] / 1024
            content = item.get('content', '')

            # Truncate and escape content for display
            if content:
                # Escape special characters
                display_content = content.replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
                if len(display_content) > 100:
                    display_content = display_content[:100] + '...'
            else:
                display_content = '<无法解码>'

            print(f"\n[{i}] String - {size_kb:.2f} KB")
            print(f"    内容: \"{display_content}\"")

            # Show holder chain (simplified)
            chain = item['holder_chain']
            if len(chain) > 1:
                # Find the most interesting holder
                for obj in chain[1:]:  # Skip the String itself
                    class_name = obj.get('class_name', 'unknown')
                    if class_name != 'java.lang.String':
                        print(f"    持有者: {class_name}")
                        break

    def print_large_int_arrays(self):
        """Print large int[]/long[] analysis with holder chains"""
        if not self.large_int_arrays and not self.large_long_arrays:
            return

        print(f"\n{'='*80}")
        print("=== TOP 大 int[]/long[] 分析 ===")
        print(f"{'='*80}")

        # Combine and sort
        all_arrays = []
        for item in self.large_int_arrays:
            item['type'] = 'int'
            all_arrays.append(item)
        for item in self.large_long_arrays:
            item['type'] = 'long'
            all_arrays.append(item)

        all_arrays.sort(key=lambda x: x['size'], reverse=True)

        for i, item in enumerate(all_arrays[:20], 1):
            size_kb = item['size'] / 1024
            array_type = item['type']

            print(f"\n[{i}] {array_type}[] - {size_kb:.2f} KB")

            # Show holder chain
            chain = item['holder_chain']
            print(f"    持有者链:")
            for j, obj in enumerate(chain[:5]):  # Limit depth
                indent = "    " + "  " * j
                class_name = obj.get('class_name', 'unknown')
                markers = []
                if obj.get('is_gc_root'):
                    markers.append(f"GC Root")
                if obj.get('is_interesting'):
                    markers.append("★")

                marker_str = f" {markers}" if markers else ""
                print(f"{indent}└─ {class_name}{marker_str}")

    def print_bitmap_analysis(self, top_n=10):
        """Print enhanced Bitmap analysis results"""
        if not self.bitmap_info:
            print("\n=== Bitmap 分析 ===")
            print("未检测到 Bitmap 对象")
            return

        total_bitmap_mem = sum(info['estimated_size'] for info in self.bitmap_info.values())

        print(f"\n{'='*80}")
        print("=== Bitmap 深度分析 ===")
        print(f"{'='*80}")
        print(f"Bitmap 总数: {len(self.bitmap_info)}")
        print(f"Bitmap 总内存: {total_bitmap_mem/1024/1024:.2f} MB (Native 内存，不计入 Java Heap)")

        # Print top bitmaps
        print(f"\n--- TOP {top_n} 最大 Bitmap ---")

        sorted_bitmaps = sorted(self.bitmap_info.items(),
                               key=lambda x: x[1]['estimated_size'], reverse=True)

        for i, (obj_id, info) in enumerate(sorted_bitmaps[:top_n], 1):
            size_str = f"{info['width']}x{info['height']}"
            mem_mb = info['estimated_size'] / 1024 / 1024
            density = info.get('density', 0)
            is_mutable = info.get('is_mutable', False)
            is_recycled = info.get('is_recycled', False)

            # Status flags
            flags = []
            if is_mutable:
                flags.append("可变")
            if is_recycled:
                flags.append("⚠️ 已回收")
            flag_str = f" [{', '.join(flags)}]" if flags else ""

            print(f"\n[{i}] {size_str} - {mem_mb:.2f} MB{flag_str}")
            if density > 0:
                print(f"    密度: {density} dpi")

            # Show holder chain
            chain = info.get('holder_chain', [])
            if chain and len(chain) > 1:
                print(f"    持有者:")
                for j, obj in enumerate(chain[1:4]):  # Skip bitmap itself, show up to 3
                    class_name = obj.get('class_name', 'unknown')
                    markers = []
                    if obj.get('is_app_class'):
                        markers.append("🔴 App")
                    marker_str = f" {markers}" if markers else ""
                    print(f"      └─ {class_name}{marker_str}")

        # Print duplicate bitmaps
        if hasattr(self, 'duplicate_bitmaps') and self.duplicate_bitmaps:
            print(f"\n--- 可能重复的 Bitmap（相同尺寸）---")
            print("提示: 相同尺寸的 Bitmap 可能是重复加载，考虑使用缓存")

            for dup in self.duplicate_bitmaps[:5]:
                width, height = dup['size']
                count = dup['count']
                wasted_mb = dup['total_wasted'] / 1024 / 1024
                print(f"  {width}x{height}: {count} 个实例, 可能浪费 {wasted_mb:.2f} MB")

    def print_collection_analysis(self, top_n=10):
        """Print enhanced collection analysis results"""
        has_data = (hasattr(self, 'collection_analysis') and self.collection_analysis) or \
                   (hasattr(self, 'empty_collections') and self.empty_collections) or \
                   (hasattr(self, 'large_collections') and self.large_collections)

        if not has_data:
            return

        print(f"\n{'='*80}")
        print("=== 集合类深度分析 ===")
        print(f"{'='*80}")

        # Empty collections
        if hasattr(self, 'empty_collections') and self.empty_collections:
            total_empty = sum(count for _, count in self.empty_collections)
            print(f"\n--- 空集合统计 (共 {total_empty} 个) ---")
            print("提示: 空集合占用内存但不存储数据，考虑延迟初始化或使用 Collections.emptyXxx()")
            for name, count in self.empty_collections[:5]:
                short_name = name.split('.')[-1]
                print(f"  {short_name}: {count} 个空实例")

        # Large collections
        if hasattr(self, 'large_collections') and self.large_collections:
            print(f"\n--- 超大集合 TOP {min(top_n, len(self.large_collections))} (>1000 元素) ---")
            print("提示: 超大集合可能是缓存或数据累积，检查是否需要清理")
            for i, item in enumerate(self.large_collections[:top_n], 1):
                short_name = item['class_name'].split('.')[-1]
                print(f"\n[{i}] {short_name}: {item['size']:,} 个元素")

                chain = item.get('holder_chain', [])
                if chain and len(chain) > 1:
                    print(f"    持有者:")
                    for obj in chain[1:3]:
                        class_name = obj.get('class_name', 'unknown')
                        markers = []
                        if obj.get('is_app_class'):
                            markers.append("🔴 App")
                        marker_str = f" {markers}" if markers else ""
                        print(f"      └─ {class_name}{marker_str}")

        # Over-allocated collections
        if hasattr(self, 'collection_analysis') and self.collection_analysis:
            print(f"\n--- 容量过度分配 TOP {min(top_n, len(self.collection_analysis))} ---")
            print("提示: 初始容量过大会浪费内存，考虑使用合适的初始容量")
            print(f"{'类名':<30} {'实际大小':<10} {'容量':<10} {'利用率':<10} {'浪费'}")
            print("-" * 70)

            for item in self.collection_analysis[:top_n]:
                short_name = item['class_name'].split('.')[-1]
                print(f"{short_name:<30} {item['size']:<10} {item['capacity']:<10} "
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

    def export_large_byte_arrays(self, f):
        """Export large byte[] analysis to file"""
        if not self.large_byte_arrays:
            return

        f.write("=" * 80 + "\n")
        f.write("TOP 大 byte[] 分析 (谁持有了这些内存?)\n")
        f.write("=" * 80 + "\n\n")

        for i, item in enumerate(self.large_byte_arrays, 1):
            size_kb = item['size'] / 1024
            size_mb = item['size'] / 1024 / 1024
            size_str = f"{size_mb:.2f} MB" if size_mb >= 1 else f"{size_kb:.2f} KB"

            f.write(f"[{i}] byte[] - {size_str}\n")
            f.write(f"    推断用途: {item['usage']}\n")
            f.write(f"    持有者链:\n")

            for j, obj in enumerate(item['holder_chain']):
                indent = "    " + "  " * j
                class_name = obj.get('class_name', 'unknown')
                markers = []
                if obj.get('is_gc_root'):
                    markers.append(f"GC Root: {obj.get('gc_root_type', 'UNKNOWN')}")
                if obj.get('is_interesting'):
                    markers.append("★ 业务对象")
                marker_str = f" [{', '.join(markers)}]" if markers else ""
                f.write(f"{indent}└─ {class_name}{marker_str}\n")
            f.write("\n")

    def export_large_strings(self, f):
        """Export large String analysis to file"""
        if not self.large_strings:
            return

        f.write("=" * 80 + "\n")
        f.write("TOP 大 String 分析 (实际内容是什么?)\n")
        f.write("=" * 80 + "\n\n")

        for i, item in enumerate(self.large_strings, 1):
            size_kb = item['size'] / 1024
            content = item.get('content', '')

            if content:
                display_content = content.replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
                if len(display_content) > 200:
                    display_content = display_content[:200] + '...'
            else:
                display_content = '<无法解码>'

            f.write(f"[{i}] String - {size_kb:.2f} KB\n")
            f.write(f"    内容: \"{display_content}\"\n")

            chain = item['holder_chain']
            if len(chain) > 1:
                for obj in chain[1:]:
                    class_name = obj.get('class_name', 'unknown')
                    if class_name != 'java.lang.String':
                        f.write(f"    持有者: {class_name}\n")
                        break
            f.write("\n")

    def export_large_int_arrays(self, f):
        """Export large int[]/long[] analysis to file"""
        if not self.large_int_arrays and not self.large_long_arrays:
            return

        f.write("=" * 80 + "\n")
        f.write("TOP 大 int[]/long[] 分析\n")
        f.write("=" * 80 + "\n\n")

        all_arrays = []
        for item in self.large_int_arrays:
            item['type'] = 'int'
            all_arrays.append(item)
        for item in self.large_long_arrays:
            item['type'] = 'long'
            all_arrays.append(item)

        all_arrays.sort(key=lambda x: x['size'], reverse=True)

        for i, item in enumerate(all_arrays[:20], 1):
            size_kb = item['size'] / 1024
            f.write(f"[{i}] {item['type']}[] - {size_kb:.2f} KB\n")
            f.write(f"    持有者链:\n")

            for j, obj in enumerate(item['holder_chain'][:5]):
                indent = "    " + "  " * j
                class_name = obj.get('class_name', 'unknown')
                markers = []
                if obj.get('is_gc_root'):
                    markers.append("GC Root")
                if obj.get('is_interesting'):
                    markers.append("★")
                marker_str = f" {markers}" if markers else ""
                f.write(f"{indent}└─ {class_name}{marker_str}\n")
            f.write("\n")

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
                # Phase 6: Deep Insight Analysis (most valuable for developers)
                self.export_large_byte_arrays(f)
                self.export_large_strings(f)
                self.export_large_int_arrays(f)

                # Dominator Tree Top
                f.write("\nTOP 30 Retained Size:\n")
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

    def export_markdown(self, output_file, deep_analysis=True):
        """Export analysis results to Markdown format with collapsible sections"""
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("# Android HPROF 深度内存分析报告\n\n")
            f.write(f"**分析时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  \n")
            f.write(f"**HPROF文件**: `{os.path.basename(self.filename)}`\n\n")

            # App Package Info
            if self.app_package:
                f.write(f"**App 包名**: `{self.app_package}`\n\n")

            f.write("---\n\n")

            # Table of Contents
            f.write("## 目录\n\n")
            f.write("- [内存概览](#内存概览)\n")
            f.write("- [优化建议](#优化建议)\n")
            if deep_analysis:
                f.write("- [大对象分析](#大对象分析)\n")
                f.write("  - [TOP 大 byte[]](#top-大-byte)\n")
                f.write("  - [TOP 大 String](#top-大-string)\n")
                f.write("  - [Bitmap 分析](#bitmap-分析)\n")
                f.write("- [集合类分析](#集合类分析)\n")
                f.write("- [LruCache 分析](#lrucache-分析)\n")
                f.write("- [内存泄漏嫌疑](#内存泄漏嫌疑)\n")
            f.write("- [包统计](#包统计)\n")
            f.write("- [类统计](#类统计)\n\n")

            f.write("---\n\n")

            # Memory Overview
            f.write("## 内存概览\n\n")
            total_memory = (self.total_instance_size + self.total_array_size) / 1024 / 1024
            f.write(f"| 指标 | 值 |\n")
            f.write(f"|------|----|\n")
            f.write(f"| 总内存使用 | **{total_memory:.2f} MB** |\n")
            f.write(f"| 实例数 | {self.total_instances:,} |\n")
            f.write(f"| 实例大小 | {self.total_instance_size / 1024 / 1024:.2f} MB |\n")
            f.write(f"| 数组数 | {self.total_arrays:,} |\n")
            f.write(f"| 数组大小 | {self.total_array_size / 1024 / 1024:.2f} MB |\n")
            f.write(f"| GC Roots | {len(self.gc_roots):,} |\n\n")

            # GC Root Statistics (collapsible)
            f.write("<details>\n<summary>GC Root 类型分布</summary>\n\n")
            f.write("| 类型 | 数量 |\n")
            f.write("|------|------|\n")
            for root_type, obj_ids in sorted(self.gc_root_types.items(),
                                             key=lambda x: len(x[1]), reverse=True):
                type_name = self.GC_ROOT_NAMES.get(root_type, f'UNKNOWN_{root_type}')
                f.write(f"| {type_name} | {len(obj_ids):,} |\n")
            f.write("\n</details>\n\n")

            f.write("---\n\n")

            # Optimization Suggestions
            f.write("## 优化建议\n\n")
            self._write_markdown_suggestions(f)

            if deep_analysis:
                f.write("---\n\n")

                # Large Objects Analysis
                f.write("## 大对象分析\n\n")

                # Large byte[]
                f.write("### TOP 大 byte[]\n\n")
                if hasattr(self, 'large_byte_arrays') and self.large_byte_arrays:
                    for i, item in enumerate(self.large_byte_arrays[:10], 1):
                        size = item['size']
                        usage = item.get('usage', '未知')
                        holder_chain = item.get('holder_chain', [])
                        f.write(f"**[{i}]** `byte[]` - **{size/1024:.2f} KB**\n")
                        f.write(f"- 推断用途: {usage}\n")
                        if holder_chain:
                            f.write("- 持有者链:\n")
                            for j, info in enumerate(holder_chain[:5]):
                                indent = "  " * (j + 1)
                                class_name = info.get('class_name', 'unknown')
                                marker = ""
                                if info.get('is_gc_root'):
                                    marker = f" `[GC Root: {info.get('gc_root_type', 'UNKNOWN')}]`"
                                elif info.get('is_app_class'):
                                    marker = " ⭐"
                                f.write(f"{indent}- `{class_name}`{marker}\n")
                        f.write("\n")
                else:
                    f.write("*未检测到大 byte[]*\n\n")

                # Large String
                f.write("### TOP 大 String\n\n")
                if hasattr(self, 'large_strings') and self.large_strings:
                    for i, item in enumerate(self.large_strings[:10], 1):
                        size = item['size']
                        content = item.get('content', '')
                        display_content = content[:100].replace('\n', '\\n').replace('|', '\\|') if content else "<无法解码>"
                        f.write(f"**[{i}]** String - **{size/1024:.2f} KB**\n")
                        f.write(f"```\n{display_content}...\n```\n\n")
                else:
                    f.write("*未检测到大 String*\n\n")

                # Bitmap Analysis
                f.write("### Bitmap 分析\n\n")
                if self.bitmap_info:
                    f.write("| # | 尺寸 | 内存估算 | Config |\n")
                    f.write("|---|------|----------|--------|\n")
                    sorted_bitmaps = sorted(self.bitmap_info.items(),
                                           key=lambda x: x[1]['estimated_size'], reverse=True)
                    for i, (obj_id, info) in enumerate(sorted_bitmaps[:15], 1):
                        size_str = f"{info['width']}x{info['height']}"
                        mem_mb = info['estimated_size']/1024/1024
                        config = info.get('config', 'ARGB_8888')
                        f.write(f"| {i} | {size_str} | {mem_mb:.2f} MB | {config} |\n")
                    f.write("\n")

                    # Duplicate bitmaps
                    if hasattr(self, 'duplicate_bitmaps') and self.duplicate_bitmaps:
                        f.write("<details>\n<summary>重复 Bitmap 检测</summary>\n\n")
                        for dup in self.duplicate_bitmaps[:10]:
                            f.write(f"- **{dup['dimensions']}**: {dup['count']} 个相同尺寸，浪费 {dup['total_wasted']/1024:.1f} KB\n")
                        f.write("\n</details>\n\n")
                else:
                    f.write("*未检测到 Bitmap 对象*\n\n")

                f.write("---\n\n")

                # Collection Analysis
                f.write("## 集合类分析\n\n")

                # Empty collections
                if hasattr(self, 'empty_collections') and self.empty_collections:
                    total_empty = sum(count for _, count in self.empty_collections)
                    f.write(f"### 空集合统计 (共 {total_empty} 个)\n\n")
                    f.write("| 类型 | 数量 |\n")
                    f.write("|------|------|\n")
                    for name, count in self.empty_collections[:10]:
                        short_name = name.split('.')[-1]
                        f.write(f"| {short_name} | {count} |\n")
                    f.write("\n")

                # Large collections
                if hasattr(self, 'large_collections') and self.large_collections:
                    f.write(f"### 超大集合 (>1000 元素，共 {len(self.large_collections)} 个)\n\n")
                    f.write("<details>\n<summary>展开查看</summary>\n\n")
                    f.write("| 类型 | 元素数 |\n")
                    f.write("|------|--------|\n")
                    for item in self.large_collections[:20]:
                        short_name = item['class_name'].split('.')[-1]
                        f.write(f"| {short_name} | {item['size']:,} |\n")
                    f.write("\n</details>\n\n")

                f.write("---\n\n")

                # LruCache Analysis
                f.write("## LruCache 分析\n\n")
                if hasattr(self, 'lru_cache_analysis') and self.lru_cache_analysis:
                    f.write("| 类名 | 当前/最大 | 利用率 | 命中率 |\n")
                    f.write("|------|-----------|--------|--------|\n")
                    for cache in self.lru_cache_analysis[:10]:
                        short_name = cache['class_name'].split('.')[-1]
                        util = f"{cache['utilization']*100:.0f}%"
                        hit = f"{cache['hit_rate']*100:.0f}%" if cache['hitCount'] + cache['missCount'] > 0 else "N/A"
                        f.write(f"| {short_name} | {cache['size']:,}/{cache['maxSize']:,} | {util} | {hit} |\n")
                    f.write("\n")
                else:
                    f.write("*未检测到 LruCache 实例*\n\n")

                f.write("---\n\n")

                # Memory Leak Suspects
                f.write("## 内存泄漏嫌疑\n\n")
                if self.leak_suspects:
                    f.write(f"检测到 **{len(self.leak_suspects)}** 个可疑对象\n\n")
                    f.write("<details>\n<summary>展开查看详情</summary>\n\n")
                    for i, suspect in enumerate(self.leak_suspects[:15], 1):
                        f.write(f"### [{i}] {suspect['type']}\n\n")
                        f.write(f"{suspect['description']}\n")
                        if 'retained_size' in suspect:
                            f.write(f"- Retained Size: {suspect['retained_size']/1024/1024:.2f} MB\n")
                        f.write("\n")
                    f.write("</details>\n\n")
                else:
                    f.write("*未检测到明显的内存泄漏*\n\n")

            f.write("---\n\n")

            # Package Statistics
            f.write("## 包统计\n\n")
            f.write("<details>\n<summary>TOP 20 内存占用包</summary>\n\n")
            f.write("| 包名 | 实例数 | 大小 |\n")
            f.write("|------|--------|------|\n")
            sorted_packages = sorted(self.package_stats.items(),
                                   key=lambda x: x[1]['size'], reverse=True)
            for package, stats in sorted_packages[:20]:
                size_mb = stats['size'] / 1024 / 1024
                f.write(f"| {package} | {stats['count']:,} | {size_mb:.2f} MB |\n")
            f.write("\n</details>\n\n")

            # Class Statistics
            f.write("## 类统计\n\n")
            f.write("<details>\n<summary>TOP 30 内存占用类</summary>\n\n")
            f.write("| 类名 | 实例数 | 大小 |\n")
            f.write("|------|--------|------|\n")
            sorted_classes = sorted(self.class_stats.items(),
                                  key=lambda x: x[1]['size'], reverse=True)
            for class_name, stats in sorted_classes[:30]:
                size_mb = stats['size'] / 1024 / 1024
                short_name = class_name if len(class_name) < 50 else "..." + class_name[-47:]
                f.write(f"| `{short_name}` | {stats['count']:,} | {size_mb:.2f} MB |\n")
            f.write("\n</details>\n\n")

            f.write("---\n\n")
            f.write("*报告由 Android-App-Memory-Analysis 工具生成*\n")

    def _write_markdown_suggestions(self, f):
        """Write optimization suggestions in markdown format"""
        priority_high = []
        priority_medium = []
        priority_low = []

        # Check for memory leaks
        if hasattr(self, 'suspicious_holdings'):
            leaked = [h for h in self.suspicious_holdings if h['type'] == 'LEAKED_COMPONENT']
            if leaked:
                priority_high.append({
                    'issue': '检测到可能的内存泄漏',
                    'detail': f'{len(leaked)} 个 Activity/Fragment 被静态字段持有',
                    'suggestion': ['检查是否有 static 变量持有 Activity/Fragment 引用',
                                   '使用 WeakReference 替代强引用',
                                   '在 onDestroy() 中清理引用']
                })

        # Check for large bitmaps
        if self.bitmap_info:
            large_bitmaps = [b for b in self.bitmap_info.values() if b['estimated_size'] > 1024*1024]
            if large_bitmaps:
                total_mb = sum(b['estimated_size'] for b in large_bitmaps) / 1024 / 1024
                priority_medium.append({
                    'issue': '大尺寸 Bitmap',
                    'detail': f'{len(large_bitmaps)} 个 Bitmap 超过 1MB，共占用 {total_mb:.1f} MB',
                    'suggestion': ['使用 inSampleSize 降低图片分辨率',
                                   '使用 RGB_565 替代 ARGB_8888（节省 50% 内存）',
                                   '及时调用 recycle() 释放不用的 Bitmap']
                })

        # Check for empty collections
        if hasattr(self, 'empty_collections') and self.empty_collections:
            total_empty = sum(count for _, count in self.empty_collections)
            if total_empty > 100:
                priority_low.append({
                    'issue': '大量空集合',
                    'detail': f'{total_empty} 个空集合对象',
                    'suggestion': ['使用 Collections.emptyList()/emptyMap() 替代 new ArrayList()',
                                   '延迟初始化：需要时再创建集合']
                })

        # Check for large collections
        if hasattr(self, 'large_collections') and self.large_collections:
            priority_medium.append({
                'issue': '超大集合',
                'detail': f'{len(self.large_collections)} 个集合超过 1000 个元素',
                'suggestion': ['检查是否需要保存这么多数据',
                               '考虑分页加载或使用数据库',
                               '定期清理不需要的数据']
            })

        # Check for LruCache issues
        if hasattr(self, 'lru_cache_analysis') and self.lru_cache_analysis:
            low_hit = [c for c in self.lru_cache_analysis if c['hit_rate'] < 0.5 and (c['hitCount'] + c['missCount']) > 10]
            if low_hit:
                priority_medium.append({
                    'issue': 'LruCache 命中率低',
                    'detail': f'{len(low_hit)} 个缓存命中率低于 50%',
                    'suggestion': ['增加缓存容量 (maxSize)',
                                   '优化缓存键策略',
                                   '预加载常用数据']
                })

        # Write suggestions
        if priority_high:
            f.write("### 🔴 高优先级 (需立即处理)\n\n")
            for s in priority_high:
                f.write(f"**{s['issue']}**\n\n")
                f.write(f"> {s['detail']}\n\n")
                f.write("建议:\n")
                for sug in s['suggestion']:
                    f.write(f"- {sug}\n")
                f.write("\n")

        if priority_medium:
            f.write("### 🟡 中优先级 (建议优化)\n\n")
            for s in priority_medium:
                f.write(f"**{s['issue']}**\n\n")
                f.write(f"> {s['detail']}\n\n")
                f.write("建议:\n")
                for sug in s['suggestion']:
                    f.write(f"- {sug}\n")
                f.write("\n")

        if priority_low:
            f.write("### 🟢 低优先级 (可选优化)\n\n")
            for s in priority_low:
                f.write(f"**{s['issue']}**\n\n")
                f.write(f"> {s['detail']}\n\n")
                f.write("建议:\n")
                for sug in s['suggestion']:
                    f.write(f"- {sug}\n")
                f.write("\n")

        if not priority_high and not priority_medium and not priority_low:
            f.write("*未发现明显的内存优化点*\n\n")

    # ==================== HPROF Comparison ====================

    @staticmethod
    def compare(file1, file2, output_file=None, markdown=False):
        """Compare two HPROF files and show differences"""
        print(f"正在解析第一个 HPROF 文件: {file1}")
        parser1 = HprofParser(file1)
        parser1.parse(simple_mode=True, deep_analysis=True)

        print(f"\n正在解析第二个 HPROF 文件: {file2}")
        parser2 = HprofParser(file2)
        parser2.parse(simple_mode=True, deep_analysis=True)

        print("\n" + "="*80)
        print("=== HPROF 内存对比分析 ===")
        print("="*80)

        # Compare overall statistics
        mem1 = (parser1.total_instance_size + parser1.total_array_size) / 1024 / 1024
        mem2 = (parser2.total_instance_size + parser2.total_array_size) / 1024 / 1024
        mem_diff = mem2 - mem1
        mem_pct = (mem_diff / mem1 * 100) if mem1 > 0 else 0

        print(f"\n--- 内存概览对比 ---")
        print(f"{'指标':<20} {'文件1':<15} {'文件2':<15} {'变化':<15}")
        print("-" * 65)
        print(f"{'总内存':<20} {mem1:.2f} MB{'':<5} {mem2:.2f} MB{'':<5} {mem_diff:+.2f} MB ({mem_pct:+.1f}%)")

        inst1 = parser1.total_instances
        inst2 = parser2.total_instances
        inst_diff = inst2 - inst1
        print(f"{'实例数':<20} {inst1:,}{'':<5} {inst2:,}{'':<5} {inst_diff:+,}")

        arr1 = parser1.total_arrays
        arr2 = parser2.total_arrays
        arr_diff = arr2 - arr1
        print(f"{'数组数':<20} {arr1:,}{'':<5} {arr2:,}{'':<5} {arr_diff:+,}")

        # Compare top classes by size change
        print(f"\n--- 类内存变化 TOP 20 (按变化量排序) ---")
        print(f"{'类名':<50} {'文件1(MB)':<12} {'文件2(MB)':<12} {'变化(MB)':<12}")
        print("-" * 86)

        all_classes = set(parser1.class_stats.keys()) | set(parser2.class_stats.keys())
        class_changes = []
        for class_name in all_classes:
            stats1 = parser1.class_stats.get(class_name, {'count': 0, 'size': 0})
            stats2 = parser2.class_stats.get(class_name, {'count': 0, 'size': 0})
            size_diff = stats2['size'] - stats1['size']
            count_diff = stats2['count'] - stats1['count']
            if abs(size_diff) > 1024:  # Only show > 1KB changes
                class_changes.append({
                    'name': class_name,
                    'size1': stats1['size'],
                    'size2': stats2['size'],
                    'count1': stats1['count'],
                    'count2': stats2['count'],
                    'size_diff': size_diff,
                    'count_diff': count_diff
                })

        # Sort by absolute size change
        class_changes.sort(key=lambda x: abs(x['size_diff']), reverse=True)

        for item in class_changes[:20]:
            name = item['name'][:48] if len(item['name']) > 48 else item['name']
            s1 = item['size1'] / 1024 / 1024
            s2 = item['size2'] / 1024 / 1024
            diff = item['size_diff'] / 1024 / 1024
            marker = "📈" if diff > 0 else "📉"
            print(f"{name:<50} {s1:<12.2f} {s2:<12.2f} {marker} {diff:+.2f}")

        # Compare packages
        print(f"\n--- 包内存变化 TOP 10 ---")
        print(f"{'包名':<40} {'文件1(MB)':<12} {'文件2(MB)':<12} {'变化(MB)':<12}")
        print("-" * 76)

        all_packages = set(parser1.package_stats.keys()) | set(parser2.package_stats.keys())
        pkg_changes = []
        for pkg_name in all_packages:
            stats1 = parser1.package_stats.get(pkg_name, {'count': 0, 'size': 0})
            stats2 = parser2.package_stats.get(pkg_name, {'count': 0, 'size': 0})
            size_diff = stats2['size'] - stats1['size']
            if abs(size_diff) > 10240:  # Only show > 10KB changes
                pkg_changes.append({
                    'name': pkg_name,
                    'size1': stats1['size'],
                    'size2': stats2['size'],
                    'size_diff': size_diff
                })

        pkg_changes.sort(key=lambda x: abs(x['size_diff']), reverse=True)

        for item in pkg_changes[:10]:
            name = item['name'][:38] if len(item['name']) > 38 else item['name']
            s1 = item['size1'] / 1024 / 1024
            s2 = item['size2'] / 1024 / 1024
            diff = item['size_diff'] / 1024 / 1024
            marker = "📈" if diff > 0 else "📉"
            print(f"{name:<40} {s1:<12.2f} {s2:<12.2f} {marker} {diff:+.2f}")

        # Compare new leak suspects
        print(f"\n--- 新增泄漏嫌疑 ---")
        suspects1 = {(s['type'], s['class_name']) for s in parser1.leak_suspects if 'class_name' in s}
        suspects2 = {(s['type'], s['class_name']) for s in parser2.leak_suspects if 'class_name' in s}
        new_suspects = suspects2 - suspects1

        if new_suspects:
            print(f"⚠️  检测到 {len(new_suspects)} 个新的泄漏嫌疑:")
            for type_name, class_name in list(new_suspects)[:10]:
                print(f"  [{type_name}] {class_name}")
        else:
            print("✅ 未检测到新的泄漏嫌疑")

        # Summary
        print(f"\n--- 分析总结 ---")
        if mem_diff > 0:
            print(f"⚠️  内存增长 {mem_diff:.2f} MB ({mem_pct:.1f}%)")
            if class_changes and class_changes[0]['size_diff'] > 0:
                top = class_changes[0]
                print(f"   最大增长: {top['name']} (+{top['size_diff']/1024/1024:.2f} MB)")
        elif mem_diff < 0:
            print(f"✅ 内存减少 {abs(mem_diff):.2f} MB ({abs(mem_pct):.1f}%)")
        else:
            print("💡 内存使用基本持平")

        # Export comparison report
        if output_file:
            HprofParser._export_comparison(parser1, parser2, class_changes, pkg_changes,
                                          new_suspects, output_file, markdown)
            print(f"\n对比报告已导出到: {output_file}")

    @staticmethod
    def _export_comparison(parser1, parser2, class_changes, pkg_changes, new_suspects, output_file, markdown=False):
        """Export comparison results to file"""
        with open(output_file, 'w', encoding='utf-8') as f:
            if markdown:
                f.write("# HPROF 内存对比分析报告\n\n")
                f.write(f"**文件1**: `{os.path.basename(parser1.filename)}`  \n")
                f.write(f"**文件2**: `{os.path.basename(parser2.filename)}`  \n")
                f.write(f"**分析时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

                mem1 = (parser1.total_instance_size + parser1.total_array_size) / 1024 / 1024
                mem2 = (parser2.total_instance_size + parser2.total_array_size) / 1024 / 1024
                mem_diff = mem2 - mem1

                f.write("## 内存概览\n\n")
                f.write("| 指标 | 文件1 | 文件2 | 变化 |\n")
                f.write("|------|-------|-------|------|\n")
                f.write(f"| 总内存 | {mem1:.2f} MB | {mem2:.2f} MB | {mem_diff:+.2f} MB |\n")
                f.write(f"| 实例数 | {parser1.total_instances:,} | {parser2.total_instances:,} | {parser2.total_instances - parser1.total_instances:+,} |\n\n")

                f.write("## 类内存变化 TOP 20\n\n")
                f.write("| 类名 | 文件1 | 文件2 | 变化 |\n")
                f.write("|------|-------|-------|------|\n")
                for item in class_changes[:20]:
                    name = item['name'][-45:] if len(item['name']) > 45 else item['name']
                    s1 = item['size1'] / 1024 / 1024
                    s2 = item['size2'] / 1024 / 1024
                    diff = item['size_diff'] / 1024 / 1024
                    f.write(f"| `{name}` | {s1:.2f} MB | {s2:.2f} MB | {diff:+.2f} MB |\n")

                if new_suspects:
                    f.write("\n## 新增泄漏嫌疑\n\n")
                    for type_name, class_name in list(new_suspects)[:10]:
                        f.write(f"- **[{type_name}]** `{class_name}`\n")
            else:
                f.write("HPROF 内存对比分析报告\n")
                f.write("=" * 60 + "\n")
                f.write(f"文件1: {parser1.filename}\n")
                f.write(f"文件2: {parser2.filename}\n")
                f.write(f"分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

                mem1 = (parser1.total_instance_size + parser1.total_array_size) / 1024 / 1024
                mem2 = (parser2.total_instance_size + parser2.total_array_size) / 1024 / 1024
                mem_diff = mem2 - mem1

                f.write("内存概览:\n")
                f.write(f"  文件1 总内存: {mem1:.2f} MB\n")
                f.write(f"  文件2 总内存: {mem2:.2f} MB\n")
                f.write(f"  变化: {mem_diff:+.2f} MB\n\n")

                f.write("类内存变化 TOP 20:\n")
                for item in class_changes[:20]:
                    diff = item['size_diff'] / 1024 / 1024
                    f.write(f"  {item['name']}: {diff:+.2f} MB\n")

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


    def parse_basic(self):
        """
        Parse HPROF file without printing or deep analysis.
        Used for quick summary extraction in panorama analyzer.
        Returns True on success, False on failure.
        """
        try:
            self.openHprof(self.filename)
            self.readHead()
            self.readRecords()
            return True
        except Exception as e:
            print(f"解析HPROF文件失败: {e}")
            return False
        finally:
            if self.hprof:
                self.hprof.close()

    def get_summary(self, top_n=10):
        """
        Get a summary of HPROF analysis for panorama integration.
        Call parse_basic() first before calling this method.

        Returns a dict with:
        - total_instances: int
        - total_memory_mb: float
        - top_classes: list of (class_name, count, size_mb)
        - bitmap_count: int
        - bitmap_size_mb: float
        """
        total_memory_bytes = self.total_instance_size + self.total_array_size

        # Get top N classes by size
        sorted_classes = sorted(
            self.class_stats.items(),
            key=lambda x: x[1]['size'],
            reverse=True
        )[:top_n]

        top_classes = [
            {
                'name': class_name,
                'count': stats['count'],
                'size_mb': round(stats['size'] / 1024 / 1024, 2)
            }
            for class_name, stats in sorted_classes
        ]

        # Bitmap count from class_stats
        bitmap_stats = self.class_stats.get('android.graphics.Bitmap', {'count': 0, 'size': 0})

        return {
            'total_instances': self.total_instances,
            'total_arrays': self.total_arrays,
            'total_memory_mb': round(total_memory_bytes / 1024 / 1024, 2),
            'instance_size_mb': round(self.total_instance_size / 1024 / 1024, 2),
            'array_size_mb': round(self.total_array_size / 1024 / 1024, 2),
            'top_classes': top_classes,
            'bitmap_count': bitmap_stats['count'],
            'bitmap_size_mb': round(bitmap_stats['size'] / 1024 / 1024, 2),
        }


if __name__ == '__main__':
    arg_parser = argparse.ArgumentParser(description="Android HPROF 深度内存分析工具")
    arg_parser.add_argument('-f', '--file', required=True, help="HPROF文件路径")
    arg_parser.add_argument('-o', '--output', help="分析结果输出文件")
    arg_parser.add_argument('-t', '--top', type=int, default=20, help="显示TOP N个内存占用类 (默认20)")
    arg_parser.add_argument('-m', '--min-size', type=float, default=0.1, help="最小显示大小(MB) (默认0.1)")
    arg_parser.add_argument('-s', '--simple', action='store_true', help="简单输出模式")
    arg_parser.add_argument('--no-deep', action='store_true', help="禁用深度分析(更快但功能较少)")
    arg_parser.add_argument('--markdown', action='store_true', help="输出 Markdown 格式报告")
    arg_parser.add_argument('--compare', metavar='FILE2', help="与另一个 HPROF 文件对比分析")
    args = arg_parser.parse_args()

    if args.compare:
        # Comparison mode
        HprofParser.compare(args.file, args.compare, args.output, args.markdown)
    else:
        # Normal analysis mode
        parser = HprofParser(args.file)
        parser.parse(args.simple, args.top, args.min_size, args.output,
                     deep_analysis=not args.no_deep, markdown=args.markdown)
