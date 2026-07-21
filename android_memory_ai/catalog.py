"""Load and validate the public operational knowledge catalog."""

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


class CatalogError(ValueError):
    """Raised when the repository knowledge catalog breaks its contract."""


def default_catalog_path() -> Path:
    return Path(__file__).resolve().parent.parent / "knowledge" / "android_memory_catalog.json"


def load_catalog(path: Optional[Path] = None) -> Dict[str, Any]:
    catalog_path = Path(path) if path else default_catalog_path()
    try:
        data = json.loads(catalog_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CatalogError("knowledge catalog not found: {}".format(catalog_path)) from exc
    except json.JSONDecodeError as exc:
        raise CatalogError("invalid knowledge catalog JSON: {}".format(exc)) from exc

    _validate_catalog(data)
    return data


def select_records(
    catalog: Dict[str, Any],
    intent: str,
    artifact_types: Iterable[str],
) -> List[Dict[str, Any]]:
    available = set(artifact_types)
    selected = []
    for record in catalog["records"]:
        intents = set(record.get("intents", []))
        evidence = set(record.get("evidence", {}).get("required", []))
        supporting = set(record.get("evidence", {}).get("supporting", []))
        if "all" in intents or intent in intents or available.intersection(evidence | supporting):
            selected.append(record)
    return selected


def _validate_catalog(data: Dict[str, Any]) -> None:
    required_root = {"schema_version", "catalog_id", "generated_from", "records"}
    missing_root = required_root.difference(data)
    if missing_root:
        raise CatalogError("catalog missing root fields: {}".format(sorted(missing_root)))
    if data["schema_version"] != "1.0":
        raise CatalogError("unsupported catalog schema_version: {}".format(data["schema_version"]))
    if not isinstance(data["records"], list) or not data["records"]:
        raise CatalogError("catalog records must be a non-empty list")
    generated_from = data["generated_from"]
    if not isinstance(generated_from, dict):
        raise CatalogError("generated_from must be an object")
    source_revision = generated_from.get("revision")
    if not isinstance(source_revision, str) or not re.fullmatch(r"[0-9a-f]{40}", source_revision):
        raise CatalogError("generated_from revision must be a full Git SHA")

    ids = set()
    for index, record in enumerate(data["records"]):
        required_record = {
            "id",
            "title",
            "summary",
            "intents",
            "accounting_domains",
            "evidence",
            "does_not_prove",
            "version_scope",
            "theory_origin",
            "sources",
        }
        missing = required_record.difference(record)
        if missing:
            raise CatalogError(
                "record {} missing fields: {}".format(index, sorted(missing))
            )
        record_id = record["id"]
        if not isinstance(record_id, str) or not re.fullmatch(r"[a-z0-9-]+", record_id):
            raise CatalogError("invalid knowledge record id: {}".format(record_id))
        if record_id in ids:
            raise CatalogError("duplicate knowledge record id: {}".format(record_id))
        ids.add(record_id)
        _require_languages(record_id, "title", record["title"])
        _require_languages(record_id, "summary", record["summary"])
        _require_languages(record_id, "does_not_prove", record["does_not_prove"])
        evidence = record["evidence"]
        if not isinstance(evidence, dict):
            raise CatalogError("record {} evidence must be an object".format(record_id))
        if "required" not in evidence or "supporting" not in evidence:
            raise CatalogError(
                "record {} evidence needs required and supporting lists".format(record_id)
            )
        for evidence_role in ("required", "supporting"):
            values = evidence[evidence_role]
            if not isinstance(values, list) or not all(
                isinstance(value, str) and value for value in values
            ):
                raise CatalogError(
                    "record {} evidence {} must be a string list".format(
                        record_id, evidence_role
                    )
                )
        if not isinstance(record["intents"], list) or not record["intents"]:
            raise CatalogError("record {} needs at least one intent".format(record_id))
        if not isinstance(record["accounting_domains"], list) or not record["accounting_domains"]:
            raise CatalogError("record {} needs accounting domains".format(record_id))
        version_scope = record["version_scope"]
        if not isinstance(version_scope, dict) or not all(
            version_scope.get(key) for key in ("baseline", "caveat")
        ):
            raise CatalogError(
                "record {} version_scope needs baseline and caveat".format(record_id)
            )
        theory_origin = record["theory_origin"]
        if not isinstance(theory_origin, dict) or not theory_origin.get("article"):
            raise CatalogError("record {} needs a theory article".format(record_id))
        if theory_origin.get("revision") != source_revision:
            raise CatalogError(
                "record {} theory revision differs from generated_from".format(record_id)
            )
        if not isinstance(record["sources"], list) or not record["sources"]:
            raise CatalogError("record {} needs at least one source".format(record_id))
        for source in record["sources"]:
            if not isinstance(source, dict) or not all(
                source.get(key) for key in ("title", "url", "type")
            ):
                raise CatalogError("record {} has an incomplete source".format(record_id))
            if not source["url"].startswith("https://"):
                raise CatalogError(
                    "record {} source must use HTTPS: {}".format(
                        record_id, source["url"]
                    )
                )


def _require_languages(record_id: str, field_name: str, value: Any) -> None:
    if not isinstance(value, dict) or not value.get("zh") or not value.get("en"):
        raise CatalogError(
            "record {} field {} needs non-empty zh and en values".format(
                record_id, field_name
            )
        )
