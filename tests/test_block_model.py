from __future__ import annotations

import pytest

from jiangnan_agent.core.block import Block, BlockState
from jiangnan_agent.core.geometry import BoundingBox
from jiangnan_agent.core.scene import VoxelModel
from jiangnan_agent.core.transforms import rotate_model_y


def test_block_state_roundtrip_and_quarter_turn() -> None:
    state = BlockState.parse("minecraft:oak_stairs[waterlogged=false,half=top,facing=north]")

    assert state.to_string() == "minecraft:oak_stairs[facing=north,half=top,waterlogged=false]"
    assert state.rotate_y(1).to_string() == "minecraft:oak_stairs[facing=east,half=top,waterlogged=false]"


def test_bounding_box_uses_half_open_maximums() -> None:
    bounds = BoundingBox.from_positions([(2, 4, -1), (4, 5, 3)])

    assert bounds.size == (3, 2, 5)
    assert bounds.contains((4, 5, 3))
    assert not bounds.contains((5, 5, 3))


def test_voxel_model_fills_and_rotates_directional_states() -> None:
    model = VoxelModel()
    stair = BlockState.parse("minecraft:oak_stairs[facing=north,half=bottom,shape=straight,waterlogged=false]")
    model.set_block((0, 0, 0), stair)
    model.fill(BoundingBox(1, 0, 0, 2, 1, 1), "minecraft:stone")

    rotated = rotate_model_y(model, 1)

    assert rotated.block_at((0, 0, 0)) == BlockState.parse(
        "minecraft:oak_stairs[facing=east,half=bottom,shape=straight,waterlogged=false]"
    )
    assert rotated.block_at((0, 0, 1)) == BlockState.parse("minecraft:stone")
    assert len(rotated.blocks) == 2


def test_block_is_a_coordinate_and_state_pair() -> None:
    block = Block((1, 2, 3), BlockState.parse("minecraft:oak_door[half=lower,facing=west]"))

    assert block.position == (1, 2, 3)
    assert block.state.block_id == "minecraft:oak_door"


def test_invalid_block_state_is_rejected() -> None:
    with pytest.raises(ValueError):
        BlockState.parse("minecraft:oak_stairs[facing]")
