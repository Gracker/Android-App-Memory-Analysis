import copy
import gzip
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
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


def minimal_png(width=1080, height=2400):
    return (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\x0dIHDR"
        + width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
    )


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

    def test_common_chinese_growth_wording_selects_regression(self):
        intent, candidates = infer_intent("auto", "QA 发现操作几轮以后内存变多了")
        self.assertEqual("regression", intent)
        self.assertEqual(["regression"], candidates)


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
        self.assertEqual(
            "unavailable",
            context["evidence"]["accounting_ledger"]["status"],
        )
        self.assertEqual(
            "meminfo-main-table-not-parsed",
            context["evidence"]["accounting_ledger"]["reason"],
        )

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

    def test_discovery_preserves_invalid_and_valid_context_candidates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "manifest.json").write_text("{}", encoding="utf-8")
            (root / "getprop.txt").write_text(
                "[ro.build.fingerprint]: [vendor/device/build]\n",
                encoding="utf-8",
            )
            artifacts = discover_artifacts(root)

        devices = [item for item in artifacts if item.artifact_type == "device_context"]
        self.assertEqual(
            {("manifest.json", "invalid"), ("getprop.txt", "ok")},
            {(item.path, item.status) for item in devices},
        )

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

    def test_demo_context_leads_with_meminfo_rows_and_smaps_supplements(self):
        root = Path(__file__).resolve().parent.parent / "demo" / "smaps_sample"
        context = build_ai_context(root, intent="quick-triage")
        ledger = context["evidence"]["accounting_ledger"]
        rows = {row["name"]: row for row in ledger["rows"]}
        meminfo = next(
            artifact
            for artifact in context["evidence"]["artifacts"]
            if artifact["artifact_type"] == "meminfo" and artifact["status"] == "ok"
        )

        self.assertEqual("available", ledger["status"])
        self.assertEqual(
            meminfo["artifact_id"],
            ledger["source_artifacts"]["meminfo"],
        )
        self.assertEqual(19, len(ledger["rows"]))
        self.assertEqual(80860, rows["Native Heap"]["meminfo"]["pss_total_kb"])
        self.assertEqual(80860, rows["Native Heap"]["smaps"]["pss_kb"])
        self.assertEqual(
            80860,
            rows["Native Heap"]["smaps"]["allocator_breakdown"]["scudo_pss_kb"],
        )
        self.assertNotIn("top_pss_mappings", rows["Native Heap"]["smaps"])
        self.assertEqual(
            "not-comparable",
            rows["EGL mtrack"]["comparison"]["status"],
        )

        markdown = render_markdown(context, "zh")
        self.assertLess(
            markdown.index("## meminfo 主账本 + smaps 逐行旁证"),
            markdown.index("## 证据清单"),
        )
        self.assertIn("| Native Heap | 80860 kB", markdown)

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

    def test_multiple_qa_logs_extract_bounded_signals_without_raw_lines(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            logs = root / "qa" / "logs"
            logs.mkdir(parents=True)
            secret = "account=user@example.com token=secret-value"
            (logs / "logcat-main.log").write_text(
                "07-22 09:10:11.123 1234 1234 D LeakCanary: APPLICATION LEAKS\n"
                "GC Root: System class\n"
                "├─ com.example.LeakOwner instance\n"
                "│    Leaking: YES (Activity received Activity#onDestroy())\n"
                "╰→ com.example.LeakedActivity instance\n"
                "07-22 09:10:12.456 1234 1234 E AndroidRuntime: "
                "java.lang.OutOfMemoryError: Failed to allocate a 4096 byte allocation "
                + secret
                + "\n",
                encoding="utf-8",
            )
            with gzip.open(str(logs / "system.log.gz"), "wt", encoding="utf-8") as handle:
                handle.write(
                    "07-22 09:10:13.789 1000 1000 I lmkd: Killing 'com.example.app'\n"
                )
            context = build_ai_context(root, question="QA logs show a possible leak and OOM")

        log_artifacts = [
            item for item in context["evidence"]["artifacts"]
            if item["artifact_type"] == "android_log" and item["status"] == "ok"
        ]
        self.assertEqual(2, len(log_artifacts))
        self.assertEqual(2, len({item["artifact_id"] for item in log_artifacts}))
        qa_logs = context["evidence"]["qa_observations"]["android_logs"]
        signal_types = {
            signal["signal_type"]
            for log in qa_logs
            for signal in log["signals"]
        }
        self.assertIn("leakcanary-retained-object", signal_types)
        self.assertIn("java-heap-oom", signal_types)
        self.assertIn("lmkd-kill", signal_types)
        self.assertTrue(qa_logs[0]["managed_owner_path_candidate"])
        serialized = render_json(context)
        self.assertNotIn(secret, serialized)
        self.assertNotIn("Failed to allocate a 4096 byte allocation", serialized)
        self.assertFalse(context["analysis_contract"]["privacy"]["raw_contents_embedded"])
        self.assertTrue(
            all(
                len(sample["line_sha256"]) == 64
                for log in qa_logs
                for signal in log["signals"]
                for sample in signal["samples"]
            )
        )

    def test_folder_scan_reads_bounded_android_signals_inside_a_bugreport_zip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive_path = root / "qa-capture.bundle"
            with zipfile.ZipFile(str(archive_path), "w") as archive:
                archive.writestr("images/binary.dat", b"\x00" * 8192)
                archive.writestr(
                    "FS/data/anr/dumpstate_log.txt",
                    "07-22 09:10:12.456 1000 1000 I lmkd: "
                    "Killing 'com.example.app'\n",
                )
            context = build_ai_context(root, question="QA 设备发生了内存问题")

        logs = context["evidence"]["qa_observations"]["android_logs"]
        self.assertEqual(1, len(logs))
        self.assertEqual("zip", logs[0]["compression"])
        self.assertEqual(1, logs[0]["archive_members_scanned"])
        signal = logs[0]["signals"][0]
        self.assertEqual("lmkd-kill", signal["signal_type"])
        self.assertEqual(
            "FS/data/anr/dumpstate_log.txt",
            signal["samples"][0]["archive_member"],
        )
        self.assertIn("system-pressure", context["request"]["evaluated_intents"])

    def test_folder_evidence_adds_a_relevant_intent_to_vague_issue_background(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "qa-output.data").write_text(
                "I/LeakCanary: retained object\n",
                encoding="utf-8",
            )
            context = build_ai_context(root, question="QA 说内存变多")

        self.assertEqual("regression", context["request"]["intent"])
        self.assertEqual("question-and-evidence", context["request"]["intent_source"])
        self.assertEqual(
            ["regression", "java-leak"],
            context["request"]["evaluated_intents"],
        )

    def test_folder_evidence_can_route_an_unspecified_issue(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "qa-output.data").write_text(
                "I/LeakCanary: retained object\n",
                encoding="utf-8",
            )
            context = build_ai_context(root, question="帮我分析 QA 材料")

        self.assertEqual("java-leak", context["request"]["intent"])
        self.assertEqual("evidence", context["request"]["intent_source"])
        self.assertEqual(
            ["java-leak"],
            context["request"]["evaluated_intents"],
        )

    def test_follow_up_analysis_compares_new_evidence_with_the_prior_context(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "meminfo.txt").write_text(MINIMAL_MEMINFO, encoding="utf-8")
            first = build_ai_context(root, question="第一次分析内存增长")
            (root / "android-memory-context.json").write_text(
                render_json(first),
                encoding="utf-8",
            )
            (root / "qa-new.log").write_text(
                "I/LeakCanary: retained object\n",
                encoding="utf-8",
            )
            second = build_ai_context(
                root,
                question="我对上次结论不满意，QA 又补充了日志，请重新分析",
            )

        history = second["evidence"]["analysis_history"]
        self.assertTrue(history["has_prior_analysis"])
        self.assertEqual(
            "reanalysis-with-new-evidence",
            history["mode"],
        )
        self.assertEqual(
            "question-and-evidence-delta",
            history["mode_source"],
        )
        self.assertEqual(1, len(history["previous_contexts"]))
        delta = history["evidence_delta"]
        self.assertEqual(1, delta["added_count"])
        self.assertEqual("qa-new.log", delta["added"][0]["path"])
        self.assertEqual(0, delta["changed_count"])
        self.assertGreaterEqual(delta["unchanged_by_fingerprint_count"], 1)
        self.assertNotIn("snapshot", history["previous_contexts"][0])

    def test_changed_folder_evidence_selects_supplement_mode_without_keywords(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            meminfo = root / "meminfo.txt"
            meminfo.write_text(MINIMAL_MEMINFO, encoding="utf-8")
            first = build_ai_context(root, question="第一次分析")
            (root / "context.json").write_text(render_json(first), encoding="utf-8")
            meminfo.write_text(
                MINIMAL_MEMINFO.replace("4096", "8192"),
                encoding="utf-8",
            )
            second = build_ai_context(root, question="再看一下这个目录")

        history = second["evidence"]["analysis_history"]
        self.assertEqual("supplement", history["mode"])
        self.assertEqual("evidence-delta", history["mode_source"])
        self.assertEqual(1, history["evidence_delta"]["changed_count"])
        changed = history["evidence_delta"]["changed"][0]
        self.assertEqual("meminfo.txt", changed["path"])
        self.assertNotEqual(
            changed["before"]["sha256"],
            changed["after"]["sha256"],
        )

    def test_unchanged_prior_context_requires_mode_clarification(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "meminfo.txt").write_text(MINIMAL_MEMINFO, encoding="utf-8")
            first = build_ai_context(root, question="第一次分析")
            (root / "context.json").write_text(render_json(first), encoding="utf-8")
            second = build_ai_context(root, question="再看一下这个目录")

        history = second["evidence"]["analysis_history"]
        self.assertEqual("clarification-required", history["mode"])
        self.assertEqual("prior-analysis-detected", history["mode_source"])
        self.assertEqual(0, history["evidence_delta"]["added_count"])
        self.assertEqual(0, history["evidence_delta"]["changed_count"])

    def test_previous_conclusion_report_is_indexed_without_embedding_its_text(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            secret = "token=prior-secret-value"
            (root / "analysis.md").write_text(
                "# 分析结论\n\n可能是 Java 泄漏。" + secret + "\n",
                encoding="utf-8",
            )
            context = build_ai_context(root, question="请继续分析")

        history = context["evidence"]["analysis_history"]
        self.assertEqual("supplement", history["mode"])
        self.assertEqual(1, len(history["previous_analysis_reports"]))
        self.assertTrue(
            history["previous_analysis_reports"][0]["manual_review_required"]
        )
        self.assertNotIn(secret, render_json(context))

    def test_external_prior_report_path_requires_local_path_opt_in(self):
        with tempfile.TemporaryDirectory() as directory, \
                tempfile.TemporaryDirectory() as external:
            root = Path(directory)
            report = Path(external) / "analysis.md"
            report.write_text(
                "# Analysis conclusion\n\nNo owner was established.\n",
                encoding="utf-8",
            )
            resolved_report = str(report.resolve())
            redacted = build_ai_context(
                root,
                question="继续分析",
                artifact_overrides={"previous_analysis_report": [str(report)]},
            )
            local = build_ai_context(
                root,
                question="继续分析",
                artifact_overrides={"previous_analysis_report": [str(report)]},
                include_local_paths=True,
            )

        redacted_history = redacted["evidence"]["analysis_history"]
        local_history = local["evidence"]["analysis_history"]
        self.assertEqual(
            "<external>/analysis.md",
            redacted_history["previous_analysis_reports"][0]["path"],
        )
        self.assertTrue(any(
            "绝对路径已脱敏" in item["zh"] for item in redacted["limitations"]
        ))
        self.assertEqual(
            resolved_report,
            local_history["previous_analysis_reports"][0]["path"],
        )

    def test_declared_reanalysis_without_prior_material_is_an_explicit_limitation(self):
        with tempfile.TemporaryDirectory() as directory:
            context = build_ai_context(
                Path(directory),
                question="我不满意之前的分析，请重新分析",
            )

        history = context["evidence"]["analysis_history"]
        self.assertTrue(history["prior_analysis_declared_by_request"])
        self.assertEqual("reanalysis", history["mode"])
        self.assertTrue(history["limitations"])
        self.assertTrue(any(
            "当前会话历史" in item["zh"] for item in context["limitations"]
        ))

    def test_explicit_follow_up_mode_without_prior_material_is_limited(self):
        with tempfile.TemporaryDirectory() as directory:
            context = build_ai_context(
                Path(directory),
                analysis_mode="supplement",
            )

        history = context["evidence"]["analysis_history"]
        self.assertTrue(history["follow_up_requested"])
        self.assertTrue(history["has_prior_analysis"])
        self.assertEqual("supplement", history["mode"])
        self.assertFalse(history["baseline_applied"])
        self.assertTrue(history["limitations"])

    def test_explicit_initial_mode_keeps_old_context_as_inventory_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "meminfo.txt").write_text(MINIMAL_MEMINFO, encoding="utf-8")
            first = build_ai_context(root, question="第一次分析")
            (root / "context.json").write_text(render_json(first), encoding="utf-8")
            second = build_ai_context(root, analysis_mode="initial")

        history = second["evidence"]["analysis_history"]
        self.assertEqual("initial", history["mode"])
        self.assertFalse(history["baseline_applied"])
        self.assertIsNone(history["baseline_context_artifact_id"])
        self.assertEqual("no-baseline-context", history["evidence_delta"]["status"])
        self.assertIn("inventory only", history["review_contract"][0])

    def test_previous_schema_context_remains_compatible_and_tracks_missing_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            meminfo = root / "meminfo.txt"
            meminfo.write_text(MINIMAL_MEMINFO, encoding="utf-8")
            first = build_ai_context(root, question="第一次分析")
            first["schema_version"] = "1.1"
            first["generator"]["version"] = "1.1.0"
            (root / "context-v1.json").write_text(
                render_json(first),
                encoding="utf-8",
            )
            meminfo.unlink()
            second = build_ai_context(root, question="继续补充分析")

        history = second["evidence"]["analysis_history"]
        self.assertEqual("supplement", history["mode"])
        self.assertEqual("1.1", history["previous_contexts"][0]["schema_version"])
        self.assertEqual(1, history["evidence_delta"]["missing_since_previous_count"])
        self.assertEqual(
            "meminfo.txt",
            history["evidence_delta"]["missing_since_previous"][0]["path"],
        )

    def test_prior_analysis_artifacts_do_not_satisfy_memory_coverage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = build_ai_context(root, question="第一次分析")
            (root / "android-memory-context.json").write_text(
                render_json(first),
                encoding="utf-8",
            )
            (root / "analysis.md").write_text(
                "# Analysis conclusion\n\nNo owner was established.\n",
                encoding="utf-8",
            )
            second = build_ai_context(
                root,
                intent="java-leak",
                question="继续分析",
            )

        available = second["evidence"]["coverage"]["available"]
        self.assertNotIn("previous_ai_context", available)
        self.assertNotIn("previous_analysis_report", available)
        self.assertEqual("insufficient", second["analysis_contract"]["support_level"])

    def test_malformed_prior_context_is_safely_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            malformed = {
                "context_type": "android-memory-ai-context",
                "schema_version": {"unexpected": "x" * 5000},
                "generated_at": 123,
                "generator": {"name": ["unexpected"], "version": "old"},
                "request": ["unexpected"],
                "subject": ["unexpected"],
                "analysis_contract": ["unexpected"],
                "evidence": {
                    "artifacts": [
                        "unexpected",
                        {
                            "artifact_id": {"unexpected": "x" * 5000},
                            "artifact_type": ["unexpected"],
                            "status": "ok",
                            "path": {"unexpected": "x" * 5000},
                            "size_bytes": {"unexpected": "x" * 5000},
                            "sha256": {"unexpected": "x" * 5000},
                        },
                    ],
                },
            }
            (root / "context.json").write_text(
                json.dumps(malformed),
                encoding="utf-8",
            )
            context = build_ai_context(root, question="继续分析")

        history = context["evidence"]["analysis_history"]
        self.assertEqual("supplement", history["mode"])
        previous = history["previous_contexts"][0]
        self.assertEqual(2, previous["artifact_count"])
        self.assertLess(len(str(previous)), 12000)
        self.assertNotIn("x" * 3000, render_json(context))

    def test_case_identity_mismatch_blocks_direct_revision(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            meminfo = root / "meminfo.txt"
            meminfo.write_text(MINIMAL_MEMINFO, encoding="utf-8")
            first = build_ai_context(root, question="第一次分析")
            (root / "context.json").write_text(render_json(first), encoding="utf-8")
            meminfo.write_text(
                MINIMAL_MEMINFO.replace("com.example.app", "com.other.app"),
                encoding="utf-8",
            )
            second = build_ai_context(root, question="继续分析")

        history = second["evidence"]["analysis_history"]
        self.assertEqual("different-case", history["case_identity"]["status"])
        self.assertEqual(
            {
                "before": "com.example.app",
                "after": "com.other.app",
            },
            history["case_identity"]["differing_fields"]["package"],
        )
        self.assertTrue(any(
            "稳定 case 身份字段不一致" in item["zh"]
            for item in second["limitations"]
        ))

    def test_same_named_external_artifacts_do_not_collapse_in_the_delta(self):
        with tempfile.TemporaryDirectory() as directory, \
                tempfile.TemporaryDirectory() as first_external, \
                tempfile.TemporaryDirectory() as second_external:
            root = Path(directory)
            first_log = Path(first_external) / "same.log"
            second_log = Path(second_external) / "same.log"
            first_log.write_text(
                "E/AndroidRuntime: java.lang.OutOfMemoryError\n",
                encoding="utf-8",
            )
            second_log.write_text(
                "I/lmkd: Killing 'com.example.app'\n",
                encoding="utf-8",
            )
            overrides = {
                "android_log": [str(first_log), str(second_log)],
            }
            first = build_ai_context(root, artifact_overrides=overrides)
            (root / "context.json").write_text(render_json(first), encoding="utf-8")
            second = build_ai_context(
                root,
                question="继续分析",
                artifact_overrides=overrides,
            )

        delta = second["evidence"]["analysis_history"]["evidence_delta"]
        self.assertEqual(2, delta["unchanged_by_fingerprint_count"])
        self.assertEqual(0, delta["added_count"])
        self.assertEqual(0, delta["missing_since_previous_count"])

    def test_multiple_qa_screenshots_record_metadata_without_ocr_claims(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            screenshots = root / "qa" / "screenshots"
            screenshots.mkdir(parents=True)
            (screenshots / "leakcanary.png").write_bytes(minimal_png())
            (screenshots / "memory-chart.png").write_bytes(minimal_png(1440, 3120))
            context = build_ai_context(root)

        images = context["evidence"]["qa_observations"]["screenshots"]
        self.assertEqual(2, len(images))
        self.assertEqual(
            {(1080, 2400), (1440, 3120)},
            {(item["image"]["width"], item["image"]["height"]) for item in images},
        )
        self.assertTrue(all(item["visual_review_required"] for item in images))
        self.assertTrue(all(item["ocr_performed"] is False for item in images))
        self.assertFalse(context["evidence"]["qa_observations"]["screenshot_pixels_embedded"])
        markdown = render_markdown(context, "zh")
        self.assertIn("QA 日志与截图", markdown)
        self.assertIn("必须查看可见区域", markdown)

    def test_explicit_multiple_qa_artifacts_keep_external_paths_redacted(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as external:
            root = Path(directory)
            external_root = Path(external)
            first = external_root / "first.log"
            second = external_root / "second.log"
            first.write_text("E/AndroidRuntime: java.lang.OutOfMemoryError\n", encoding="utf-8")
            second.write_text("I/lmkd: Killing 'com.example.app'\n", encoding="utf-8")
            context = build_ai_context(
                root,
                artifact_overrides={"android_log": [str(first), str(second)]},
            )

        logs = context["evidence"]["qa_observations"]["android_logs"]
        self.assertEqual(2, len(logs))
        self.assertEqual({"<external>/first.log", "<external>/second.log"}, {
            item["path"] for item in logs
        })
        self.assertNotIn(str(external_root), render_json(context))

    def test_external_qa_overrides_supplement_folder_discovery(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as external:
            root = Path(directory)
            (root / "folder.log").write_text(
                "I/LeakCanary: retained object\n",
                encoding="utf-8",
            )
            external_log = Path(external) / "external.log"
            external_log.write_text(
                "E/AndroidRuntime: java.lang.OutOfMemoryError\n",
                encoding="utf-8",
            )
            context = build_ai_context(
                root,
                artifact_overrides={"android_log": [str(external_log)]},
            )

        logs = context["evidence"]["qa_observations"]["android_logs"]
        self.assertEqual(2, len(logs))
        self.assertEqual(
            {"folder.log", "<external>/external.log"},
            {item["path"] for item in logs},
        )

    def test_oom_log_is_not_treated_as_a_managed_owner_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "qa.log").write_text(
                "E/AndroidRuntime: java.lang.OutOfMemoryError\n",
                encoding="utf-8",
            )
            (root / "run_config.txt").write_text(
                "timestamp_utc=2026-07-22T09:00:00Z\npackage=com.example.app\n"
                "pid=1234\nprocess_role=main\nuser_profile=0\nscenario=open-close\n"
                "phase=after\nloops=5\ncooldown_seconds=30\n"
                "collection_mode=logcat\nperturbation=low\n",
                encoding="utf-8",
            )
            (root / "comparison.json").write_text(
                json.dumps({"changes": {"java_heap_pss_kb": 1024}}),
                encoding="utf-8",
            )
            context = build_ai_context(root, intent="java-leak")

        coverage = context["evidence"]["coverage"]
        self.assertIn("android_log", coverage["inadequate"])
        self.assertIn(["hprof", "android_log"], coverage["missing_any_of"])
        self.assertEqual("insufficient", coverage["level"])

    def test_folder_first_scan_classifies_nested_arbitrary_names_and_keeps_unknowns(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            qa = root / "downloads" / "qa-case"
            qa.mkdir(parents=True)
            (qa / "capture-a.data").write_text(MINIMAL_MEMINFO, encoding="utf-8")
            (qa / "device-output.txt").write_text(
                "07-22 09:10:11.123 1234 1234 D LeakCanary: retained object\n",
                encoding="utf-8",
            )
            (qa / "visual-evidence.bin").write_bytes(minimal_png())
            (qa / "vendor-private.blob").write_bytes(b"\x00\x01\x02\x03")
            context = build_ai_context(root, question="QA says memory grows")

        artifacts = context["evidence"]["artifacts"]
        by_type = {}
        for artifact in artifacts:
            if artifact.get("status") != "missing":
                by_type.setdefault(artifact["artifact_type"], []).append(artifact)
        self.assertEqual("downloads/qa-case/capture-a.data", by_type["meminfo"][0]["path"])
        self.assertEqual("content-signature", by_type["meminfo"][0]["source"])
        self.assertEqual(1, len(by_type["android_log"]))
        self.assertEqual(1, len(by_type["qa_screenshot"]))
        self.assertEqual(1, len(by_type["unclassified_file"]))
        inventory = context["evidence"]["folder_inventory"]
        self.assertEqual(4, inventory["total_files"])
        self.assertEqual(4, inventory["indexed_files"])
        self.assertEqual(1, inventory["unclassified_files"])
        self.assertTrue(inventory["all_indexed_files_represented"])
        self.assertTrue(
            any("无法按内容签名分类" in item["zh"] for item in context["limitations"])
        )

    def test_folder_scan_treats_misleading_names_as_hints_not_truth(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "meminfo.txt").write_text(
                "07-22 09:10:11.123 1234 1234 E AndroidRuntime: "
                "java.lang.OutOfMemoryError\n",
                encoding="utf-8",
            )
            (root / "arbitrary-evidence.data").write_text(
                "I/LeakCanary: retained object\n",
                encoding="utf-8",
            )
            context = build_ai_context(root, question="QA reported a leak")

        local_artifacts = [
            item for item in context["evidence"]["artifacts"]
            if item.get("path") in {"meminfo.txt", "arbitrary-evidence.data"}
            and item.get("status") == "ok"
        ]
        self.assertEqual(
            {"android_log"},
            {item["artifact_type"] for item in local_artifacts},
        )
        self.assertEqual(
            {"content-signature"},
            {item["source"] for item in local_artifacts},
        )
        self.assertEqual(
            2,
            len(context["evidence"]["qa_observations"]["android_logs"]),
        )

    def test_multiple_content_detected_meminfo_files_preserve_identity_conflict(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "before.capture").write_text(
                MINIMAL_MEMINFO.replace("com.example.app", "com.before.app"),
                encoding="utf-8",
            )
            (root / "after.capture").write_text(
                MINIMAL_MEMINFO.replace("com.example.app", "com.after.app"),
                encoding="utf-8",
            )
            context = build_ai_context(root)

        meminfo = [
            item for item in context["evidence"]["artifacts"]
            if item["artifact_type"] == "meminfo" and item["status"] == "ok"
        ]
        self.assertEqual(2, len(meminfo))
        package_conflicts = [
            item for item in context["evidence"]["conflicts"]
            if item["field"] == "package"
        ]
        self.assertEqual(1, len(package_conflicts))
        self.assertEqual(
            {"com.before.app", "com.after.app"},
            set(package_conflicts[0]["values"].values()),
        )
        ledger = context["evidence"]["accounting_ledger"]
        self.assertEqual("ambiguous", ledger["status"])
        self.assertEqual(
            "multiple-meminfo-artifacts-require-explicit-phase-pairing",
            ledger["reason"],
        )
        self.assertEqual(2, len(ledger["meminfo_artifact_ids"]))

    def test_folder_scan_does_not_follow_symlinks_outside_evidence_root(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as external:
            root = Path(directory)
            external_log = Path(external) / "outside.log"
            external_log.write_text(
                "E/AndroidRuntime: java.lang.OutOfMemoryError\n",
                encoding="utf-8",
            )
            (root / "linked.log").symlink_to(external_log)
            context = build_ai_context(root)

        inventory = context["evidence"]["folder_inventory"]
        self.assertEqual(0, inventory["total_files"])
        self.assertEqual(1, inventory["skipped_symlinks"])
        self.assertEqual([], context["evidence"]["qa_observations"]["android_logs"])

    def test_folder_scan_reports_per_type_overflow_instead_of_silently_dropping_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for index in range(65):
                (root / "qa-{:02d}.log".format(index)).write_text(
                    "I/Test: no memory signal\n",
                    encoding="utf-8",
                )
            context = build_ai_context(root)

        logs = [
            item for item in context["evidence"]["artifacts"]
            if item["artifact_type"] == "android_log"
        ]
        overflow = [item for item in logs if item["status"] == "not_collected"]
        self.assertEqual(64, len([item for item in logs if item["status"] == "ok"]))
        self.assertEqual(1, len(overflow))
        self.assertEqual(65, overflow[0]["metadata"]["candidate_count"])
        inventory = context["evidence"]["folder_inventory"]
        self.assertEqual(65, inventory["total_files"])
        self.assertFalse(inventory["all_indexed_files_represented"])
        self.assertTrue(
            any("同类材料超过" in item["zh"] for item in context["limitations"])
        )

    def test_content_detected_logs_share_the_per_type_processing_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for index in range(65):
                (root / "capture-{:02d}.data".format(index)).write_text(
                    "I/Test: Android diagnostic line\n",
                    encoding="utf-8",
                )
            context = build_ai_context(root)

        logs = [
            item for item in context["evidence"]["artifacts"]
            if item["artifact_type"] == "android_log"
        ]
        overflow = [item for item in logs if item["status"] == "not_collected"]
        self.assertEqual(64, len([item for item in logs if item["status"] == "ok"]))
        self.assertEqual(1, len(overflow))
        self.assertEqual(65, overflow[0]["metadata"]["candidate_count"])


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
            (evidence / "qa.log").write_text(
                "E/AndroidRuntime: java.lang.OutOfMemoryError\n",
                encoding="utf-8",
            )
            (evidence / "qa.png").write_bytes(minimal_png())
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
        self.assertEqual(
            1,
            len(context["evidence"]["qa_observations"]["android_logs"]),
        )
        self.assertEqual(
            1,
            len(context["evidence"]["qa_observations"]["screenshots"]),
        )

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
