"""Typed, version-neutral profiles used by the gable roof builders."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from fractions import Fraction
from types import MappingProxyType

from ..core.block import BlockState

_PERMILLE_MAX = 1000
_SURFACE_FORMS = frozenset({"stair", "slab", "full_block"})
_GABLE_END_TREATMENTS = frozenset({"hard_gable", "overhanging_gable"})
_SURFACE_CONNECTIONS = frozenset({"legacy", "edge_liner"})


def _integer(value: object, name: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return value


def _role(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty material role")
    return value.strip()


def _section_points(points: object) -> tuple[tuple[int, int], ...]:
    if not isinstance(points, (tuple, list)) or len(points) < 2:
        raise ValueError("section points must contain at least two control points")
    normalized: list[tuple[int, int]] = []
    for point in points:
        if not isinstance(point, (tuple, list)) or len(point) != 2:
            raise ValueError("each section point must contain a run and height value")
        run, height = point
        for name, value in (("section point run", run), ("section point height", height)):
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= _PERMILLE_MAX:
                raise ValueError(f"{name} must be an integer from 0 through 1000")
        normalized.append((run, height))
    result = tuple(normalized)
    if result[0] != (0, 0) or result[-1] != (_PERMILLE_MAX, _PERMILLE_MAX):
        raise ValueError("section control points must start at (0, 0) and end at (1000, 1000)")
    if any(right[0] <= left[0] for left, right in zip(result, result[1:])):
        raise ValueError("section point run values must be strictly increasing")
    if any(right[1] < left[1] for left, right in zip(result, result[1:])):
        raise ValueError("section point height values must not decrease")
    return result


class SurfaceForm(StrEnum):
    STAIR = "stair"
    SLAB = "slab"
    FULL_BLOCK = "full_block"


class GableEndTreatment(StrEnum):
    HARD_GABLE = "hard_gable"
    OVERHANGING_GABLE = "overhanging_gable"


@dataclass(frozen=True)
class SurfaceBand:
    """A half-open roof-run interval and the block form/material role for it."""

    start: int
    end: int
    form: str
    material_role: str

    def __post_init__(self) -> None:
        start = _integer(self.start, "surface band start", minimum=0)
        end = _integer(self.end, "surface band end", minimum=1)
        if start >= end or end > _PERMILLE_MAX:
            raise ValueError("surface band must be a non-empty interval within 0..1000")
        form = str(self.form)
        if form not in _SURFACE_FORMS:
            raise ValueError("surface band form must be stair, slab, or full_block")
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)
        object.__setattr__(self, "form", form)
        object.__setattr__(self, "material_role", _role(self.material_role, "surface band material_role"))


@dataclass(frozen=True)
class RoofProfile:
    """A symmetric gable section measured upward from the eave datum."""

    ridge_height: int = 3
    section_points: tuple[tuple[int, int], ...] = ((0, 0), (1000, 1000))
    surface_bands: tuple[SurfaceBand, ...] = (SurfaceBand(0, 1000, "stair", "roof_stair"),)

    def __post_init__(self) -> None:
        ridge_height = _integer(self.ridge_height, "ridge_height", minimum=1)
        points = _section_points(self.section_points)
        if not isinstance(self.surface_bands, (tuple, list)) or not self.surface_bands:
            raise ValueError("surface bands must contain at least one band")
        bands = tuple(self.surface_bands)
        if any(not isinstance(band, SurfaceBand) for band in bands):
            raise ValueError("surface bands must be SurfaceBand values")
        if bands[0].start != 0 or bands[-1].end != _PERMILLE_MAX:
            raise ValueError("surface bands must cover the entire 0..1000 section")
        if any(left.end != right.start for left, right in zip(bands, bands[1:])):
            raise ValueError("surface bands must be contiguous without gaps or overlaps")
        object.__setattr__(self, "ridge_height", ridge_height)
        object.__setattr__(self, "section_points", points)
        object.__setattr__(self, "surface_bands", bands)


@dataclass(frozen=True)
class EaveProfile:
    """Side projection, gable-end treatment, and ordered eave trim layers."""

    side_overhang: int = 1
    gable_end_treatment: str = "overhanging_gable"
    gable_end_projection: int = 1
    thickness: int = 1
    layer_roles: tuple[str, ...] = ("eaves",)
    decoration_role: str | None = None
    decoration_spacing: int = 0
    surface_connection: str = "legacy"
    surface_connection_role: str | None = None

    def __post_init__(self) -> None:
        side_overhang = _integer(self.side_overhang, "side_overhang", minimum=0)
        treatment = str(self.gable_end_treatment)
        if treatment not in _GABLE_END_TREATMENTS:
            raise ValueError("gable_end_treatment must be hard_gable or overhanging_gable")
        projection = _integer(self.gable_end_projection, "gable_end_projection", minimum=0)
        if treatment == "hard_gable" and projection != 0:
            raise ValueError("hard_gable requires gable_end_projection=0")
        if treatment == "overhanging_gable" and projection < 1:
            raise ValueError("overhanging_gable requires a positive gable_end_projection")
        thickness = _integer(self.thickness, "thickness", minimum=0)
        if not isinstance(self.layer_roles, (tuple, list)):
            raise ValueError("layer_roles must be a sequence of material roles")
        layer_roles = tuple(_role(role, "eave layer role") for role in self.layer_roles)
        if len(layer_roles) != thickness:
            raise ValueError("eave layer_roles count must equal thickness")
        spacing = _integer(self.decoration_spacing, "decoration_spacing", minimum=0)
        decoration_role = self.decoration_role
        if decoration_role is not None:
            decoration_role = _role(decoration_role, "decoration_role")
            if spacing < 1:
                raise ValueError("decoration_spacing must be positive when decoration_role is set")
        elif spacing != 0:
            raise ValueError("decoration_spacing must be zero when decoration_role is not set")
        surface_connection = str(self.surface_connection)
        if surface_connection not in _SURFACE_CONNECTIONS:
            raise ValueError("surface_connection must be legacy or edge_liner")
        surface_connection_role = self.surface_connection_role
        if surface_connection == "edge_liner":
            surface_connection_role = _role(surface_connection_role, "surface_connection_role")
            if thickness < 1:
                raise ValueError("edge_liner requires at least one eave layer")
            if decoration_role is not None:
                raise ValueError("edge_liner cannot be combined with eave decoration")
        elif surface_connection_role is not None:
            raise ValueError("surface_connection_role is only valid with edge_liner")
        object.__setattr__(self, "side_overhang", side_overhang)
        object.__setattr__(self, "gable_end_treatment", treatment)
        object.__setattr__(self, "gable_end_projection", projection)
        object.__setattr__(self, "thickness", thickness)
        object.__setattr__(self, "layer_roles", layer_roles)
        object.__setattr__(self, "decoration_role", decoration_role)
        object.__setattr__(self, "decoration_spacing", spacing)
        object.__setattr__(self, "surface_connection", surface_connection)
        object.__setattr__(self, "surface_connection_role", surface_connection_role)


@dataclass(frozen=True)
class RidgeProfile:
    """Optional centered cap and repeating ridge decoration."""

    cap_width: int = 0
    cap_height: int = 0
    material_role: str = "ridge"
    decoration_role: str | None = None
    decoration_spacing: int = 0

    def __post_init__(self) -> None:
        cap_width = _integer(self.cap_width, "cap_width", minimum=0)
        cap_height = _integer(self.cap_height, "cap_height", minimum=0)
        if cap_height == 0 and cap_width != 0:
            raise ValueError("cap_width must be zero when the ridge cap is disabled")
        if cap_height > 0 and (cap_width < 1 or cap_width % 2 == 0):
            raise ValueError("enabled ridge cap width must be a positive odd number")
        spacing = _integer(self.decoration_spacing, "decoration_spacing", minimum=0)
        decoration_role = self.decoration_role
        if decoration_role is not None:
            decoration_role = _role(decoration_role, "decoration_role")
            if spacing < 1:
                raise ValueError("decoration_spacing must be positive when decoration_role is set")
        elif spacing != 0:
            raise ValueError("decoration_spacing must be zero when decoration_role is not set")
        object.__setattr__(self, "cap_width", cap_width)
        object.__setattr__(self, "cap_height", cap_height)
        object.__setattr__(self, "material_role", _role(self.material_role, "material_role"))
        object.__setattr__(self, "decoration_role", decoration_role)
        object.__setattr__(self, "decoration_spacing", spacing)


@dataclass(frozen=True)
class MaterialPalette:
    """Immutable map from semantic roof roles to complete Minecraft block states."""

    roles: Mapping[str, str]

    def __post_init__(self) -> None:
        if not isinstance(self.roles, Mapping) or not self.roles:
            raise ValueError("material palette roles must be a non-empty mapping")
        normalized: dict[str, str] = {}
        for role, value in self.roles.items():
            role = _role(role, "palette role")
            if not isinstance(value, str):
                raise ValueError(f"material for role {role!r} must be a block-state string")
            state = BlockState.parse(value)
            if state.block_id.rsplit(":", 1)[-1] in {"air", "cave_air", "void_air"}:
                raise ValueError("air cannot be used as a roof material")
            normalized[role] = state.to_string()
        object.__setattr__(self, "roles", MappingProxyType(normalized))


@dataclass(frozen=True)
class RoofPreset:
    """Versioned creative profile data grouped for lookup and application."""

    preset_id: str
    roof_profile: RoofProfile
    eave_profile: EaveProfile
    ridge_profile: RidgeProfile
    material_palette: MaterialPalette

    def __post_init__(self) -> None:
        preset_id = _role(self.preset_id, "preset_id")
        if not all(
            (
                isinstance(self.roof_profile, RoofProfile),
                isinstance(self.eave_profile, EaveProfile),
                isinstance(self.ridge_profile, RidgeProfile),
                isinstance(self.material_palette, MaterialPalette),
            )
        ):
            raise ValueError("roof preset requires typed roof, eave, ridge, and material profiles")
        required_roles = {band.material_role for band in self.roof_profile.surface_bands}
        required_roles.update(self.eave_profile.layer_roles)
        if self.eave_profile.surface_connection_role is not None:
            required_roles.add(self.eave_profile.surface_connection_role)
        if self.eave_profile.decoration_role is not None:
            required_roles.add(self.eave_profile.decoration_role)
        if self.ridge_profile.cap_height > 0:
            required_roles.add(self.ridge_profile.material_role)
        if self.ridge_profile.decoration_role is not None:
            required_roles.add(self.ridge_profile.decoration_role)
        missing = required_roles - set(self.material_palette.roles)
        if missing:
            raise ValueError(f"roof preset palette is missing roles: {', '.join(sorted(missing))}")
        object.__setattr__(self, "preset_id", preset_id)


def _profile_mapping(value: object, name: str, allowed: set[str]) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a JSON object")
    unknown = set(value) - allowed
    if unknown:
        raise ValueError(f"unknown {name} field: {sorted(unknown)[0]}")
    return value


def roof_profile_from_mapping(value: object) -> RoofProfile:
    config = _profile_mapping(value, "roof_profile", {"ridge_height", "section_points", "surface_bands"})
    bands = config.get("surface_bands")
    if not isinstance(bands, (list, tuple)):
        raise ValueError("roof_profile.surface_bands must be an array")
    try:
        return RoofProfile(
            ridge_height=config["ridge_height"],
            section_points=config["section_points"],
            surface_bands=tuple(
                SurfaceBand(**_profile_mapping(band, "surface band", {"start", "end", "form", "material_role"}))
                for band in bands
            ),
        )
    except KeyError as exc:
        raise ValueError(f"roof_profile is missing required field {exc.args[0]!r}") from exc
    except TypeError as exc:
        raise ValueError(f"invalid roof_profile fields: {exc}") from exc


def eave_profile_from_mapping(value: object) -> EaveProfile:
    config = _profile_mapping(
        value,
        "eave_profile",
        {
            "side_overhang",
            "gable_end_treatment",
            "gable_end_projection",
            "thickness",
            "layer_roles",
            "decoration_role",
            "decoration_spacing",
            "surface_connection",
            "surface_connection_role",
        },
    )
    try:
        return EaveProfile(**config)
    except TypeError as exc:
        raise ValueError(f"invalid eave_profile fields: {exc}") from exc


def ridge_profile_from_mapping(value: object) -> RidgeProfile:
    config = _profile_mapping(
        value,
        "ridge_profile",
        {"cap_width", "cap_height", "material_role", "decoration_role", "decoration_spacing"},
    )
    try:
        return RidgeProfile(**config)
    except TypeError as exc:
        raise ValueError(f"invalid ridge_profile fields: {exc}") from exc


def material_palette_from_mapping(value: object) -> MaterialPalette:
    if not isinstance(value, Mapping):
        raise ValueError("material_palette must be a JSON object mapping roles to block states")
    return MaterialPalette(value)


def _round_fraction_half_up(value: Fraction) -> int:
    quotient, remainder = divmod(value.numerator, value.denominator)
    return quotient + (1 if remainder * 2 >= value.denominator else 0)


def sample_roof_section(
    half_run: int,
    ridge_height: int,
    points: tuple[tuple[int, int], ...],
) -> tuple[int, ...]:
    """Sample a normalized section at each block run using exact rational math."""

    half_run = _integer(half_run, "half_run", minimum=1)
    ridge_height = _integer(ridge_height, "ridge_height", minimum=1)
    points = _section_points(points)
    heights: list[int] = []
    for run in range(half_run + 1):
        t = Fraction(run * _PERMILLE_MAX, half_run)
        for (left_run, left_height), (right_run, right_height) in zip(points, points[1:]):
            if t <= right_run:
                normalized_height = Fraction(left_height) + (
                    (t - left_run) * (right_height - left_height) / (right_run - left_run)
                )
                heights.append(_round_fraction_half_up(normalized_height * ridge_height / _PERMILLE_MAX))
                break
    if len(heights) != half_run + 1 or heights[0] != 0 or heights[-1] != ridge_height:
        raise ValueError("section points did not produce complete eave and ridge endpoints")
    if any(right - left not in (0, 1) for left, right in zip(heights, heights[1:])):
        raise ValueError("sampled roof section has a height step greater than one block")
    return tuple(heights)
