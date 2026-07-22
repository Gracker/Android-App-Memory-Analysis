"""Stable data contracts shared by the CLI and repository-owned Skills."""

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


RUNTIME_NAME = "android-memory-ai"
RUNTIME_VERSION = "1.2.0"
SCHEMA_VERSION = "1.2"


@dataclass
class ArtifactEvidence:
    """A discovered artifact and what can safely be asserted about it."""

    artifact_id: str
    artifact_type: str
    status: str
    accounting_domain: str
    perturbation: str
    path: Optional[str] = None
    local_path: Optional[str] = field(default=None, repr=False)
    size_bytes: Optional[int] = None
    sha256: Optional[str] = None
    source: str = "discovered"
    validation: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data.pop("local_path", None)
        return _without_none(data)


@dataclass
class EvidenceGap:
    """A missing or unusable input plus an actionable collection route."""

    artifact_type: str
    priority: str
    reason_zh: str
    reason_en: str
    command: Optional[str]
    prerequisites_zh: List[str]
    prerequisites_en: List[str]
    perturbation: str
    alternatives: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return _without_none(asdict(self))


@dataclass
class EvidenceCoverage:
    """Intent-specific evidence support without pseudo-probabilities."""

    level: str
    intent: str
    required: List[str]
    supporting: List[str]
    available: List[str]
    missing_required: List[str]
    missing_supporting: List[str]
    inadequate: List[str] = field(default_factory=list)
    satisfied_any_of: List[List[str]] = field(default_factory=list)
    missing_any_of: List[List[str]] = field(default_factory=list)
    rationale_zh: str = ""
    rationale_en: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return _without_none(asdict(self))


@dataclass
class EvidenceConflict:
    """Two evidence sources that should not be silently reconciled."""

    field: str
    values: Dict[str, Any]
    severity: str
    explanation_zh: str
    explanation_en: str

    def to_dict(self) -> Dict[str, Any]:
        return _without_none(asdict(self))


def _without_none(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _without_none(item)
            for key, item in value.items()
            if item is not None
        }
    if isinstance(value, list):
        return [_without_none(item) for item in value]
    return value
