from __future__ import annotations

import pytest

from jiangnan_agent.assembly.model import Assembly, Module
from jiangnan_agent.core.scene import VoxelModel
from jiangnan_agent.io.project_history import BlockChange, ProjectRevision, diff_assemblies


def make_assembly(entries: dict[str, dict[tuple[int, int, int], str]]) -> Assembly:
    modules = []
    for module_id, blocks in entries.items():
        model = VoxelModel()
        for position, state in blocks.items():
            model.set_block(position, state)
        modules.append(Module(module_id, "room", model))
    return Assembly(modules)


def test_diff_reports_added_removed_and_changed_block_states() -> None:
    before = make_assembly(
        {
            "hall": {(0, 0, 0): "minecraft:stone", (1, 0, 0): "minecraft:dirt"},
            "removed": {(5, 0, 0): "minecraft:oak_planks"},
        }
    )
    after = make_assembly(
        {
            "hall": {(0, 0, 0): "minecraft:stone", (1, 0, 0): "minecraft:gold_block", (2, 0, 0): "minecraft:glass"},
            "added": {(7, 0, 0): "minecraft:brick"},
        }
    )

    module_ids, changes = diff_assemblies(before, after)

    assert module_ids == ("added", "hall", "removed")
    assert changes == (
        BlockChange("added", (7, 0, 0), None, "minecraft:brick"),
        BlockChange("hall", (1, 0, 0), "minecraft:dirt", "minecraft:gold_block"),
        BlockChange("hall", (2, 0, 0), None, "minecraft:glass"),
        BlockChange("removed", (5, 0, 0), "minecraft:oak_planks", None),
    )


def test_revision_snapshot_does_not_follow_later_model_mutation() -> None:
    assembly = make_assembly({"hall": {(0, 0, 0): "minecraft:stone"}})

    revision = ProjectRevision.create(0, None, "Initial", (), assembly)
    assembly.modules["hall"].model.set_block((0, 0, 0), "minecraft:dirt")

    restored = revision.restore_assembly()
    assert restored.modules["hall"].model.block_at((0, 0, 0)).block_id == "minecraft:stone"


def test_project_revision_round_trip_preserves_snapshot_and_change_log() -> None:
    assembly = make_assembly({"hall": {(0, 0, 0): "minecraft:stone"}})
    revision = ProjectRevision.create(
        3,
        2,
        "Replace roof",
        ("hall",),
        assembly,
        block_changes=(BlockChange("hall", (2, 4, 0), "minecraft:oak_stairs", "minecraft:stone_stairs"),),
        created_at="2026-10-29T00:00:00+00:00",
    )

    restored = ProjectRevision.from_dict(revision.to_dict())

    assert restored.to_dict() == revision.to_dict()
    assert restored.restore_assembly().modules["hall"].model.blocks == assembly.modules["hall"].model.blocks


def test_revision_rejects_malformed_change_metadata_as_value_error() -> None:
    assembly = make_assembly({})

    with pytest.raises(ValueError, match="changed_module_ids"):
        ProjectRevision.create(1, 0, "Bad metadata", ("hall", None), assembly)  # type: ignore[arg-type]
