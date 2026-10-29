"""Pure transforms for module geometry and its connection metadata."""

from __future__ import annotations

from itertools import product

from ..core.geometry import BoundingBox, Position
from ..core.scene import VoxelModel
from ..core.transforms import rotate_model_y
from .model import ClearanceZone, ConnectionAnchor, Module

_FACINGS = ("north", "east", "south", "west")


def _append_step(module: Module, step: dict[str, object]) -> tuple[dict[str, object], ...]:
    return (*module.transform_steps, step)


def _checked_offset(offset: Position) -> Position:
    if (
        not isinstance(offset, tuple)
        or len(offset) != 3
        or any(isinstance(value, bool) or not isinstance(value, int) for value in offset)
    ):
        raise ValueError("translation must contain three integer offsets")
    return offset


def _rotate_point(position: Position, bounds: BoundingBox, turns: int) -> Position:
    x, y, z = position
    local_x, local_z = x - bounds.min_x, z - bounds.min_z
    width, _height, depth = bounds.size
    if turns == 0:
        return position
    if turns == 1:
        return bounds.min_x + depth - local_z, y, bounds.min_z + local_x
    if turns == 2:
        return bounds.min_x + width - local_x, y, bounds.min_z + depth - local_z
    return bounds.min_x + local_z, y, bounds.min_z + width - local_x


def _rotate_facing(facing: str, turns: int) -> str:
    return _FACINGS[(_FACINGS.index(facing) + turns) % 4]


def _map_box(bounds: BoundingBox, transform) -> BoundingBox:
    corners = (
        transform((x, y, z))
        for x, y, z in product(
            (bounds.min_x, bounds.max_x),
            (bounds.min_y, bounds.max_y),
            (bounds.min_z, bounds.max_z),
        )
    )
    values = tuple(corners)
    return BoundingBox(
        min(point[0] for point in values),
        min(point[1] for point in values),
        min(point[2] for point in values),
        max(point[0] for point in values),
        max(point[1] for point in values),
        max(point[2] for point in values),
    )


def translate_module(module: Module, offset: Position) -> Module:
    """Return a copy shifted in X/Y/Z, including anchors and clearance zones."""

    dx, dy, dz = _checked_offset(offset)
    anchors = tuple(
        ConnectionAnchor(
            anchor.name,
            (anchor.position[0] + dx, anchor.position[1] + dy, anchor.position[2] + dz),
            anchor.facing,
            anchor.connection_type,
            anchor.width,
            anchor.height,
        )
        for anchor in module.anchors
    )
    clearances = tuple(
        ClearanceZone(zone.name, zone.bounds.translated(dx, dy, dz), zone.purpose)
        for zone in module.clearance_zones
    )
    steps = module.transform_steps
    if offset != (0, 0, 0):
        steps = _append_step(module, {"op": "translate", "offset": (dx, dy, dz)})
    return Module(
        module.module_id,
        module.kind,
        module.model.translated(dx, dy, dz),
        anchors,
        clearances,
        module.parameters,
        steps,
        module.metadata,
    )


def rotate_module(module: Module, quarter_turns: int) -> Module:
    """Rotate blocks, anchor planes, and clearance boxes around the model's X/Z extents."""

    if isinstance(quarter_turns, bool) or not isinstance(quarter_turns, int):
        raise ValueError("quarter_turns must be an integer")
    turns = quarter_turns % 4
    bounds = module.model.bounds
    anchors = tuple(
        ConnectionAnchor(
            anchor.name,
            _rotate_point(anchor.position, bounds, turns),
            _rotate_facing(anchor.facing, turns),
            anchor.connection_type,
            anchor.width,
            anchor.height,
        )
        for anchor in module.anchors
    )
    clearances = tuple(
        ClearanceZone(zone.name, _map_box(zone.bounds, lambda point: _rotate_point(point, bounds, turns)), zone.purpose)
        for zone in module.clearance_zones
    )
    steps = module.transform_steps
    if turns:
        steps = _append_step(module, {"op": "rotate_y", "quarter_turns": turns})
    return Module(
        module.module_id,
        module.kind,
        rotate_model_y(module.model, turns),
        anchors,
        clearances,
        module.parameters,
        steps,
        module.metadata,
    )


def mirror_module(module: Module, axis: str) -> Module:
    """Reflect a module across its X or Z center plane and mirror directional states."""

    if axis not in ("x", "z"):
        raise ValueError("mirror axis must be 'x' or 'z'")
    bounds = module.model.bounds

    def mirror_point(position: Position) -> Position:
        x, y, z = position
        if axis == "x":
            return bounds.min_x + bounds.max_x - x, y, z
        return x, y, bounds.min_z + bounds.max_z - z

    def mirror_block(position: Position) -> Position:
        x, y, z = position
        if axis == "x":
            return bounds.min_x + bounds.max_x - 1 - x, y, z
        return x, y, bounds.min_z + bounds.max_z - 1 - z

    mirrored_model = VoxelModel()
    for position, state in module.model.blocks.items():
        mirrored_model.set_block(mirror_block(position), state.mirror(axis))
    anchors = tuple(
        ConnectionAnchor(
            anchor.name,
            mirror_point(anchor.position),
            anchor.facing
            if (axis == "x" and anchor.facing in ("north", "south"))
            or (axis == "z" and anchor.facing in ("east", "west"))
            else {"east": "west", "west": "east", "north": "south", "south": "north"}[anchor.facing],
            anchor.connection_type,
            anchor.width,
            anchor.height,
        )
        for anchor in module.anchors
    )
    clearances = tuple(
        ClearanceZone(zone.name, _map_box(zone.bounds, mirror_point), zone.purpose)
        for zone in module.clearance_zones
    )
    steps = _append_step(module, {"op": "mirror", "axis": axis})
    return Module(
        module.module_id,
        module.kind,
        mirrored_model,
        anchors,
        clearances,
        module.parameters,
        steps,
        module.metadata,
    )
