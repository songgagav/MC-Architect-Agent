"""Composable block-model generators for common building components."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from fractions import Fraction

from ..core.block import BlockState
from ..core.geometry import BoundingBox, Position
from ..core.scene import VoxelModel
from .roof_profiles import (
    EaveProfile,
    MaterialPalette,
    RidgeProfile,
    RoofProfile,
    sample_roof_section,
)
from .minecraft_materials import roof_material_shape, validate_roof_material_state

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
    """Create the legacy symmetric stepped roof through the profile builder."""

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
    end_treatment = "overhanging_gable" if eaves else "hard_gable"
    roof_profile = RoofProfile(ridge_height=rise)
    eave_profile = EaveProfile(
        side_overhang=eaves,
        gable_end_treatment=end_treatment,
        gable_end_projection=eaves,
        thickness=0,
        layer_roles=(),
    )
    palette = MaterialPalette({"roof_stair": state.to_string()})
    return generate_roof_surface(width, depth, base_y, roof_profile, eave_profile, palette)


@dataclass(frozen=True)
class RoofComponents:
    """The independently generated and assembled roof component models."""

    surface: VoxelModel
    eaves: VoxelModel
    ridge: VoxelModel
    combined: VoxelModel


def _validate_roof_profiles(
    width: int,
    depth: int,
    base_y: int,
    roof_profile: RoofProfile,
    eave_profile: EaveProfile,
    palette: MaterialPalette,
) -> tuple[int, tuple[int, ...]]:
    width = _integer(width, "width", minimum=1)
    depth = _integer(depth, "depth", minimum=3)
    base_y = _integer(base_y, "base_y")
    if depth % 2 == 0:
        raise ValueError("gable roof depth must be odd and at least 3")
    if not isinstance(roof_profile, RoofProfile):
        raise ValueError("roof_profile must be a RoofProfile")
    if not isinstance(eave_profile, EaveProfile):
        raise ValueError("eave_profile must be an EaveProfile")
    if not isinstance(palette, MaterialPalette):
        raise ValueError("palette must be a MaterialPalette")
    for state_string in palette.roles.values():
        validate_roof_material_state(_material(state_string))
    for band in roof_profile.surface_bands:
        if band.material_role not in palette.roles:
            raise ValueError(f"missing material palette role {band.material_role!r}")
    for role in eave_profile.layer_roles:
        if role not in palette.roles:
            raise ValueError(f"missing material palette role {role!r}")
    if eave_profile.decoration_role is not None and eave_profile.decoration_role not in palette.roles:
        raise ValueError(f"missing material palette role {eave_profile.decoration_role!r}")
    half_run = (depth - 1) // 2
    section = sample_roof_section(half_run, roof_profile.ridge_height, roof_profile.section_points)
    return base_y, section


def _roof_band(roof_profile: RoofProfile, distance: int, half_run: int):
    position = Fraction(distance * 1000, half_run)
    last_index = len(roof_profile.surface_bands) - 1
    for index, band in enumerate(roof_profile.surface_bands):
        if band.start <= position < band.end or (index == last_index and position == band.end):
            return band
    raise ValueError(f"no surface band covers roof run position {position}")


def _surface_state(
    band_form: str,
    material_role: str,
    palette: MaterialPalette,
    facing: str,
) -> BlockState:
    try:
        state = _material(palette.roles[material_role])
    except KeyError as exc:
        raise ValueError(f"missing material palette role {material_role!r}") from exc
    shape = roof_material_shape(state)
    if band_form == "stair":
        if shape != "stair":
            raise ValueError(f"material for stair surface role {material_role!r} must be a stair block")
        return _state_with(
            state,
            facing=facing,
            half="bottom",
            shape="straight",
            waterlogged="false",
        )
    if band_form == "slab":
        if shape != "slab":
            raise ValueError(f"material for slab surface role {material_role!r} must be a slab block")
        return _state_with(state, type="top", waterlogged="false")
    if shape != "full":
        raise ValueError(f"material for full_block surface role {material_role!r} must be a full block")
    return state


def generate_roof_surface(
    width: int,
    depth: int,
    base_y: int,
    roof_profile: RoofProfile,
    eave_profile: EaveProfile,
    palette: MaterialPalette,
    excluded_cells: Iterable[Position] = (),
) -> VoxelModel:
    """Generate a stepped roof skin, omitting coordinates owned by other parts."""

    base_y, section = _validate_roof_profiles(width, depth, base_y, roof_profile, eave_profile, palette)
    width = _integer(width, "width", minimum=1)
    depth = _integer(depth, "depth", minimum=3)
    half_run = (depth - 1) // 2
    excluded = {_position(position, "excluded cell") for position in excluded_cells}
    x_start = -eave_profile.gable_end_projection
    x_end = width + eave_profile.gable_end_projection
    z_start = -eave_profile.side_overhang
    z_end = depth + eave_profile.side_overhang
    center_z = half_run
    model = VoxelModel()
    rows: list[tuple[int, int, object, BlockState]] = []
    for z in range(z_start, z_end):
        if z < 0 or z >= depth:
            distance = 0
        else:
            distance = min(z, depth - 1 - z)
        height = section[distance]
        band = _roof_band(roof_profile, distance, half_run)
        facing = "south" if z <= center_z else "north"
        state = _surface_state(band.form, band.material_role, palette, facing)
        rows.append((z, height, band, state))
        for x in range(x_start, x_end):
            position = (x, base_y + height, z)
            if position not in excluded:
                model.set_block(position, state)
    for (z, height, band, state), (next_z, next_height, next_band, next_state) in zip(rows, rows[1:]):
        if next_z != z + 1 or next_height == height:
            continue
        if band.form != "full_block" and next_band.form != "full_block":
            continue
        fill_state = state if band.form == "full_block" else next_state
        fill_position_y = base_y + (next_height if next_height > height else height)
        fill_position_z = z if next_height > height else next_z
        for x in range(x_start, x_end):
            position = (x, fill_position_y, fill_position_z)
            if position not in excluded:
                model.set_block(position, fill_state)
    return model


def generate_eaves_component(
    width: int,
    depth: int,
    base_y: int,
    roof_profile: RoofProfile,
    eave_profile: EaveProfile,
    palette: MaterialPalette,
) -> tuple[VoxelModel, frozenset[Position]]:
    """Generate eave trim and return the roof-edge surface cells it owns."""

    _base_y, _section = _validate_roof_profiles(width, depth, base_y, roof_profile, eave_profile, palette)
    width = _integer(width, "width", minimum=1)
    depth = _integer(depth, "depth", minimum=3)
    start_x = -eave_profile.gable_end_projection
    end_x = width + eave_profile.gable_end_projection
    edge_zs = (0, depth - 1)
    model = VoxelModel()
    owned: set[Position] = set()
    for layer, role in enumerate(eave_profile.layer_roles):
        state = _material(palette.roles[role])
        y = base_y - layer
        for z in edge_zs:
            for x in range(start_x, end_x):
                position = (x, y, z)
                model.set_block(position, state)
                if layer == 0:
                    owned.add(position)
    if eave_profile.decoration_role is not None:
        decoration = _material(palette.roles[eave_profile.decoration_role])
        y = base_y + 1
        for x in range(start_x, end_x, eave_profile.decoration_spacing):
            for z in edge_zs:
                model.set_block((x, y, z), decoration)
    return model, frozenset(owned)


def generate_ridge_cap(
    width: int,
    depth: int,
    base_y: int,
    roof_profile: RoofProfile,
    eave_profile: EaveProfile,
    ridge_profile: RidgeProfile,
    palette: MaterialPalette,
) -> tuple[VoxelModel, frozenset[Position]]:
    """Generate a ridge cap and return the roof-apex cells it owns."""

    base_y, _section = _validate_roof_profiles(width, depth, base_y, roof_profile, eave_profile, palette)
    width = _integer(width, "width", minimum=1)
    depth = _integer(depth, "depth", minimum=3)
    if not isinstance(ridge_profile, RidgeProfile):
        raise ValueError("ridge_profile must be a RidgeProfile")
    if ridge_profile.cap_width > depth:
        raise ValueError("ridge cap width cannot exceed roof depth")
    if ridge_profile.cap_height > 0 and ridge_profile.material_role not in palette.roles:
        raise ValueError(f"missing material palette role {ridge_profile.material_role!r}")
    if ridge_profile.decoration_role is not None and ridge_profile.decoration_role not in palette.roles:
        raise ValueError(f"missing material palette role {ridge_profile.decoration_role!r}")
    model = VoxelModel()
    if ridge_profile.cap_height == 0 and ridge_profile.decoration_role is None:
        return model, frozenset()
    x_start = -eave_profile.gable_end_projection
    x_end = width + eave_profile.gable_end_projection
    center_z = (depth - 1) // 2
    z_start = center_z - ridge_profile.cap_width // 2
    owned: set[Position] = set()
    if ridge_profile.cap_height > 0:
        cap_state = _material(palette.roles[ridge_profile.material_role])
        for layer in range(ridge_profile.cap_height):
            y = base_y + roof_profile.ridge_height + layer
            for z in range(z_start, z_start + ridge_profile.cap_width):
                for x in range(x_start, x_end):
                    position = (x, y, z)
                    model.set_block(position, cap_state)
                    if layer == 0:
                        owned.add(position)
    if ridge_profile.decoration_role is not None:
        decoration = _material(palette.roles[ridge_profile.decoration_role])
        y = base_y + roof_profile.ridge_height + max(1, ridge_profile.cap_height)
        for x in range(x_start, x_end, ridge_profile.decoration_spacing):
            model.set_block((x, y, center_z), decoration)
    return model, frozenset(owned)


def generate_roof_components(
    width: int,
    depth: int,
    base_y: int,
    roof_profile: RoofProfile,
    eave_profile: EaveProfile,
    ridge_profile: RidgeProfile,
    palette: MaterialPalette,
) -> RoofComponents:
    """Build separate surface, eaves, ridge, and combined roof models."""

    if not isinstance(ridge_profile, RidgeProfile):
        raise ValueError("ridge_profile must be a RidgeProfile")
    eaves, eave_owned = generate_eaves_component(
        width, depth, base_y, roof_profile, eave_profile, palette
    )
    ridge, ridge_owned = generate_ridge_cap(
        width, depth, base_y, roof_profile, eave_profile, ridge_profile, palette
    )
    surface = generate_roof_surface(
        width,
        depth,
        base_y,
        roof_profile,
        eave_profile,
        palette,
        excluded_cells=(*eave_owned, *ridge_owned),
    )
    combined = VoxelModel()
    for component_name, component in (("surface", surface), ("eaves", eaves), ("ridge", ridge)):
        overlap = set(combined.blocks).intersection(component.blocks)
        if overlap:
            raise ValueError(f"unexpected roof component overlap at {min(overlap)} while adding {component_name}")
        for position, state in component.blocks.items():
            combined.set_block(position, state)
    return RoofComponents(surface, eaves, ridge, combined)
