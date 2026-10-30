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


def test_mirror_block_state_reflects_direction_handedness_and_rotation() -> None:
    stairs = BlockState.parse("minecraft:oak_stairs[facing=east,shape=inner_left,half=bottom]")
    door = BlockState.parse("minecraft:oak_door[facing=north,hinge=left,half=lower]")
    rail = BlockState.parse("minecraft:rail[east=true,north=true,south=false,west=false,shape=north_east]")
    head = BlockState.parse("minecraft:player_head[rotation=12]")

    assert stairs.mirror("x").to_string() == "minecraft:oak_stairs[facing=west,half=bottom,shape=inner_right]"
    assert door.mirror("z").to_string() == "minecraft:oak_door[facing=south,half=lower,hinge=right]"
    assert rail.mirror("x").to_string() == "minecraft:rail[east=false,north=true,shape=north_west,south=false,west=true]"
    assert head.mirror("x").to_string() == "minecraft:player_head[rotation=4]"
    assert head.mirror("z").to_string() == "minecraft:player_head[rotation=12]"


@pytest.mark.parametrize(
    ("orientation", "rotated", "mirrored_x", "mirrored_z"),
    (
        ("down_east", "down_south", "down_west", "down_east"),
        ("down_north", "down_east", "down_north", "down_south"),
        ("down_south", "down_west", "down_south", "down_north"),
        ("down_west", "down_north", "down_east", "down_west"),
        ("east_up", "south_up", "west_up", "east_up"),
        ("north_up", "east_up", "north_up", "south_up"),
        ("south_up", "west_up", "south_up", "north_up"),
        ("up_east", "up_south", "up_west", "up_east"),
        ("up_north", "up_east", "up_north", "up_south"),
        ("up_south", "up_west", "up_south", "up_north"),
        ("up_west", "up_north", "up_east", "up_west"),
        ("west_up", "north_up", "east_up", "west_up"),
    ),
)
def test_minecraft_1215_orientation_rotates_and_mirrors_all_supported_values(
    orientation: str,
    rotated: str,
    mirrored_x: str,
    mirrored_z: str,
) -> None:
    state = BlockState("minecraft:crafter", (("orientation", orientation),))

    assert dict(state.rotate_y(1).properties)["orientation"] == rotated
    assert dict(state.mirror("x").properties)["orientation"] == mirrored_x
    assert dict(state.mirror("z").properties)["orientation"] == mirrored_z


@pytest.mark.parametrize(
    ("facing", "rotated"),
    (("north", "east"), ("east", "south"), ("south", "west"), ("west", "north"), ("up", "up"), ("down", "down")),
)
def test_facing_rotation_handles_horizontal_and_vertical_directions(facing: str, rotated: str) -> None:
    state = BlockState("minecraft:dispenser", (("facing", facing),))

    assert dict(state.rotate_y(1).properties)["facing"] == rotated


@pytest.mark.parametrize("rotation", range(16))
def test_rotation_property_covers_all_sixteen_values(rotation: int) -> None:
    state = BlockState("minecraft:player_head", (("rotation", str(rotation)),))

    assert dict(state.rotate_y(1).properties)["rotation"] == str((rotation + 4) % 16)
    assert dict(state.mirror("x").properties)["rotation"] == str((-rotation) % 16)
    assert dict(state.mirror("z").properties)["rotation"] == str((8 - rotation) % 16)


def test_rotate_maps_axis_rail_shape_and_cardinal_connections() -> None:
    state = BlockState.parse(
        "minecraft:rail[east=true,north=false,south=true,west=false,shape=north_east]"
    )
    log = BlockState.parse("minecraft:oak_log[axis=x]")

    rotated = state.rotate_y(1)

    assert dict(rotated.properties) == {
        "east": "false",
        "north": "false",
        "shape": "south_east",
        "south": "true",
        "west": "true",
    }
    assert dict(log.rotate_y(1).properties)["axis"] == "z"
    assert dict(BlockState("minecraft:oak_log", (("axis", "y"),)).rotate_y(1).properties)["axis"] == "y"
    assert dict(BlockState("minecraft:rail", (("shape", "north_south"),)).rotate_y(1).properties)["shape"] == "east_west"


def test_mirror_maps_rail_curve_and_validates_directional_connections() -> None:
    rail = BlockState.parse("minecraft:rail[shape=north_east]")
    connections = BlockState.parse("minecraft:iron_bars[east=true,north=low]")

    assert dict(rail.mirror("x").properties)["shape"] == "north_west"
    assert dict(connections.mirror("x").properties) == {"north": "low", "west": "true"}


@pytest.mark.parametrize(
    ("state_text", "operation"),
    (
        ("minecraft:oak_stairs[facing=sideways]", "rotate"),
        ("minecraft:oak_stairs[facing=sideways]", "mirror"),
        ("minecraft:oak_log[axis=diagonal]", "rotate"),
        ("minecraft:oak_log[axis=diagonal]", "mirror"),
        ("minecraft:player_head[rotation=16]", "rotate"),
        ("minecraft:player_head[rotation=16]", "mirror"),
        ("minecraft:crafter[orientation=up_north_east]", "rotate"),
        ("minecraft:crafter[orientation=up_north_east]", "mirror"),
        ("minecraft:oak_stairs[shape=diagonal]", "rotate"),
        ("minecraft:oak_stairs[shape=diagonal]", "mirror"),
        ("minecraft:oak_door[hinge=center]", "mirror"),
        ("minecraft:iron_bars[north=diagonal]", "rotate"),
        ("minecraft:iron_bars[north=diagonal]", "mirror"),
    ),
)
def test_unsupported_directional_states_are_rejected(state_text: str, operation: str) -> None:
    state = BlockState.parse(state_text)

    with pytest.raises(ValueError, match="unsupported"):
        state.rotate_y(1) if operation == "rotate" else state.mirror("x")
