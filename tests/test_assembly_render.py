from __future__ import annotations

import pytest

from jiangnan_agent.assembly.model import Assembly, Module
from jiangnan_agent.assembly.validation import render_assembly
from jiangnan_agent.core.scene import VoxelModel


def module(module_id: str, position: tuple[int, int, int], block: str) -> Module:
    model = VoxelModel()
    model.set_block(position, block)
    return Module(module_id, "part", model)


def test_render_is_stable_and_does_not_mutate_module_models() -> None:
    early = module("a-part", (3, 0, 0), "minecraft:oak_planks")
    later = module("z-part", (0, 0, 0), "minecraft:stone")

    first = render_assembly(Assembly((later, early)))
    second = render_assembly(Assembly((early, later)))

    assert first.blocks == second.blocks
    assert tuple(first.blocks) == tuple(second.blocks)
    assert first.block_at((0, 0, 0)).block_id == "minecraft:stone"
    assert first.block_at((3, 0, 0)).block_id == "minecraft:oak_planks"
    assert len(later.model.blocks) == len(early.model.blocks) == 1


def test_render_rejects_conflicting_block_writes() -> None:
    assembly = Assembly(
        (
            module("stone", (1, 0, 0), "minecraft:stone"),
            module("wood", (1, 0, 0), "minecraft:oak_planks"),
        )
    )

    with pytest.raises(ValueError, match=r"conflicting blocks at \(1, 0, 0\)"):
        render_assembly(assembly)


def test_render_merges_identical_shared_blocks_deterministically() -> None:
    assembly = Assembly(
        (
            module("first", (0, 0, 0), "minecraft:stone"),
            module("second", (0, 0, 0), "minecraft:stone"),
        )
    )

    rendered = render_assembly(assembly)

    assert len(rendered.blocks) == 1
    assert rendered.block_at((0, 0, 0)).block_id == "minecraft:stone"
