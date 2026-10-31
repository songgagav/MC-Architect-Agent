from __future__ import annotations

from dataclasses import replace

import pytest

from jiangnan_agent.assembly.adapters import corridor_module, hall_module
from jiangnan_agent.assembly.model import Assembly, Connection, ConnectionAnchor, Module
from jiangnan_agent.assembly.transforms import mirror_module, rotate_module, translate_module
from jiangnan_agent.assembly.validation import validate_assembly
from jiangnan_agent.assets import module_from_asset
from jiangnan_agent.core.scene import VoxelModel
from jiangnan_agent.generators.facade_profiles import facade_profile_to_mapping
from jiangnan_agent.generators.hall import CorridorParameters, HallParameters
from jiangnan_agent.parameters import load_facade_preset
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


def test_profiled_project_edit_save_reload_undo_redo_preserves_openings_and_other_modules(tmp_path) -> None:
    profile = load_facade_preset("jiangnan_whitewall_timber")
    hall = module_from_asset("hall-main", "jiangnan.hall", {"facade_profile": facade_profile_to_mapping(profile)})
    corridor = module_from_asset("corridor-kept", "jiangnan.corridor", {"length": 9})
    project = JiangnanProject(name="Profiled hall", assembly=Assembly((hall, corridor)))
    untouched = project.assembly.modules["corridor-kept"]
    untouched_blocks = dict(untouched.model.blocks)
    editor = ProjectEditor(project)

    editor.regenerate_module("hall-main", {"bay_count": 5}, "Resize profiled hall")
    resized = project.assembly.modules["hall-main"]
    assert resized.parameters["facade_profile"]["profile_id"] == profile.profile_id
    assert [item["opening_id"] for item in resized.parameters["facade_profile"]["openings"]] == [
        item.opening_id for item in profile.openings
    ]
    assert project.assembly.modules["corridor-kept"] is untouched
    assert untouched.model.blocks == untouched_blocks

    updated_profile = replace(
        profile,
        window=replace(profile.window, lattice_style="vertical"),
        materials={**dict(profile.materials), "wall": "minecraft:white_terracotta"},
    )
    editor.regenerate_module(
        "hall-main",
        {"facade_profile": facade_profile_to_mapping(updated_profile)},
        "Change wall finish and window lattice",
    )
    edited_blocks = dict(project.assembly.modules["hall-main"].model.blocks)
    assert edited_blocks != dict(resized.model.blocks)
    assert project.assembly.modules["hall-main"].metadata["parameter_config"]["facade_profile"]["window"][
        "lattice_style"
    ] == "vertical"

    path = tmp_path / "profiled-hall.jap.json"
    save_project(project, path)
    reopened = load_project(path)
    reopened_module = reopened.assembly.modules["hall-main"]
    assert reopened_module.model.blocks == edited_blocks
    assert reopened_module.parameters["facade_profile"]["profile_id"] == profile.profile_id
    assert reopened.assembly.modules["corridor-kept"].model.blocks == untouched_blocks

    history = ProjectEditor(reopened)
    assert history.undo() is True
    assert reopened.assembly.modules["hall-main"].model.blocks == dict(resized.model.blocks)
    save_project(reopened, path)
    reopened_again = load_project(path)
    redo = ProjectEditor(reopened_again)
    assert redo.redo() is True
    assert reopened_again.assembly.modules["hall-main"].model.blocks == edited_blocks
    assert reopened_again.assembly.modules["hall-main"].parameters["facade_profile"]["window"][
        "lattice_style"
    ] == "vertical"


def test_legacy_v4_project_without_facade_profile_keeps_hash_after_edit(tmp_path) -> None:
    from test_roof_eaves_v2 import _canonical_hash

    hall = module_from_asset("hall-old", "jiangnan.hall", asset_version=4)
    project = JiangnanProject(name="Legacy façade-free hall", assembly=Assembly((hall,)))
    path = tmp_path / "legacy-hall.jap.json"
    save_project(project, path)
    reopened = load_project(path)
    assert "facade_profile" not in reopened.assembly.modules["hall-old"].parameters

    ProjectEditor(reopened).regenerate_module("hall-old", {"bay_count": 3}, "Keep the old hall")
    edited = reopened.assembly.modules["hall-old"]
    baseline = module_from_asset("hall-old-baseline", "jiangnan.hall", asset_version=4)
    assert _canonical_hash(edited.model) == _canonical_hash(baseline.model)


def test_add_module_records_block_delta_and_supports_undo_redo() -> None:
    project = JiangnanProject(name="New hall")
    editor = ProjectEditor(project)
    hall = hall_module("hall-main", HallParameters(bay_count=3))

    revision = editor.add_module(hall, "Create three-bay hall")

    assert set(project.assembly.modules) == {"hall-main"}
    assert revision.revision_id == 1
    assert revision.parent_revision_id == 0
    assert revision.changed_module_ids == ("hall-main",)
    assert len(revision.block_changes) == len(hall.model.blocks)
    assert all(change.module_id == "hall-main" and change.before_state is None for change in revision.block_changes)
    assert editor.undo() is True
    assert project.assembly.modules == {}
    assert editor.redo() is True
    assert project.assembly.modules["hall-main"].model.blocks == hall.model.blocks


def test_connect_new_module_records_aligned_module_and_connection() -> None:
    main_hall = hall_module("hall-main", HallParameters(bay_count=3))
    project = JiangnanProject(name="Connected halls", assembly=Assembly((main_hall,)))
    editor = ProjectEditor(project)
    side_hall = hall_module("hall-side", HallParameters(bay_count=3))

    revision = editor.connect_modules(
        "hall-main",
        "front",
        side_hall,
        "front",
        "Attach side hall",
    )

    placed = project.assembly.modules["hall-side"]
    first_anchor = project.assembly.modules["hall-main"].anchor("front")
    second_anchor = placed.anchor("front")
    opposite = {"north": "south", "east": "west", "south": "north", "west": "east"}
    assert second_anchor.position == first_anchor.position
    assert second_anchor.facing == opposite[first_anchor.facing]
    assert len(project.assembly.connections) == 1
    assert revision.changed_module_ids == ("hall-main", "hall-side")
    assert len(revision.block_changes) == len(placed.model.blocks)
    assert all(change.module_id == "hall-side" for change in revision.block_changes)

    assert editor.undo() is True
    assert set(project.assembly.modules) == {"hall-main"}
    assert project.assembly.connections == ()
    assert editor.redo() is True
    assert set(project.assembly.modules) == {"hall-main", "hall-side"}
    assert len(project.assembly.connections) == 1


def test_connect_new_module_only_marks_endpoints_of_the_new_connection() -> None:
    parameters = CorridorParameters(length=9, width=5)
    first = corridor_module("existing-a", parameters, passage_width=2)
    second = corridor_module("existing-b", parameters, passage_width=2)
    start = first.anchor("end").position
    end = second.anchor("start").position
    offset = tuple(left - right for left, right in zip(start, end))
    second = translate_module(second, offset)
    isolated = corridor_module("isolated", parameters, passage_width=2)
    project = JiangnanProject(name="Unrelated connections", assembly=Assembly((first, second, isolated)))
    editor = ProjectEditor(project)
    editor.connect_modules("existing-a", "end", "existing-b", "start", "Connect existing pair")

    attached = corridor_module("attached", parameters, passage_width=2)
    revision = editor.connect_modules("isolated", "end", attached, "start", "Attach new corridor")

    assert revision.changed_module_ids == ("attached", "isolated")
    assert {change.module_id for change in revision.block_changes} == {"attached"}


def test_transform_module_records_exact_delta() -> None:
    project = JiangnanProject(name="Move hall", assembly=Assembly((hall_module("hall-main"),)))
    editor = ProjectEditor(project)
    original = project.assembly.modules["hall-main"]
    original_blocks = dict(original.model.blocks)
    offset = (100, 2, -7)

    revision = editor.transform_module(
        "hall-main",
        "translate",
        "Move hall east",
        offset=offset,
    )

    moved = project.assembly.modules["hall-main"]
    expected_blocks = {
        (position[0] + offset[0], position[1] + offset[1], position[2] + offset[2]): state
        for position, state in original_blocks.items()
    }
    assert moved.model.blocks == expected_blocks
    assert moved.anchor("front").position == tuple(
        coordinate + delta for coordinate, delta in zip(original.anchor("front").position, offset)
    )
    assert moved.transform_steps[-1] == {"op": "translate", "offset": offset}
    assert revision.changed_module_ids == ("hall-main",)
    assert len(revision.block_changes) == 2 * len(original_blocks)
    removed = {change.position for change in revision.block_changes if change.after_state is None}
    added = {change.position for change in revision.block_changes if change.before_state is None}
    assert removed == set(original_blocks)
    assert added == set(expected_blocks)


@pytest.mark.parametrize(
    ("operation", "arguments", "expected_facing", "expected_step"),
    (
        ("rotate_y", {"quarter_turns": 1}, "east", {"op": "rotate_y", "quarter_turns": 1}),
        ("mirror", {"axis": "z"}, "south", {"op": "mirror", "axis": "z"}),
    ),
)
def test_transform_module_preserves_directional_state_and_records_operation(
    operation: str,
    arguments: dict[str, object],
    expected_facing: str,
    expected_step: dict[str, object],
) -> None:
    model = VoxelModel()
    model.set_block((0, 0, 0), "minecraft:oak_stairs[facing=north,half=bottom,shape=straight,waterlogged=false]")
    project = JiangnanProject(name="Directional transform", assembly=Assembly((Module("roof", "part", model),)))

    revision = ProjectEditor(project).transform_module("roof", operation, "Transform roof", **arguments)

    rotated_state = project.assembly.modules["roof"].model.block_at((0, 0, 0))
    assert dict(rotated_state.properties)["facing"] == expected_facing
    assert project.assembly.modules["roof"].transform_steps[-1] == expected_step
    assert revision.changed_module_ids == ("roof",)
    assert len(revision.block_changes) == 1
    change = revision.block_changes[0]
    assert change.before_state == "minecraft:oak_stairs[facing=north,half=bottom,shape=straight,waterlogged=false]"
    assert change.after_state == (
        f"minecraft:oak_stairs[facing={expected_facing},half=bottom,shape=straight,waterlogged=false]"
    )
    assert {change.position for change in revision.block_changes} == {(0, 0, 0)}


@pytest.mark.parametrize(
    ("operation", "arguments"),
    (
        ("tilt", {}),
        ("translate", {}),
        ("rotate_y", {}),
        ("mirror", {}),
        ("translate", {"offset": (1, 0, 0), "axis": "x"}),
    ),
)
def test_transform_module_rejects_invalid_or_conflicting_arguments(
    operation: str,
    arguments: dict[str, object],
) -> None:
    project = JiangnanProject(name="Invalid transform", assembly=Assembly((hall_module("hall-main"),)))
    editor = ProjectEditor(project)
    before = project.revision_history[0].snapshot_json

    with pytest.raises(ValueError):
        editor.transform_module("hall-main", operation, "Invalid transform", **arguments)

    assert project.revision_cursor == 0
    assert len(project.revision_history) == 1
    assert project.revision_history[0].snapshot_json == before


@pytest.mark.parametrize("operation", ("add", "transform", "connect"))
def test_new_mutations_reject_unrecorded_assembly_changes(operation: str) -> None:
    project = make_project()
    editor = ProjectEditor(project)
    project.assembly.modules["corridor-1"].model.set_block((0, 0, 0), "minecraft:gold_block")

    if operation == "add":
        mutate = lambda: editor.add_module(hall_module("hall-new"), "Add hall")
    elif operation == "transform":
        mutate = lambda: editor.transform_module("hall-1", "translate", "Move hall", offset=(1, 0, 0))
    else:
        mutate = lambda: editor.connect_modules("hall-1", "front", "corridor-1", "start", "Connect")

    with pytest.raises(ValueError, match="revision snapshot"):
        mutate()

    assert len(project.revision_history) == 1
    assert project.revision_cursor == 0
    assert project.assembly.modules["corridor-1"].model.block_at((0, 0, 0)).block_id == "minecraft:gold_block"
