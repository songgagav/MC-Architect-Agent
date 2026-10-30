"""Typed models for versioned and traceable knowledge records."""

from __future__ import annotations

from dataclasses import dataclass, field
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


class RegionStatus(StrEnum):
    ACTIVE = "active"
    CATALOG_ONLY = "catalog_only"


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
    publisher_or_author: str = "legacy source record"
    publication_date: str | None = None
    date_note: str = "not stated in legacy record"
    url: str | None = None
    doi: str | None = None
    isbn: str | None = None
    section_or_page: str = "not recorded in legacy record"
    verification_level: str = "legacy_unverified"
    accessed_date: str = "not recorded in legacy record"

    def __post_init__(self) -> None:
        for name in ("source_id", "source_type", "title", "locator"):
            _text(getattr(self, name), name)
        for name in (
            "publisher_or_author",
            "date_note",
            "section_or_page",
            "verification_level",
            "accessed_date",
        ):
            _text(getattr(self, name), name)
        for name in ("publication_date", "url", "doi", "isbn"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{name} must be null or a non-empty string")


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
    verification_level: str = "legacy_unverified"
    status: str = "active"

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
        if self.status not in {"active", "pending_verification"}:
            raise ValueError("status must be 'active' or 'pending_verification'")
        _text(self.verification_level, "verification_level")
        if self.status == "pending_verification" and self.verification_level == "primary_source_full_text":
            raise ValueError("pending rules cannot claim full-text verification")


@dataclass(frozen=True)
class RegionProfile:
    region_id: str
    label: str
    status: RegionStatus
    scope: str
    source_ids: tuple[str, ...] = ()
    notes: str = ""

    def __post_init__(self) -> None:
        for name in ("region_id", "label", "scope"):
            _text(getattr(self, name), name)
        if not isinstance(self.status, RegionStatus):
            raise ValueError("status must be a supported RegionStatus")
        if any(not isinstance(item, str) or not item.strip() for item in self.source_ids):
            raise ValueError("source_ids must contain non-empty strings")
        if not isinstance(self.notes, str):
            raise ValueError("notes must be a string")


@dataclass(frozen=True)
class KnowledgeBase:
    version: int
    sources: Mapping[str, KnowledgeSource]
    rules: tuple[KnowledgeRule, ...]
    regions: Mapping[str, RegionProfile] = field(default_factory=dict)

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
        regions = dict(self.regions)
        if any(key != profile.region_id for key, profile in regions.items()):
            raise ValueError("region profile keys must match region IDs")
        missing_region_sources = sorted(
            {source_id for profile in regions.values() for source_id in profile.source_ids} - set(sources)
        )
        if missing_region_sources:
            raise ValueError(
                f"region profiles reference unknown sources: {', '.join(missing_region_sources)}"
            )
        known_regions = set(regions) | {"unspecified", "not_applicable"}
        unknown_regions = sorted(
            {region for rule in self.rules for region in rule.applicable_regions} - known_regions
        ) if regions else []
        if unknown_regions:
            raise ValueError(f"knowledge rules reference unknown regions: {', '.join(unknown_regions)}")
        inactive_rule_regions = sorted({
            region
            for rule in self.rules
            if rule.status == "active"
            for region in rule.applicable_regions
            if region in regions and regions[region].status is RegionStatus.CATALOG_ONLY
        })
        if inactive_rule_regions:
            raise ValueError(
                f"catalog-only regions cannot have active rules: {', '.join(inactive_rule_regions)}"
            )
        object.__setattr__(self, "sources", MappingProxyType(sources))
        object.__setattr__(self, "regions", MappingProxyType(regions))

    def rules_for(
        self,
        evidence_kind: EvidenceKind | None = None,
        *,
        region: str | None = None,
        building_type: str | None = None,
        include_pending: bool = False,
    ) -> tuple[KnowledgeRule, ...]:
        """Return exact-tag rules; pending and catalog-only records are opt-in/inert."""
        if region is not None:
            profile = self.regions.get(region)
            if profile is not None and profile.status is RegionStatus.CATALOG_ONLY:
                return ()
            if self.regions and profile is None and region not in {"unspecified", "not_applicable"}:
                return ()
        return tuple(
            rule
            for rule in self.rules
            if (include_pending or rule.status == "active")
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
    split_sources = path.parent / "sources.json"
    split_regions = path.parent / "regions.json"
    if split_sources.is_file() or split_regions.is_file():
        if not split_sources.is_file() or not split_regions.is_file():
            raise ValueError(f"split knowledge version {version} requires sources.json and regions.json")
        source_data = json.loads(split_sources.read_text(encoding="utf-8"))
        region_data = json.loads(split_regions.read_text(encoding="utf-8"))
        if source_data.get("version") != version or region_data.get("version") != version:
            raise ValueError(f"knowledge source/region version mismatch in {path.parent}")
        source_items = source_data.get("sources", [])
        region_items = region_data.get("regions", [])
        rule_items = data.get("rules", [])
    else:
        source_items = data.get("sources", [])
        region_items = []
        rule_items = data.get("rules", [])
    sources = {
        item["source_id"]: KnowledgeSource(**item)
        for item in source_items
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
            verification_level=item.get("verification_level", "legacy_unverified"),
            status=item.get("status", "active"),
        )
        for item in rule_items
    )
    regions = {
        item["region_id"]: RegionProfile(
            region_id=item["region_id"],
            label=item["label"],
            status=RegionStatus(item["status"]),
            scope=item["scope"],
            source_ids=tuple(item.get("source_ids", [])),
            notes=item.get("notes", ""),
        )
        for item in region_items
    }
    return KnowledgeBase(version, sources, rules, regions)
