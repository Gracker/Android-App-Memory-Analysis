#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
cd "$REPO_ROOT"

python3 scripts/sync_skill_runtime.py --check
python3 -m unittest discover -s tests -v
python3 tools/validate_ai_assets.py

VERIFY_TMP=$(mktemp -d /tmp/android-memory-ai-verify.XXXXXX)
trap 'rm -rf "$VERIFY_TMP"' EXIT

python3 analyze.py ai-context \
  -d demo/smaps_sample \
  --question "Native memory keeps growing" \
  --format json \
  -o "$VERIFY_TMP/context.json"

python3 - "$VERIFY_TMP/context.json" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as handle:
    data = json.load(handle)
assert data["schema_version"] == "1.2"
assert data["context_type"] == "android-memory-ai-context"
assert data["generator"] == {"name": "android-memory-ai", "version": "1.2.0"}
assert data["request"]["intent"] == "native-memory"
assert data["request"]["evaluated_intents"] == ["native-memory", "regression"]
assert data["analysis_contract"]["support_level"] == "insufficient"
assert data["analysis_contract"]["privacy"]["raw_contents_embedded"] is False
assert data["analysis_contract"]["privacy"]["local_paths_included"] is False
assert data["evidence"]["path_policy"] == "relative-or-redacted"
assert "root" not in data["evidence"]
ledger = data["evidence"]["accounting_ledger"]
assert ledger["status"] == "available"
assert ledger["view"] == "meminfo-primary-smaps-supplemental"
assert len(ledger["rows"]) == 19
rows = {row["name"]: row for row in ledger["rows"]}
assert rows["Native Heap"]["meminfo"]["pss_total_kb"] == 80860
assert rows["Native Heap"]["smaps"]["pss_kb"] == 80860
assert (
    rows["Native Heap"]["smaps"]["allocator_breakdown"]["scudo_pss_kb"]
    == 80860
)
assert rows["EGL mtrack"]["comparison"]["status"] == "not-comparable"
assert ledger["total_reconciliation"]["formula"] == (
    "smaps_total_pss_kb + meminfo_memtrack_only_pss_kb"
)
PY

python3 analyze.py panorama \
  -m demo/smaps_sample/meminfo.txt \
  -S demo/smaps_sample/smaps \
  --json \
  -o "$VERIFY_TMP/panorama.json"

python3 - "$VERIFY_TMP/panorama.json" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as handle:
    data = json.load(handle)
assert list(data).index("accounting_ledger") < list(data).index("memory_overview")
ledger = data["accounting_ledger"]
assert ledger["status"] == "available"
assert [row["name"] for row in ledger["rows"]][:3] == [
    "Native Heap",
    "Dalvik Heap",
    "Dalvik Other",
]
assert len(ledger["rows"]) == 19
assert len(ledger["dalvik_detail_rows"]) == 12
PY

python3 analyze.py combined \
  --modern \
  --smaps demo/smaps_sample/smaps \
  --meminfo demo/smaps_sample/meminfo.txt \
  --json-output "$VERIFY_TMP/combined.json"

python3 - "$VERIFY_TMP/combined.json" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as handle:
    data = json.load(handle)
ledger = data["accounting_ledger"]
assert ledger["status"] == "available"
assert len(ledger["rows"]) == 19
assert ledger["total_reconciliation"]["status"] == "aligned"
assert data["native_memory"]["scudo_heap_mb"] > 78
PY

mkdir -p "$VERIFY_TMP/qa-evidence"
printf '%s\n' \
  '07-22 09:10:11.123 1234 1234 D LeakCanary: APPLICATION LEAKS' \
  'GC Root: System class' \
  '├─ com.example.LeakOwner instance' \
  '│    Leaking: YES (Activity received Activity#onDestroy())' \
  '╰→ com.example.LeakedActivity instance' \
  > "$VERIFY_TMP/qa-evidence/leakcanary.log"
printf '%s\n' \
  "07-22 09:10:12.456 1000 1000 I lmkd: Killing 'com.example.app'" \
  > "$VERIFY_TMP/qa-evidence/system.log"
python3 - "$VERIFY_TMP/qa-evidence/leakcanary.png" <<'PY'
import sys

with open(sys.argv[1], "wb") as handle:
    handle.write(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\x0dIHDR"
        + (1080).to_bytes(4, "big")
        + (2400).to_bytes(4, "big")
    )
PY

python3 analyze.py ai-context \
  -d "$VERIFY_TMP/qa-evidence" \
  --question "QA supplied a LeakCanary trace and LMKD log" \
  --format json \
  -o "$VERIFY_TMP/qa-context.json"

python3 - "$VERIFY_TMP/qa-context.json" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as handle:
    data = json.load(handle)
qa = data["evidence"]["qa_observations"]
assert len(qa["android_logs"]) == 2
assert len(qa["screenshots"]) == 1
assert qa["raw_log_lines_embedded"] is False
assert qa["screenshot_pixels_embedded"] is False
assert any(item["managed_owner_path_candidate"] for item in qa["android_logs"])
signal_types = {
    signal["signal_type"]
    for item in qa["android_logs"]
    for signal in item["signals"]
}
assert "leakcanary-retained-object" in signal_types
assert "lmkd-kill" in signal_types
PY

cp "$VERIFY_TMP/qa-context.json" "$VERIFY_TMP/qa-evidence/previous-context.json"
printf '%s\n' \
  '07-22 09:11:13.789 1234 1234 E AndroidRuntime: java.lang.OutOfMemoryError' \
  > "$VERIFY_TMP/qa-evidence/supplemental.log"
python3 analyze.py ai-context \
  -d "$VERIFY_TMP/qa-evidence" \
  --question "I disagree with the prior conclusion and QA added evidence; reanalyze" \
  --format json \
  -o "$VERIFY_TMP/qa-context-v2.json"

python3 - "$VERIFY_TMP/qa-context-v2.json" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as handle:
    data = json.load(handle)
history = data["evidence"]["analysis_history"]
assert data["request"]["analysis_mode"] == "reanalysis-with-new-evidence"
assert history["mode_source"] == "question-and-evidence-delta"
assert len(history["previous_contexts"]) == 1
assert history["evidence_delta"]["added_count"] == 1
assert history["evidence_delta"]["added"][0]["path"] == "supplemental.log"
assert history["evidence_delta"]["changed_count"] == 0
assert "previous_ai_context" not in data["evidence"]["coverage"]["available"]
PY

mkdir -p "$VERIFY_TMP/installed/.agents/skills"
cp -R skills/android-memory-evidence "$VERIFY_TMP/installed/.agents/skills/"
cp -R skills/android-memory-diagnose "$VERIFY_TMP/installed/.agents/skills/"
cp -R skills/android-memory-remediate "$VERIFY_TMP/installed/.agents/skills/"

cd "$VERIFY_TMP/installed"
env -u ANDROID_MEMORY_ANALYSIS_ROOT -u PYTHONPATH python3 \
  .agents/skills/android-memory-evidence/scripts/build_context.py \
  --dump-dir "$REPO_ROOT/demo/smaps_sample" \
  --question "Native memory keeps growing" \
  --phase copied-skill-test \
  --format json \
  --output "$VERIFY_TMP/copied-skill-context.json"
cd "$REPO_ROOT"

python3 - "$VERIFY_TMP/copied-skill-context.json" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as handle:
    data = json.load(handle)
assert data["generator"] == {"name": "android-memory-ai", "version": "1.2.0"}
assert data["subject"]["phase"] == "copied-skill-test"
assert data["analysis_contract"]["privacy"]["local_paths_included"] is False
PY

python3 skills/android-memory-evidence/scripts/build_context.py \
  --repo "$REPO_ROOT" \
  --dump-dir demo/smaps_sample \
  --question "Is the graphics memory evidence complete?" \
  --phase imported-skill-test \
  --format json \
  --output "$VERIFY_TMP/skill-context.json"

python3 - "$VERIFY_TMP/skill-context.json" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as handle:
    data = json.load(handle)
assert data["context_type"] == "android-memory-ai-context"
assert data["request"]["intent"] == "graphics"
assert data["subject"]["phase"] == "imported-skill-test"
PY

mkdir "$VERIFY_TMP/incomplete"
set +e
python3 analyze.py ai-context \
  -d "$VERIFY_TMP/incomplete" \
  --intent java-leak \
  --strict \
  --format json \
  -o "$VERIFY_TMP/incomplete.json"
STRICT_STATUS=$?
set -e
if test "$STRICT_STATUS" -ne 2; then
  printf 'Expected strict incomplete context to exit 2, got %s\n' "$STRICT_STATUS" >&2
  exit 1
fi

printf 'Android memory AI verification passed.\n'
