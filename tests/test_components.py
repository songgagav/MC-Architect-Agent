from __future__ import annotations

import importlib

import pytest

from jiangnan_agent.core.block import BlockState
from jiangnan_agent.core.geometry import BoundingBox
from jiangnan_agent.generators.components import (
    generate_beam,
    generate_column,
    generate_door,
    generate_eaves,
    generate_gable_roof,
    generate_plinth,
    generate_wall,
    generate_window,
)


def test_column_is_vertical_and_sets_supported_wood_axis() -> None:
    model = generate_column(2, 3, -1, 3, "minecraft:stripped_spruce_log")

    assert set(model.blocks) == {(2, 3, -1), (2, 4, -1), (2, 5, -1)}
    assert {state.to_string() for state in model.blocks.values()} == {
        "minecraft:stripped_spruce_log[axis=y]"
    }


def test_beam_includes_endpoints_and_sets_horizontal_wood_axis() -> None:
    model = generate_beam((1, 7, 3), (4, 7, 3), "minecraft:stripped_spruce_log")

    assert set(model.blocks) == {(1, 7, 3), (2, 7, 3), (3, 7, 3), (4, 7, 3)}
    assert {state.to_string() for state in model.blocks.values()} == {
        "minecraft:stripped_spruce_log[axis=x]"
    }


def test_beam_rejects_diagonal_endpoints() -> None:
    with pytest.raises(ValueError, match="axis-aligned"):
        generate_beam((0, 0, 0), (2, 1, 0), "minecraft:stone")


def test_wall_preserves_only_the_requested_bounded_opening() -> None:
    bounds = BoundingBox(0, 0, 0, 5, 4, 1)
    opening = BoundingBox(2, 1, 0, 3, 3, 1)

    wall = generate_wall(bounds, "minecraft:calcite", openings=(opening,))

    assert len(wall.blocks) == 18
    assert wall.block_at((2, 1, 0)) == BlockState.parse("minecraft:air")
    assert wall.block_at((2, 2, 0)) == BlockState.parse("minecraft:air")
    assert wall.block_at((2, 0, 0)) == BlockState.parse("minecraft:calcite")


def test_wall_rejects_opening_outside_its_bounds() -> None:
    with pytest.raises(ValueError, match="within wall bounds"):
        generate_wall(
            BoundingBox(0, 0, 0, 3, 3, 1),
            "minecraft:calcite",
            openings=(BoundingBox(2, 2, 0, 4, 4, 1),),
        )


def test_plinth_fills_the_half_open_volume() -> None:
    plinth = generate_plinth(BoundingBox(-1, 0, 2, 2, 2, 4), "minecraft:smooth_stone")

    assert len(plinth.blocks) == 12
    assert plinth.block_at((-1, 0, 2)).block_id == "minecraft:smooth_stone"
    assert plinth.block_at((2, 1, 3)).block_id == "minecraft:air"


def test_double_door_has_valid_halves_facing_and_hinges() -> None:
    door = generate_door(4, 10, 6, 2, "minecraft:spruce_door", facing="south")

    assert door.block_at((4, 10, 6)).to_string() == (
        "minecraft:spruce_door[facing=south,half=lower,hinge=left,open=false,powered=false]"
    )
    assert door.block_at((5, 10, 6)).to_string() == (
        "minecraft:spruce_door[facing=south,half=lower,hinge=right,open=false,powered=false]"
    )
    assert door.block_at((4, 11, 6)).to_string().endswith("half=upper,hinge=left,open=false,powered=false]")
    assert door.block_at((5, 11, 6)).to_string().endswith("half=upper,hinge=right,open=false,powered=false]")


@pytest.mark.parametrize("width", [0, 3, 1.0])
def test_door_rejects_unsupported_width(width: int) -> None:
    with pytest.raises(ValueError, match="width must be 1 or 2"):
        generate_door(0, 0, 0, width, "minecraft:spruce_door")


def test_window_panes_store_connections_and_waterlogging() -> None:
    window = generate_window(
        0,
        4,
        0,
        2,
        2,
        "minecraft:white_stained_glass_pane",
        connected_faces=("north",),
    )

    left = dict(window.block_at((0, 4, 0)).properties)
    right = dict(window.block_at((1, 4, 0)).properties)
    assert len(window.blocks) == 4
    assert left == {"east": "true", "north": "true", "south": "false", "waterlogged": "false", "west": "false"}
    assert right["west"] == "true"
    assert right["north"] == "true"


def test_eaves_extend_an_axis_aligned_run_by_the_requested_overhang() -> None:
    eaves = generate_eaves(
        (0, 8, 2),
        (4, 8, 2),
        "minecraft:deepslate_tile_slab[type=bottom,waterlogged=false]",
        overhang=1,
    )

    assert set(eaves.blocks) == {(x, 8, 2) for x in range(-1, 6)}


def test_gable_roof_creates_symmetric_stair_rows_with_no_gaps() -> None:
    roof = generate_gable_roof(3, 5, 10, 2, 1, "minecraft:stone_brick_stairs")

    assert len(roof.blocks) == 35
    for z in range(-1, 6):
        y_values = {y for x, y, row_z in roof.blocks if row_z == z}
        assert len(y_values) == 1
        assert len([x for x, _y, row_z in roof.blocks if row_z == z]) == 5
    assert roof.block_at((0, 11, 1)).to_string() == (
        "minecraft:stone_brick_stairs[facing=south,half=bottom,shape=straight,waterlogged=false]"
    )
    assert roof.block_at((0, 11, 3)).to_string() == (
        "minecraft:stone_brick_stairs[facing=north,half=bottom,shape=straight,waterlogged=false]"
    )


def test_roof_rejects_even_depth_excessive_rise_and_non_stair_material() -> None:
    with pytest.raises(ValueError, match="odd and at least 3"):
        generate_gable_roof(5, 4, 0, 1, 0, "minecraft:stone_brick_stairs")
    with pytest.raises(ValueError, match="roof rise"):
        generate_gable_roof(5, 5, 0, 3, 0, "minecraft:stone_brick_stairs")
    with pytest.raises(ValueError, match="stair block"):
        generate_gable_roof(5, 5, 0, 1, 0, "minecraft:stone")


def test_components_module_exposes_the_profile_roof_surface_builder() -> None:
    components = importlib.import_module("jiangnan_agent.generators.components")

    assert callable(getattr(components, "generate_roof_surface", None))
