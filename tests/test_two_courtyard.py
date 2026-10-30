from __future__ import annotations

from jiangnan_agent.assembly.operations import split_assembly
from jiangnan_agent.assembly.validation import render_assembly, validate_assembly
from jiangnan_agent.io.schematic import read_schematic, write_schematic
from examples.two_courtyard import build_two_courtyard, replace_corridor_roof


def test_two_courtyard_composes_generated_modules_and_roundtrips_schematic(tmp_path) -> None:
    assembly = build_two_courtyard()

    assert set(assembly.modules) == {
        "front_hall",
        "walk_front",
        "gate_hall",
        "walk_rear",
        "rear_hall",
        "front_court_west_wall",
        "front_court_east_wall",
        "rear_court_west_wall",
        "rear_court_east_wall",
    }
    assert len(assembly.connections) == 12
    assert len(split_assembly(assembly)) == 1
    assert validate_assembly(assembly) == ()

    rendered = render_assembly(assembly)
    repeated = render_assembly(build_two_courtyard())
    assert rendered.blocks == repeated.blocks

    path = tmp_path / "two-courtyard.schem"
    write_schematic(rendered, path, data_version=4325, name="Two Courtyard")
    loaded = read_schematic(path)
    assert loaded.data_version == 4325
    assert loaded.model.bounds.size == rendered.bounds.size
    assert len(loaded.model.blocks) == len(rendered.blocks)
    expected_local = rendered.translated(
        -rendered.bounds.min_x,
        -rendered.bounds.min_y,
        -rendered.bounds.min_z,
    )
    assert loaded.offset == (rendered.bounds.min_x, rendered.bounds.min_y, rendered.bounds.min_z)
    assert loaded.model.blocks == expected_local.blocks


def test_replacing_one_corridor_roof_preserves_every_other_module() -> None:
    assembly = build_two_courtyard()
    untouched = {module_id: module for module_id, module in assembly.modules.items() if module_id != "walk_front"}
    old_roof = {
        position: state
        for position, state in assembly.modules["walk_front"].model.blocks.items()
        if state.block_id.endswith("_stairs")
    }

    updated = replace_corridor_roof(assembly, "walk_front", "minecraft:spruce_stairs")

    assert validate_assembly(updated) == ()
    assert all(updated.modules[module_id] is module for module_id, module in untouched.items())
    assert all(state.block_id == "minecraft:polished_deepslate_stairs" for state in old_roof.values())
    assert all(
        assembly.modules["walk_front"].model.blocks[position].block_id == "minecraft:polished_deepslate_stairs"
        for position in old_roof
    )
    assert all(
        updated.modules["walk_front"].model.blocks[position].block_id == "minecraft:spruce_stairs"
        for position in old_roof
    )
