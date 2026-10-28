"""Validated data contracts for reusable modules and assemblies."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from ..core.geometry import BoundingBox, Position
from ..core.scene import VoxelModel

_CARDINAL_FACINGS = frozenset({"north", "east", "south", "west"})


def _nonempty_string(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _position(value: Position) -> Position:
    if (
        not isinstance(value, tuple)
        or len(value) != 3
        or any(isinstance(coordinate, bool) or not isinstance(coordinate, int) for coordinate in value)
    ):
        raise ValueError("position must contain three integer coordinates")
    return value


def _positive_integer(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


@dataclass(frozen=True)
class ConnectionAnchor:
    """A named connection plane on a module, with its outward facing and aperture size."""

    name: str
    position: Position
    facing: str
    connection_type: str
    width: int = 1
    height: int = 1

    def __post_init__(self) -> None:
        _nonempty_string(self.name, "anchor name")
        _position(self.position)
        if self.facing not in _CARDINAL_FACINGS:
            raise ValueError("anchor facing must be north, east, south, or west")
        _nonempty_string(self.connection_type, "connection type")
        _positive_integer(self.width, "anchor width")
        _positive_integer(self.height, "anchor height")


@dataclass(frozen=True)
class ClearanceZone:
    """A half-open volume that should remain clear of other modules."""

    name: str
    bounds: BoundingBox
    purpose: str

    def __post_init__(self) -> None:
        _nonempty_string(self.name, "clearance zone name")
        if not isinstance(self.bounds, BoundingBox):
            raise ValueError("clearance zone bounds must be a BoundingBox")
        _nonempty_string(self.purpose, "clearance zone purpose")


@dataclass(frozen=True)
class Module:
    """An independently addressable sparse voxel building fragment."""

    module_id: str
    kind: str
    model: VoxelModel
    anchors: tuple[ConnectionAnchor, ...] = ()
    clearance_zones: tuple[ClearanceZone, ...] = ()

    def __post_init__(self) -> None:
        _nonempty_string(self.module_id, "module ID")
        _nonempty_string(self.kind, "module kind")
        if not isinstance(self.model, VoxelModel):
            raise ValueError("module model must be a VoxelModel")
        anchors = tuple(self.anchors)
        if any(not isinstance(anchor, ConnectionAnchor) for anchor in anchors):
            raise ValueError("module anchors must be ConnectionAnchor values")
        anchor_names = [anchor.name for anchor in anchors]
        if len(anchor_names) != len(set(anchor_names)):
            raise ValueError("module anchor names must be unique")
        clearance_zones = tuple(self.clearance_zones)
        if any(not isinstance(zone, ClearanceZone) for zone in clearance_zones):
            raise ValueError("module clearance zones must be ClearanceZone values")
        zone_names = [zone.name for zone in clearance_zones]
        if len(zone_names) != len(set(zone_names)):
            raise ValueError("module clearance zone names must be unique")

        model_copy = VoxelModel()
        for position, state in self.model.blocks.items():
            model_copy.set_block(position, state)
        object.__setattr__(self, "model", model_copy)
        object.__setattr__(self, "anchors", anchors)
        object.__setattr__(self, "clearance_zones", clearance_zones)

    def anchor(self, name: str) -> ConnectionAnchor:
        """Return a named anchor or raise a clear lookup error."""

        for anchor in self.anchors:
            if anchor.name == name:
                return anchor
        raise KeyError(f"module {self.module_id!r} has no anchor {name!r}")


@dataclass(frozen=True)
class Connection:
    """An edge between two named anchors in an assembly graph."""

    first_module_id: str
    first_anchor: str
    second_module_id: str
    second_anchor: str

    def __post_init__(self) -> None:
        _nonempty_string(self.first_module_id, "first module ID")
        _nonempty_string(self.first_anchor, "first anchor name")
        _nonempty_string(self.second_module_id, "second module ID")
        _nonempty_string(self.second_anchor, "second anchor name")
        if self.first_module_id == self.second_module_id:
            raise ValueError("a connection must join two different modules")


@dataclass(frozen=True, init=False)
class Assembly:
    """A stable-ID mapping of modules and their explicit connection graph."""

    modules: Mapping[str, Module]
    connections: tuple[Connection, ...]

    def __init__(
        self,
        modules: Iterable[Module] = (),
        connections: Iterable[Connection] = (),
    ) -> None:
        module_map: dict[str, Module] = {}
        for module in modules:
            if not isinstance(module, Module):
                raise ValueError("assembly modules must be Module values")
            if module.module_id in module_map:
                raise ValueError(f"duplicate module ID: {module.module_id!r}")
            module_map[module.module_id] = module

        connection_list = tuple(connections)
        if any(not isinstance(connection, Connection) for connection in connection_list):
            raise ValueError("assembly connections must be Connection values")
        object.__setattr__(self, "modules", MappingProxyType(module_map))
        object.__setattr__(self, "connections", connection_list)
