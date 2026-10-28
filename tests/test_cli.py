from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from jiangnan_agent.generators.hall import HallParameters, generate_hall
from jiangnan_agent.io.project_json import JiangnanProject, save_project
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
