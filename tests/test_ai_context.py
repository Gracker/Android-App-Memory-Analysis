import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from android_memory_ai.catalog import CatalogError, load_catalog
from android_memory_ai.capture_manifest import build_capture_manifest, write_capture_manifest
from android_memory_ai.context import build_ai_context
from android_memory_ai.contracts import RUNTIME_NAME, RUNTIME_VERSION
from android_memory_ai.evidence import discover_artifacts
from android_memory_ai.guidance import infer_intent
from android_memory_ai.render import render_json, render_markdown
from tools.live_dumper import LiveDumper


MINIMAL_MEMINFO = """** MEMINFO in pid 1234 [com.example.app] **
 App Summary
                       Pss(KB)
                        ------
           Java Heap:     1024
         Native Heap:     2048
               TOTAL:     4096       TOTAL SWAP PSS: 0
"""


class CatalogTests(unittest.TestCase):
    def test_catalog_is_versioned_and_has_unique_records(self):
        catalog = load_catalog()
        self.assertEqual("1.0", catalog["schema_version"])
        record_ids = [record["id"] for record in catalog["records"]]
        self.assertGreaterEqual(len(record_ids), 10)
        self.assertEqual(len(record_ids), len(set(record_ids)))

    def test_catalog_rejects_missing_required_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.json"
            path.write_text(json.dumps({"schema_version": "1.0"}), encoding="utf-8")
            with self.assertRaises(CatalogError):
                load_catalog(path)

    def test_catalog_rejects_untraceable_sources_and_revision_drift(self):
        catalog = load_catalog()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.json"
            invalid_source = copy.deepcopy(catalog)
            invalid_source["records"][0]["sources"][0]["url"] = "http://example.com"
            path.write_text(json.dumps(invalid_source), encoding="utf-8")
            with self.assertRaises(CatalogError):
                load_catalog(path)

            invalid_revision = copy.deepcopy(catalog)
            invalid_revision["records"][0]["theory_origin"]["revision"] = "0" * 40
            path.write_text(json.dumps(invalid_revision), encoding="utf-8")
            with self.assertRaises(CatalogError):
                load_catalog(path)


class IntentTests(unittest.TestCase):
    def test_auto_intent_handles_chinese_and_english(self):
        intent, candidates = infer_intent("auto", "Native memory 和 JNI malloc 一直增长")
        self.assertEqual("native-memory", intent)
        self.assertIn("native-memory", candidates)
        self.assertIn("regression", candidates)

    def test_auto_intent_falls_back_to_quick_triage(self):
        intent, candidates = infer_intent("auto", "帮我看一下")
        self.assertEqual("quick-triage", intent)
        self.assertEqual([], candidates)

    def test_explicit_branch_does_not_suppress_a_growth_contract(self):
        intent, candidates = infer_intent(
            "native-memory",
            "Native allocation keeps growing",
        )
        self.assertEqual("native-memory", intent)
        self.assertEqual(["native-memory", "regression"], candidates)


class EvidenceContextTests(unittest.TestCase):
    def test_context_records_the_runtime_that_generated_it(self):
        with tempfile.TemporaryDirectory() as directory:
            context = build_ai_context(Path(directory))

        self.assertEqual(
            {"name": RUNTIME_NAME, "version": RUNTIME_VERSION},
            context["generator"],
        )

    def test_partial_meminfo_produces_bounded_context_and_collection_steps(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "meminfo.txt").write_text(MINIMAL_MEMINFO, encoding="utf-8")
            context = build_ai_context(root, question="请快速分析")

        self.assertEqual("quick-triage", context["request"]["intent"])
        self.assertEqual("limited", context["analysis_contract"]["support_level"])
        self.assertEqual("com.example.app", context["subject"]["package"])
        self.assertFalse(context["analysis_contract"]["privacy"]["raw_contents_embedded"])
        self.assertNotIn(MINIMAL_MEMINFO, render_json(context))
        gap_types = {gap["artifact_type"] for gap in context["next_evidence"]}
        self.assertIn("device_context", gap_types)
        self.assertIn("smaps", gap_types)

    def test_malformed_named_artifact_is_not_counted_as_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "meminfo.txt").write_text(MINIMAL_MEMINFO, encoding="utf-8")
            (root / "smaps.txt").write_text("not really smaps\n", encoding="utf-8")
            context = build_ai_context(root, intent="native-memory")

        smaps = next(
            artifact
            for artifact in context["evidence"]["artifacts"]
            if artifact["artifact_type"] == "smaps"
        )
        self.assertEqual("invalid", smaps["status"])
        self.assertEqual("insufficient", context["analysis_contract"]["support_level"])
        self.assertTrue(context["limitations"])

    def test_package_conflicts_are_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "meta.txt").write_text(
                "Package: com.expected.app\nPID: 1234\nAndroidSdk: 37\n",
                encoding="utf-8",
            )
            (root / "meminfo.txt").write_text(
                MINIMAL_MEMINFO.replace("com.example.app", "com.other.app"),
                encoding="utf-8",
            )
            context = build_ai_context(root)

        self.assertEqual("com.expected.app", context["subject"]["package"])
        conflicts = context["evidence"]["conflicts"]
        self.assertTrue(any(conflict["field"] == "package" for conflict in conflicts))

    def test_external_explicit_paths_are_redacted_but_context_is_parsed(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as external:
            root = Path(directory)
            external_path = Path(external) / "device.txt"
            external_path.write_text(
                "BuildFingerprint: vendor/device/build\nAndroidSdk: 37\n",
                encoding="utf-8",
            )
            context = build_ai_context(
                root,
                artifact_overrides={"device_context": str(external_path)},
            )

        device = next(
            artifact
            for artifact in context["evidence"]["artifacts"]
            if artifact["artifact_type"] == "device_context"
        )
        self.assertEqual("<external>/device.txt", device["path"])
        self.assertNotIn(str(Path(external).parent), json.dumps(context))
        self.assertEqual(37, context["subject"]["android_sdk"])
        self.assertEqual("vendor/device/build", context["subject"]["build_fingerprint"])
        self.assertFalse(context["analysis_contract"]["privacy"]["local_paths_included"])

    def test_local_paths_require_explicit_opt_in(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as external:
            root = Path(directory)
            external_path = Path(external) / "device.txt"
            external_path.write_text(
                "BuildFingerprint: vendor/device/build\nAndroidSdk: 37\n",
                encoding="utf-8",
            )
            context = build_ai_context(
                root,
                artifact_overrides={"device_context": str(external_path)},
                include_local_paths=True,
            )

        device = next(
            artifact
            for artifact in context["evidence"]["artifacts"]
            if artifact["artifact_type"] == "device_context"
        )
        self.assertEqual(str(external_path.resolve()), device["path"])
        self.assertEqual(str(root.resolve()), context["evidence"]["root"])
        self.assertTrue(context["analysis_contract"]["privacy"]["local_paths_included"])

    def test_missing_external_override_is_redacted(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as external:
            root = Path(directory)
            missing = Path(external) / "missing.hprof"
            context = build_ai_context(
                root,
                artifact_overrides={"hprof": str(missing)},
            )

        hprof = next(
            artifact
            for artifact in context["evidence"]["artifacts"]
            if artifact["artifact_type"] == "hprof"
        )
        self.assertEqual("<external>/missing.hprof", hprof["path"])
        self.assertNotIn(str(external), json.dumps(context))

    def test_native_coverage_separates_mapping_and_owner_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "meminfo.txt").write_text(MINIMAL_MEMINFO, encoding="utf-8")
            context = build_ai_context(root, intent="native-memory")

        gaps = {gap["artifact_type"]: gap for gap in context["next_evidence"]}
        self.assertEqual("one-of", gaps["smaps"]["priority"])
        self.assertEqual("one-of", gaps["showmap"]["priority"])
        self.assertEqual("supporting", gaps["native_heap_profile"]["priority"])
        self.assertIn("device_context", gaps)
        self.assertIn("phase_metadata", gaps)
        self.assertIn("run_config.txt", gaps["phase_metadata"]["command"])
        self.assertIn("process_role", gaps["phase_metadata"]["command"])
        self.assertIn("user_profile", gaps["phase_metadata"]["command"])
        self.assertIn(
            "$ANDROID_MEMORY_ANALYSIS_ROOT",
            gaps["native_heap_profile"]["command"],
        )

    def test_mixed_growth_question_evaluates_native_and_regression_contracts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "meminfo.txt").write_text(MINIMAL_MEMINFO, encoding="utf-8")
            (root / "smaps.txt").write_text(
                "70000000-70001000 rw-p 00000000 00:00 0 [anon:scudo:primary]\n"
                "Pss: 4 kB\n",
                encoding="utf-8",
            )
            context = build_ai_context(
                root,
                question="Native memory keeps growing",
            )

        self.assertEqual("native-memory", context["request"]["intent"])
        self.assertEqual(
            ["native-memory", "regression"],
            context["request"]["evaluated_intents"],
        )
        self.assertEqual("insufficient", context["analysis_contract"]["support_level"])
        self.assertEqual(
            "limited",
            context["analysis_contract"]["primary_intent_support_level"],
        )
        gap_types = {gap["artifact_type"] for gap in context["next_evidence"]}
        self.assertIn("comparison_report", gap_types)
        self.assertIn("phase_metadata", gap_types)

    def test_regression_requires_a_comparison_not_a_single_meminfo(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "meminfo.txt").write_text(MINIMAL_MEMINFO, encoding="utf-8")
            (root / "run_config.txt").write_text(
                "timestamp_utc=2026-07-21T12:00:00Z\npackage=com.example.app\n"
                "pid=1234\nprocess_role=main\nuser_profile=0\nscenario=open-close\n"
                "phase=after\nloops=5\ncooldown_seconds=30\n"
                "collection_mode=meminfo-local\nperturbation=low\n",
                encoding="utf-8",
            )
            context = build_ai_context(root, intent="regression")

        self.assertEqual("insufficient", context["analysis_contract"]["support_level"])
        self.assertIn(
            "comparison_report",
            context["evidence"]["coverage"]["missing_required"],
        )
        self.assertNotIn(
            "phase_metadata",
            context["evidence"]["coverage"]["inadequate"],
        )

    def test_discovery_prefers_a_valid_later_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "manifest.json").write_text("{}", encoding="utf-8")
            (root / "getprop.txt").write_text(
                "[ro.build.fingerprint]: [vendor/device/build]\n",
                encoding="utf-8",
            )
            artifacts = discover_artifacts(root)

        device = next(item for item in artifacts if item.artifact_type == "device_context")
        self.assertEqual("ok", device.status)
        self.assertEqual("getprop.txt", device.path)

    def test_existing_demo_is_supported_and_attaches_unversioned_report_boundary(self):
        root = Path(__file__).resolve().parent.parent / "demo" / "smaps_sample"
        context = build_ai_context(root, intent="quick-triage")
        self.assertIn(
            context["analysis_contract"]["support_level"],
            ("supported", "strong"),
        )
        reports = context["evidence"]["derived_reports"]
        self.assertTrue(reports)
        self.assertEqual("unversioned", reports[0]["schema_version"])
        self.assertIn("hprof", reports[0]["unverified_dependencies"])

    def test_markdown_uses_same_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "meminfo.txt").write_text(MINIMAL_MEMINFO, encoding="utf-8")
            context = build_ai_context(root)
        markdown = render_markdown(context, "zh")
        self.assertIn("Android 内存 AI 证据上下文", markdown)
        self.assertIn("accounting-ledgers-are-not-additive", markdown)
        self.assertIn("下一步补证", markdown)

    def test_demo_markdown_includes_bounded_derived_report_summary(self):
        root = Path(__file__).resolve().parent.parent / "demo" / "smaps_sample"
        markdown = render_markdown(build_ai_context(root), "zh")
        self.assertIn("派生分析摘要", markdown)
        self.assertIn("Report has no schema_version", markdown)

    def test_derived_report_summary_has_a_size_and_depth_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "meminfo.txt").write_text(MINIMAL_MEMINFO, encoding="utf-8")
            report = {
                "memory_overview": {"total_pss_kb": 4096},
                "recommendations": ["x" * 3000 for _ in range(100)],
            }
            (root / "panorama.json").write_text(json.dumps(report), encoding="utf-8")
            context = build_ai_context(root)

        derived = context["evidence"]["derived_reports"][0]
        self.assertTrue(derived["summary_truncated"])
        self.assertLess(len(json.dumps(derived["summary"])), 120000)
        self.assertTrue(any("context budget" in item for item in derived["limitations"]))


class SkillDistributionTests(unittest.TestCase):
    def test_bundled_runtime_matches_the_canonical_sources(self):
        root = Path(__file__).resolve().parent.parent
        result = subprocess.run(
            [sys.executable, str(root / "scripts" / "sync_skill_runtime.py"), "--check"],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_copied_evidence_skill_runs_without_repo_or_environment(self):
        root = Path(__file__).resolve().parent.parent
        source_skill = root / "skills" / "android-memory-evidence"
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "project with spaces"
            installed_skill = project / ".agents" / "skills" / source_skill.name
            installed_skill.parent.mkdir(parents=True)
            shutil.copytree(str(source_skill), str(installed_skill))

            evidence = project / "evidence"
            evidence.mkdir()
            device_context = evidence / "device.txt"
            device_context.write_text(
                "BuildFingerprint: vendor/device/public-install\nAndroidSdk: 37\n",
                encoding="utf-8",
            )
            output = project / "context.json"
            environment = os.environ.copy()
            environment["ANDROID_MEMORY_ANALYSIS_ROOT"] = str(project / "missing-checkout")
            environment.pop("PYTHONPATH", None)
            result = subprocess.run(
                [
                    sys.executable,
                    str(installed_skill / "scripts" / "build_context.py"),
                    "--dump-dir",
                    "evidence",
                    "--device-context",
                    "evidence/device.txt",
                    "--question",
                    "Please triage this partial capture",
                    "--output",
                    str(output),
                ],
                cwd=str(project),
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            context = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(
            {"name": RUNTIME_NAME, "version": RUNTIME_VERSION},
            context["generator"],
        )
        self.assertEqual(37, context["subject"]["android_sdk"])
        self.assertEqual(
            "vendor/device/public-install",
            context["subject"]["build_fingerprint"],
        )
        self.assertFalse(context["analysis_contract"]["privacy"]["local_paths_included"])

    def test_invalid_explicit_repo_fails_instead_of_masking_the_error(self):
        root = Path(__file__).resolve().parent.parent
        helper = root / "skills" / "android-memory-evidence" / "scripts" / "build_context.py"
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [
                    sys.executable,
                    str(helper),
                    "--repo",
                    directory,
                    "--dump-dir",
                    directory,
                ],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(1, result.returncode)
        self.assertIn("--repo does not contain", result.stderr)


class CaptureManifestTests(unittest.TestCase):
    def test_manifest_distinguishes_ok_skipped_and_not_collected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            meminfo = root / "meminfo.txt"
            meminfo.write_text(MINIMAL_MEMINFO, encoding="utf-8")
            files = _capture_files(root)
            manifest = build_capture_manifest(
                root,
                "com.example.app",
                "1234",
                "20260721_120000",
                {"meminfo": str(meminfo)},
                files,
                "running",
                True,
            )

        statuses = {item["artifact_type"]: item["status"] for item in manifest["artifacts"]}
        self.assertEqual("ok", statuses["meminfo"])
        self.assertEqual("skipped", statuses["hprof"])
        self.assertEqual("not_collected", statuses["smaps"])
        self.assertFalse(manifest["collection"]["natural_baseline"])

    def test_context_preserves_capture_outcomes_and_subject_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            meminfo = root / "meminfo.txt"
            meminfo.write_text(MINIMAL_MEMINFO, encoding="utf-8")
            sdk = root / "android_sdk.txt"
            sdk.write_text("37\n", encoding="utf-8")
            fingerprint = root / "build_fingerprint.txt"
            fingerprint.write_text("vendor/device/build\n", encoding="utf-8")
            files = _capture_files(root)
            manifest = build_capture_manifest(
                root,
                "com.example.app",
                "1234",
                "20260721_120000",
                {"meminfo": str(meminfo), "android_sdk": str(sdk), "build_fingerprint": str(fingerprint)},
                files,
                "running",
                True,
            )
            write_capture_manifest(root / "manifest.json", manifest)
            context = build_ai_context(root, intent="native-memory")

        artifacts = {
            item["artifact_type"]: item
            for item in context["evidence"]["artifacts"]
        }
        self.assertEqual("skipped", artifacts["hprof"]["status"])
        self.assertEqual("not_collected", artifacts["smaps"]["status"])
        self.assertEqual("capture-manifest", artifacts["smaps"]["source"])
        self.assertEqual("single-diagnostic", context["subject"]["phase"])
        self.assertEqual(37, context["subject"]["android_sdk"])
        self.assertIn("phase_metadata", context["evidence"]["coverage"]["inadequate"])
        self.assertTrue(
            any(
                gap["artifact_type"] == "phase_metadata"
                for gap in context["next_evidence"]
            )
        )

    def test_live_collector_archives_permission_failures(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dumper = LiveDumper.__new__(LiveDumper)
            dumper._adb_shell_full = lambda command, timeout=30: (
                "",
                1,
                "cat: /proc/1234/smaps: Permission denied",
            )
            ok = dumper.dump_smaps(
                1234,
                str(root / "smaps.txt"),
                str(root / "smaps.err"),
            )
            self.assertFalse(ok)
            self.assertIn(
                "Permission denied",
                (root / "smaps.err").read_text(encoding="utf-8"),
            )
            files = _capture_files(root)
            manifest = build_capture_manifest(
                root,
                "com.example.app",
                "1234",
                "20260721_120000",
                {"smaps_error": str(root / "smaps.err")},
                files,
                "running",
                True,
            )
            smaps = next(
                item for item in manifest["artifacts"]
                if item["artifact_type"] == "smaps"
            )
            self.assertEqual("permission_denied", smaps["status"])
            self.assertEqual(64, len(smaps["error_sha256"]))


def _capture_files(root):
    return {
        "build_fingerprint": str(root / "build_fingerprint.txt"),
        "android_release": str(root / "android_release.txt"),
        "android_sdk": str(root / "android_sdk.txt"),
        "page_size": str(root / "page_size.txt"),
        "package_uid": str(root / "package_uid.txt"),
        "processes": str(root / "processes.txt"),
        "activity_processes": str(root / "activity_processes.txt"),
        "exit_info": str(root / "exit_info.txt"),
        "memory_limiter_status": str(root / "memory_limiter_status.txt"),
        "showmap": str(root / "showmap.txt"),
        "smaps": str(root / "smaps.txt"),
        "meminfo": str(root / "meminfo.txt"),
        "gfxinfo": str(root / "gfxinfo.txt"),
        "proc_meminfo": str(root / "proc_meminfo.txt"),
        "zram_swap": str(root / "zram_swap.txt"),
        "dmabuf": str(root / "dmabuf_debug.txt"),
        "hprof": str(root / "heap.hprof"),
    }


if __name__ == "__main__":
    unittest.main()
