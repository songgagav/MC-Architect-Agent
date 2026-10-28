"""Minecraft block and block-state values."""

from __future__ import annotations

from dataclasses import dataclass
import re

from .geometry import Position

_IDENTIFIER = re.compile(r"^[a-z0-9_.-]+:[a-z0-9_./-]+$")
_PROPERTY_KEY = re.compile(r"^[a-z0-9_]+$")
_PROPERTY_VALUE = re.compile(r"^[a-z0-9_:./-]+$")
_FACING = ("north", "east", "south", "west")


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
        turns = quarter_turns % 4
        props = dict(self.properties)
        facing = props.get("facing")
        if facing in _FACING:
            props["facing"] = _FACING[(_FACING.index(facing) + turns) % 4]
        if turns % 2 and props.get("axis") in ("x", "z"):
            props["axis"] = "z" if props["axis"] == "x" else "x"
        if "rotation" in props:
            rotation = int(props["rotation"])
            if 0 <= rotation <= 15:
                props["rotation"] = str((rotation + turns * 4) % 16)
        return BlockState(self.block_id, tuple(props.items()))

    def mirror(self, axis: str) -> BlockState:
        """Reflect horizontal direction and handedness properties across X or Z."""

        if axis not in ("x", "z"):
            raise ValueError("mirror axis must be 'x' or 'z'")
        direction_map = (
            {"east": "west", "west": "east"}
            if axis == "x"
            else {"north": "south", "south": "north"}
        )
        props: dict[str, str] = {}
        for key, value in self.properties:
            mirrored_key = direction_map.get(key, key)
            if key == "facing":
                value = direction_map.get(value, value)
            elif key == "rotation":
                try:
                    rotation = int(value)
                except ValueError:
                    pass
                else:
                    if 0 <= rotation <= 15:
                        value = str((-rotation if axis == "x" else 8 - rotation) % 16)
            elif key in ("hinge", "shape"):
                value = value.replace("left", "__mirror_tmp__").replace("right", "left").replace(
                    "__mirror_tmp__", "right"
                )
                value = re.sub(
                    r"(north|east|south|west)",
                    lambda match: direction_map.get(match.group(0), match.group(0)),
                    value,
                )
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
