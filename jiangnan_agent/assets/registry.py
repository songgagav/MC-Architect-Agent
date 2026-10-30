"""Versioned registry of executable building assets."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path

from ..knowledge import load_knowledge_base


@dataclass(frozen=True)
class AssetSpec:
    asset_id: str
    version: int
    kind: str
    parameter_schema_id: str
    parameter_schema_version: int
    knowledge_base_version: int
    source_id: str
    anchor_interfaces: tuple[str, ...]
    region_ids: tuple[str, ...] = ()
    knowledge_rule_ids: tuple[str, ...] = ()
    minecraft_version: str | None = None
    region_association_kind: str = "unclassified"
    region_association_note: str = ""

    def __post_init__(self) -> None:
        for name in ("asset_id", "kind", "parameter_schema_id", "source_id"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ValueError(f"{name} must be a non-empty string")
        for name in ("version", "parameter_schema_version", "knowledge_base_version"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if not self.anchor_interfaces or any(not isinstance(item, str) or not item for item in self.anchor_interfaces):
            raise ValueError("anchor_interfaces must contain non-empty anchor names")
        for field_name, values in (("region_ids", self.region_ids), ("knowledge_rule_ids", self.knowledge_rule_ids)):
            if any(not isinstance(item, str) or not item for item in values):
                raise ValueError(f"{field_name} must contain non-empty strings")
        if self.minecraft_version is not None and (
            not isinstance(self.minecraft_version, str) or not self.minecraft_version.strip()
        ):
            raise ValueError("minecraft_version must be null or a non-empty string")
        if self.region_association_kind not in {"unclassified", "design_target"}:
            raise ValueError("region_association_kind must be unclassified or design_target")
        if not isinstance(self.region_association_note, str):
            raise ValueError("region_association_note must be a string")
        if self.version >= 3 and (
            not self.region_ids
            or not self.knowledge_rule_ids
            or self.minecraft_version != "1.21.5"
            or self.region_association_kind != "design_target"
            or not self.region_association_note.strip()
        ):
            raise ValueError("version 3+ assets need region/rule links and Minecraft 1.21.5 design-target metadata")


@lru_cache(maxsize=None)
def list_assets(version: int | None = None) -> tuple[AssetSpec, ...]:
    if version is None:
        available = _available_catalog_versions()
        if not available:
            raise ValueError("no asset registry versions are available")
        version = available[-1]
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise ValueError("asset registry version must be a positive integer")
    path = Path(__file__).parent / f"v{version}" / "assets.json"
    if not path.is_file():
        raise ValueError(f"unsupported asset registry version: {version}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("version") != version:
        raise ValueError(f"asset registry version mismatch in {path}")
    assets = tuple(
        AssetSpec(
            asset_id=item["asset_id"],
            version=item["version"],
            kind=item["kind"],
            parameter_schema_id=item["parameter_schema_id"],
            parameter_schema_version=item["parameter_schema_version"],
            knowledge_base_version=item["knowledge_base_version"],
            source_id=item["source_id"],
            anchor_interfaces=tuple(item["anchor_interfaces"]),
            region_ids=tuple(item.get("region_ids", [])),
            knowledge_rule_ids=tuple(item.get("knowledge_rule_ids", [])),
            minecraft_version=item.get("minecraft_version"),
            region_association_kind=item.get("region_association_kind", "unclassified"),
            region_association_note=item.get("region_association_note", ""),
        )
        for item in data.get("assets", [])
    )
    id_versions = [(asset.asset_id, asset.version) for asset in assets]
    kind_asset_ids: dict[str, set[str]] = {}
    for asset in assets:
        knowledge = load_knowledge_base(asset.knowledge_base_version)
        if asset.source_id not in knowledge.sources:
            raise ValueError(
                f"asset {asset.asset_id!r} references unknown knowledge source {asset.source_id!r}"
            )
        if asset.version >= 3:
            if knowledge.sources[asset.source_id].source_type != "project_code":
                raise ValueError(f"asset {asset.asset_id!r} must cite its generator source code")
            profiles = knowledge.regions
            for region_id in asset.region_ids:
                profile = profiles.get(region_id)
                if profile is None or profile.status.value != "active":
                    raise ValueError(
                        f"asset {asset.asset_id!r} references non-active region {region_id!r}"
                    )
            rules = {rule.rule_id: rule for rule in knowledge.rules}
            for rule_id in asset.knowledge_rule_ids:
                rule = rules.get(rule_id)
                if rule is None or rule.status != "active":
                    raise ValueError(
                        f"asset {asset.asset_id!r} references unknown or inactive knowledge rule {rule_id!r}"
                    )
                if not set(asset.region_ids).intersection(rule.applicable_regions):
                    raise ValueError(
                        f"asset {asset.asset_id!r} has a knowledge rule outside its design-target regions: {rule_id!r}"
                    )
        kind_asset_ids.setdefault(asset.kind, set()).add(asset.asset_id)
    if len(id_versions) != len(set(id_versions)) or any(len(ids) > 1 for ids in kind_asset_ids.values()):
        raise ValueError("asset ID/version pairs must be unique and each generator kind needs one stable asset ID")
    return tuple(sorted(assets, key=lambda asset: (asset.asset_id, asset.version)))


def _available_catalog_versions() -> tuple[int, ...]:
    versions: list[int] = []
    for path in Path(__file__).parent.glob("v*/assets.json"):
        try:
            version = int(path.parent.name.removeprefix("v"))
        except ValueError:
            continue
        if version > 0:
            versions.append(version)
    return tuple(sorted(set(versions)))


def get_asset(
    asset_id: str,
    asset_version: int | None = None,
    *,
    catalog_version: int | None = None,
) -> AssetSpec:
    matches = [asset for asset in list_assets(catalog_version) if asset.asset_id == asset_id]
    if asset_version is not None:
        matches = [asset for asset in matches if asset.version == asset_version]
    if not matches:
        suffix = "" if asset_version is None else f" at version {asset_version}"
        raise ValueError(f"unknown asset ID{suffix}: {asset_id!r}")
    return max(matches, key=lambda asset: asset.version)


def get_asset_for_kind(kind: str, *, catalog_version: int | None = None) -> AssetSpec:
    matches = [asset for asset in list_assets(catalog_version) if asset.kind == kind]
    if not matches:
        available = list_assets(catalog_version)
        raise ValueError(f"kind must be one of the registered assets: {', '.join(asset.kind for asset in available)}")
    return max(matches, key=lambda asset: asset.version)
