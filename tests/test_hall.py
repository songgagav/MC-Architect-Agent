from __future__ import annotations

import pytest

from jiangnan_agent.core.block import BlockState
from jiangnan_agent.generators.hall import (
    CorridorParameters,
    HallParameters,
    generate_corridor,
    generate_hall,
)


def test_default_hall_is_three_bays_with_openings_and_connected_frame() -> None:
    model = generate_hall()

    assert model.bounds.size == (18, 10, 9)
    assert model.block_at((0, 1, 0)).to_string() == "minecraft:stripped_spruce_log[axis=y]"
    assert model.block_at((7, 5, 6)).to_string() == "minecraft:stripped_spruce_log[axis=x]"
    assert model.block_at((7, 2, 6)).to_string().startswith("minecraft:spruce_door[")
    assert dict(model.block_at((2, 3, 6)).properties)["north"] == "true"
    assert model.block_at((7, 2, 6)).block_id == "minecraft:spruce_door"


def test_five_bay_hall_expands_posts_and_is_deterministic() -> None:
    parameters = HallParameters(bay_count=5)

    first = generate_hall(parameters)
    second = generate_hall(parameters)

    assert first.bounds.size == (28, 10, 9)
    assert first.blocks == second.blocks
    for x in (0, 5, 10, 15, 20, 25):
        assert first.block_at((x, 1, 6)).block_id == "minecraft:stripped_spruce_log"
        assert first.block_at((x, 5, 6)).block_id == "minecraft:stripped_spruce_log"


def test_hall_material_overrides_apply_to_walls_and_roof() -> None:
    model = generate_hall(
        HallParameters(materials={"wall": "minecraft:white_terracotta", "roof": "minecraft:spruce_stairs"})
    )

    assert model.block_at((1, 2, 0)).block_id == "minecraft:white_terracotta"
    assert any(state.block_id == "minecraft:spruce_stairs" for state in model.blocks.values())


@pytest.mark.parametrize(
    "parameters",
    [
        {"bay_count": 2},
        {"bay_count": 3, "bay_width": 3},
        {"depth": 6},
        {"column_height": 2},
        {"plinth_height": 0},
        {"roof_rise": 4},
        {"eaves": -1},
        {"materials": {"unknown": "minecraft:stone"}},
        {"materials": {"roof": "minecraft:stone"}},
    ],
)
def test_hall_rejects_invalid_parameters(parameters: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        HallParameters(**parameters)


def test_corridor_has_repeated_two_sided_posts_and_continuous_roof() -> None:
    model = generate_corridor()

    assert model.bounds.size == (13, 7, 5)
    for x in (0, 3, 6, 9, 10):
        for z in (0, 2):
            assert model.block_at((x, 1, z)).to_string() == "minecraft:stripped_spruce_log[axis=y]"
            assert model.block_at((x, 4, z)).to_string() == "minecraft:stripped_spruce_log[axis=x]"
    assert all(model.block_at((x, 6, 1)).block_id == "minecraft:polished_deepslate_stairs" for x in range(11))


@pytest.mark.parametrize(
    "parameters",
    [
        {"length": 2},
        {"width": 4},
        {"column_spacing": 0},
        {"column_height": 1},
        {"roof_rise": 2},
        {"materials": {"wall": "minecraft:calcite"}},
    ],
)
def test_corridor_rejects_invalid_parameters(parameters: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        CorridorParameters(**parameters)


def test_hall_roof_and_door_states_survive_model_reads() -> None:
    model = generate_hall()

    assert dict(model.block_at((7, 2, 6)).properties) == {
        "facing": "south",
        "half": "lower",
        "hinge": "left",
        "open": "false",
        "powered": "false",
    }
    assert any(
        state == BlockState.parse(
            "minecraft:polished_deepslate_stairs[facing=north,half=bottom,shape=straight,waterlogged=false]"
        )
        for state in model.blocks.values()
    )
