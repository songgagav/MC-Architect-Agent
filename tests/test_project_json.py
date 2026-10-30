from __future__ import annotations

import pytest

from jiangnan_agent.assembly.model import Assembly, ClearanceZone, Connection, ConnectionAnchor, Module
from jiangnan_agent.core.geometry import BoundingBox
from jiangnan_agent.core.scene import VoxelModel
from jiangnan_agent.io.assembly_json import assembly_from_dict, assembly_to_dict
from jiangnan_agent.io.project_history import ProjectRevision
from jiangnan_agent.io.project_json import JiangnanProject, load_project, save_project


def test_project_save_and_load_preserves_modules_and_settings(tmp_path) -> None:
    project = JiangnanProject(
        name="苏州厅堂",
        project_id="fixed-project-id",
        modules=[{"id": "hall-1", "custom_extension": {"keep": True}}],
        settings={"seed": 17, "building": {"width": 9}},
        assembly=make_persistable_assembly(),
    )
    path = tmp_path / "workspace" / "hall.jap.json"

    save_project(project, path)
    loaded = load_project(path)

    assert loaded.to_dict() == project.to_dict()
    assert loaded.assembly.modules["hall-1"].model.block_at((-4, 2, 9)).block_id == "minecraft:oak_stairs"
    assert loaded.revision_cursor == 0
    assert len(loaded.revision_history) == 1


def test_project_rejects_unknown_format_version() -> None:
    with pytest.raises(ValueError, match="unsupported project format"):
        JiangnanProject.from_dict({"name": "bad", "format_version": 7})


def make_persistable_assembly() -> Assembly:
    hall_model = VoxelModel()
    hall_model.set_block((-4, 2, 9), "minecraft:oak_stairs[facing=east,shape=outer_left,half=top]")
    hall_model.set_block((-3, 2, 9), "minecraft:spruce_door[facing=south,half=upper,hinge=left,open=false,powered=false]")
    hall = Module(
        "hall-1",
        "hall",
        hall_model,
        anchors=(ConnectionAnchor("rear", (-2, 1, 9), "south", "passage", 2, 3),),
        clearance_zones=(ClearanceZone("eaves", BoundingBox(-5, 5, 8, 1, 7, 12), "roof"),),
        parameters={"bay_count": 3, "materials": {"roof": "minecraft:stone"}},
        transform_steps=({"op": "translate", "offset": (-4, 1, 9)}, {"op": "rotate_y", "quarter_turns": 1}),
    )
    corridor = Module(
        "corridor-1",
        "corridor",
        VoxelModel(),
        anchors=(ConnectionAnchor("start", (-2, 1, 9), "north", "passage", 2, 3),),
    )
    return Assembly((corridor, hall), (Connection("hall-1", "rear", "corridor-1", "start"),))


def test_assembly_round_trip_preserves_blocks_metadata_and_connections() -> None:
    source = make_persistable_assembly()

    restored = assembly_from_dict(assembly_to_dict(source))

    assert restored.modules["hall-1"].model.blocks == source.modules["hall-1"].model.blocks
    assert restored.modules["hall-1"].parameters == source.modules["hall-1"].parameters
    assert restored.modules["hall-1"].anchors == source.modules["hall-1"].anchors
    assert restored.modules["hall-1"].clearance_zones == source.modules["hall-1"].clearance_zones
    assert restored.modules["hall-1"].transform_steps == source.modules["hall-1"].transform_steps
    assert restored.modules["corridor-1"].model.blocks == {}
    assert restored.connections == source.connections


def test_assembly_json_uses_stable_module_and_block_order() -> None:
    first = make_persistable_assembly()
    second = Assembly(reversed(tuple(first.modules.values())), reversed(first.connections))

    assert assembly_to_dict(first) == assembly_to_dict(second)


def test_project_format_one_migrates_without_losing_existing_fields() -> None:
    legacy = JiangnanProject.from_dict(
        {
            "format_version": 1,
            "project_id": "legacy-id",
            "name": "Legacy Hall",
            "minecraft_version": "1.21.5",
            "data_version": 4325,
            "modules": [{"id": "hall-legacy", "custom": {"preserve": True}}],
            "settings": {"seed": 23},
        }
    )

    assert legacy.format_version == 2
    assert legacy.modules == [{"id": "hall-legacy", "custom": {"preserve": True}}]
    assert legacy.settings == {"seed": 23}
    assert legacy.assembly.modules == {}
    assert JiangnanProject.from_dict(legacy.to_dict()).to_dict() == legacy.to_dict()


def test_project_format_two_rejects_malformed_assembly() -> None:
    with pytest.raises(ValueError, match="assembly"):
        JiangnanProject.from_dict({"name": "bad", "format_version": 2, "assembly": {"modules": "invalid"}})


@pytest.mark.parametrize("version", [True, 1.9, 2.9, "1", float("nan"), float("inf")])
def test_project_rejects_non_integer_format_versions(version) -> None:
    with pytest.raises(ValueError, match="format version"):
        JiangnanProject.from_dict(
            {
                "name": "Malformed version",
                "format_version": version,
                "assembly": assembly_to_dict(make_persistable_assembly()),
            }
        )


def test_project_save_and_load_preserves_revision_history_and_cursor(tmp_path) -> None:
    initial = make_persistable_assembly()
    changed_model = VoxelModel()
    changed_model.set_block((-4, 2, 9), "minecraft:oak_stairs[facing=east,shape=outer_left,half=top]")
    changed_model.set_block((-3, 2, 9), "minecraft:spruce_door[facing=south,half=upper,hinge=left,open=false,powered=false]")
    changed_model.set_block((0, 0, 0), "minecraft:stone")
    changed_hall = Module("hall-1", "hall", changed_model)
    changed = Assembly((changed_hall, initial.modules["corridor-1"]), initial.connections)
    base_revision = ProjectRevision.create(0, None, "Initial", (), initial)
    edited_revision = ProjectRevision.create(1, 0, "Add a block", ("hall-1",), changed)
    project = JiangnanProject(
        name="History project",
        assembly=changed,
        revision_history=[base_revision, edited_revision],
        revision_cursor=1,
    )
    path = tmp_path / "history.jap.json"

    save_project(project, path)
    loaded = load_project(path)

    assert loaded.to_dict() == project.to_dict()
    assert loaded.revision_history[0].restore_assembly().modules["hall-1"].model.blocks == initial.modules["hall-1"].model.blocks
