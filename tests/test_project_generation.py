from __future__ import annotations

import pytest

from jiangnan_agent.assembly.adapters import hall_module
from jiangnan_agent.assembly.model import Assembly, Module
from jiangnan_agent.assembly.validation import render_assembly
from jiangnan_agent.core.scene import VoxelModel
from jiangnan_agent.generators.simple_house import SimpleHouseConfig, generate_simple_house
from jiangnan_agent.io.project_generation import generate_project_model
from jiangnan_agent.io.project_json import JiangnanProject


def test_generate_project_model_uses_legacy_settings_for_empty_assembly() -> None:
    config = SimpleHouseConfig(width=7, length=9, wall_height=3)
    project = JiangnanProject(
        name="Legacy house",
        settings={"building": {"type": "simple_house", "width": 7, "length": 9, "wall_height": 3}},
    )

    assert generate_project_model(project).blocks == generate_simple_house(config).blocks


def test_generate_project_model_prefers_nonempty_assembly_over_legacy_settings() -> None:
    module = hall_module("hall-main")
    project = JiangnanProject(
        name="Assembly hall",
        settings={"building": {"type": "simple_house", "width": 7, "length": 9}},
        assembly=Assembly((module,)),
    )

    assert generate_project_model(project).blocks == render_assembly(project.assembly).blocks


def test_generate_project_model_does_not_fallback_when_assembly_is_invalid() -> None:
    first_model = VoxelModel()
    first_model.set_block((0, 0, 0), "minecraft:stone")
    second_model = VoxelModel()
    second_model.set_block((0, 0, 0), "minecraft:dirt")
    project = JiangnanProject(
        name="Invalid assembly",
        settings={"building": {"type": "simple_house", "width": 7, "length": 9}},
        assembly=Assembly((Module("first", "part", first_model), Module("second", "part", second_model))),
    )

    with pytest.raises(ValueError, match="assembly validation failed"):
        generate_project_model(project)
