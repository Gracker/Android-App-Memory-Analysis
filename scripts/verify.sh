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
assert data["schema_version"] == "1.0"
assert data["context_type"] == "android-memory-ai-context"
assert data["generator"] == {"name": "android-memory-ai", "version": "1.0.0"}
assert data["request"]["intent"] == "native-memory"
assert data["request"]["evaluated_intents"] == ["native-memory", "regression"]
assert data["analysis_contract"]["support_level"] == "insufficient"
assert data["analysis_contract"]["privacy"]["raw_contents_embedded"] is False
assert data["analysis_contract"]["privacy"]["local_paths_included"] is False
assert data["evidence"]["path_policy"] == "relative-or-redacted"
assert "root" not in data["evidence"]
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
assert data["generator"] == {"name": "android-memory-ai", "version": "1.0.0"}
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
