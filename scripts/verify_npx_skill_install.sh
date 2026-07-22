#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
SKILLS_CLI_VERSION=1.5.19

VERIFY_NPX_TMP=$(mktemp -d /tmp/android-memory-npx-install.XXXXXX)
trap 'rm -rf "$VERIFY_NPX_TMP"' EXIT

mkdir "$VERIFY_NPX_TMP/source"
cp -R "$REPO_ROOT/skills" "$VERIFY_NPX_TMP/source/"
cp "$REPO_ROOT/.gitignore" "$VERIFY_NPX_TMP/source/.gitignore"
git -C "$VERIFY_NPX_TMP/source" init -q
git -C "$VERIFY_NPX_TMP/source" add .gitignore skills
git -C "$VERIFY_NPX_TMP/source" \
  -c user.name=AndroidMemorySkillTest \
  -c user.email=android-memory-skill-test@example.invalid \
  commit -qm "Public Skill fixture"

mkdir "$VERIFY_NPX_TMP/consumer"
cd "$VERIFY_NPX_TMP/consumer"
SKILL_GIT_SOURCE="file://$VERIFY_NPX_TMP/source"
npx --yes "skills@$SKILLS_CLI_VERSION" add "$SKILL_GIT_SOURCE" \
  --skill '*' \
  --agent codex \
  --yes

for skill_name in \
  android-memory-evidence \
  android-memory-diagnose \
  android-memory-remediate
do
  test -f ".agents/skills/$skill_name/SKILL.md"
  test -f ".agents/skills/$skill_name/LICENSE"
done
if find .agents/skills -name '*.pyc' -print -quit | grep -q .; then
  printf 'Installed package contains ignored Python bytecode.\n' >&2
  exit 1
fi

mkdir "$VERIFY_NPX_TMP/qa-evidence"
printf '%s\n' \
  '07-22 09:10:11.123 1234 1234 E AndroidRuntime: java.lang.OutOfMemoryError' \
  > "$VERIFY_NPX_TMP/qa-evidence/logcat.log"
python3 - "$VERIFY_NPX_TMP/qa-evidence/screenshot.png" <<'PY'
import sys

with open(sys.argv[1], "wb") as handle:
    handle.write(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\x0dIHDR"
        + (1080).to_bytes(4, "big")
        + (2400).to_bytes(4, "big")
    )
PY

env -u ANDROID_MEMORY_ANALYSIS_ROOT -u PYTHONPATH python3 \
  .agents/skills/android-memory-evidence/scripts/build_context.py \
  --dump-dir "$VERIFY_NPX_TMP/qa-evidence" \
  --question "Native memory keeps growing after five loops" \
  --format json \
  --output "$VERIFY_NPX_TMP/context.json"

python3 - "$VERIFY_NPX_TMP/context.json" "$VERIFY_NPX_TMP/consumer/skills-lock.json" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as handle:
    context = json.load(handle)
with open(sys.argv[2], "r", encoding="utf-8") as handle:
    lock = json.load(handle)

expected = {
    "android-memory-evidence",
    "android-memory-diagnose",
    "android-memory-remediate",
}
assert context["context_type"] == "android-memory-ai-context"
assert context["generator"] == {"name": "android-memory-ai", "version": "1.2.0"}
assert set(context["request"]["evaluated_intents"]) == {"native-memory", "regression"}
assert set(lock["skills"]) == expected
assert all(lock["skills"][name]["sourceType"] == "git" for name in expected)
assert all(lock["skills"][name]["skillPath"].startswith("skills/") for name in expected)
qa = context["evidence"]["qa_observations"]
assert len(qa["android_logs"]) == 1
assert len(qa["screenshots"]) == 1
assert qa["android_logs"][0]["signals"][0]["signal_type"] == "java-heap-oom"
PY

cp "$VERIFY_NPX_TMP/context.json" "$VERIFY_NPX_TMP/qa-evidence/previous-context.json"
printf '%s\n' \
  '07-22 09:11:13.789 1234 1234 D LeakCanary: retained object' \
  > "$VERIFY_NPX_TMP/qa-evidence/new-evidence.log"
env -u ANDROID_MEMORY_ANALYSIS_ROOT -u PYTHONPATH python3 \
  .agents/skills/android-memory-evidence/scripts/build_context.py \
  --dump-dir "$VERIFY_NPX_TMP/qa-evidence" \
  --question "I disagree with the old conclusion and added evidence; reanalyze" \
  --format json \
  --output "$VERIFY_NPX_TMP/context-v2.json"

python3 - "$VERIFY_NPX_TMP/context-v2.json" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as handle:
    context = json.load(handle)
history = context["evidence"]["analysis_history"]
assert context["request"]["analysis_mode"] == "reanalysis-with-new-evidence"
assert len(history["previous_contexts"]) == 1
assert history["evidence_delta"]["added_count"] == 1
assert history["evidence_delta"]["added"][0]["path"] == "new-evidence.log"
PY

npx --yes "skills@$SKILLS_CLI_VERSION" add "$SKILL_GIT_SOURCE" \
  --skill '*' \
  --agent codex \
  --yes

env -u ANDROID_MEMORY_ANALYSIS_ROOT -u PYTHONPATH python3 \
  .agents/skills/android-memory-evidence/scripts/build_context.py \
  --dump-dir "$REPO_ROOT/demo/smaps_sample" \
  --question "Verify the updated installed runtime" \
  --format json \
  --output "$VERIFY_NPX_TMP/context-after-reinstall.json"

printf 'Public npx Skill install, reinstall, and execution verification passed.\n'
