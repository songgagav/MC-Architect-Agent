"""Typed, deterministic profiles for Minecraft façade and opening design."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import json
import re
from types import MappingProxyType

from ..core.block import BlockState

_FACES = frozenset({"front", "rear", "left", "right"})
_OPENING_KINDS = frozenset({"door", "window"})
_CONNECTION_USES = frozenset({"primary_entry", "non_connecting"})
_LATTICE_STYLES = frozenset({"plain", "grid", "vertical", "cross"})
_OPENING_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")


def _integer(value: object, name: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer of at least {minimum}")
    return value


def _role(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty material role")
    return value.strip()


def _enum(value: object, name: str, choices: frozenset[str]) -> str:
    if not isinstance(value, str) or value not in choices:
        raise ValueError(f"{name} must be one of {', '.join(sorted(choices))}")
    return value


def _role_sequence(value: object, name: str, *, expected: int | None = None) -> tuple[str, ...]:
    if not isinstance(value, (tuple, list)):
        raise ValueError(f"{name} must be an array of material roles")
    result = tuple(_role(item, name) for item in value)
    if expected is not None and len(result) != expected:
        raise ValueError(f"{name} count must equal thickness")
    return result


def _profile_mapping(value: object, name: str, allowed: set[str]) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a JSON object")
    extra = set(value) - allowed
    if extra:
        raise ValueError(f"{name} has unsupported fields: {', '.join(sorted(map(str, extra)))}")
    return value


@dataclass(frozen=True)
class FacadeOpening:
    """Stable opening identity and its location on a local façade face."""

    opening_id: str
    face: str
    kind: str
    connection_use: str
    segment_index: int
    offset: int
    sill_offset: int

    def __post_init__(self) -> None:
        if not isinstance(self.opening_id, str) or not _OPENING_ID.fullmatch(self.opening_id.strip()):
            raise ValueError("opening_id must be a non-empty stable identifier")
        object.__setattr__(self, "opening_id", self.opening_id.strip())
        object.__setattr__(self, "face", _enum(self.face, "face", _FACES))
        object.__setattr__(self, "kind", _enum(self.kind, "kind", _OPENING_KINDS))
        object.__setattr__(self, "connection_use", _enum(self.connection_use, "connection_use", _CONNECTION_USES))
        object.__setattr__(self, "segment_index", _integer(self.segment_index, "segment_index"))
        object.__setattr__(self, "offset", _integer(self.offset, "offset"))
        object.__setattr__(self, "sill_offset", _integer(self.sill_offset, "sill_offset"))


@dataclass(frozen=True)
class WallPanelProfile:
    """Layered wall material roles and the direction in which thickness grows."""

    thickness: int = 1
    expand_direction: str = "inward"
    layer_roles: tuple[str, ...] = ("wall",)
    replaceable: bool = True

    def __post_init__(self) -> None:
        thickness = _integer(self.thickness, "thickness", minimum=1)
        if self.expand_direction not in {"inward", "outward"}:
            raise ValueError("expand_direction must be inward or outward")
        roles = _role_sequence(self.layer_roles, "layer_roles", expected=thickness)
        if not isinstance(self.replaceable, bool):
            raise ValueError("replaceable must be a boolean")
        object.__setattr__(self, "thickness", thickness)
        object.__setattr__(self, "layer_roles", roles)


@dataclass(frozen=True)
class DoorProfile:
    """Discrete single or paired vanilla-door configuration."""

    width: int = 2
    height: int = 2
    frame_thickness: int = 0
    frame_material_role: str = "column"
    lintel_material_role: str = "beam"
    lintel: bool = True

    def __post_init__(self) -> None:
        width = _integer(self.width, "door width", minimum=1)
        if width not in (1, 2):
            raise ValueError("door width must be 1 or 2 blocks")
        height = _integer(self.height, "door height", minimum=1)
        if height != 2:
            raise ValueError("vanilla door height must be exactly 2 blocks")
        thickness = _integer(self.frame_thickness, "frame_thickness")
        if thickness > 1:
            raise ValueError("door frame_thickness must be 0 or 1 block")
        if not isinstance(self.lintel, bool):
            raise ValueError("lintel must be a boolean")
        object.__setattr__(self, "width", width)
        object.__setattr__(self, "height", height)
        object.__setattr__(self, "frame_thickness", thickness)
        object.__setattr__(self, "frame_material_role", _role(self.frame_material_role, "frame_material_role"))
        object.__setattr__(self, "lintel_material_role", _role(self.lintel_material_role, "lintel_material_role"))


@dataclass(frozen=True)
class WindowProfile:
    """A grid-sized window, its sill, frame, glazing, and discrete lattice pattern."""

    width: int = 2
    height: int = 2
    sill_height: int = 2
    frame_thickness: int = 1
    frame_material_role: str = "beam"
    glazing_material_role: str = "window"
    lattice_material_role: str = "lattice"
    lattice_style: str = "plain"

    def __post_init__(self) -> None:
        width = _integer(self.width, "window width", minimum=1)
        height = _integer(self.height, "window height", minimum=1)
        sill = _integer(self.sill_height, "sill_height")
        thickness = _integer(self.frame_thickness, "frame_thickness")
        if thickness > 1:
            raise ValueError("window frame_thickness must be 0 or 1 block")
        style = _enum(self.lattice_style, "lattice_style", _LATTICE_STYLES)
        object.__setattr__(self, "width", width)
        object.__setattr__(self, "height", height)
        object.__setattr__(self, "sill_height", sill)
        object.__setattr__(self, "frame_thickness", thickness)
        object.__setattr__(self, "frame_material_role", _role(self.frame_material_role, "frame_material_role"))
        object.__setattr__(self, "glazing_material_role", _role(self.glazing_material_role, "glazing_material_role"))
        object.__setattr__(self, "lattice_material_role", _role(self.lattice_material_role, "lattice_material_role"))
        object.__setattr__(self, "lattice_style", style)


@dataclass(frozen=True)
class TimberDetailProfile:
    """Optional exposed timber and simple column/beam detailing switches."""

    exterior_posts: bool = True
    column_bases: bool = False
    column_capitals: bool = False
    beam_layers: int = 1
    trim_material_role: str = "beam"

    def __post_init__(self) -> None:
        for name in ("exterior_posts", "column_bases", "column_capitals"):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be a boolean")
        object.__setattr__(self, "beam_layers", _integer(self.beam_layers, "beam_layers", minimum=1))
        object.__setattr__(self, "trim_material_role", _role(self.trim_material_role, "trim_material_role"))


@dataclass(frozen=True)
class FacadeProfile:
    """Versioned façade configuration, independent of project module instances."""

    profile_id: str
    version: int = 1
    wall: WallPanelProfile = WallPanelProfile()
    door: DoorProfile = DoorProfile()
    window: WindowProfile = WindowProfile()
    timber: TimberDetailProfile = TimberDetailProfile()
    openings: tuple[FacadeOpening, ...] = ()
    materials: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        if not isinstance(self.profile_id, str) or not self.profile_id.strip():
            raise ValueError("profile_id must be a non-empty string")
        version = _integer(self.version, "version", minimum=1)
        if not isinstance(self.wall, WallPanelProfile):
            object.__setattr__(self, "wall", wall_panel_profile_from_mapping(self.wall))
        if not isinstance(self.door, DoorProfile):
            object.__setattr__(self, "door", door_profile_from_mapping(self.door))
        if not isinstance(self.window, WindowProfile):
            object.__setattr__(self, "window", window_profile_from_mapping(self.window))
        if not isinstance(self.timber, TimberDetailProfile):
            object.__setattr__(self, "timber", timber_detail_profile_from_mapping(self.timber))
        if not isinstance(self.openings, (tuple, list)):
            raise ValueError("openings must be an array")
        openings = tuple(
            opening if isinstance(opening, FacadeOpening) else facade_opening_from_mapping(opening)
            for opening in self.openings
        )
        ids = tuple(opening.opening_id for opening in openings)
        if len(ids) != len(set(ids)):
            raise ValueError("opening_id values must be unique within a façade profile")
        if not isinstance(self.materials, Mapping):
            raise ValueError("materials must be a mapping of roles to Minecraft block states")
        materials: dict[str, str] = {}
        for role, state in self.materials.items():
            role = _role(role, "material role")
            if not isinstance(state, str):
                raise ValueError(f"material for {role!r} must be a block-state string")
            parsed = BlockState.parse(state)
            if parsed.block_id.rsplit(":", 1)[-1] in {"air", "cave_air", "void_air"}:
                raise ValueError("air cannot be used as a façade material")
            materials[role] = parsed.to_string()
        object.__setattr__(self, "profile_id", self.profile_id.strip())
        object.__setattr__(self, "version", version)
        object.__setattr__(self, "openings", openings)
        object.__setattr__(self, "materials", MappingProxyType(materials))


def validate_facade_profile_for_hall(profile: FacadeProfile) -> FacadeOpening:
    """Require one front-facing primary entry for the hall connection adapter."""

    if not isinstance(profile, FacadeProfile):
        raise ValueError("facade_profile must be a FacadeProfile")
    entries = [opening for opening in profile.openings if opening.connection_use == "primary_entry"]
    if len(entries) != 1 or entries[0].face != "front" or entries[0].kind != "door":
        raise ValueError("hall façade profile requires exactly one front door primary_entry")
    return entries[0]


def facade_opening_to_mapping(profile: FacadeOpening) -> dict[str, object]:
    return {
        "opening_id": profile.opening_id,
        "face": profile.face,
        "kind": profile.kind,
        "connection_use": profile.connection_use,
        "segment_index": profile.segment_index,
        "offset": profile.offset,
        "sill_offset": profile.sill_offset,
    }


def facade_opening_from_mapping(value: object) -> FacadeOpening:
    config = _profile_mapping(
        value,
        "opening",
        {"opening_id", "face", "kind", "connection_use", "segment_index", "offset", "sill_offset"},
    )
    required = {"opening_id", "face", "kind", "connection_use", "segment_index", "offset", "sill_offset"}
    if not required.issubset(config):
        raise ValueError(f"opening is missing required fields: {', '.join(sorted(required - set(config)))}")
    return FacadeOpening(**config)  # type: ignore[arg-type]


def wall_panel_profile_to_mapping(profile: WallPanelProfile) -> dict[str, object]:
    return {
        "thickness": profile.thickness,
        "expand_direction": profile.expand_direction,
        "layer_roles": list(profile.layer_roles),
        "replaceable": profile.replaceable,
    }


def wall_panel_profile_from_mapping(value: object) -> WallPanelProfile:
    config = _profile_mapping(value, "wall", {"thickness", "expand_direction", "layer_roles", "replaceable"})
    return WallPanelProfile(**config)  # type: ignore[arg-type]


def door_profile_to_mapping(profile: DoorProfile) -> dict[str, object]:
    return {
        "width": profile.width,
        "height": profile.height,
        "frame_thickness": profile.frame_thickness,
        "frame_material_role": profile.frame_material_role,
        "lintel_material_role": profile.lintel_material_role,
        "lintel": profile.lintel,
    }


def door_profile_from_mapping(value: object) -> DoorProfile:
    config = _profile_mapping(
        value,
        "door",
        {"width", "height", "frame_thickness", "frame_material_role", "lintel_material_role", "lintel"},
    )
    return DoorProfile(**config)  # type: ignore[arg-type]


def window_profile_to_mapping(profile: WindowProfile) -> dict[str, object]:
    return {
        "width": profile.width,
        "height": profile.height,
        "sill_height": profile.sill_height,
        "frame_thickness": profile.frame_thickness,
        "frame_material_role": profile.frame_material_role,
        "glazing_material_role": profile.glazing_material_role,
        "lattice_material_role": profile.lattice_material_role,
        "lattice_style": profile.lattice_style,
    }


def window_profile_from_mapping(value: object) -> WindowProfile:
    config = _profile_mapping(
        value,
        "window",
        {
            "width",
            "height",
            "sill_height",
            "frame_thickness",
            "frame_material_role",
            "glazing_material_role",
            "lattice_material_role",
            "lattice_style",
        },
    )
    return WindowProfile(**config)  # type: ignore[arg-type]


def timber_detail_profile_to_mapping(profile: TimberDetailProfile) -> dict[str, object]:
    return {
        "exterior_posts": profile.exterior_posts,
        "column_bases": profile.column_bases,
        "column_capitals": profile.column_capitals,
        "beam_layers": profile.beam_layers,
        "trim_material_role": profile.trim_material_role,
    }


def timber_detail_profile_from_mapping(value: object) -> TimberDetailProfile:
    config = _profile_mapping(
        value,
        "timber",
        {"exterior_posts", "column_bases", "column_capitals", "beam_layers", "trim_material_role"},
    )
    return TimberDetailProfile(**config)  # type: ignore[arg-type]


def facade_profile_to_mapping(profile: FacadeProfile) -> dict[str, object]:
    if not isinstance(profile, FacadeProfile):
        raise ValueError("profile must be a FacadeProfile")
    return {
        "profile_id": profile.profile_id,
        "version": profile.version,
        "wall": wall_panel_profile_to_mapping(profile.wall),
        "door": door_profile_to_mapping(profile.door),
        "window": window_profile_to_mapping(profile.window),
        "timber": timber_detail_profile_to_mapping(profile.timber),
        "openings": [facade_opening_to_mapping(opening) for opening in profile.openings],
        "materials": dict(sorted(profile.materials.items())),
    }


def facade_profile_from_mapping(value: object) -> FacadeProfile:
    config = _profile_mapping(value, "facade_profile", {"profile_id", "version", "wall", "door", "window", "timber", "openings", "materials"})
    if "profile_id" not in config:
        raise ValueError("facade_profile is missing required field 'profile_id'")
    openings = config.get("openings", ())
    if not isinstance(openings, (tuple, list)):
        raise ValueError("facade_profile.openings must be an array")
    materials = config.get("materials", {})
    if not isinstance(materials, Mapping):
        raise ValueError("facade_profile.materials must be an object")
    return FacadeProfile(
        profile_id=config["profile_id"],  # type: ignore[arg-type]
        version=config.get("version", 1),  # type: ignore[arg-type]
        wall=wall_panel_profile_from_mapping(config.get("wall", {})),
        door=door_profile_from_mapping(config.get("door", {})),
        window=window_profile_from_mapping(config.get("window", {})),
        timber=timber_detail_profile_from_mapping(config.get("timber", {})),
        openings=tuple(facade_opening_from_mapping(item) for item in openings),
        materials=materials,
    )


def encode_facade_profile(profile: FacadeProfile) -> str:
    """Return canonical compact JSON with sorted mapping keys."""

    return json.dumps(facade_profile_to_mapping(profile), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def decode_facade_profile(value: str) -> FacadeProfile:
    """Read profile JSON, rejecting duplicate object keys and malformed JSON."""

    if not isinstance(value, str):
        raise ValueError("facade profile JSON must be a string")

    def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, item in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key!r}")
            result[key] = item
        return result

    try:
        data = json.loads(value, object_pairs_hook=unique_object)
    except json.JSONDecodeError as exc:
        raise ValueError("invalid façade profile JSON") from exc
    return facade_profile_from_mapping(data)
