from __future__ import annotations

from pathlib import Path

import pytest

from examples.gen3_facade_examples import build_gen3_facade_examples
from jiangnan_agent.io.project_json import load_project
from jiangnan_agent.io.schematic import read_schematic


def _normalized_blocks(model, bounds):
    return {
        (position[0] - bounds.min_x, position[1] - bounds.min_y, position[2] - bounds.min_z): state
        for position, state in model.blocks.items()
    }


def test_gen3_examples_build_projects_with_three_presets_roofs_and_roundtrip_schematics(tmp_path: Path) -> None:
    examples = build_gen3_facade_examples(tmp_path, run_id="test-run")

    assert {item.preset_id for item in examples} == {
        "jiangnan_whitewall_timber",
        "huizhou_graybrick_entry",
        "garden_open_gallery",
    }
    assert {item.roof_preset_id for item in examples} == {
        "jiangnan_dark_tile",
        "gray_brick_layered",
        "warm_spruce_garden",
    }
    assert {item.bay_count for item in examples} == {3, 5}
    for item in examples:
        project = load_project(item.project_path)
        module = project.assembly.modules[item.module_id]
        document = read_schematic(item.schematic_path)
        profile = module.parameters["facade_profile"]
        assert module.parameters["facade_profile"]["profile_id"] == item.preset_id
        primary = next(
            opening for opening in profile["openings"]
            if opening["connection_use"] == "primary_entry"
        )
        front_windows = sorted(
            opening["segment_index"]
            for opening in profile["openings"]
            if opening["face"] == "front" and opening["kind"] == "window"
        )
        assert primary["segment_index"] == item.bay_count // 2
        if item.bay_count == 5:
            assert front_windows == [1, 3]
        if item.preset_id == "garden_open_gallery":
            assert profile["window"]["width"] == 3
            assert profile["window"]["height"] == 2
            assert profile["window"]["lattice_style"] == "vertical"
            assert {opening["face"] for opening in profile["openings"]} == {"front"}
            assert any(state.block_id == "minecraft:glass_pane" for state in module.model.blocks.values())
        assert document.name == project.name
        assert document.data_version == 4325
        assert document.model.blocks == _normalized_blocks(module.model, module.model.bounds)
        assert item.block_count == len(module.model.blocks)


def test_gen3_example_run_refuses_to_overwrite_an_existing_run(tmp_path: Path) -> None:
    build_gen3_facade_examples(tmp_path, run_id="fixed-run")

    with pytest.raises(FileExistsError):
        build_gen3_facade_examples(tmp_path, run_id="fixed-run")
