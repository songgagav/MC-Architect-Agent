"""Versioned module asset registry and generator adapters."""

from .factory import module_from_asset
from .registry import AssetSpec, get_asset, get_asset_for_kind, list_assets

__all__ = ["AssetSpec", "get_asset", "get_asset_for_kind", "list_assets", "module_from_asset"]
