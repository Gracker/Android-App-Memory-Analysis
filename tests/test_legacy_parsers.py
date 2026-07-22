import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

from tools.hprof_parser import HprofParser
from tools import smaps_parser


class HprofParserRegressionTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
