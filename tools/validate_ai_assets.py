#!/usr/bin/env python3
"""Validate the knowledge catalog and repository-owned Skills without third-party deps."""

import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from android_memory_ai.catalog import load_catalog
from android_memory_ai.contracts import RUNTIME_NAME, RUNTIME_VERSION, SCHEMA_VERSION
from android_memory_ai.evidence import ARTIFACT_SPECS
from android_memory_ai.guidance import INTENT_PROFILES


FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
ALLOWED_SOURCE_HOSTS = {
    "android.googlesource.com",
    "developer.android.com",
    "docs.kernel.org",
    "perfetto.dev",
    "source.android.com",
}


def validate_skill(skill_dir: Path) -> None:
    skill_file = skill_dir / "SKILL.md"
    if not skill_file.is_file():
        raise ValueError("missing SKILL.md: {}".format(skill_dir))
    content = skill_file.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(content)
    if not match:
        raise ValueError("invalid frontmatter: {}".format(skill_file))
    fields = {}
    for line in match.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            raise ValueError("invalid frontmatter line in {}: {}".format(skill_file, line))
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip().strip('"').strip("'")
    if set(fields) != {"name", "description"}:
        raise ValueError("{} frontmatter must contain only name and description".format(skill_file))
    name = fields["name"]
    if name != skill_dir.name:
        raise ValueError("skill name {} must match folder {}".format(name, skill_dir.name))
    if not re.fullmatch(r"[a-z0-9-]{1,64}", name):
        raise ValueError("invalid skill name: {}".format(name))
    if not fields["description"]:
        raise ValueError("empty skill description: {}".format(skill_file))

    openai_yaml = skill_dir / "agents" / "openai.yaml"
    if not openai_yaml.is_file():
        raise ValueError("missing agents/openai.yaml: {}".format(skill_dir))
    interface = openai_yaml.read_text(encoding="utf-8")
    if "display_name:" not in interface or "short_description:" not in interface:
        raise ValueError("incomplete skill interface: {}".format(openai_yaml))
    if "default_prompt:" not in interface or "$" + name not in interface:
        raise ValueError("default_prompt must mention ${}: {}".format(name, openai_yaml))

    for reference in re.findall(r"\[[^\]]+\]\(([^)]+)\)", content):
        if "://" in reference or reference.startswith("#"):
            continue
        target = (skill_dir / reference).resolve()
        if not target.exists():
            raise ValueError("broken skill reference {} in {}".format(reference, skill_file))


def validate_runtime_bundle(root: Path, catalog) -> None:
    runtime = root / "skills" / "android-memory-evidence" / "runtime"
    manifest_path = runtime / "runtime-manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("invalid bundled runtime manifest: {}".format(exc))

    expected_contract = {
        "bundle_schema_version": "1.0",
        "skill": "android-memory-evidence",
        "minimum_python": "3.8",
        "release_version": (root / "VERSION").read_text(encoding="utf-8").strip(),
        "runtime_name": RUNTIME_NAME,
        "runtime_version": RUNTIME_VERSION,
        "context_schema_version": SCHEMA_VERSION,
        "catalog_id": catalog["catalog_id"],
        "catalog_version": catalog["catalog_version"],
    }
    for field, expected in expected_contract.items():
        if manifest.get(field) != expected:
            raise ValueError(
                "bundled runtime {} is {!r}, expected {!r}".format(
                    field, manifest.get(field), expected
                )
            )

    listed_paths = set()
    for entry in manifest.get("files", []):
        relative = entry.get("path")
        if not isinstance(relative, str) or not relative or relative in listed_paths:
            raise ValueError("invalid or duplicate bundled runtime path: {}".format(relative))
        listed_paths.add(relative)
        bundled_path = runtime / relative
        if not bundled_path.is_file():
            raise ValueError("missing bundled runtime file: {}".format(relative))
        digest = hashlib.sha256(bundled_path.read_bytes()).hexdigest()
        if digest != entry.get("sha256"):
            raise ValueError("bundled runtime hash mismatch: {}".format(relative))
        source = entry.get("source")
        if source and source != "generated-entrypoint":
            source_path = root / source
            if not source_path.is_file() or source_path.read_bytes() != bundled_path.read_bytes():
                raise ValueError("bundled runtime source drift: {}".format(relative))

    actual_paths = {
        path.relative_to(runtime).as_posix()
        for path in runtime.rglob("*")
        if path.is_file()
        and path != manifest_path
        and path.suffix != ".pyc"
        and "__pycache__" not in path.parts
    }
    if listed_paths != actual_paths:
        raise ValueError(
            "bundled runtime file set differs from manifest: missing={} extra={}".format(
                sorted(listed_paths - actual_paths),
                sorted(actual_paths - listed_paths),
            )
        )


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    release_version = (root / "VERSION").read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", release_version):
        raise ValueError("VERSION must contain a semantic version")
    license_content = (root / "LICENSE").read_bytes()
    catalog = load_catalog(root / "knowledge" / "android_memory_catalog.json")
    if catalog["generated_from"].get("visibility") != "private":
        raise ValueError("catalog must preserve the private-source boundary")
    known_artifacts = {spec.artifact_type for spec in ARTIFACT_SPECS}
    known_intents = set(INTENT_PROFILES) | {"all"}
    for record in catalog["records"]:
        unknown_intents = set(record["intents"]) - known_intents
        if unknown_intents:
            raise ValueError(
                "{} has unknown intents: {}".format(record["id"], sorted(unknown_intents))
            )
        evidence_types = set(record["evidence"]["required"]) | set(
            record["evidence"]["supporting"]
        )
        unknown_artifacts = evidence_types - known_artifacts
        if unknown_artifacts:
            raise ValueError(
                "{} has unknown artifacts: {}".format(record["id"], sorted(unknown_artifacts))
            )
        for practice_path in record.get("practice", []):
            if not (root / practice_path).exists():
                raise ValueError(
                    "{} references missing practice path: {}".format(
                        record["id"], practice_path
                    )
                )
        for source in record["sources"]:
            if urlparse(source["url"]).hostname not in ALLOWED_SOURCE_HOSTS:
                raise ValueError(
                    "{} source is not on an approved primary host: {}".format(
                        record["id"], source["url"]
                    )
                )

    skills_root = root / "skills"
    skill_dirs = sorted(path for path in skills_root.glob("android-memory-*") if path.is_dir())
    if len(skill_dirs) != 3:
        raise ValueError("expected exactly 3 Android memory Skills, found {}".format(len(skill_dirs)))
    for skill_dir in skill_dirs:
        validate_skill(skill_dir)
        skill_license = skill_dir / "LICENSE"
        if not skill_license.is_file() or skill_license.read_bytes() != license_content:
            raise ValueError("Skill license differs from root LICENSE: {}".format(skill_dir))
    validate_runtime_bundle(root, catalog)

    print(
        "Validated catalog, self-contained runtime, and {} Android memory Skills.".format(
            len(skill_dirs)
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
