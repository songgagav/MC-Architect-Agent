from __future__ import annotations

import pytest

from jiangnan_agent.assembly.model import Assembly, ClearanceZone, Connection, ConnectionAnchor, Module
from jiangnan_agent.core.geometry import BoundingBox
from jiangnan_agent.core.scene import VoxelModel


def make_module(module_id: str, anchors: tuple[ConnectionAnchor, ...] = ()) -> Module:
    model = VoxelModel()
    model.set_block((0, 0, 0), "minecraft:stone")
    return Module(module_id=module_id, kind="room", model=model, anchors=anchors)


def test_connection_anchor_validates_geometry_and_semantics() -> None:
    anchor = ConnectionAnchor("front", (1, 1, 3), "south", "passage", width=2, height=3)

    assert anchor.position == (1, 1, 3)
    assert anchor.facing == "south"
    assert anchor.connection_type == "passage"
    assert (anchor.width, anchor.height) == (2, 3)

    with pytest.raises(ValueError, match="facing"):
        ConnectionAnchor("bad", (0, 0, 0), "up", "passage")
    with pytest.raises(ValueError, match="width"):
        ConnectionAnchor("bad", (0, 0, 0), "north", "passage", width=0)
    with pytest.raises(ValueError, match="position"):
        ConnectionAnchor("bad", (0, True, 0), "north", "passage")


def test_clearance_zone_requires_name_and_purpose() -> None:
    zone = ClearanceZone("front-eaves", BoundingBox(0, 4, 0, 4, 6, 1), "eaves")

    assert zone.bounds.size == (4, 2, 1)
    assert zone.purpose == "eaves"
    with pytest.raises(ValueError, match="name"):
        ClearanceZone("", BoundingBox(0, 0, 0, 1, 1, 1), "eaves")


def test_module_copies_its_voxel_model_and_rejects_duplicate_anchor_names() -> None:
    source = VoxelModel()
    source.set_block((0, 0, 0), "minecraft:stone")
    anchor = ConnectionAnchor("front", (0, 0, 1), "south", "passage")
    module = Module("hall-1", "hall", source, anchors=(anchor,))

    source.set_block((0, 0, 0), "minecraft:dirt")
    source.set_block((1, 0, 0), "minecraft:gold_block")

    assert module.model.block_at((0, 0, 0)).block_id == "minecraft:stone"
    assert module.model.block_at((1, 0, 0)).block_id == "minecraft:air"
    with pytest.raises(ValueError, match="anchor names"):
        Module("hall-2", "hall", VoxelModel(), anchors=(anchor, anchor))


def test_assembly_indexes_modules_by_unique_stable_id() -> None:
    first = make_module("room-1")
    assembly = Assembly((first,))

    assert assembly.modules["room-1"] is first or assembly.modules["room-1"].module_id == "room-1"
    with pytest.raises(ValueError, match="duplicate module ID"):
        Assembly((first, make_module("room-1")))


def test_connection_records_named_endpoints() -> None:
    connection = Connection("hall-1", "front", "corridor-1", "north")

    assert (connection.first_module_id, connection.first_anchor) == ("hall-1", "front")
    assert (connection.second_module_id, connection.second_anchor) == ("corridor-1", "north")


def test_module_copies_and_freezes_nested_json_parameters() -> None:
    parameters = {"bay_count": 3, "materials": {"roof": "minecraft:stone"}, "labels": ["front"]}
    module = Module("hall-1", "hall", VoxelModel(), parameters=parameters)

    parameters["materials"]["roof"] = "minecraft:dirt"
    parameters["labels"].append("changed")

    assert module.parameters["materials"]["roof"] == "minecraft:stone"
    assert module.parameters["labels"] == ("front",)
    with pytest.raises(TypeError):
        module.parameters["materials"]["roof"] = "minecraft:dirt"
    with pytest.raises(ValueError, match="JSON-compatible"):
        Module("invalid", "room", VoxelModel(), parameters={"custom": object()})


def test_building_adapters_capture_generator_parameters() -> None:
    from jiangnan_agent.assembly.adapters import corridor_module, hall_module
    from jiangnan_agent.generators.hall import CorridorParameters, HallParameters

    hall_parameters = HallParameters(bay_count=5, bay_width=6, depth=9, materials={"roof": "minecraft:stone_stairs"})
    corridor_parameters = CorridorParameters(length=13, width=5, materials={"roof": "minecraft:stone_stairs"})
    hall = hall_module("hall-1", hall_parameters, through_passage=True)
    corridor = corridor_module("corridor-1", corridor_parameters, passage_width=2)

    assert hall.parameters["bay_count"] == 5
    assert hall.parameters["materials"]["roof"] == "minecraft:stone_stairs"
    assert hall.parameters["through_passage"] is True
    assert corridor.parameters["length"] == 13
    assert corridor.parameters["passage_width"] == 2
