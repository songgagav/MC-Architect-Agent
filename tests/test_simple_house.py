from __future__ import annotations

from jiangnan_agent.generators.simple_house import SimpleHouseConfig, generate_simple_house


def test_simple_house_generates_door_and_property_bearing_roof() -> None:
    model = generate_simple_house(SimpleHouseConfig(width=9, length=11, wall_height=4))

    assert model.block_at((4, 1, 10)).block_id == "minecraft:air"
    assert any(
        state.block_id == "minecraft:spruce_stairs" and "facing" in dict(state.properties)
        for state in model.blocks.values()
    )
    assert model.bounds.size[0] >= 9
