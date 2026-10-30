"""Graph operations for placing, joining, splitting, and replacing modules."""

from __future__ import annotations

from collections import deque

from .model import Assembly, Connection, ConnectionAnchor, Module
from .transforms import rotate_module, translate_module

_FACINGS = ("north", "east", "south", "west")
_OPPOSITE = {"north": "south", "east": "west", "south": "north", "west": "east"}


def _anchor_pair(first: ConnectionAnchor, second: ConnectionAnchor) -> None:
    if first.connection_type != second.connection_type:
        raise ValueError("connection type mismatch between anchors")
    if (first.width, first.height) != (second.width, second.height):
        raise ValueError("connection opening size mismatch between anchors")
    if first.position[1] != second.position[1]:
        raise ValueError(
            f"anchor height mismatch: {first.position[1]} versus {second.position[1]}"
        )


def _anchor_is_used(assembly: Assembly, module_id: str, anchor_name: str) -> bool:
    return any(
        (connection.first_module_id, connection.first_anchor) == (module_id, anchor_name)
        or (connection.second_module_id, connection.second_anchor) == (module_id, anchor_name)
        for connection in assembly.connections
    )


def connect_modules(
    assembly: Assembly,
    first_module_id: str,
    first_anchor_name: str,
    second_module: Module | str,
    second_anchor_name: str,
) -> Assembly:
    """Join an existing module to a new one, or record a checked existing join.

    Passing a Module rotates and translates it to the first anchor. Passing an
    existing module ID records a connection only when both anchors already align.
    The source assembly is never mutated.
    """

    if first_module_id not in assembly.modules:
        raise ValueError(f"unknown module ID: {first_module_id!r}")
    first_module = assembly.modules[first_module_id]
    try:
        first_anchor = first_module.anchor(first_anchor_name)
    except KeyError as exc:
        raise ValueError(str(exc)) from exc
    if _anchor_is_used(assembly, first_module_id, first_anchor_name):
        raise ValueError(f"anchor {first_anchor_name!r} on {first_module_id!r} is already connected")

    adding_new = isinstance(second_module, Module)
    if adding_new:
        target = second_module
        if target.module_id in assembly.modules:
            raise ValueError(f"duplicate module ID: {target.module_id!r}")
    elif isinstance(second_module, str):
        try:
            target = assembly.modules[second_module]
        except KeyError as exc:
            raise ValueError(f"unknown module ID: {second_module!r}") from exc
    else:
        raise ValueError("second_module must be a Module or an existing module ID")

    if target.module_id == first_module_id:
        raise ValueError("a connection must join two different modules")
    try:
        second_anchor = target.anchor(second_anchor_name)
    except KeyError as exc:
        raise ValueError(str(exc)) from exc
    if _anchor_is_used(assembly, target.module_id, second_anchor_name):
        raise ValueError(f"anchor {second_anchor_name!r} on {target.module_id!r} is already connected")
    _anchor_pair(first_anchor, second_anchor)

    if adding_new:
        turns = (_FACINGS.index(_OPPOSITE[first_anchor.facing]) - _FACINGS.index(second_anchor.facing)) % 4
        rotated = rotate_module(target, turns)
        rotated_anchor = rotated.anchor(second_anchor_name)
        dx = first_anchor.position[0] - rotated_anchor.position[0]
        dz = first_anchor.position[2] - rotated_anchor.position[2]
        target = translate_module(rotated, (dx, 0, dz))
        second_anchor = target.anchor(second_anchor_name)
    else:
        if first_anchor.position != second_anchor.position:
            raise ValueError("connection anchor position mismatch")
        if first_anchor.facing != _OPPOSITE[second_anchor.facing]:
            raise ValueError("connection anchor facings must oppose")

    connection = Connection(first_module_id, first_anchor_name, target.module_id, second_anchor_name)
    modules = (*assembly.modules.values(), target) if adding_new else tuple(assembly.modules.values())
    return Assembly(modules, (*assembly.connections, connection))


def disconnect_modules(assembly: Assembly, connection: Connection) -> Assembly:
    """Return a copy with one exact connection edge removed."""

    if connection not in assembly.connections:
        reverse = Connection(
            connection.second_module_id,
            connection.second_anchor,
            connection.first_module_id,
            connection.first_anchor,
        )
        if reverse not in assembly.connections:
            raise ValueError("connection is not present in the assembly")
        connection = reverse
    remaining = tuple(edge for edge in assembly.connections if edge != connection)
    return Assembly(assembly.modules.values(), remaining)


def replace_module(assembly: Assembly, module_id: str, replacement: Module) -> Assembly:
    """Replace one module while preserving its stable ID and connection records."""

    if module_id not in assembly.modules:
        raise ValueError(f"unknown module ID: {module_id!r}")
    if not isinstance(replacement, Module):
        raise ValueError("replacement must be a Module")
    if replacement.module_id != module_id:
        raise ValueError("replacement must keep the same module ID")
    modules = tuple(replacement if module.module_id == module_id else module for module in assembly.modules.values())
    return Assembly(modules, assembly.connections)


def split_assembly(assembly: Assembly) -> tuple[Assembly, ...]:
    """Return stable connected components, including isolated modules."""

    module_ids = set(assembly.modules)
    neighbors = {module_id: set() for module_id in module_ids}
    for connection in assembly.connections:
        if connection.first_module_id in module_ids and connection.second_module_id in module_ids:
            neighbors[connection.first_module_id].add(connection.second_module_id)
            neighbors[connection.second_module_id].add(connection.first_module_id)

    components: list[tuple[str, ...]] = []
    remaining = set(module_ids)
    while remaining:
        start = min(remaining)
        pending = deque([start])
        found: set[str] = set()
        while pending:
            module_id = pending.popleft()
            if module_id in found:
                continue
            found.add(module_id)
            pending.extend(sorted(neighbors[module_id] - found))
        remaining -= found
        components.append(tuple(sorted(found)))

    pieces: list[Assembly] = []
    for component in sorted(components):
        included = set(component)
        modules = (assembly.modules[module_id] for module_id in component)
        connections = (
            connection
            for connection in assembly.connections
            if connection.first_module_id in included and connection.second_module_id in included
        )
        pieces.append(Assembly(modules, connections))
    return tuple(pieces)
