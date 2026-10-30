"""Parameterized hall and straight-corridor assemblies."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from enum import Enum
from types import MappingProxyType

from ..core.block import BlockState
from ..core.geometry import BoundingBox
from ..core.scene import VoxelModel
from .components import (
    generate_beam,
    generate_column,
    generate_door,
    generate_plinth,
    generate_roof_components,
    generate_wall,
    generate_window,
)
from .facade_profiles import (
    FacadeOpening,
    FacadeProfile,
    facade_profile_from_mapping,
    validate_facade_profile_for_hall,
)
from .facade_components import facade_frame_positions, generate_facade_door, generate_facade_window
from .facade_geometry import (
    BlockOwnershipMap,
    FaceSegmentBounds,
    OpeningMask,
    build_facade_segments,
    face_basis,
    resolve_facade_opening,
)
from .roof_profiles import (
    EaveProfile,
    MaterialPalette,
    RidgeProfile,
    RoofProfile,
    eave_profile_from_mapping,
    material_palette_from_mapping,
    ridge_profile_from_mapping,
    roof_profile_from_mapping,
    sample_roof_section,
)

DEFAULT_HALL_MATERIALS: dict[str, str] = {
    "plinth": "minecraft:smooth_stone",
    "floor": "minecraft:spruce_planks",
    "column": "minecraft:stripped_spruce_log",
    "beam": "minecraft:stripped_spruce_log",
    "wall": "minecraft:calcite",
    "door": "minecraft:spruce_door",
    "window": "minecraft:white_stained_glass_pane",
    "roof": "minecraft:polished_deepslate_stairs",
    "eaves": "minecraft:deepslate_tile_slab[type=bottom,waterlogged=false]",
}

DEFAULT_CORRIDOR_MATERIALS: dict[str, str] = {
    "floor": DEFAULT_HALL_MATERIALS["floor"],
    "column": DEFAULT_HALL_MATERIALS["column"],
    "beam": DEFAULT_HALL_MATERIALS["beam"],
    "roof": DEFAULT_HALL_MATERIALS["roof"],
    "eaves": DEFAULT_HALL_MATERIALS["eaves"],
}


class _Unspecified(Enum):
    VALUE = "unspecified"


_UNSPECIFIED = _Unspecified.VALUE


def _require_integer(value: int, name: str, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return value


def _checked_materials(
    overrides: Mapping[str, str] | None,
    defaults: Mapping[str, str],
) -> Mapping[str, str] | None:
    if overrides is None:
        return None
    if not isinstance(overrides, Mapping):
        raise ValueError("materials must be a mapping of roles to Minecraft state strings")

    normalized: dict[str, str] = {}
    for role, value in overrides.items():
        if role not in defaults:
            raise ValueError(f"unknown material role: {role!r}")
        if not isinstance(value, str):
            raise ValueError(f"material for {role!r} must be a Minecraft state string")
        state = BlockState.parse(value)
        if role == "door" and not state.block_id.endswith("_door"):
            raise ValueError("door material must be a door block")
        if role == "roof" and not state.block_id.endswith("_stairs"):
            raise ValueError("roof material must be a stair block")
        normalized[role] = state.to_string()
    return MappingProxyType(normalized)


def _resolve_materials(
    overrides: Mapping[str, str] | None,
    defaults: Mapping[str, str],
) -> dict[str, BlockState]:
    raw = dict(defaults)
    raw.update(overrides or {})
    return {role: BlockState.parse(state) for role, state in raw.items()}


def _merge(destination: VoxelModel, source: VoxelModel) -> None:
    for position, state in source.blocks.items():
        destination.set_block(position, state)


def _merge_roof(
    destination: VoxelModel,
    roof: VoxelModel,
    *,
    beam_y: int,
    width: int,
    depth: int,
) -> None:
    allowed_beam_connections = {
        (x, beam_y, z)
        for x in range(width)
        for z in (0, depth - 1)
    }
    unexpected = set(destination.blocks).intersection(roof.blocks) - allowed_beam_connections
    if unexpected:
        raise ValueError(f"roof component overlaps existing structure at {min(unexpected)}")
    _merge(destination, roof)


def _roof_model(
    width: int,
    depth: int,
    base_y: int,
    parameters: HallParameters | CorridorParameters,
    materials: Mapping[str, BlockState],
) -> VoxelModel:
    roof_profile = parameters.roof_profile or RoofProfile(ridge_height=parameters.roof_rise)
    eave_profile = parameters.eave_profile or EaveProfile(
        side_overhang=parameters.eaves,
        gable_end_treatment="overhanging_gable" if parameters.eaves else "hard_gable",
        gable_end_projection=parameters.eaves,
        thickness=1,
        layer_roles=("eaves",),
    )
    ridge_profile = parameters.ridge_profile or RidgeProfile()
    palette_roles = {
        "roof_stair": materials["roof"].to_string(),
        "eaves": materials["eaves"].to_string(),
    }
    if parameters.material_palette is not None:
        palette_roles.update(parameters.material_palette.roles)
    palette = MaterialPalette(palette_roles)
    return generate_roof_components(
        width,
        depth,
        base_y,
        roof_profile,
        eave_profile,
        ridge_profile,
        palette,
    ).combined


@dataclass(frozen=True)
class HallParameters:
    """Dimensions and materials for a front-facing, odd-bay hall."""

    bay_count: int = 3
    bay_width: int = 5
    depth: int = 7
    column_height: int = 4
    plinth_height: int = 1
    roof_rise: int | _Unspecified = _UNSPECIFIED
    eaves: int | _Unspecified = _UNSPECIFIED
    door_width: int | _Unspecified = _UNSPECIFIED
    materials: Mapping[str, str] | None = None
    facade_profile: FacadeProfile | None = None
    roof_profile: RoofProfile | None = None
    eave_profile: EaveProfile | None = None
    ridge_profile: RidgeProfile | None = None
    material_palette: MaterialPalette | None = None
    _roof_rise_explicit: bool = field(default=False, init=False, repr=False, compare=False)
    _eaves_explicit: bool = field(default=False, init=False, repr=False, compare=False)
    _door_width_explicit: bool = field(default=False, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        _coerce_profile_fields(self)
        bay_count = _require_integer(self.bay_count, "bay_count", 3)
        bay_width = _require_integer(self.bay_width, "bay_width", 1)
        depth = _require_integer(self.depth, "depth", 5)
        column_height = _require_integer(self.column_height, "column_height", 3)
        plinth_height = _require_integer(self.plinth_height, "plinth_height", 1)
        roof_rise_explicit = self.roof_rise is not _UNSPECIFIED
        eaves_explicit = self.eaves is not _UNSPECIFIED
        roof_rise = 3 if not roof_rise_explicit else _require_integer(self.roof_rise, "roof_rise", 1)
        eaves = 1 if not eaves_explicit else _require_integer(self.eaves, "eaves", 0)
        door_width_explicit = self.door_width is not _UNSPECIFIED
        door_width = 2 if not door_width_explicit else _require_integer(self.door_width, "door_width", 1)
        if bay_count % 2 == 0:
            raise ValueError("bay_count must be an odd number of at least 3")
        if depth % 2 == 0:
            raise ValueError("depth must be odd and at least 5")
        if door_width not in (1, 2):
            raise ValueError("door_width must be 1 or 2 blocks")
        if bay_width < door_width + 2:
            raise ValueError("bay_width must leave a wall block on each side of the door")
        if self.roof_profile is None and roof_rise > (depth - 1) // 2:
            raise ValueError("roof_rise cannot exceed half the hall depth")
        _validate_profile_inputs(
            roof_rise,
            eaves,
            roof_rise_explicit,
            eaves_explicit,
            self.roof_profile,
            self.eave_profile,
            self.ridge_profile,
            self.material_palette,
        )
        if self.roof_profile is not None:
            sample_roof_section((depth - 1) // 2, self.roof_profile.ridge_height, self.roof_profile.section_points)
        normalized_materials = _checked_materials(self.materials, DEFAULT_HALL_MATERIALS)
        _validate_facade_legacy_conflicts(
            self.facade_profile,
            door_width=door_width,
            door_width_explicit=door_width_explicit,
            materials=normalized_materials,
        )
        _validate_palette_aliases(normalized_materials, self.material_palette)
        object.__setattr__(self, "roof_rise", roof_rise)
        object.__setattr__(self, "eaves", eaves)
        object.__setattr__(self, "door_width", door_width)
        object.__setattr__(self, "materials", normalized_materials)
        object.__setattr__(self, "_roof_rise_explicit", roof_rise_explicit)
        object.__setattr__(self, "_eaves_explicit", eaves_explicit)
        object.__setattr__(self, "_door_width_explicit", door_width_explicit)


@dataclass(frozen=True)
class CorridorParameters:
    """Dimensions and materials for one straight, open-sided corridor."""

    length: int = 11
    width: int = 3
    column_spacing: int = 3
    column_height: int = 3
    roof_rise: int | _Unspecified = _UNSPECIFIED
    eaves: int | _Unspecified = _UNSPECIFIED
    materials: Mapping[str, str] | None = None
    facade_profile: FacadeProfile | None = None
    roof_profile: RoofProfile | None = None
    eave_profile: EaveProfile | None = None
    ridge_profile: RidgeProfile | None = None
    material_palette: MaterialPalette | None = None
    _roof_rise_explicit: bool = field(default=False, init=False, repr=False, compare=False)
    _eaves_explicit: bool = field(default=False, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        _coerce_profile_fields(self)
        length = _require_integer(self.length, "length", 3)
        width = _require_integer(self.width, "width", 3)
        _require_integer(self.column_spacing, "column_spacing", 1)
        _require_integer(self.column_height, "column_height", 2)
        roof_rise_explicit = self.roof_rise is not _UNSPECIFIED
        eaves_explicit = self.eaves is not _UNSPECIFIED
        roof_rise = 1 if not roof_rise_explicit else _require_integer(self.roof_rise, "roof_rise", 1)
        eaves = 1 if not eaves_explicit else _require_integer(self.eaves, "eaves", 0)
        if width % 2 == 0:
            raise ValueError("corridor width must be odd for a centered roof ridge")
        if self.roof_profile is None and roof_rise > (width - 1) // 2:
            raise ValueError("roof_rise cannot exceed half the corridor width")
        _validate_profile_inputs(
            roof_rise,
            eaves,
            roof_rise_explicit,
            eaves_explicit,
            self.roof_profile,
            self.eave_profile,
            self.ridge_profile,
            self.material_palette,
        )
        if self.roof_profile is not None:
            sample_roof_section((width - 1) // 2, self.roof_profile.ridge_height, self.roof_profile.section_points)
        normalized_materials = _checked_materials(self.materials, DEFAULT_CORRIDOR_MATERIALS)
        _validate_facade_legacy_conflicts(self.facade_profile, materials=normalized_materials)
        _validate_palette_aliases(normalized_materials, self.material_palette)
        if self.facade_profile is not None:
            closed_ends = set(self.facade_profile.enclosed_faces) & {"left", "right"}
            if closed_ends:
                raise ValueError("corridor facade cannot enclose start/end connection faces")
            missing_faces = {opening.face for opening in self.facade_profile.openings} - set(
                self.facade_profile.enclosed_faces
            )
            if missing_faces:
                raise ValueError("corridor openings require their face to be listed in enclosed_faces")
        object.__setattr__(self, "roof_rise", roof_rise)
        object.__setattr__(self, "eaves", eaves)
        object.__setattr__(self, "materials", normalized_materials)
        object.__setattr__(self, "_roof_rise_explicit", roof_rise_explicit)
        object.__setattr__(self, "_eaves_explicit", eaves_explicit)


def _coerce_profile_fields(parameters: HallParameters | CorridorParameters) -> None:
    for name, parser in (
        ("roof_profile", roof_profile_from_mapping),
        ("eave_profile", eave_profile_from_mapping),
        ("ridge_profile", ridge_profile_from_mapping),
        ("material_palette", material_palette_from_mapping),
        ("facade_profile", facade_profile_from_mapping),
    ):
        value = getattr(parameters, name)
        if value is not None and not isinstance(
            value,
            {
                "roof_profile": RoofProfile,
                "eave_profile": EaveProfile,
                "ridge_profile": RidgeProfile,
                "material_palette": MaterialPalette,
                "facade_profile": FacadeProfile,
            }[name],
        ):
            object.__setattr__(parameters, name, parser(value))
    if isinstance(parameters, HallParameters) and parameters.facade_profile is not None:
        validate_facade_profile_for_hall(parameters.facade_profile)


def _validate_facade_legacy_conflicts(
    profile: FacadeProfile | None,
    *,
    door_width: int | None = None,
    door_width_explicit: bool = False,
    materials: Mapping[str, str] | None = None,
) -> None:
    if profile is None:
        return
    if door_width_explicit and door_width != profile.door.width:
        raise ValueError("explicit door_width conflicts with facade profile door width")
    if materials is None:
        return
    for role, value in materials.items():
        profile_value = profile.materials.get(role)
        if profile_value is not None and BlockState.parse(value) != BlockState.parse(profile_value):
            raise ValueError(f"explicit materials role {role!r} conflicts with facade profile material")


def _validate_profile_inputs(
    roof_rise: int,
    eaves: int,
    roof_rise_explicit: bool,
    eaves_explicit: bool,
    roof_profile: RoofProfile | None,
    eave_profile: EaveProfile | None,
    ridge_profile: RidgeProfile | None,
    material_palette: MaterialPalette | None,
) -> None:
    for value, expected, name in (
        (roof_profile, RoofProfile, "roof_profile"),
        (eave_profile, EaveProfile, "eave_profile"),
        (ridge_profile, RidgeProfile, "ridge_profile"),
        (material_palette, MaterialPalette, "material_palette"),
    ):
        if value is not None and not isinstance(value, expected):
            raise ValueError(f"{name} must be {expected.__name__}")
    if roof_profile is not None and roof_rise_explicit and roof_profile.ridge_height != roof_rise:
        raise ValueError("roof_rise conflicts with roof_profile.ridge_height")
    if eave_profile is not None and eaves_explicit:
        if eave_profile.side_overhang != eaves or eave_profile.gable_end_projection != eaves:
            raise ValueError("eaves conflicts with eave_profile overhang values")


def _validate_palette_aliases(
    materials: Mapping[str, str] | None,
    material_palette: MaterialPalette | None,
) -> None:
    if materials is None or material_palette is None:
        return
    for legacy_role, palette_role in (("roof", "roof_stair"), ("eaves", "eaves")):
        legacy = materials.get(legacy_role)
        explicit = material_palette.roles.get(palette_role)
        if legacy is not None and explicit is not None and BlockState.parse(legacy) != BlockState.parse(explicit):
            raise ValueError(f"materials.{legacy_role} conflicts with material_palette.{palette_role}")


def _hall_face_segments(parameters: HallParameters) -> dict[str, tuple[FaceSegmentBounds, ...]]:
    width = parameters.bay_count * parameters.bay_width + 1
    depth = parameters.depth
    wall_base_y = parameters.plinth_height + 1
    beam_y = parameters.plinth_height + parameters.column_height
    bay_posts = tuple(range(0, width, parameters.bay_width))
    side_posts = tuple(sorted(set(range(0, depth - 1, parameters.bay_width)) | {depth - 1}))
    bounds = {
        "front": BoundingBox(0, wall_base_y, depth - 1, width, beam_y, depth),
        "rear": BoundingBox(0, wall_base_y, 0, width, beam_y, 1),
        "left": BoundingBox(0, wall_base_y, 0, 1, beam_y, depth),
        "right": BoundingBox(width - 1, wall_base_y, 0, width, beam_y, depth),
    }
    return {
        "front": build_facade_segments("front", bounds["front"], bay_posts),
        "rear": build_facade_segments("rear", bounds["rear"], bay_posts),
        "left": build_facade_segments("left", bounds["left"], side_posts),
        "right": build_facade_segments("right", bounds["right"], side_posts),
    }


def _resolve_profile_openings(
    profile: FacadeProfile,
    segments: Mapping[str, tuple[FaceSegmentBounds, ...]],
) -> list[tuple[FacadeOpening, BoundingBox]]:
    result: list[tuple[FacadeOpening, BoundingBox]] = []
    for opening in profile.openings:
        segment = next(
            (item for item in segments[opening.face] if item.segment_index == opening.segment_index),
            None,
        )
        if segment is None:
            raise ValueError(
                f"opening {opening.opening_id!r} references missing {opening.face} segment {opening.segment_index}"
            )
        component = profile.door if opening.kind == "door" else profile.window
        bounds = resolve_facade_opening(
            opening,
            segment,
            width=component.width,
            height=component.height,
        )
        result.append((opening, bounds))
    return result


def resolve_hall_primary_entry(parameters: HallParameters) -> BoundingBox:
    """Resolve the selected hall entry to its exact face-local block bounds."""

    if not isinstance(parameters, HallParameters) or parameters.facade_profile is None:
        raise ValueError("hall parameters must contain a façade profile")
    primary = validate_facade_profile_for_hall(parameters.facade_profile)
    resolved = _resolve_profile_openings(parameters.facade_profile, _hall_face_segments(parameters))
    return next(bounds for opening, bounds in resolved if opening.opening_id == primary.opening_id)


def _merge_wall_panels(destination: VoxelModel, source: VoxelModel) -> None:
    for position, state in sorted(source.blocks.items()):
        current = destination.blocks.get(position)
        if current is not None and current != state:
            raise ValueError(f"overlapping façade walls use conflicting materials at {position}")
        if current is None:
            destination.set_block(position, state)


def _axis_aligned_material(material: BlockState, axis: str) -> BlockState:
    path = material.block_id.rsplit(":", 1)[-1]
    if path.endswith(("_log", "_wood", "_stem", "_hyphae")) or "axis" in dict(material.properties):
        properties = dict(material.properties)
        properties["axis"] = axis
        return BlockState(material.block_id, tuple(properties.items()))
    return material


def _generate_profiled_facades(
    model: VoxelModel,
    profile: FacadeProfile,
    segments: Mapping[str, tuple[FaceSegmentBounds, ...]],
    materials: Mapping[str, BlockState],
    *,
    faces: tuple[str, ...],
    column_positions: tuple[tuple[int, int], ...],
    column_base_y: int,
    column_top_y: int,
    through_passage: bool = False,
) -> None:
    openings = _resolve_profile_openings(profile, segments)
    if any(opening.face not in faces for opening, _bounds in openings):
        raise ValueError("façade opening references a face that is not enclosed")
    primary = validate_facade_profile_for_hall(profile) if through_passage else None
    if primary is not None:
        rear_opening = FacadeOpening(
            primary.opening_id,
            "rear",
            "door",
            "non_connecting",
            primary.segment_index,
            primary.offset,
            primary.sill_offset,
        )
        rear_segment = next(
            (item for item in segments["rear"] if item.segment_index == rear_opening.segment_index),
            None,
        )
        if rear_segment is None:
            raise ValueError("primary entry has no matching rear wall segment for through_passage")
        rear_bounds = resolve_facade_opening(
            rear_opening,
            rear_segment,
            width=profile.door.width,
            height=profile.door.height,
        )
        openings.append((rear_opening, rear_bounds))

    opening_mask = OpeningMask()
    for opening, bounds in openings:
        opening_mask.reserve(opening.opening_id, opening.kind, bounds)

    facade_materials = {role: BlockState.parse(state) for role, state in DEFAULT_HALL_MATERIALS.items()}
    facade_materials.update(materials)
    facade_materials.update({role: BlockState.parse(value) for role, value in profile.materials.items()})

    timber = profile.timber
    if not timber.exterior_posts:
        raise ValueError("exterior structural posts cannot be hidden in façade profile v1")
    timber_cells: set[tuple[int, int, int]] = set()
    if timber.column_bases:
        timber_cells.update((x, column_base_y, z) for x, z in column_positions)
    if timber.column_capitals:
        timber_cells.update((x, column_top_y, z) for x, z in column_positions)
    if timber.beam_layers > 1 and faces:
        panel_height = min(segment.bounds.size[1] for face in faces for segment in segments[face])
        if timber.beam_layers > panel_height + 1:
            raise ValueError("timber beam_layers exceed the available wall height")
    if timber_cells or timber.beam_layers > 1:
        if timber.trim_material_role not in facade_materials:
            raise ValueError(f"missing façade material role {timber.trim_material_role!r}")
    trim_material = facade_materials.get(timber.trim_material_role)

    wall_model = VoxelModel()
    for face in faces:
        for segment in segments[face]:
            segment_openings = [
                bounds
                for opening, bounds in openings
                if opening.face == face and opening.segment_index == segment.segment_index
            ]
            panel = generate_wall(
                segment.bounds,
                facade_materials,
                segment_openings,
                profile=profile.wall,
                face=face,
                opening_mask=opening_mask,
            )
            _merge_wall_panels(wall_model, panel)

    ownership = BlockOwnershipMap(opening_mask=opening_mask)
    structure_claims = []
    for position in sorted(model.blocks):
        options: dict[str, object] = {"protected": position not in timber_cells}
        if position in timber_cells:
            options["replaceable_by"] = ("timber",)
        structure_claims.append((position, "structure", options))
    ownership.claim_batch(structure_claims)
    ownership.merge(wall_model, "wall")
    _merge(model, wall_model)

    if timber_cells:
        assert trim_material is not None
        timber_model = VoxelModel()
        timber_claims = []
        for x, y, z in sorted(timber_cells):
            state = _axis_aligned_material(trim_material, "y")
            timber_model.set_block((x, y, z), state)
            timber_claims.append(((x, y, z), "timber", {"replaces": "structure"}))
        ownership.claim_batch(timber_claims)
        _merge(model, timber_model)

    if timber.beam_layers > 1:
        assert trim_material is not None
        beam_model = VoxelModel()
        beam_claims = []
        for layer in range(1, timber.beam_layers):
            for face in faces:
                basis = face_basis(face)
                normal_axis = 2 if basis.tangent_axis == 0 else 0
                for segment in segments[face]:
                    y = segment.bounds.max_y - layer
                    if y < segment.bounds.min_y:
                        raise ValueError("timber beam_layers exceed the available wall height")
                    start_values = [segment.bounds.min_x, y, segment.bounds.min_z]
                    end_values = [segment.bounds.max_x - 1, y, segment.bounds.max_z - 1]
                    start = tuple(start_values)
                    end = tuple(end_values)
                    if start[normal_axis] != end[normal_axis]:
                        raise ValueError("timber beam layer segment must be one block thick")
                    generated = VoxelModel()
                    if start == end:
                        axis = "x" if basis.tangent_axis == 0 else "z"
                        generated.set_block(start, _axis_aligned_material(trim_material, axis))
                    else:
                        generated = generate_beam(
                            start,
                            end,
                            trim_material,
                        )
                    for position, state in sorted(generated.blocks.items()):
                        reservation = opening_mask.reservation_at(position)
                        if reservation is not None:
                            raise ValueError(
                                f"timber beam layer overlaps reserved opening {reservation.opening_id!r} at {position}"
                            )
                        if ownership.owner_at(position) != "wall":
                            raise ValueError(f"timber beam layer overlaps protected structure at {position}")
                        ownership.allow_replacement(position, "timber")
                        if position in beam_model.blocks:
                            raise ValueError(f"timber beam layers overlap at {position}")
                        beam_model.set_block(position, state)
                        beam_claims.append((position, "timber", {"replaces": "wall"}))
        ownership.claim_batch(beam_claims)
        _merge(model, beam_model)

    for opening, bounds in openings:
        component_profile = profile.door if opening.kind == "door" else profile.window
        origin = (bounds.min_x, bounds.min_y, bounds.min_z)
        for position in facade_frame_positions(origin, component_profile, opening.face):
            if ownership.owner_at(position) == "wall":
                ownership.allow_replacement(position, "frame")
        if opening.kind == "door":
            component = generate_facade_door(
                origin,
                profile.door,
                opening.face,
                ownership,
                opening_mask,
                opening_id=opening.opening_id,
                materials=facade_materials,
            )
        else:
            component = generate_facade_window(
                origin,
                profile.window,
                opening.face,
                ownership,
                opening_mask,
                opening_id=opening.opening_id,
                materials=facade_materials,
            )
        _merge(model, component)


def generate_hall(
    parameters: HallParameters | None = None,
    *,
    through_passage: bool = False,
) -> VoxelModel:
    """Assemble a parameterized hall with a centered door and a gable roof."""

    parameters = parameters or HallParameters()
    if not isinstance(parameters, HallParameters):
        raise ValueError("parameters must be HallParameters")
    if not isinstance(through_passage, bool):
        raise ValueError("through_passage must be a boolean")
    if through_passage and parameters.facade_profile is None:
        raise ValueError("through_passage generation requires an explicit façade profile")
    materials = _resolve_materials(parameters.materials, DEFAULT_HALL_MATERIALS)
    width = parameters.bay_count * parameters.bay_width + 1
    depth = parameters.depth
    front_z = depth - 1
    plinth_top_y = parameters.plinth_height
    wall_base_y = plinth_top_y + 1
    beam_y = plinth_top_y + parameters.column_height
    roof_base_y = beam_y + 1
    model = VoxelModel()

    _merge(
        model,
        generate_plinth(
            BoundingBox(0, 0, 0, width, parameters.plinth_height, depth),
            materials["plinth"],
        ),
    )
    _merge(
        model,
        generate_plinth(
            BoundingBox(1, plinth_top_y, 1, width - 1, plinth_top_y + 1, depth - 1),
            materials["floor"],
        ),
    )

    bay_posts = tuple(range(0, width, parameters.bay_width))
    side_posts = set(range(0, depth - 1, parameters.bay_width)) | {depth - 1}
    post_positions = {(x, z) for x in bay_posts for z in (0, front_z)}
    post_positions.update((x, z) for x in (0, width - 1) for z in side_posts)
    for x, z in sorted(post_positions):
        _merge(model, generate_column(x, plinth_top_y, z, parameters.column_height, materials["column"]))

    for z in (0, front_z):
        _merge(model, generate_beam((0, beam_y, z), (width - 1, beam_y, z), materials["beam"]))
    for x in (0, width - 1):
        _merge(model, generate_beam((x, beam_y, 0), (x, beam_y, front_z), materials["beam"]))

    if parameters.facade_profile is not None:
        _generate_profiled_facades(
            model,
            parameters.facade_profile,
            _hall_face_segments(parameters),
            materials,
            faces=("front", "rear", "left", "right"),
            column_positions=tuple(sorted(post_positions)),
            column_base_y=plinth_top_y,
            column_top_y=beam_y - 1,
            through_passage=through_passage,
        )
        _merge_roof(
            model,
            _roof_model(width, depth, roof_base_y, parameters, materials),
            beam_y=beam_y,
            width=width,
            depth=depth,
        )
        return model

    center_bay = parameters.bay_count // 2
    door_x = center_bay * parameters.bay_width + 1 + (parameters.bay_width - 1 - parameters.door_width) // 2
    window_width = min(2, parameters.bay_width - 3)
    wall_height = parameters.column_height - 1
    window_height = min(2, wall_height - 1)
    window_y = wall_base_y + 1

    for bay in range(parameters.bay_count):
        x_start = bay * parameters.bay_width
        x_end = (bay + 1) * parameters.bay_width
        panel_x_start, panel_x_end = x_start + 1, x_end
        for z in (0, front_z):
            openings: list[BoundingBox] = []
            if z == front_z and bay == center_bay:
                openings.append(BoundingBox(door_x, wall_base_y, z, door_x + parameters.door_width, wall_base_y + 2, z + 1))
            elif z == front_z:
                window_x = panel_x_start + (panel_x_end - panel_x_start - window_width) // 2
                openings.append(BoundingBox(window_x, window_y, z, window_x + window_width, window_y + window_height, z + 1))
            _merge(
                model,
                generate_wall(
                    BoundingBox(panel_x_start, wall_base_y, z, panel_x_end, beam_y, z + 1),
                    materials["wall"],
                    openings,
                ),
            )
            if z == front_z and bay == center_bay:
                _merge(model, generate_door(door_x, wall_base_y, z, parameters.door_width, materials["door"], "south"))
            elif z == front_z:
                window_x = panel_x_start + (panel_x_end - panel_x_start - window_width) // 2
                _merge(model, generate_window(window_x, window_y, z, window_width, window_height, materials["window"], ("north",)))

    for z_start, z_end in zip(sorted(side_posts), sorted(side_posts)[1:]):
        if z_end - z_start <= 1:
            continue
        for x in (0, width - 1):
            x_start = x if x == 0 else x
            x_end = x + 1
            _merge(
                model,
                generate_wall(
                    BoundingBox(x_start, wall_base_y, z_start + 1, x_end, beam_y, z_end),
                    materials["wall"],
                ),
            )

    _merge_roof(
        model,
        _roof_model(width, depth, roof_base_y, parameters, materials),
        beam_y=beam_y,
        width=width,
        depth=depth,
    )
    return model


def generate_corridor(parameters: CorridorParameters | None = None) -> VoxelModel:
    """Assemble a straight open-sided corridor with repeated posts and a gable roof."""

    parameters = parameters or CorridorParameters()
    if not isinstance(parameters, CorridorParameters):
        raise ValueError("parameters must be CorridorParameters")
    materials = _resolve_materials(parameters.materials, DEFAULT_CORRIDOR_MATERIALS)
    model = VoxelModel()
    _merge(
        model,
        generate_plinth(BoundingBox(0, 0, 0, parameters.length, 1, parameters.width), materials["floor"]),
    )

    post_x_positions = set(range(0, parameters.length, parameters.column_spacing)) | {parameters.length - 1}
    post_z_positions = (0, parameters.width - 1)
    for x in sorted(post_x_positions):
        for z in post_z_positions:
            _merge(model, generate_column(x, 1, z, parameters.column_height, materials["column"]))

    beam_y = 1 + parameters.column_height
    for z in post_z_positions:
        _merge(model, generate_beam((0, beam_y, z), (parameters.length - 1, beam_y, z), materials["beam"]))

    roof_base_y = beam_y + 1
    _merge_roof(
        model,
        _roof_model(parameters.length, parameters.width, roof_base_y, parameters, materials),
        beam_y=beam_y,
        width=parameters.length,
        depth=parameters.width,
    )
    if parameters.facade_profile is not None:
        wall_base_y = 2
        beam_y = 1 + parameters.column_height
        post_x_positions = tuple(
            sorted(set(range(0, parameters.length, parameters.column_spacing)) | {parameters.length - 1})
        )
        post_z_positions = (0, parameters.width - 1)
        face_bounds = {
            "front": BoundingBox(0, wall_base_y, parameters.width - 1, parameters.length, beam_y, parameters.width),
            "rear": BoundingBox(0, wall_base_y, 0, parameters.length, beam_y, 1),
            "left": BoundingBox(0, wall_base_y, 0, 1, beam_y, parameters.width),
            "right": BoundingBox(parameters.length - 1, wall_base_y, 0, parameters.length, beam_y, parameters.width),
        }
        segments = {
            "front": build_facade_segments("front", face_bounds["front"], post_x_positions),
            "rear": build_facade_segments("rear", face_bounds["rear"], post_x_positions),
            "left": build_facade_segments("left", face_bounds["left"], post_z_positions),
            "right": build_facade_segments("right", face_bounds["right"], post_z_positions),
        }
        _generate_profiled_facades(
            model,
            parameters.facade_profile,
            segments,
            materials,
            faces=parameters.facade_profile.enclosed_faces,
            column_positions=tuple((x, z) for x in post_x_positions for z in post_z_positions),
            column_base_y=1,
            column_top_y=beam_y - 1,
        )
    return model
