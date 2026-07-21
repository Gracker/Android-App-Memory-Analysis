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

env -u ANDROID_MEMORY_ANALYSIS_ROOT -u PYTHONPATH python3 \
  .agents/skills/android-memory-evidence/scripts/build_context.py \
  --dump-dir "$REPO_ROOT/demo/smaps_sample" \
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
assert context["generator"] == {"name": "android-memory-ai", "version": "1.0.0"}
assert set(context["request"]["evaluated_intents"]) == {"native-memory", "regression"}
assert set(lock["skills"]) == expected
assert all(lock["skills"][name]["sourceType"] == "git" for name in expected)
assert all(lock["skills"][name]["skillPath"].startswith("skills/") for name in expected)
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
