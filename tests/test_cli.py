from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from jiangnan_agent.generators.hall import HallParameters, generate_hall
from jiangnan_agent.assembly.adapters import hall_module
from jiangnan_agent.assembly.model import Assembly, Module
from jiangnan_agent.core.scene import VoxelModel
from jiangnan_agent.io.project_editor import ProjectEditor
from jiangnan_agent.io.project_json import JiangnanProject, load_project, save_project
from jiangnan_agent.io.schematic import read_schematic


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def run_cli(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "jiangnan_agent.cli", *arguments],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_init_creates_and_validates_project(tmp_path: Path) -> None:
    project_path = tmp_path / "sample.jap.json"

    created = run_cli("init", "--name", "Sample Hall", "--output", str(project_path))
    assert created.returncode == 0, created.stderr
    assert project_path.exists()

    validated = run_cli("validate", str(project_path))
    assert validated.returncode == 0, validated.stderr
    assert "Sample Hall" in validated.stdout


def test_generate_writes_readable_sponge_schematic(tmp_path: Path) -> None:
    project_path = tmp_path / "sample.jap.json"
    schematic_path = tmp_path / "sample.schem"
    created = run_cli("init", "--name", "Sample Hall", "--output", str(project_path))
    assert created.returncode == 0, created.stderr

    generated = run_cli("generate", "--project", str(project_path), "--output", str(schematic_path))

    assert generated.returncode == 0, generated.stderr
    schematic = read_schematic(schematic_path)
    assert schematic.data_version == 4325
    assert schematic.name == "Sample Hall"
    assert len(schematic.model.blocks) > 0


def test_generate_hall_writes_readable_schematic(tmp_path: Path) -> None:
    project_path = tmp_path / "three_bay_hall.jap.json"
    schematic_path = tmp_path / "three_bay_hall.schem"
    parameters = HallParameters(bay_count=3, bay_width=5, depth=7)
    save_project(
        JiangnanProject(
            name="Three Bay Hall",
            settings={"building": {"type": "hall", "bay_count": 3, "bay_width": 5, "depth": 7}},
        ),
        project_path,
    )

    generated = run_cli("generate", "--project", str(project_path), "--output", str(schematic_path))

    assert generated.returncode == 0, generated.stderr
    schematic = read_schematic(schematic_path)
    expected = generate_hall(parameters)
    assert schematic.data_version == 4325
    assert schematic.name == "Three Bay Hall"
    assert len(schematic.model.blocks) == len(expected.blocks)
    assert schematic.model.bounds.size == expected.bounds.size
    normalized_expected = expected.translated(
        -expected.bounds.min_x,
        -expected.bounds.min_y,
        -expected.bounds.min_z,
    )
    assert schematic.model.blocks == normalized_expected.blocks


def test_generate_exports_saved_assembly_instead_of_legacy_building_settings(tmp_path: Path) -> None:
    project_path = tmp_path / "assembly.jap.json"
    schematic_path = tmp_path / "assembly.schem"
    model = VoxelModel()
    model.set_block((-5, 2, 3), "minecraft:gold_block")
    project = JiangnanProject(
        name="Assembly wins",
        settings={"building": {"type": "simple_house", "width": 9}},
        assembly=Assembly((Module("custom-1", "custom", model),)),
    )
    save_project(project, project_path)

    generated = run_cli("generate", "--project", str(project_path), "--output", str(schematic_path))

    assert generated.returncode == 0, generated.stderr
    schematic = read_schematic(schematic_path)
    assert schematic.model.blocks == {(0, 0, 0): next(iter(model.blocks.values()))}


def test_history_lists_revisions_and_affected_modules(tmp_path: Path) -> None:
    project_path = tmp_path / "history.jap.json"
    project = JiangnanProject(name="History Hall", assembly=Assembly((hall_module("hall-1"),)))
    ProjectEditor(project).regenerate_module("hall-1", {"bay_count": 5}, "Widen the hall")
    save_project(project, project_path)

    history = run_cli("history", str(project_path))

    assert history.returncode == 0, history.stderr
    assert "Widen the hall" in history.stdout
    assert "hall-1" in history.stdout
    assert "当前" in history.stdout


def test_info_reports_assembly_module_count_and_selected_revision(tmp_path: Path) -> None:
    project_path = tmp_path / "info.jap.json"
    project = JiangnanProject(name="Info Hall", assembly=Assembly((hall_module("hall-1"),)))
    ProjectEditor(project).regenerate_module("hall-1", {"column_height": 5}, "Raise hall")
    save_project(project, project_path)

    info = run_cli("info", str(project_path))

    assert info.returncode == 0, info.stderr
    assert "模块数: 1" in info.stdout
    assert "当前版本: 1" in info.stdout


def test_cli_undo_and_redo_persist_the_selected_snapshot(tmp_path: Path) -> None:
    project_path = tmp_path / "editable.jap.json"
    project = JiangnanProject(name="Editable Hall", assembly=Assembly((hall_module("hall-1"),)))
    ProjectEditor(project).regenerate_module("hall-1", {"bay_count": 5}, "Widen the hall")
    save_project(project, project_path)

    undone = run_cli("undo", str(project_path))
    assert undone.returncode == 0, undone.stderr
    assert load_project(project_path).assembly.modules["hall-1"].parameters["bay_count"] == 3

    redone = run_cli("redo", str(project_path))
    assert redone.returncode == 0, redone.stderr
    assert load_project(project_path).assembly.modules["hall-1"].parameters["bay_count"] == 5


def test_unavailable_history_navigation_fails_without_changing_project(tmp_path: Path) -> None:
    project_path = tmp_path / "initial.jap.json"
    save_project(JiangnanProject(name="Initial"), project_path)
    original = project_path.read_bytes()

    for command in ("undo", "redo"):
        result = run_cli(command, str(project_path))
        assert result.returncode != 0
        assert project_path.read_bytes() == original
