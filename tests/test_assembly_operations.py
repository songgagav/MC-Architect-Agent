from __future__ import annotations

import pytest

from jiangnan_agent.assembly.model import Assembly, Connection, ConnectionAnchor, Module
from jiangnan_agent.assembly.operations import (
    connect_modules,
    disconnect_modules,
    replace_module,
    split_assembly,
)
from jiangnan_agent.core.scene import VoxelModel


def module(
    module_id: str,
    anchor_specs: tuple[tuple[str, tuple[int, int, int], str, int, int], ...],
    block: str = "minecraft:stone",
) -> Module:
    model = VoxelModel()
    model.set_block((0, 0, 0), block)
    anchors = tuple(
        ConnectionAnchor(name, position, facing, "passage", width, height)
        for name, position, facing, width, height in anchor_specs
    )
    return Module(module_id, "test_module", model, anchors)


def test_connect_modules_rotates_and_aligns_new_module_anchors() -> None:
    source = module("hall", (("front", (3, 0, 5), "south", 2, 3),))
    target = module("gallery", (("end", (0, 0, -1), "east", 2, 3),), "minecraft:oak_planks")

    connected = connect_modules(Assembly((source,)), "hall", "front", target, "end")

    placed = connected.modules["gallery"]
    assert placed.anchor("end").position == (3, 0, 5)
    assert placed.anchor("end").facing == "north"
    assert placed.model.block_at((4, 0, 4)).block_id == "minecraft:oak_planks"
    assert connected.connections == (Connection("hall", "front", "gallery", "end"),)


def test_connect_existing_modules_records_only_exact_compatible_joins() -> None:
    hall = module("hall", (("front", (1, 0, 1), "south", 2, 3),))
    gallery = module("gallery", (("end", (1, 0, 1), "north", 2, 3),))
    placed = Assembly((hall, gallery))

    linked = connect_modules(placed, "hall", "front", "gallery", "end")

    assert linked.connections == (Connection("hall", "front", "gallery", "end"),)
    assert placed.connections == ()


@pytest.mark.parametrize(
    ("target_anchor", "message"),
    [
        (ConnectionAnchor("end", (1, 1, 0), "north", "passage", 2, 3), "height mismatch"),
        (ConnectionAnchor("end", (1, 0, 0), "north", "doorway", 2, 3), "connection type"),
        (ConnectionAnchor("end", (1, 0, 0), "north", "passage", 1, 3), "opening size"),
    ],
)
def test_connect_rejects_incompatible_module_without_partial_mutation(
    target_anchor: ConnectionAnchor,
    message: str,
) -> None:
    source = module("hall", (("front", (1, 0, 1), "south", 2, 3),))
    target = Module("gallery", "gallery", VoxelModel(), (target_anchor,))
    assembly = Assembly((source,))

    with pytest.raises(ValueError, match=message):
        connect_modules(assembly, "hall", "front", target, "end")

    assert tuple(assembly.modules) == ("hall",)
    assert assembly.connections == ()


def test_connect_rejects_reusing_an_anchor() -> None:
    first = module("hall", (("front", (1, 0, 1), "south", 1, 2),))
    second = module("gallery-a", (("end", (1, 0, 1), "north", 1, 2),))
    assembly = connect_modules(Assembly((first,)), "hall", "front", second, "end")
    third = module("gallery-b", (("end", (1, 0, 1), "north", 1, 2),))

    with pytest.raises(ValueError, match="already connected"):
        connect_modules(assembly, "hall", "front", third, "end")


def test_disconnect_and_split_follow_the_connection_graph() -> None:
    hall = module("hall", (("front", (1, 0, 1), "south", 1, 2),))
    gallery = module("gallery", (("end", (1, 0, 1), "north", 1, 2), ("outer", (2, 0, 1), "east", 1, 2)))
    wing = module("wing", (("side", (2, 0, 1), "west", 1, 2),))
    one_link = connect_modules(Assembly((hall,)), "hall", "front", gallery, "end")
    connected = connect_modules(one_link, "gallery", "outer", wing, "side")

    disconnected = disconnect_modules(
        connected,
        Connection("gallery", "outer", "wing", "side"),
    )
    pieces = split_assembly(disconnected)

    assert [tuple(piece.modules) for piece in pieces] == [("gallery", "hall"), ("wing",)]
    assert len(pieces[0].connections) == 1
    assert pieces[1].connections == ()
    assert len(connected.connections) == 2


def test_replace_module_keeps_id_and_does_not_mutate_other_modules() -> None:
    hall = module("hall", (("front", (1, 0, 1), "south", 1, 2),))
    wing = module("wing", (), "minecraft:oak_planks")
    assembly = Assembly((hall, wing))
    replacement = module("wing", (), "minecraft:birch_planks")

    updated = replace_module(assembly, "wing", replacement)

    assert updated.modules["wing"].model.block_at((0, 0, 0)).block_id == "minecraft:birch_planks"
    assert updated.modules["hall"] is hall
    assert assembly.modules["wing"].model.block_at((0, 0, 0)).block_id == "minecraft:oak_planks"
    with pytest.raises(ValueError, match="same module ID"):
        replace_module(assembly, "wing", module("new-wing", ()))
