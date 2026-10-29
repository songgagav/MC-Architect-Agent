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
