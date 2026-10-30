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
    door_width: int = 2
    materials: Mapping[str, str] | None = None
    roof_profile: RoofProfile | None = None
    eave_profile: EaveProfile | None = None
    ridge_profile: RidgeProfile | None = None
    material_palette: MaterialPalette | None = None
    _roof_rise_explicit: bool = field(default=False, init=False, repr=False, compare=False)
    _eaves_explicit: bool = field(default=False, init=False, repr=False, compare=False)

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
        door_width = _require_integer(self.door_width, "door_width", 1)
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
        _validate_palette_aliases(normalized_materials, self.material_palette)
        object.__setattr__(self, "roof_rise", roof_rise)
        object.__setattr__(self, "eaves", eaves)
        object.__setattr__(self, "materials", normalized_materials)
        object.__setattr__(self, "_roof_rise_explicit", roof_rise_explicit)
        object.__setattr__(self, "_eaves_explicit", eaves_explicit)


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
        _validate_palette_aliases(normalized_materials, self.material_palette)
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
    ):
        value = getattr(parameters, name)
        if value is not None and not isinstance(
            value,
            {
                "roof_profile": RoofProfile,
                "eave_profile": EaveProfile,
                "ridge_profile": RidgeProfile,
                "material_palette": MaterialPalette,
            }[name],
        ):
            object.__setattr__(parameters, name, parser(value))


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


def generate_hall(parameters: HallParameters | None = None) -> VoxelModel:
    """Assemble a parameterized hall with a centered door and a gable roof."""

    parameters = parameters or HallParameters()
    if not isinstance(parameters, HallParameters):
        raise ValueError("parameters must be HallParameters")
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

    _merge(
        model,
        _roof_model(width, depth, roof_base_y, parameters, materials),
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
    _merge(
        model,
        _roof_model(parameters.length, parameters.width, roof_base_y, parameters, materials),
    )
    return model
