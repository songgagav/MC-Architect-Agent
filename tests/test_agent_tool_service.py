from __future__ import annotations

import json
from pathlib import Path

import pytest

from jiangnan_agent.assembly.model import Assembly, Module
from jiangnan_agent.core.scene import VoxelModel
from jiangnan_agent.io.project_generation import generate_project_model
from jiangnan_agent.io.project_json import JiangnanProject, load_project, save_project
from jiangnan_agent.io.schematic import read_schematic
from jiangnan_agent.agent_tools.service import ProjectToolService


def make_service(tmp_path: Path) -> ProjectToolService:
    return ProjectToolService(tmp_path)


def test_project_and_module_discovery_create_a_three_bay_hall(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    project = service.create_project("三开间江南民居", "residence.jap.json")

    assert project["project_path"] == "residence.jap.json"
    assert project["module_count"] == 0
    assert service.list_projects()[0]["project_id"] == project["project_id"]
    created = service.create_module("residence.jap.json", "hall-main", "hall", {"bay_count": 3})

    assert created["operation"] == "create_module"
    assert created["revision_id"] == 1
    assert created["affected_module_ids"] == ["hall-main"]
    module = service.get_module("residence.jap.json", "hall-main")
    assert module["parameters"]["bay_count"] == 3
    assert module["block_count"] > 0
    assert service.list_modules("residence.jap.json")[0]["module_id"] == "hall-main"
    assert service.get_project("residence.jap.json")["module_count"] == 1
    json.dumps([project, created, module, service.list_modules("residence.jap.json")])


def test_parameter_edits_are_saved_by_stable_id_and_revision_summaries_are_bounded(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    service.create_project("Residence", "residence.json")
    service.create_module("residence.json", "hall-main", "hall", {"bay_count": 3})

    result = service.set_parameters("residence.json", "hall-main", {"bay_count": 5})
    project_path = tmp_path / "workspace" / "projects" / "residence.json"
    loaded = load_project(project_path)
    inspection = service.inspect_changes("residence.json", result["revision_id"], limit=2)

    assert loaded.assembly.modules["hall-main"].parameters["bay_count"] == 5
    assert result["affected_module_ids"] == ["hall-main"]
    assert inspection["revision_id"] == result["revision_id"]
    assert inspection["block_change_count"] > 2
    assert len(inspection["block_changes"]) == 2
    assert inspection["truncated"] is True


def test_invalid_tool_edit_leaves_project_and_history_unchanged(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    service.create_project("Residence", "residence.json")
    service.create_module("residence.json", "hall-main", "hall", {"bay_count": 3})
    project_path = tmp_path / "workspace" / "projects" / "residence.json"
    original_bytes = project_path.read_bytes()

    with pytest.raises(ValueError):
        service.set_parameters("residence.json", "hall-main", {"bay_count": 4})

    assert project_path.read_bytes() == original_bytes
    assert len(load_project(project_path).revision_history) == 2


def test_replace_module_keeps_its_transform_and_records_the_replacement(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    service.create_project("Residence", "residence.json")
    service.create_module("residence.json", "hall-main", "hall", {"bay_count": 3})
    service.transform_module("residence.json", "hall-main", "translate", offset=[20, 0, 4])

    replaced = service.replace_module("residence.json", "hall-main", "hall", {"bay_count": 5})
    module = service.get_module("residence.json", "hall-main")
    loaded = load_project(tmp_path / "workspace" / "projects" / "residence.json")

    assert replaced["revision_id"] == 3
    assert module["parameters"]["bay_count"] == 5
    assert module["bounds"]["minimum"][0] >= 19
    assert module["bounds"]["minimum"][2] >= 3
    assert module["transform_steps"][-1] == {"op": "translate", "offset": [20, 0, 4]}
    assert loaded.revision_history[-1].message == "Replace module hall-main with hall"


def test_tool_service_transforms_and_connects_existing_modules(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    service.create_project("Corridor pair", "corridors.json")
    parameters = {"length": 9, "width": 5, "passage_width": 2}
    service.create_module("corridors.json", "corridor-west", "corridor", parameters)
    service.create_module("corridors.json", "corridor-east", "corridor", parameters)

    west_anchors = {
        anchor["name"]: anchor["position"]
        for anchor in service.get_module("corridors.json", "corridor-west")["anchors"]
    }
    east_anchors = {
        anchor["name"]: anchor["position"]
        for anchor in service.get_module("corridors.json", "corridor-east")["anchors"]
    }
    west_end = west_anchors["end"]
    east_start = east_anchors["start"]
    offset = [left - right for left, right in zip(west_end, east_start)]
    moved = service.transform_module("corridors.json", "corridor-east", "translate", offset=offset)
    connected = service.connect_modules(
        "corridors.json", "corridor-west", "end", "corridor-east", "start"
    )
    loaded = load_project(tmp_path / "workspace" / "projects" / "corridors.json")

    assert moved["revision_id"] == 3
    assert connected["revision_id"] == 4
    assert connected["connection_count"] == 1
    assert loaded.assembly.modules["corridor-east"].transform_steps[-1]["op"] == "translate"
    assert connected["affected_module_ids"] == ["corridor-east", "corridor-west"]


def test_create_module_can_attach_to_a_named_anchor(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    service.create_project("Hall and corridor", "hall-corridor.json")
    service.create_module("hall-corridor.json", "hall-main", "hall", {"bay_count": 3})

    attached = service.create_module(
        "hall-corridor.json",
        "corridor-front",
        "corridor",
        {"length": 9, "width": 5, "passage_width": 2},
        attach_to_module_id="hall-main",
        attach_to_anchor_name="front",
        module_anchor_name="start",
    )
    project = load_project(tmp_path / "workspace" / "projects" / "hall-corridor.json")

    assert attached["revision_id"] == 2
    assert attached["connection_count"] == 1
    assert set(project.assembly.modules) == {"hall-main", "corridor-front"}


def test_validation_and_schematic_export_roundtrip(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    service.create_project("Residence", "residence.json")
    service.create_module("residence.json", "hall-main", "hall", {"bay_count": 3})

    validation = service.validate_assembly("residence.json")
    exported = service.export_schematic("residence.json", "hall-main.schem")
    project = load_project(tmp_path / "workspace" / "projects" / "residence.json")
    source_model = generate_project_model(project)
    schematic = read_schematic(tmp_path / "workspace" / "exports" / "hall-main.schem")
    expected_offset = (source_model.bounds.min_x, source_model.bounds.min_y, source_model.bounds.min_z)
    expected_local_blocks = {
        (x - expected_offset[0], y - expected_offset[1], z - expected_offset[2]): state
        for (x, y, z), state in source_model.blocks.items()
    }

    assert validation["valid"] is True
    assert validation["issues"] == []
    assert exported["block_count"] == len(schematic.model.blocks)
    assert exported["dimensions"] == list(schematic.model.bounds.size)
    assert schematic.offset == expected_offset
    assert schematic.model.blocks == expected_local_blocks
    assert exported["offset"] == list(expected_offset)


def test_create_and_export_refuse_existing_files(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    service.create_project("Residence", "residence.json")
    service.create_module("residence.json", "hall-main", "hall", {"bay_count": 3})
    project_path = tmp_path / "workspace" / "projects" / "residence.json"
    original_project = project_path.read_bytes()
    export_path = tmp_path / "workspace" / "exports" / "existing.schem"
    export_path.parent.mkdir(parents=True)
    export_path.write_bytes(b"keep this export")

    with pytest.raises(ValueError, match="already exists"):
        service.create_project("Overwrite", "residence.json")
    with pytest.raises(ValueError, match="already exists"):
        service.export_schematic("residence.json", "existing.schem")

    assert project_path.read_bytes() == original_project
    assert export_path.read_bytes() == b"keep this export"


def test_export_schematic_does_not_fallback_from_invalid_assembly(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    project_dir = tmp_path / "workspace" / "projects"
    project_dir.mkdir(parents=True)
    first = VoxelModel()
    first.set_block((0, 0, 0), "minecraft:stone")
    second = VoxelModel()
    second.set_block((0, 0, 0), "minecraft:dirt")
    project = JiangnanProject(
        name="Invalid but has legacy settings",
        settings={"building": {"type": "simple_house", "width": 7, "length": 9}},
        assembly=Assembly((Module("first", "part", first), Module("second", "part", second))),
    )
    save_project(project, project_dir / "invalid.json")

    with pytest.raises(ValueError, match="assembly validation failed"):
        service.export_schematic("invalid.json", "invalid.schem")

    assert not (tmp_path / "workspace" / "exports" / "invalid.schem").exists()
