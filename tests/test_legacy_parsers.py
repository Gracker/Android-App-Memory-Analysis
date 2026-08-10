import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

from tools.hprof_parser import HprofParser
from tools import smaps_parser
from tools.accounting_ledger import build_accounting_ledger_from_files
from tools.combined_analyzer import CombinedAnalyzer
from tools.meminfo_parser import MeminfoParser, parse_meminfo_file
from tools.memory_analyzer import MemoryAnalyzer


class HprofParserRegressionTests(unittest.TestCase):
    def test_gc_root_path_excludes_all_non_strong_reference_variants(self):
        cases = (
            ('java.lang.ref.WeakReference', None),
            ('java.lang.ref.SoftReference', None),
            ('java.lang.ref.PhantomReference', None),
            ('sun.misc.Cleaner', None),
            ('com.example.CustomCleanupReference', 'java.lang.ref.PhantomReference'),
        )

        for class_name, superclass_name in cases:
            with self.subTest(class_name=class_name):
                parser = HprofParser("unused.hprof")
                wrapper_class_id = 20
                parser.classes[wrapper_class_id] = {'name': class_name}
                parser.instances[2] = {'class_id': wrapper_class_id}

                if superclass_name:
                    superclass_id = 21
                    parser.classes[superclass_id] = {'name': superclass_name}
                    parser.class_fields[wrapper_class_id] = {
                        'super_class_id': superclass_id,
                    }

                parser.gc_roots[3] = {'type': parser.HEAP_TAG_ROOT_UNKNOWN}
                parser.incoming_refs[1].add(2)
                parser.incoming_refs[2].add(3)

                self.assertIsNone(parser.find_path_to_gc_root(1))
                self.assertEqual(
                    [1, 2, 3],
                    parser.find_path_to_gc_root(1, exclude_weak_refs=False),
                )

    def test_gc_root_path_keeps_ordinary_strong_reference_holders(self):
        parser = HprofParser("unused.hprof")
        parser.classes[20] = {'name': 'com.example.ReferenceCache'}
        parser.instances[2] = {'class_id': 20}
        parser.gc_roots[3] = {'type': parser.HEAP_TAG_ROOT_UNKNOWN}
        parser.incoming_refs[1].add(2)
        parser.incoming_refs[2].add(3)

        self.assertEqual([1, 2, 3], parser.find_path_to_gc_root(1))

    def test_markdown_export_formats_duplicate_bitmap_dimensions(self):
        parser = HprofParser("unused.hprof")
        parser.bitmap_info[1] = {
            'width': 100,
            'height': 200,
            'estimated_size': 80_000,
            'config': 'ARGB_8888',
        }
        parser.duplicate_bitmaps = [{
            'size': (100, 200),
            'count': 2,
            'bitmap_ids': [1, 2],
            'total_wasted': 80_000,
        }]

        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "report.md"
            parser.export_markdown(str(report_path))
            report = report_path.read_text(encoding="utf-8")

        self.assertIn("**100x200**: 2 个相同尺寸", report)

    def test_retained_size_handles_a_chain_deeper_than_the_recursion_limit(self):
        parser = HprofParser("unused.hprof")
        depth = sys.getrecursionlimit() + 500
        parser.shallow_sizes = {object_id: 1 for object_id in range(depth)}

        for object_id in range(depth - 1):
            parser.dominated_by[object_id].add(object_id + 1)

        parser.calculate_retained_sizes()

        self.assertEqual(depth, parser.retained_sizes[0])
        self.assertEqual(1, parser.retained_sizes[depth - 1])
        self.assertEqual(depth, len(parser.retained_sizes))


class SmapsParserRegressionTests(unittest.TestCase):
    def test_mapping_classification_uses_terminal_suffixes_and_strict_prefixes(self):
        cases = (
            (
                "/apex/com.android.art/lib64/libart.so",
                smaps_parser.HEAP_SO,
                smaps_parser.HEAP_UNKNOWN,
            ),
            (
                "/apex/com.android.art/lib64/libart.so (deleted)",
                smaps_parser.HEAP_SO,
                smaps_parser.HEAP_UNKNOWN,
            ),
            (
                "/apex/com.android.art/lib64/libdexfile.so",
                smaps_parser.HEAP_SO,
                smaps_parser.HEAP_UNKNOWN,
            ),
            (
                "/apex/com.android.art/javalib/core-libart.jar",
                smaps_parser.HEAP_JAR,
                smaps_parser.HEAP_UNKNOWN,
            ),
            (
                "/apex/com.android.art/javalib/boot-core-libart.vdex",
                smaps_parser.HEAP_DEX,
                smaps_parser.HEAP_DEX_BOOT_VDEX,
            ),
            (
                "/data/app/example/oat/arm64/base.vdex",
                smaps_parser.HEAP_DEX,
                smaps_parser.HEAP_DEX_APP_VDEX,
            ),
            (
                "/data/app/example/oat/arm64/base.odex",
                smaps_parser.HEAP_DEX,
                smaps_parser.HEAP_DEX_APP_DEX,
            ),
            (
                "/apex/com.android.art/javalib/boot-core-libart.oat",
                smaps_parser.HEAP_OAT,
                smaps_parser.HEAP_UNKNOWN,
            ),
            (
                "/apex/com.android.art/javalib/boot-core-libart.art",
                smaps_parser.HEAP_ART,
                smaps_parser.HEAP_ART_BOOT,
            ),
            (
                "/data/app/example/oat/arm64/base.art",
                smaps_parser.HEAP_ART,
                smaps_parser.HEAP_ART_APP,
            ),
            (
                "/data/app/classes.dexterity.map",
                smaps_parser.HEAP_UNKNOWN_MAP,
                smaps_parser.HEAP_UNKNOWN,
            ),
            (
                "/data/app/classes.dex_cache",
                smaps_parser.HEAP_UNKNOWN_MAP,
                smaps_parser.HEAP_UNKNOWN,
            ),
            (
                "/data/app/bootleg/base.vdex",
                smaps_parser.HEAP_DEX,
                smaps_parser.HEAP_DEX_APP_VDEX,
            ),
            (
                "/data/misc/apexdata/com.android.art/dalvik-cache/base.art",
                smaps_parser.HEAP_ART,
                smaps_parser.HEAP_ART_APP,
            ),
            (
                "[anon:dalvik-classes.dex extracted in memory from /data/app/base.apk]",
                smaps_parser.HEAP_DEX,
                smaps_parser.HEAP_DEX_APP_DEX,
            ),
            (
                "/devil/shared-buffer",
                smaps_parser.HEAP_UNKNOWN_MAP,
                smaps_parser.HEAP_UNKNOWN,
            ),
            (
                "/dev/foo/dev/ashmem/CursorWindow",
                smaps_parser.HEAP_UNKNOWN_DEV,
                smaps_parser.HEAP_UNKNOWN,
            ),
            (
                "/dev/ashmemory",
                smaps_parser.HEAP_UNKNOWN_DEV,
                smaps_parser.HEAP_UNKNOWN,
            ),
            (
                "/dev/ashmem/libc malloc",
                smaps_parser.HEAP_NATIVE,
                smaps_parser.HEAP_UNKNOWN,
            ),
            (
                "/dev/ashmem/dalvik-main space",
                smaps_parser.HEAP_DALVIK,
                smaps_parser.HEAP_DALVIK_NORMAL,
            ),
            (
                "/dev/ashmem/dalvik-LinearAlloc",
                smaps_parser.HEAP_DALVIK_OTHER,
                smaps_parser.HEAP_DALVIK_OTHER_LINEARALLOC,
            ),
        )

        for name, expected_heap, expected_subheap in cases:
            with self.subTest(name=name):
                self.assertEqual(
                    (expected_heap, expected_subheap),
                    smaps_parser.classify_mapping(name),
                )

    def test_anonymous_bss_only_inherits_an_adjacent_shared_object_mapping(self):
        sample = """1000-2000 r-xp 00000000 00:00 0 /system/lib64/libart.so
Pss:                  10 kB
2000-3000 rw-p 00000000 00:00 0
Pss:                  20 kB
4000-5000 rw-p 00000000 00:00 0
Pss:                  30 kB
5000-6000 r--p 00000000 00:00 0 /system/framework/core-libart.jar
Pss:                  40 kB
6000-7000 rw-p 00000000 00:00 0
Pss:                  50 kB
"""
        with tempfile.TemporaryDirectory() as directory:
            smaps_path = Path(directory) / "smaps"
            smaps_path.write_text(sample, encoding="utf-8")
            entries = list(smaps_parser.iter_smaps_entries(str(smaps_path)))
            summary = smaps_parser.parse_smaps_summary(str(smaps_path))
            with redirect_stdout(io.StringIO()):
                smaps_parser.parse_smaps(str(smaps_path))

        self.assertEqual(
            [
                smaps_parser.HEAP_SO,
                smaps_parser.HEAP_SO,
                smaps_parser.HEAP_UNKNOWN,
                smaps_parser.HEAP_JAR,
                smaps_parser.HEAP_UNKNOWN,
            ],
            [entry.heap_type for entry in entries],
        )
        self.assertEqual(30, smaps_parser.pss_count[smaps_parser.HEAP_SO])
        self.assertEqual(40, smaps_parser.pss_count[smaps_parser.HEAP_JAR])
        self.assertEqual(80, smaps_parser.pss_count[smaps_parser.HEAP_UNKNOWN])
        self.assertEqual(
            summary["total_pss_kb"],
            sum(smaps_parser.pss_count),
        )

    def test_summary_aggregates_do_not_classify_library_names_as_buffers(self):
        sample = """1000-2000 r-xp 00000000 00:00 0 /system/lib64/libdmabufheap.so
Pss:                  10 kB
2000-3000 r-xp 00000000 00:00 0 /system/lib64/libgpuhelper.so
Pss:                  20 kB
3000-4000 r--p 00000000 00:00 0 /dev/__properties__/vendor_gralloc_prop
Pss:                  30 kB
4000-5000 rw-s 00000000 00:09 1 /dmabuf:
Pss:                  40 kB
5000-6000 rw-s 00000000 00:00 0 /dev/kgsl-3d0
Pss:                  50 kB
6000-7000 r--p 00000000 00:00 0 /data/local/tmp/file.bin
Pss:                  60 kB
7000-8000 rw-s 00000000 00:00 0 /dev/dma_heap/system
Pss:                  70 kB
8000-9000 rw-s 00000000 00:00 0 /dev/ion
Pss:                  80 kB
"""
        with tempfile.TemporaryDirectory() as directory:
            smaps_path = Path(directory) / "smaps"
            smaps_path.write_text(sample, encoding="utf-8")
            summary = smaps_parser.parse_smaps_summary(str(smaps_path))

        aggregates = summary["aggregates"]
        self.assertEqual(40, aggregates["dmabuf_kb"])
        self.assertEqual(50, aggregates["graphics_kb"])
        self.assertEqual(90, aggregates["file_mapping_kb"])
        self.assertEqual(30, aggregates["code_kb"])

    def test_native_allocator_breakdown_covers_old_and_new_markers(self):
        sample = """1000-2000 rw-p 00000000 00:00 0 [anon:native]
Pss:                  10 kB
2000-3000 rw-p 00000000 00:00 0 /dev/ashmem/libc malloc
Pss:                  20 kB
3000-4000 rw-p 00000000 00:00 0 [anon:libc_malloc]
Pss:                  30 kB
4000-5000 rw-p 00000000 00:00 0 [anon:scudo:primary]
Pss:                  40 kB
5000-6000 rw-p 00000000 00:00 0 [anon:GWP-ASan]
Pss:                  50 kB
"""
        with tempfile.TemporaryDirectory() as directory:
            smaps_path = Path(directory) / "smaps"
            smaps_path.write_text(sample, encoding="utf-8")
            summary = smaps_parser.parse_smaps_summary(str(smaps_path))

        aggregates = summary["aggregates"]
        self.assertEqual(150, aggregates["native_heap_kb"])
        self.assertEqual(10, aggregates["native_legacy_heap_kb"])
        self.assertEqual(50, aggregates["native_libc_malloc_kb"])
        self.assertEqual(40, aggregates["native_scudo_kb"])
        self.assertEqual(50, aggregates["native_gwp_asan_kb"])

    def test_all_analyzers_consume_the_same_structured_classification(self):
        sample = """1000-2000 r-xp 00000000 00:00 0 /apex/com.android.art/lib64/libart.so
Pss:                  10 kB
2000-3000 r--p 00000000 00:00 0 /apex/com.android.art/javalib/boot.art
Pss:                  20 kB
3000-4000 rw-p 00000000 00:00 0 [anon:native]
Pss:                  30 kB
4000-5000 rw-p 00000000 00:00 0 [anon:dalvik-main space]
Pss:                  40 kB
5000-6000 rw-s 00000000 00:00 0 /dev/kgsl-3d0
Pss:                  50 kB
6000-7000 rw-s 00000000 00:09 1 /dmabuf:
Pss:                  60 kB
"""
        with tempfile.TemporaryDirectory() as directory:
            smaps_path = Path(directory) / "smaps"
            smaps_path.write_text(sample, encoding="utf-8")

            memory_analyzer = MemoryAnalyzer()
            with redirect_stdout(io.StringIO()):
                self.assertTrue(memory_analyzer.analyze_smaps(str(smaps_path)))
            metrics = memory_analyzer._build_smaps_metrics()

            combined = CombinedAnalyzer("unused.hprof", str(smaps_path))
            with redirect_stdout(io.StringIO()):
                combined_data = combined.parse_smaps()

        self.assertEqual(30, metrics["native_heap_total_kb"])
        self.assertEqual(10, metrics["native_code_kb"])
        self.assertEqual(50, metrics["gfx_dev_kb"])
        self.assertEqual(50, metrics["graphics_smaps_total_kb"])
        self.assertEqual(60, metrics["dmabuf_kb"])

        self.assertEqual(210, combined_data["total_pss_kb"])
        self.assertEqual(30, combined_data["native_heap_kb"])
        self.assertEqual(40, combined_data["dalvik_heap_kb"])
        self.assertEqual(40, combined_data["dalvik_normal_kb"])
        self.assertEqual(10, combined_data["so_kb"])
        self.assertEqual(20, combined_data["art_kb"])
        self.assertEqual(50, combined_data["graphics_kb"])
        self.assertEqual(60, combined_data["dmabuf_kb"])

    def test_anon_native_pss_and_swap_pss_are_reported_as_native(self):
        sample = """1000-2000 rw-p 00000000 00:00 0 [anon:native]
Pss:                 123 kB
SwapPss:               7 kB
"""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            smaps_path = root / "smaps"
            report_path = root / "report.txt"
            smaps_path.write_text(sample, encoding="utf-8")

            with redirect_stdout(io.StringIO()):
                smaps_parser.parse_smaps(str(smaps_path))
                smaps_parser.print_result(
                    SimpleNamespace(
                        pid=None,
                        output=str(report_path),
                        type="ALL",
                        simple=False,
                    )
                )

            report = report_path.read_text(encoding="utf-8")

        self.assertEqual(
            smaps_parser.HEAP_NATIVE,
            smaps_parser.match_type("[anon:native]", smaps_parser.HEAP_UNKNOWN),
        )
        self.assertIn("Native (本地C/C++代码内存) : 0.123 MB", report)
        self.assertIn("PSS: 0.123 MB", report)
        self.assertIn("SwapPSS: 0.007 MB", report)
        self.assertIn("[anon:native] : 123 kB", report)

    def test_structured_summary_preserves_main_type_subtype_and_row_mappings(self):
        sample = """1000-2000 rw-p 00000000 00:00 0 [anon:dalvik-main space]
Pss:                 123 kB
SwapPss:               7 kB
"""
        with tempfile.TemporaryDirectory() as directory:
            smaps_path = Path(directory) / "smaps"
            smaps_path.write_text(sample, encoding="utf-8")
            summary = smaps_parser.parse_smaps_summary(str(smaps_path))

        self.assertEqual(smaps_parser.HEAP_DALVIK, summary["by_type"][0]["type_id"])
        self.assertEqual(
            smaps_parser.HEAP_DALVIK_NORMAL,
            summary["by_subtype"][0]["type_id"],
        )
        self.assertEqual(
            "[anon:dalvik-main space]",
            summary["by_type"][0]["top_pss_mappings"][0]["name"],
        )


class MeminfoParserRegressionTests(unittest.TestCase):
    def test_demo_two_line_header_preserves_every_main_and_dalvik_row(self):
        root = Path(__file__).resolve().parent.parent / "demo" / "smaps_sample"
        data = parse_meminfo_file(str(root / "meminfo.txt"))

        self.assertEqual(19, len(data.categories))
        self.assertEqual(12, len(data.dalvik_details))
        self.assertEqual(
            [
                "pss_total_kb",
                "private_dirty_kb",
                "private_clean_kb",
                "swap_pss_kb",
                "rss_total_kb",
                "heap_size_kb",
                "heap_alloc_kb",
                "heap_free_kb",
            ],
            data.table_columns,
        )
        native = data.categories["Native Heap"]
        self.assertEqual(80860, native.pss_total)
        self.assertEqual(80824, native.private_dirty)
        self.assertEqual(25, native.swap_pss)
        self.assertEqual(139028, native.heap_size)
        self.assertEqual(48404, data.dalvik_details[".Heap"].pss_total)

    def test_full_legacy_header_maps_shared_and_private_columns_by_schema(self):
        content = """** MEMINFO in pid 42 [com.example] **
                   Pss      Pss   Shared  Private   Shared  Private     Swap      Rss     Heap     Heap     Heap
                 Total    Clean    Dirty    Dirty    Clean    Clean    Dirty    Total     Size    Alloc     Free
                ------   ------   ------   ------   ------   ------   ------   ------   ------   ------   ------
  Native Heap      100        1        2       90        3        4        5      110      200      150       50
        TOTAL      100        1        2       90        3        4        5      110      200      150       50

 App Summary
"""
        data = MeminfoParser(content).parse()
        native = data.categories["Native Heap"]

        self.assertEqual(1, native.pss_clean)
        self.assertEqual(2, native.shared_dirty)
        self.assertEqual(90, native.private_dirty)
        self.assertEqual(3, native.shared_clean)
        self.assertEqual(4, native.private_clean)
        self.assertEqual(5, native.swap_pss)
        self.assertEqual(110, native.rss_total)

    def test_header_schema_preserves_legacy_subset_without_shifting_columns(self):
        content = """** MEMINFO in pid 42 [com.example] **
                   Pss      Pss   Shared  Private   Shared  Private     Heap
                 Total    Clean    Dirty    Dirty    Clean    Clean     Size
                ------   ------   ------   ------   ------   ------   ------
  Native Heap      100        1        2       90        3        4      200
        TOTAL      100        1        2       90        3        4

 App Summary
"""
        data = MeminfoParser(content).parse()
        native = data.categories["Native Heap"]

        self.assertEqual(
            [
                "pss_total_kb",
                "pss_clean_kb",
                "shared_dirty_kb",
                "private_dirty_kb",
                "shared_clean_kb",
                "private_clean_kb",
                "heap_size_kb",
            ],
            data.table_columns,
        )
        self.assertEqual(90, native.private_dirty)
        self.assertEqual(4, native.private_clean)
        self.assertEqual(200, native.heap_size)
        self.assertEqual(0, native.swap_pss)
        self.assertEqual(0, native.rss_total)


class AccountingLedgerTests(unittest.TestCase):
    def test_demo_is_meminfo_first_and_smaps_supplements_every_comparable_row(self):
        root = Path(__file__).resolve().parent.parent / "demo" / "smaps_sample"
        ledger = build_accounting_ledger_from_files(
            str(root / "meminfo.txt"),
            str(root / "smaps"),
        )
        rows = {row["name"]: row for row in ledger["rows"]}

        self.assertEqual("meminfo-primary-smaps-supplemental", ledger["view"])
        self.assertEqual(19, len(ledger["rows"]))
        self.assertEqual("aligned", rows["Native Heap"]["comparison"]["status"])
        self.assertEqual(80860, rows["Native Heap"]["smaps"]["pss_kb"])
        self.assertEqual(
            80860,
            rows["Native Heap"]["smaps"]["allocator_breakdown"]["scudo_pss_kb"],
        )
        self.assertTrue(rows["Native Heap"]["smaps"]["top_pss_mappings"])
        self.assertEqual(
            "not-comparable",
            rows["EGL mtrack"]["comparison"]["status"],
        )
        self.assertEqual(
            "aligned",
            ledger["total_reconciliation"]["status"],
        )
        self.assertEqual(
            "smaps_total_pss_kb + meminfo_memtrack_only_pss_kb",
            ledger["total_reconciliation"]["formula"],
        )
        self.assertTrue(
            all(row["observations_zh"] for row in ledger["rows"])
        )


if __name__ == "__main__":
    unittest.main()
