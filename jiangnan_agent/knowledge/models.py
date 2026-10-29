"""Typed models for versioned and traceable knowledge records."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import json
from pathlib import Path
from types import MappingProxyType
from typing import Mapping


class EvidenceKind(StrEnum):
    LITERATURE_FACT = "literature_fact"
    MINECRAFT_ADAPTATION = "minecraft_adaptation"
    USER_PREFERENCE = "user_preference"


class ConfidenceLevel(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


@dataclass(frozen=True)
class KnowledgeSource:
    source_id: str
    source_type: str
    title: str
    locator: str

    def __post_init__(self) -> None:
        for name in ("source_id", "source_type", "title", "locator"):
            _text(getattr(self, name), name)


@dataclass(frozen=True)
class KnowledgeRule:
    rule_id: str
    source_id: str
    applicable_regions: tuple[str, ...]
    building_types: tuple[str, ...]
    evidence_kind: EvidenceKind
    basis: str
    confidence: ConfidenceLevel
    scope: str
    statement: str

    def __post_init__(self) -> None:
        for name in ("rule_id", "source_id", "basis", "scope", "statement"):
            _text(getattr(self, name), name)
        if not self.applicable_regions or any(not isinstance(item, str) or not item for item in self.applicable_regions):
            raise ValueError("applicable_regions must contain at least one non-empty value")
        if not self.building_types or any(not isinstance(item, str) or not item for item in self.building_types):
            raise ValueError("building_types must contain at least one non-empty value")
        if not isinstance(self.evidence_kind, EvidenceKind):
            raise ValueError("evidence_kind must be a supported EvidenceKind")
        if not isinstance(self.confidence, ConfidenceLevel):
            raise ValueError("confidence must be a supported ConfidenceLevel")


@dataclass(frozen=True)
class KnowledgeBase:
    version: int
    sources: Mapping[str, KnowledgeSource]
    rules: tuple[KnowledgeRule, ...]

    def __post_init__(self) -> None:
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1:
            raise ValueError("knowledge base version must be a positive integer")
        sources = dict(self.sources)
        if any(key != source.source_id for key, source in sources.items()):
            raise ValueError("knowledge source keys must match source IDs")
        ids = [rule.rule_id for rule in self.rules]
        if len(ids) != len(set(ids)):
            raise ValueError("knowledge rule IDs must be unique")
        missing = sorted({rule.source_id for rule in self.rules} - set(sources))
        if missing:
            raise ValueError(f"knowledge rules reference unknown sources: {', '.join(missing)}")
        object.__setattr__(self, "sources", MappingProxyType(sources))

    def rules_for(
        self,
        evidence_kind: EvidenceKind | None = None,
        *,
        region: str | None = None,
        building_type: str | None = None,
    ) -> tuple[KnowledgeRule, ...]:
        """Return rules matching exact tags; no geographic hierarchy is inferred."""
        return tuple(
            rule
            for rule in self.rules
            if (evidence_kind is None or rule.evidence_kind is evidence_kind)
            and (region is None or region in rule.applicable_regions)
            and (building_type is None or building_type in rule.building_types)
        )


def _available_knowledge_versions() -> tuple[int, ...]:
    versions: list[int] = []
    for path in Path(__file__).parent.glob("v*/rules.json"):
        try:
            version = int(path.parent.name.removeprefix("v"))
        except ValueError:
            continue
        if version > 0:
            versions.append(version)
    return tuple(sorted(set(versions)))


def load_knowledge_base(version: int | None = None) -> KnowledgeBase:
    if version is None:
        available = _available_knowledge_versions()
        if not available:
            raise ValueError("no knowledge base versions are available")
        version = available[-1]
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise ValueError("knowledge base version must be a positive integer")
    path = Path(__file__).parent / f"v{version}" / "rules.json"
    if not path.is_file():
        raise ValueError(f"unsupported knowledge base version: {version}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("version") != version:
        raise ValueError(f"knowledge base version mismatch in {path}")
    sources = {
        item["source_id"]: KnowledgeSource(**item)
        for item in data.get("sources", [])
    }
    rules = tuple(
        KnowledgeRule(
            rule_id=item["rule_id"],
            source_id=item["source_id"],
            applicable_regions=tuple(item["applicable_regions"]),
            building_types=tuple(item["building_types"]),
            evidence_kind=EvidenceKind(item["evidence_kind"]),
            basis=item["basis"],
            confidence=ConfidenceLevel(item["confidence"]),
            scope=item["scope"],
            statement=item["statement"],
        )
        for item in data.get("rules", [])
    )
    return KnowledgeBase(version, sources, rules)
