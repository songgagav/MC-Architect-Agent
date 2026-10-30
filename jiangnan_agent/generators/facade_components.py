"""Profile-driven doors and small-grid windows with strict ownership checks."""

from __future__ import annotations

from collections.abc import Mapping

from ..core.block import BlockState
from ..core.geometry import Position
from ..core.scene import VoxelModel
from .facade_geometry import BlockOwnershipMap, OpeningMask, face_basis
from .facade_profiles import DoorProfile, WindowProfile

Material = BlockState | str
_FACING_BY_FACE = {"front": "south", "rear": "north", "left": "west", "right": "east"}
_RIGHT_BY_FACING: Mapping[str, Position] = {
    "north": (1, 0, 0),
    "east": (0, 0, 1),
    "south": (-1, 0, 0),
    "west": (0, 0, -1),
}
_HORIZONTAL = ("north", "east", "south", "west")


def _origin(value: object) -> Position:
    if (
        not isinstance(value, tuple)
        or len(value) != 3
        or any(isinstance(part, bool) or not isinstance(part, int) for part in value)
    ):
        raise ValueError("origin must contain three integer coordinates")
    return value


def _material(materials: Mapping[str, Material], role: str) -> BlockState:
    if role not in materials:
        raise ValueError(f"missing façade material role {role!r}")
    value = materials[role]
    state = value if isinstance(value, BlockState) else BlockState.parse(value) if isinstance(value, str) else None
    if state is None:
        raise ValueError(f"material for role {role!r} must be a BlockState or state string")
    if state.block_id.rsplit(":", 1)[-1] in {"air", "cave_air", "void_air"}:
        raise ValueError(f"air cannot be used for façade role {role!r}")
    return state


def _context(
    ownership: BlockOwnershipMap,
    opening_mask: OpeningMask,
    opening_id: str,
    kind: str,
) -> None:
    if not isinstance(ownership, BlockOwnershipMap):
        raise ValueError("ownership must be a BlockOwnershipMap")
    if not isinstance(opening_mask, OpeningMask) or ownership.opening_mask is not opening_mask:
        raise ValueError("component and ownership must share the same OpeningMask")
    if not isinstance(opening_id, str) or not opening_id.strip():
        raise ValueError("opening_id must be a non-empty string")
    reservations = {opening_mask.reservation_at(position) for position in opening_mask.positions}
    if not any(item is not None and item.opening_id == opening_id and item.kind == kind for item in reservations):
        raise ValueError(f"opening {opening_id!r} has no reserved {kind} cells")


def _point(origin: Position, face: str, tangent_offset: int = 0, y_offset: int = 0) -> Position:
    basis = face_basis(face)
    values = list(origin)
    values[basis.tangent_axis] += tangent_offset
    values[1] += y_offset
    return tuple(values)  # type: ignore[return-value]


def _state_with(state: BlockState, **updates: str) -> BlockState:
    properties = dict(state.properties)
    properties.update(updates)
    return BlockState(state.block_id, tuple(properties.items()))


def _wood_axis(state: BlockState, axis: str) -> BlockState:
    suffixes = ("_log", "_wood", "_stem", "_hyphae")
    path = state.block_id.rsplit(":", 1)[-1]
    if path.endswith(suffixes) or "axis" in dict(state.properties):
        return _state_with(state, axis=axis)
    return state


def _component_claims(
    ownership: BlockOwnershipMap,
    opening_model: VoxelModel,
    opening_kind: str,
    opening_id: str,
    frame_model: VoxelModel,
) -> None:
    claims: list[tuple[Position, str, Mapping[str, object]]] = []
    claims.extend(
        (position, opening_kind, {"opening_id": opening_id})
        for position in sorted(opening_model.blocks)
    )
    for position in sorted(frame_model.blocks):
        options: dict[str, object] = {}
        if ownership.owner_at(position) is not None:
            options["replaces"] = "wall"
        claims.append((position, "frame", options))
    ownership.claim_batch(claims)


def _door_hinge(face: str, offset: int, width: int) -> str:
    facing = _FACING_BY_FACE[face]
    tangent = [0, 0, 0]
    tangent[face_basis(face).tangent_axis] = 1
    right = _RIGHT_BY_FACING[facing]
    first_leaf_is_right = sum(left * right_axis for left, right_axis in zip(tangent, right)) > 0
    hinge = "right" if first_leaf_is_right else "left"
    if width == 2 and offset == 1:
        hinge = "left" if hinge == "right" else "right"
    return hinge


def _append_unique(model: VoxelModel, position: Position, state: BlockState) -> None:
    if position in model.blocks:
        raise ValueError(f"façade component parts overlap at {position}")
    model.set_block(position, state)


def generate_facade_door(
    origin: Position,
    profile: DoorProfile,
    face: str,
    ownership: BlockOwnershipMap,
    opening_mask: OpeningMask,
    *,
    opening_id: str,
    materials: Mapping[str, Material],
) -> VoxelModel:
    """Create a vanilla door, optional jambs, and a lintel at a reserved opening."""

    origin = _origin(origin)
    if not isinstance(profile, DoorProfile):
        raise ValueError("profile must be a DoorProfile")
    if face not in _FACING_BY_FACE:
        raise ValueError("face must be front, rear, left, or right")
    if not isinstance(materials, Mapping):
        raise ValueError("materials must map semantic roles to block states")
    _context(ownership, opening_mask, opening_id, "door")
    door_material = _material(materials, profile.door_material_role)
    if not door_material.block_id.endswith("_door"):
        raise ValueError("door material role must reference a Minecraft door block")

    door_model = VoxelModel()
    for offset in range(profile.width):
        hinge = _door_hinge(face, offset, profile.width)
        for y_offset, half in ((0, "lower"), (1, "upper")):
            state = BlockState(
                door_material.block_id,
                (
                    ("facing", _FACING_BY_FACE[face]),
                    ("half", half),
                    ("hinge", hinge),
                    ("open", "false"),
                    ("powered", "false"),
                ),
            )
            _append_unique(door_model, _point(origin, face, offset, y_offset), state)

    frame_model = VoxelModel()
    if profile.frame_thickness:
        frame_material = _material(materials, profile.frame_material_role)
        for layer in range(profile.frame_thickness):
            for tangent_offset in (-1 - layer, profile.width + layer):
                jamb = _wood_axis(frame_material, "y")
                for y_offset in range(profile.height):
                    _append_unique(frame_model, _point(origin, face, tangent_offset, y_offset), jamb)
    if profile.lintel:
        axis = "x" if face in {"front", "rear"} else "z"
        lintel_material = _wood_axis(_material(materials, profile.lintel_material_role), axis)
        start = -profile.frame_thickness
        end = profile.width + profile.frame_thickness
        for tangent_offset in range(start, end):
            _append_unique(frame_model, _point(origin, face, tangent_offset, profile.height), lintel_material)

    combined = VoxelModel()
    for source in (door_model, frame_model):
        for position, state in source.blocks.items():
            _append_unique(combined, position, state)
    _component_claims(ownership, door_model, "door", opening_id, frame_model)
    return combined


def _lattice_positions(style: str, width: int, height: int) -> frozenset[tuple[int, int]]:
    if style == "plain":
        return frozenset()
    points: set[tuple[int, int]] = set()
    if style == "grid":
        if width >= 3:
            center_x = width // 2
            points.update((center_x, y) for y in range(height))
        if height >= 3:
            center_y = height // 2
            points.update((x, center_y) for x in range(width))
    elif style == "vertical":
        center_x = width // 2
        points.update((center_x, y) for y in range(height))
    elif style == "cross":
        if height == 1:
            points.update((x, 0) for x in range(width))
        elif width == 1:
            points.update((0, y) for y in range(height))
        else:
            for y in range(height):
                denominator = height - 1
                first_x = (y * (width - 1) + denominator // 2) // denominator
                points.add((first_x, y))
                points.add((width - 1 - first_x, y))
    return frozenset(points)


def _connected_grid_state(
    state: BlockState,
    face: str,
    *,
    connect_negative: bool,
    connect_positive: bool,
) -> BlockState:
    path = state.block_id.rsplit(":", 1)[-1]
    if not path.endswith(("_pane", "_bars", "_fence")):
        if state.properties:
            raise ValueError("plain glass materials must not have directional block-state properties")
        return state
    basis = face_basis(face)
    negative, positive = (
        ("west", "east") if basis.tangent_axis == 0 else ("north", "south")
    )
    updates = {direction: "false" for direction in _HORIZONTAL}
    updates[negative] = "true" if connect_negative else "false"
    updates[positive] = "true" if connect_positive else "false"
    updates["waterlogged"] = "false"
    allowed = {*_HORIZONTAL, "waterlogged"}
    if set(dict(state.properties)) - allowed:
        raise ValueError("pane, bars, and fence materials may only specify horizontal connections and waterlogged")
    return _state_with(state, **updates)


def generate_facade_window(
    origin: Position,
    profile: WindowProfile,
    face: str,
    ownership: BlockOwnershipMap,
    opening_mask: OpeningMask,
    *,
    opening_id: str,
    materials: Mapping[str, Material],
) -> VoxelModel:
    """Create glazing/lattice and optional frame inside one reserved window."""

    origin = _origin(origin)
    if not isinstance(profile, WindowProfile):
        raise ValueError("profile must be a WindowProfile")
    if face not in _FACING_BY_FACE:
        raise ValueError("face must be front, rear, left, or right")
    if not isinstance(materials, Mapping):
        raise ValueError("materials must map semantic roles to block states")
    _context(ownership, opening_mask, opening_id, "window")

    glazing = _material(materials, profile.glazing_material_role)
    glazing_path = glazing.block_id.rsplit(":", 1)[-1]
    if not (
        glazing_path == "glass"
        or glazing_path == "glass_pane"
        or glazing_path.endswith("_glass")
        or glazing_path.endswith("_glass_pane")
    ):
        raise ValueError("window glazing role must reference glass or a glass pane")
    lattice_cells = _lattice_positions(profile.lattice_style, profile.width, profile.height)
    lattice = None
    if lattice_cells:
        lattice = _material(materials, profile.lattice_material_role)
        lattice_path = lattice.block_id.rsplit(":", 1)[-1]
        if not lattice_path.endswith(("_pane", "_bars", "_fence")):
            raise ValueError("lattice material must be a pane, bars, or fence block")
    frame_material = _material(materials, profile.frame_material_role) if profile.frame_thickness else None
    window_model = VoxelModel()
    for y_offset in range(profile.height):
        for tangent_offset in range(profile.width):
            is_lattice = (tangent_offset, y_offset) in lattice_cells
            state = lattice if is_lattice and lattice is not None else glazing
            assert state is not None
            state = _connected_grid_state(
                state,
                face,
                connect_negative=tangent_offset > 0 or profile.frame_thickness > 0,
                connect_positive=tangent_offset < profile.width - 1 or profile.frame_thickness > 0,
            )
            _append_unique(window_model, _point(origin, face, tangent_offset, y_offset), state)

    frame_model = VoxelModel()
    if frame_material is not None:
        thickness = profile.frame_thickness
        for layer in range(thickness):
            jamb = _wood_axis(frame_material, "y")
            for tangent_offset in (-1 - layer, profile.width + layer):
                for y_offset in range(profile.height):
                    _append_unique(frame_model, _point(origin, face, tangent_offset, y_offset), jamb)
            lintel = _wood_axis(frame_material, "x" if face in {"front", "rear"} else "z")
            for tangent_offset in range(-1 - layer, profile.width + 1 + layer):
                for y_offset in (-1 - layer, profile.height + layer):
                    _append_unique(frame_model, _point(origin, face, tangent_offset, y_offset), lintel)

    combined = VoxelModel()
    for source in (window_model, frame_model):
        for position, state in source.blocks.items():
            _append_unique(combined, position, state)
    _component_claims(ownership, window_model, "window", opening_id, frame_model)
    return combined
