from __future__ import annotations

import pytest

from jiangnan_agent.assembly.adapters import corridor_module, hall_module
from jiangnan_agent.assembly.model import Assembly, Connection, ConnectionAnchor, Module
from jiangnan_agent.assembly.transforms import mirror_module, rotate_module, translate_module
from jiangnan_agent.assembly.validation import validate_assembly
from jiangnan_agent.core.scene import VoxelModel
from jiangnan_agent.generators.hall import CorridorParameters, HallParameters
from jiangnan_agent.io.project_editor import ProjectEditor
from jiangnan_agent.io.project_json import JiangnanProject, load_project, save_project


def make_project() -> JiangnanProject:
    hall = hall_module("hall-1", HallParameters(bay_count=3), through_passage=True)
    corridor = corridor_module("corridor-1", CorridorParameters(length=7, width=3))
    return JiangnanProject(name="Editable courtyard", assembly=Assembly((hall, corridor)))


def test_regeneration_changes_only_the_selected_module_and_records_delta() -> None:
    project = make_project()
    untouched = project.assembly.modules["corridor-1"]
    untouched_blocks = dict(untouched.model.blocks)

    revision = ProjectEditor(project).regenerate_module("hall-1", {"bay_count": 5}, "Widen front hall")

    assert project.assembly.modules["hall-1"].module_id == "hall-1"
    assert project.assembly.modules["hall-1"].parameters["bay_count"] == 5
    assert project.assembly.modules["corridor-1"] is untouched
    assert untouched.model.blocks == untouched_blocks
    assert revision.changed_module_ids == ("hall-1",)
    assert revision.block_changes
    assert revision.parent_revision_id == 0


def test_regeneration_replays_module_placement_transforms() -> None:
    source = hall_module("hall-1", HallParameters(bay_count=3), through_passage=True)
    placed = mirror_module(rotate_module(translate_module(source, (11, 2, -7)), 1), "z")
    project = JiangnanProject(name="Transformed hall", assembly=Assembly((placed,)))
    editor = ProjectEditor(project)

    editor.regenerate_module("hall-1", {"column_height": 5}, "Raise hall")

    expected = hall_module("hall-1", HallParameters(bay_count=3, column_height=5), through_passage=True)
    expected = mirror_module(rotate_module(translate_module(expected, (11, 2, -7)), 1), "z")
    actual = project.assembly.modules["hall-1"]
    assert actual.model.blocks == expected.model.blocks
    assert actual.anchors == expected.anchors
    assert actual.transform_steps == expected.transform_steps


def test_undo_and_redo_survive_save_and_reload(tmp_path) -> None:
    project = make_project()
    path = tmp_path / "editable.jap.json"
    editor = ProjectEditor(project)
    editor.regenerate_module("hall-1", {"bay_count": 5}, "Widen hall")
    save_project(project, path)

    reopened = load_project(path)
    reopened_editor = ProjectEditor(reopened)
    assert reopened_editor.can_undo
    assert reopened_editor.undo() is True
    assert reopened.assembly.modules["hall-1"].parameters["bay_count"] == 3
    save_project(reopened, path)

    reopened_again = load_project(path)
    redo_editor = ProjectEditor(reopened_again)
    assert redo_editor.can_redo
    assert redo_editor.redo() is True
    assert reopened_again.assembly.modules["hall-1"].parameters["bay_count"] == 5


def test_edit_after_undo_discards_redo_branch() -> None:
    project = make_project()
    editor = ProjectEditor(project)
    editor.regenerate_module("hall-1", {"bay_count": 5}, "First edit")
    assert editor.undo() is True

    editor.regenerate_module("hall-1", {"bay_count": 7}, "Replacement edit")

    assert project.assembly.modules["hall-1"].parameters["bay_count"] == 7
    assert editor.can_redo is False
    assert [revision.revision_id for revision in project.revision_history] == [0, 1]
    assert project.revision_history[-1].parent_revision_id == 0
    assert project.revision_history[-1].message == "Replacement edit"


def test_size_change_keeps_connection_and_validation_reports_misalignment() -> None:
    hall = hall_module("hall-1", HallParameters(bay_count=3), through_passage=True)
    rear = hall.anchor("rear")
    opposite = {"north": "south", "east": "west", "south": "north", "west": "east"}
    peer = Module(
        "peer-1",
        "peer",
        VoxelModel(),
        anchors=(ConnectionAnchor("front", rear.position, opposite[rear.facing], "passage", rear.width, rear.height),),
    )
    connection = Connection("hall-1", "rear", "peer-1", "front")
    project = JiangnanProject(name="Connected hall", assembly=Assembly((hall, peer), (connection,)))
    assert not [issue for issue in validate_assembly(project.assembly) if issue.code == "anchor_misalignment"]

    ProjectEditor(project).regenerate_module("hall-1", {"bay_count": 5}, "Widen connected hall")

    assert project.assembly.connections == (connection,)
    assert any(issue.code == "anchor_misalignment" for issue in validate_assembly(project.assembly))


def test_replacing_module_keeps_its_id_and_reports_block_changes() -> None:
    project = make_project()
    untouched = project.assembly.modules["corridor-1"]
    replacement_model = VoxelModel()
    replacement_model.set_block((0, 0, 0), "minecraft:gold_block")
    replacement = Module("hall-1", "hall", replacement_model, parameters={"custom": True})

    revision = ProjectEditor(project).replace_module("hall-1", replacement, "Replace hall")

    assert project.assembly.modules["hall-1"].model.block_at((0, 0, 0)).block_id == "minecraft:gold_block"
    assert project.assembly.modules["corridor-1"] is untouched
    assert revision.changed_module_ids == ("hall-1",)
    assert revision.block_changes


def test_edit_rejects_unrecorded_mutation_in_another_module() -> None:
    project = make_project()
    editor = ProjectEditor(project)
    project.assembly.modules["corridor-1"].model.set_block((0, 0, 0), "minecraft:gold_block")

    with pytest.raises(ValueError, match="revision snapshot"):
        editor.regenerate_module("hall-1", {"bay_count": 5}, "Widen hall")

    assert len(project.revision_history) == 1
    assert project.revision_history[0].changed_module_ids == ()
    assert project.assembly.modules["corridor-1"].model.block_at((0, 0, 0)).block_id == "minecraft:gold_block"


def test_undo_rejects_unrecorded_live_model_mutation() -> None:
    project = make_project()
    editor = ProjectEditor(project)
    editor.regenerate_module("hall-1", {"bay_count": 5}, "Widen hall")
    project.assembly.modules["corridor-1"].model.set_block((0, 0, 0), "minecraft:gold_block")

    with pytest.raises(ValueError, match="revision snapshot"):
        editor.undo()

    assert project.revision_cursor == 1
    assert project.assembly.modules["corridor-1"].model.block_at((0, 0, 0)).block_id == "minecraft:gold_block"
