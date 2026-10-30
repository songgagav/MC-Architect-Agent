"""Composable block-model generators for common building components."""

from __future__ import annotations

from collections.abc import Iterable

from ..core.block import BlockState
from ..core.geometry import BoundingBox, Position
from ..core.scene import VoxelModel

Material = BlockState | str
_HORIZONTAL_FACES = ("north", "east", "south", "west")
_AXIS_BLOCK_SUFFIXES = ("_log", "_wood", "_stem", "_hyphae")


def _material(value: Material) -> BlockState:
    if isinstance(value, BlockState):
        return value
    if isinstance(value, str):
        return BlockState.parse(value)
    raise ValueError("material must be a BlockState or Minecraft state string")


def _integer(value: int, name: str, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return value


def _position(value: Position, name: str) -> Position:
    if (
        not isinstance(value, tuple)
        or len(value) != 3
        or any(isinstance(part, bool) or not isinstance(part, int) for part in value)
    ):
        raise ValueError(f"{name} must contain three integer coordinates")
    return value


def _state_with(state: BlockState, **updates: str) -> BlockState:
    properties = dict(state.properties)
    properties.update(updates)
    return BlockState(state.block_id, tuple(properties.items()))


def _wood_axis(state: BlockState, axis: str) -> BlockState:
    path = state.block_id.split(":", 1)[1]
    if path.endswith(_AXIS_BLOCK_SUFFIXES) or "axis" in dict(state.properties):
        return _state_with(state, axis=axis)
    return state


def generate_column(
    x: int,
    base_y: int,
    z: int,
    height: int,
    material: Material,
) -> VoxelModel:
    """Create a vertical column, including both base and top blocks."""

    x = _integer(x, "x")
    base_y = _integer(base_y, "base_y")
    z = _integer(z, "z")
    height = _integer(height, "height", minimum=1)
    state = _wood_axis(_material(material), "y")
    model = VoxelModel()
    for y in range(base_y, base_y + height):
        model.set_block((x, y, z), state)
    return model


def generate_beam(start: Position, end: Position, material: Material) -> VoxelModel:
    """Create a straight, axis-aligned beam with inclusive endpoints."""

    start = _position(start, "start")
    end = _position(end, "end")
    changed_axes = [axis for axis in range(3) if start[axis] != end[axis]]
    if len(changed_axes) != 1:
        raise ValueError("beam endpoints must be distinct and axis-aligned")
    axis_index = changed_axes[0]
    axis_name = ("x", "y", "z")[axis_index]
    state = _wood_axis(_material(material), axis_name)
    low, high = sorted((start[axis_index], end[axis_index]))
    model = VoxelModel()
    for coordinate in range(low, high + 1):
        position = list(start)
        position[axis_index] = coordinate
        model.set_block(tuple(position), state)  # type: ignore[arg-type]
    return model


def generate_wall(
    bounds: BoundingBox,
    material: Material,
    openings: Iterable[BoundingBox] = (),
) -> VoxelModel:
    """Fill a wall panel, leaving specified half-open rectangular openings."""

    if not isinstance(bounds, BoundingBox) or any(size <= 0 for size in bounds.size):
        raise ValueError("wall bounds must have positive width, height, and depth")
    state = _material(material)
    opening_boxes = tuple(openings)
    for opening in opening_boxes:
        if not isinstance(opening, BoundingBox) or any(size <= 0 for size in opening.size):
            raise ValueError("wall openings must have positive dimensions")
        if not (
            bounds.min_x <= opening.min_x <= opening.max_x <= bounds.max_x
            and bounds.min_y <= opening.min_y <= opening.max_y <= bounds.max_y
            and bounds.min_z <= opening.min_z <= opening.max_z <= bounds.max_z
        ):
            raise ValueError("wall openings must be within wall bounds")

    model = VoxelModel()
    for y in range(bounds.min_y, bounds.max_y):
        for z in range(bounds.min_z, bounds.max_z):
            for x in range(bounds.min_x, bounds.max_x):
                position = (x, y, z)
                if not any(opening.contains(position) for opening in opening_boxes):
                    model.set_block(position, state)
    return model


def generate_plinth(bounds: BoundingBox, material: Material) -> VoxelModel:
    """Fill a half-open foundation volume with one block state."""

    if not isinstance(bounds, BoundingBox) or any(size <= 0 for size in bounds.size):
        raise ValueError("plinth bounds must have positive width, height, and depth")
    model = VoxelModel()
    model.fill(bounds, _material(material))
    return model


def generate_door(
    x: int,
    base_y: int,
    z: int,
    width: int,
    material: Material,
    facing: str = "south",
) -> VoxelModel:
    """Create a one- or two-block-wide, two-block-tall vanilla door."""

    x = _integer(x, "x")
    base_y = _integer(base_y, "base_y")
    z = _integer(z, "z")
    if isinstance(width, bool) or not isinstance(width, int) or width not in (1, 2):
        raise ValueError("door width must be 1 or 2 blocks")
    if facing not in _HORIZONTAL_FACES:
        raise ValueError("door facing must be north, east, south, or west")
    state = _material(material)
    if not state.block_id.endswith("_door"):
        raise ValueError("door material must be a door block")

    model = VoxelModel()
    for offset in range(width):
        hinge = "left" if width == 1 or offset == 0 else "right"
        for height, half in ((0, "lower"), (1, "upper")):
            model.set_block(
                (x + offset, base_y + height, z),
                _state_with(
                    state,
                    facing=facing,
                    half=half,
                    hinge=hinge,
                    open="false",
                    powered="false",
                ),
            )
    return model


def generate_window(
    x: int,
    y: int,
    z: int,
    width: int,
    height: int,
    material: Material,
    connected_faces: Iterable[str] = (),
) -> VoxelModel:
    """Create a window panel laid out along X and Y."""

    x = _integer(x, "x")
    y = _integer(y, "y")
    z = _integer(z, "z")
    width = _integer(width, "width", minimum=1)
    height = _integer(height, "height", minimum=1)
    faces = frozenset(connected_faces)
    if not faces.issubset(_HORIZONTAL_FACES):
        raise ValueError("connected faces must be north, east, south, or west")
    state = _material(material)
    is_pane = state.block_id.endswith("_pane")
    model = VoxelModel()
    for dx in range(width):
        for dy in range(height):
            pane_state = state
            if is_pane:
                connections = set(faces)
                if dx > 0:
                    connections.add("west")
                if dx < width - 1:
                    connections.add("east")
                updates = {face: str(face in connections).lower() for face in _HORIZONTAL_FACES}
                updates["waterlogged"] = "false"
                pane_state = _state_with(state, **updates)
            model.set_block((x + dx, y + dy, z), pane_state)
    return model


def generate_eaves(
    start: Position,
    end: Position,
    material: Material,
    overhang: int = 0,
) -> VoxelModel:
    """Create a horizontal eaves run, extending both ends by ``overhang``."""

    start = _position(start, "start")
    end = _position(end, "end")
    overhang = _integer(overhang, "overhang", minimum=0)
    if start[1] != end[1] or (start[0] == end[0]) == (start[2] == end[2]):
        raise ValueError("eaves endpoints must define a nonzero horizontal X or Z run")
    axis_index = 0 if start[0] != end[0] else 2
    low, high = sorted((start[axis_index], end[axis_index]))
    extended_start = list(start)
    extended_end = list(start)
    extended_start[axis_index] = low - overhang
    extended_end[axis_index] = high + overhang
    return generate_beam(tuple(extended_start), tuple(extended_end), material)  # type: ignore[arg-type]


def generate_gable_roof(
    width: int,
    depth: int,
    base_y: int,
    rise: int,
    eaves: int,
    material: Material,
) -> VoxelModel:
    """Create a symmetric stepped gable roof, with its ridge running along X."""

    width = _integer(width, "width", minimum=1)
    depth = _integer(depth, "depth", minimum=3)
    base_y = _integer(base_y, "base_y")
    eaves = _integer(eaves, "eaves", minimum=0)
    if depth % 2 == 0:
        raise ValueError("gable roof depth must be odd and at least 3")
    half_depth = (depth - 1) // 2
    rise = _integer(rise, "roof rise", minimum=1)
    if rise > half_depth:
        raise ValueError("roof rise cannot exceed half the roof depth")
    state = _material(material)
    if not state.block_id.endswith("_stairs"):
        raise ValueError("gable roof material must be a stair block")

    model = VoxelModel()
    center_z = half_depth
    for z in range(-eaves, depth + eaves):
        if z < 0 or z >= depth:
            profile = 0
        else:
            distance_from_eave = min(z, depth - 1 - z)
            profile = (distance_from_eave * rise + half_depth // 2) // half_depth
        facing = "south" if z <= center_z else "north"
        stair = _state_with(
            state,
            facing=facing,
            half="bottom",
            shape="straight",
            waterlogged="false",
        )
        for x in range(-eaves, width + eaves):
            model.set_block((x, base_y + profile, z), stair)
    return model
