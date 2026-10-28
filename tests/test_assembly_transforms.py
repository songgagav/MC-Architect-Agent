from __future__ import annotations

import pytest

from jiangnan_agent.assembly.model import ClearanceZone, ConnectionAnchor, Module
from jiangnan_agent.assembly.transforms import mirror_module, rotate_module, translate_module
from jiangnan_agent.core.geometry import BoundingBox
from jiangnan_agent.core.scene import VoxelModel


def make_module() -> Module:
    model = VoxelModel()
    model.set_block((0, 0, 0), "minecraft:stone")
    model.set_block((1, 0, 2), "minecraft:oak_stairs[facing=north,shape=inner_left,half=bottom]")
    return Module(
        "wing-1",
        "wing",
        model,
        anchors=(
            ConnectionAnchor("west", (0, 0, 1), "west", "passage", 2, 3),
            ConnectionAnchor("south", (1, 0, 3), "south", "passage", 2, 3),
        ),
        clearance_zones=(ClearanceZone("roof-eaves", BoundingBox(0, 1, 0, 2, 2, 1), "eaves"),),
    )


def test_translation_moves_model_anchors_and_clearances_without_mutating_source() -> None:
    source = make_module()

    moved = translate_module(source, (5, 2, -1))

    assert moved.module_id == source.module_id
    assert moved.model.block_at((5, 2, -1)).block_id == "minecraft:stone"
    assert moved.anchor("west").position == (5, 2, 0)
    assert moved.clearance_zones[0].bounds == BoundingBox(5, 3, -1, 7, 4, 0)
    assert source.model.block_at((0, 0, 0)).block_id == "minecraft:stone"
    assert source.anchor("west").position == (0, 0, 1)


def test_rotation_moves_boundary_anchors_and_clearances_with_voxels() -> None:
    rotated = rotate_module(make_module(), 1)

    assert rotated.model.block_at((2, 0, 0)).block_id == "minecraft:stone"
    assert rotated.anchor("south").position == (0, 0, 1)
    assert rotated.anchor("south").facing == "west"
    assert rotated.anchor("west").position == (2, 0, 0)
    assert rotated.anchor("west").facing == "north"
    assert rotated.clearance_zones[0].bounds == BoundingBox(2, 1, 0, 3, 2, 2)
    assert dict(rotated.model.block_at((0, 0, 1)).properties)["facing"] == "east"
    assert dict(rotated.model.block_at((0, 0, 1)).properties)["shape"] == "inner_left"


def test_mirror_updates_facing_handedness_anchors_and_clearances() -> None:
    mirrored = mirror_module(make_module(), "x")

    stair = mirrored.model.block_at((0, 0, 2))
    assert dict(stair.properties)["facing"] == "north"
    assert dict(stair.properties)["shape"] == "inner_right"
    assert mirrored.anchor("west").position == (2, 0, 1)
    assert mirrored.anchor("west").facing == "east"
    assert mirrored.clearance_zones[0].bounds == BoundingBox(0, 1, 0, 2, 2, 1)


def test_mirror_rejects_non_horizontal_axes() -> None:
    with pytest.raises(ValueError, match="axis"):
        mirror_module(make_module(), "y")
