"""Deterministic JSON conversion for complete module assemblies."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..assembly.model import Assembly, ClearanceZone, Connection, ConnectionAnchor, Module
from ..core.block import BlockState
from ..core.geometry import BoundingBox
from ..core.scene import VoxelModel

_BOX_KEYS = ("min_x", "min_y", "min_z", "max_x", "max_y", "max_z")


def _integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    return value


def _position(value: object, name: str) -> tuple[int, int, int]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError(f"{name} must contain three integer coordinates")
    return tuple(_integer(coordinate, name) for coordinate in value)  # type: ignore[return-value]


def _plain_json(value: object) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain_json(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_plain_json(item) for item in value]
    return value


def _box_to_dict(bounds: BoundingBox) -> dict[str, int]:
    return {key: getattr(bounds, key) for key in _BOX_KEYS}


def _box_from_dict(data: object) -> BoundingBox:
    if not isinstance(data, Mapping) or any(key not in data for key in _BOX_KEYS):
        raise ValueError("clearance bounds must contain min_x/min_y/min_z/max_x/max_y/max_z")
    return BoundingBox(**{key: _integer(data[key], f"clearance {key}") for key in _BOX_KEYS})


def assembly_to_dict(assembly: Assembly) -> dict[str, Any]:
    """Return a stable, JSON-compatible representation of an Assembly."""

    if not isinstance(assembly, Assembly):
        raise ValueError("assembly must be an Assembly")
    modules: list[dict[str, Any]] = []
    for module in sorted(assembly.modules.values(), key=lambda item: item.module_id):
        blocks = [
            {"position": list(position), "state": state.to_string()}
            for position, state in sorted(module.model.blocks.items())
        ]
        anchors = [
            {
                "name": anchor.name,
                "position": list(anchor.position),
                "facing": anchor.facing,
                "connection_type": anchor.connection_type,
                "width": anchor.width,
                "height": anchor.height,
            }
            for anchor in sorted(module.anchors, key=lambda item: item.name)
        ]
        clearances = [
            {"name": zone.name, "bounds": _box_to_dict(zone.bounds), "purpose": zone.purpose}
            for zone in sorted(module.clearance_zones, key=lambda item: item.name)
        ]
        modules.append(
            {
                "module_id": module.module_id,
                "kind": module.kind,
                "parameters": _plain_json(module.parameters),
                "transform_steps": [_plain_json(step) for step in module.transform_steps],
                "blocks": blocks,
                "anchors": anchors,
                "clearance_zones": clearances,
            }
        )

    connections = [
        {
            "first_module_id": connection.first_module_id,
            "first_anchor": connection.first_anchor,
            "second_module_id": connection.second_module_id,
            "second_anchor": connection.second_anchor,
        }
        for connection in sorted(
            assembly.connections,
            key=lambda item: (
                item.first_module_id,
                item.first_anchor,
                item.second_module_id,
                item.second_anchor,
            ),
        )
    ]
    return {"modules": modules, "connections": connections}


def assembly_from_dict(data: Mapping[str, Any]) -> Assembly:
    """Validate and restore an Assembly from its JSON object representation."""

    if not isinstance(data, Mapping):
        raise ValueError("assembly must be a JSON object")
    raw_modules = data.get("modules")
    raw_connections = data.get("connections", [])
    if not isinstance(raw_modules, (list, tuple)):
        raise ValueError("assembly modules must be a list")
    if not isinstance(raw_connections, (list, tuple)):
        raise ValueError("assembly connections must be a list")

    modules: list[Module] = []
    for index, raw in enumerate(raw_modules):
        if not isinstance(raw, Mapping):
            raise ValueError(f"assembly module {index} must be a JSON object")
        module_id = raw.get("module_id")
        kind = raw.get("kind")
        if not isinstance(module_id, str) or not isinstance(kind, str):
            raise ValueError(f"assembly module {index} must include string module_id and kind")

        model = VoxelModel()
        raw_blocks = raw.get("blocks", [])
        if not isinstance(raw_blocks, (list, tuple)):
            raise ValueError(f"blocks for module {module_id!r} must be a list")
        for block_index, raw_block in enumerate(raw_blocks):
            if not isinstance(raw_block, Mapping) or not isinstance(raw_block.get("state"), str):
                raise ValueError(f"block {block_index} in module {module_id!r} is malformed")
            block_position = _position(raw_block.get("position"), f"block {block_index} position")
            if block_position in model.blocks:
                raise ValueError(f"duplicate block position {block_position} in module {module_id!r}")
            try:
                model.set_block(block_position, BlockState.parse(raw_block["state"]))
            except ValueError as exc:
                raise ValueError(f"invalid block state in module {module_id!r}: {exc}") from exc

        raw_anchors = raw.get("anchors", [])
        if not isinstance(raw_anchors, (list, tuple)):
            raise ValueError(f"anchors for module {module_id!r} must be a list")
        anchors: list[ConnectionAnchor] = []
        for raw_anchor in raw_anchors:
            if not isinstance(raw_anchor, Mapping):
                raise ValueError(f"anchor in module {module_id!r} must be a JSON object")
            anchors.append(
                ConnectionAnchor(
                    name=raw_anchor.get("name"),
                    position=_position(raw_anchor.get("position"), "anchor position"),
                    facing=raw_anchor.get("facing"),
                    connection_type=raw_anchor.get("connection_type"),
                    width=raw_anchor.get("width", 1),
                    height=raw_anchor.get("height", 1),
                )
            )

        raw_clearances = raw.get("clearance_zones", [])
        if not isinstance(raw_clearances, (list, tuple)):
            raise ValueError(f"clearance_zones for module {module_id!r} must be a list")
        clearances: list[ClearanceZone] = []
        for raw_zone in raw_clearances:
            if not isinstance(raw_zone, Mapping):
                raise ValueError(f"clearance zone in module {module_id!r} must be a JSON object")
            clearances.append(
                ClearanceZone(
                    name=raw_zone.get("name"),
                    bounds=_box_from_dict(raw_zone.get("bounds")),
                    purpose=raw_zone.get("purpose"),
                )
            )

        parameters = raw.get("parameters", {})
        raw_steps = raw.get("transform_steps", [])
        if not isinstance(parameters, Mapping):
            raise ValueError(f"parameters for module {module_id!r} must be a JSON object")
        if not isinstance(raw_steps, (list, tuple)):
            raise ValueError(f"transform_steps for module {module_id!r} must be a list")
        modules.append(
            Module(
                module_id,
                kind,
                model,
                tuple(anchors),
                tuple(clearances),
                parameters=parameters,
                transform_steps=tuple(raw_steps),
            )
        )

    connections: list[Connection] = []
    for index, raw_connection in enumerate(raw_connections):
        if not isinstance(raw_connection, Mapping):
            raise ValueError(f"assembly connection {index} must be a JSON object")
        try:
            connections.append(
                Connection(
                    first_module_id=raw_connection.get("first_module_id"),
                    first_anchor=raw_connection.get("first_anchor"),
                    second_module_id=raw_connection.get("second_module_id"),
                    second_anchor=raw_connection.get("second_anchor"),
                )
            )
        except ValueError as exc:
            raise ValueError(f"invalid assembly connection {index}: {exc}") from exc
    try:
        return Assembly(modules, connections)
    except ValueError as exc:
        raise ValueError(f"invalid assembly: {exc}") from exc
