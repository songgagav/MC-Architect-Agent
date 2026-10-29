"""Minecraft block and block-state values."""

from __future__ import annotations

from dataclasses import dataclass
import re

from .geometry import Position

_IDENTIFIER = re.compile(r"^[a-z0-9_.-]+:[a-z0-9_./-]+$")
_PROPERTY_KEY = re.compile(r"^[a-z0-9_]+$")
_PROPERTY_VALUE = re.compile(r"^[a-z0-9_:./-]+$")
_HORIZONTAL = ("north", "east", "south", "west")
_DIRECTIONS = (*_HORIZONTAL, "up", "down")
_STAIR_SHAPES = {"straight", "inner_left", "inner_right", "outer_left", "outer_right"}
_RAIL_AXES = {"north_south": frozenset(("north", "south")), "east_west": frozenset(("east", "west"))}
_RAIL_CURVES = {
    frozenset(("south", "east")): "south_east",
    frozenset(("south", "west")): "south_west",
    frozenset(("north", "west")): "north_west",
    frozenset(("north", "east")): "north_east",
}
_ORIENTATIONS = {
    "down_east", "down_north", "down_south", "down_west",
    "east_up", "north_up", "south_up", "up_east", "up_north", "up_south", "up_west", "west_up",
}
_EDGE_CONNECTION_VALUES = {"true", "false", "none", "low", "tall", "up", "side"}
_CHEST_TYPES = {"single", "left", "right"}


def _rotate_horizontal(direction: str, turns: int) -> str:
    if direction not in _DIRECTIONS:
        raise ValueError(f"unsupported directional block state value: {direction!r}")
    if direction in ("up", "down"):
        return direction
    return _HORIZONTAL[(_HORIZONTAL.index(direction) + turns) % 4]


def _mirror_horizontal(direction: str, axis: str) -> str:
    if direction not in _DIRECTIONS:
        raise ValueError(f"unsupported directional block state value: {direction!r}")
    if axis == "x":
        return {"east": "west", "west": "east"}.get(direction, direction)
    return {"north": "south", "south": "north"}.get(direction, direction)


def _map_orientation(value: str, map_direction) -> str:
    if value not in _ORIENTATIONS:
        raise ValueError(f"unsupported orientation block state value: {value!r}")
    first, second = value.split("_")
    result = f"{map_direction(first)}_{map_direction(second)}"
    if result not in _ORIENTATIONS:
        raise ValueError(f"unsupported transformed orientation block state value: {result!r}")
    return result


def _map_rail_shape(value: str, map_direction) -> str:
    if value in _RAIL_AXES:
        directions = _RAIL_AXES[value]
        mapped = frozenset(map_direction(direction) for direction in directions)
        return next(name for name, pair in _RAIL_AXES.items() if pair == mapped)
    if value.startswith("ascending_"):
        direction = value.removeprefix("ascending_")
        if direction not in _HORIZONTAL:
            raise ValueError(f"unsupported rail shape block state value: {value!r}")
        return f"ascending_{map_direction(direction)}"
    if value in _RAIL_CURVES.values():
        directions = frozenset(value.split("_"))
        mapped = frozenset(map_direction(direction) for direction in directions)
        if mapped in _RAIL_CURVES:
            return _RAIL_CURVES[mapped]
    raise ValueError(f"unsupported shape block state value: {value!r}")


def _rotate_shape(value: str, turns: int) -> str:
    if value in _STAIR_SHAPES:
        return value
    return _map_rail_shape(value, lambda direction: _rotate_horizontal(direction, turns))


def _mirror_shape(value: str, axis: str) -> str:
    if value in _STAIR_SHAPES:
        if value.endswith("_left"):
            return value.removesuffix("left") + "right"
        if value.endswith("_right"):
            return value.removesuffix("right") + "left"
        return value
    return _map_rail_shape(value, lambda direction: _mirror_horizontal(direction, axis))


def _rotation_index(value: str) -> int:
    try:
        rotation = int(value)
    except ValueError as exc:
        raise ValueError(f"unsupported rotation block state value: {value!r}") from exc
    if not 0 <= rotation <= 15:
        raise ValueError(f"unsupported rotation block state value: {value!r}")
    return rotation


def _validate_hinge(value: str) -> None:
    if value not in ("left", "right"):
        raise ValueError(f"unsupported hinge block state value: {value!r}")


def _validate_connection(value: str, name: str) -> None:
    if value not in _EDGE_CONNECTION_VALUES:
        raise ValueError(f"unsupported {name} connection block state value: {value!r}")


@dataclass(frozen=True)
class BlockState:
    """A namespaced block ID and its complete state property set."""

    block_id: str
    properties: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        block_id = self.block_id if ":" in self.block_id else f"minecraft:{self.block_id}"
        if not _IDENTIFIER.fullmatch(block_id):
            raise ValueError(f"invalid Minecraft block ID: {block_id!r}")
        normalized = tuple(sorted((str(key), str(value)) for key, value in self.properties))
        if any(not _PROPERTY_KEY.fullmatch(key) or not _PROPERTY_VALUE.fullmatch(value) for key, value in normalized):
            raise ValueError("invalid block state property")
        if len({key for key, _ in normalized}) != len(normalized):
            raise ValueError("duplicate block state property")
        object.__setattr__(self, "block_id", block_id)
        object.__setattr__(self, "properties", normalized)

    @classmethod
    def parse(cls, value: str) -> BlockState:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("block state must be a non-empty string")
        value = value.strip()
        if "[" not in value:
            return cls(value)
        if not value.endswith("]") or value.count("[") != 1:
            raise ValueError(f"invalid block state: {value!r}")
        block_id, raw_properties = value[:-1].split("[", 1)
        if not raw_properties:
            raise ValueError("block state property list cannot be empty")
        properties: list[tuple[str, str]] = []
        for item in raw_properties.split(","):
            if "=" not in item:
                raise ValueError(f"invalid block state property: {item!r}")
            key, prop_value = item.split("=", 1)
            if not key or not prop_value:
                raise ValueError(f"invalid block state property: {item!r}")
            properties.append((key, prop_value))
        return cls(block_id, tuple(properties))

    @property
    def id(self) -> str:
        """Compatibility alias for the block's resource location."""

        return self.block_id

    def to_string(self) -> str:
        if not self.properties:
            return self.block_id
        props = ",".join(f"{key}={value}" for key, value in self.properties)
        return f"{self.block_id}[{props}]"

    def rotate_y(self, quarter_turns: int) -> BlockState:
        if isinstance(quarter_turns, bool) or not isinstance(quarter_turns, int):
            raise ValueError("quarter_turns must be an integer")
        turns = quarter_turns % 4
        props: dict[str, str] = {}
        for key, value in self.properties:
            output_key = key
            if key in ("facing", "direction"):
                value = _rotate_horizontal(value, turns)
            elif key == "horizontal_facing":
                if value not in _HORIZONTAL:
                    raise ValueError(f"unsupported horizontal_facing block state value: {value!r}")
                value = _rotate_horizontal(value, turns)
            elif key == "orientation":
                value = _map_orientation(value, lambda direction: _rotate_horizontal(direction, turns))
            elif key in _HORIZONTAL:
                _validate_connection(value, key)
                output_key = _rotate_horizontal(key, turns)
            elif key in ("up", "down"):
                _validate_connection(value, key)
            elif key == "axis":
                if value not in ("x", "y", "z"):
                    raise ValueError(f"unsupported axis block state value: {value!r}")
                if turns % 2 and value in ("x", "z"):
                    value = "z" if value == "x" else "x"
            elif key == "horizontal_axis":
                if value not in ("x", "z"):
                    raise ValueError(f"unsupported horizontal_axis block state value: {value!r}")
                if turns % 2:
                    value = "z" if value == "x" else "x"
            elif key == "rotation":
                value = str((_rotation_index(value) + turns * 4) % 16)
            elif key == "shape":
                value = _rotate_shape(value, turns)
            elif key == "hinge":
                _validate_hinge(value)
            elif key == "vertical_direction" and value not in ("up", "down"):
                raise ValueError(f"unsupported vertical_direction block state value: {value!r}")
            elif key == "type" and self.block_id.endswith("_chest"):
                if value not in _CHEST_TYPES:
                    raise ValueError(f"unsupported chest type block state value: {value!r}")
            props[output_key] = value
        return BlockState(self.block_id, tuple(props.items()))

    def mirror(self, axis: str) -> BlockState:
        """Reflect horizontal direction and handedness properties across X or Z."""

        if axis not in ("x", "z"):
            raise ValueError("mirror axis must be 'x' or 'z'")
        props: dict[str, str] = {}
        for key, value in self.properties:
            mirrored_key = key
            if key in ("facing", "direction"):
                value = _mirror_horizontal(value, axis)
            elif key == "horizontal_facing":
                if value not in _HORIZONTAL:
                    raise ValueError(f"unsupported horizontal_facing block state value: {value!r}")
                value = _mirror_horizontal(value, axis)
            elif key == "orientation":
                value = _map_orientation(value, lambda direction: _mirror_horizontal(direction, axis))
            elif key in _HORIZONTAL:
                _validate_connection(value, key)
                mirrored_key = _mirror_horizontal(key, axis)
            elif key in ("up", "down"):
                _validate_connection(value, key)
            elif key == "axis":
                if value not in ("x", "y", "z"):
                    raise ValueError(f"unsupported axis block state value: {value!r}")
            elif key == "horizontal_axis" and value not in ("x", "z"):
                raise ValueError(f"unsupported horizontal_axis block state value: {value!r}")
            elif key == "rotation":
                rotation = _rotation_index(value)
                value = str((-rotation if axis == "x" else 8 - rotation) % 16)
            elif key == "shape":
                value = _mirror_shape(value, axis)
            elif key == "hinge":
                _validate_hinge(value)
                value = "right" if value == "left" else "left"
            elif key == "vertical_direction" and value not in ("up", "down"):
                raise ValueError(f"unsupported vertical_direction block state value: {value!r}")
            elif key == "type" and self.block_id.endswith("_chest"):
                if value not in _CHEST_TYPES:
                    raise ValueError(f"unsupported chest type block state value: {value!r}")
                if value in ("left", "right"):
                    value = "right" if value == "left" else "left"
            props[mirrored_key] = value
        return BlockState(self.block_id, tuple(props.items()))


@dataclass(frozen=True)
class Block:
    """A block state at one integer world coordinate."""

    position: Position
    state: BlockState

    def __post_init__(self) -> None:
        if len(self.position) != 3 or any(not isinstance(value, int) for value in self.position):
            raise ValueError("block position must contain three integers")
