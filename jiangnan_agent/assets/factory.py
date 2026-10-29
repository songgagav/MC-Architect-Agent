"""Create registered modules through the existing hall and corridor adapters."""

from __future__ import annotations

from ..assembly.adapters import corridor_module, hall_module
from ..assembly.model import Module
from ..generators.hall import CorridorParameters, HallParameters
from ..parameters import resolve_parameters
from .registry import get_asset


def module_from_asset(
    module_id: str,
    asset_id: str,
    parameters=None,
    *,
    schema_version: int | None = None,
    asset_version: int | None = None,
    base_config=None,
) -> Module:
    asset = get_asset(asset_id, asset_version)
    resolved = resolve_parameters(
        asset_id,
        parameters,
        schema_version=schema_version,
        base_config=base_config,
        asset_version=asset.version,
    )
    options = dict(resolved.adapter_options)
    if asset.kind == "hall" and isinstance(resolved.generator_parameters, HallParameters):
        module = hall_module(module_id, resolved.generator_parameters, through_passage=options["through_passage"])
    elif asset.kind == "corridor" and isinstance(resolved.generator_parameters, CorridorParameters):
        module = corridor_module(module_id, resolved.generator_parameters, passage_width=options["passage_width"])
    else:
        raise ValueError(f"asset {asset_id!r} has no supported local generator")

    actual_anchors = {anchor.name for anchor in module.anchors}
    if not actual_anchors <= set(asset.anchor_interfaces):
        raise ValueError(f"generated anchors do not match asset registry for {asset_id!r}")
    metadata = {
        "asset_id": asset.asset_id,
        "asset_version": asset.version,
        "knowledge_base_version": asset.knowledge_base_version,
        "parameter_schema_id": asset.parameter_schema_id,
        "parameter_schema_version": resolved.schema_version,
        "parameter_config": dict(resolved.normalized_inputs),
        "derived_parameters": dict(resolved.derived_parameters),
        "parameter_warnings": [
            {
                "rule_id": warning.rule_id,
                "message": warning.message,
                "evidence_kind": warning.evidence_kind.value,
                "confidence": warning.confidence.value,
            }
            for warning in resolved.warnings
        ],
    }
    return Module(
        module.module_id,
        module.kind,
        module.model,
        module.anchors,
        module.clearance_zones,
        module.parameters,
        module.transform_steps,
        metadata,
    )
