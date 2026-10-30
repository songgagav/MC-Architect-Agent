from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest

from jiangnan_agent.io.project_generation import generate_project_model
from jiangnan_agent.io.project_json import load_project
from jiangnan_agent.io.schematic import read_schematic


def _load_closeout_module():
    module_path = Path(__file__).resolve().parents[1] / "examples" / "gen2_roof_closeout.py"
    assert module_path.is_file(), "the reproducible GEN-2 roof closeout helper must exist"
    spec = importlib.util.spec_from_file_location("gen2_roof_closeout_under_test", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_roof_closeout_builds_all_presets_with_roundtrip_schematics(tmp_path: Path) -> None:
    helper = _load_closeout_module()

    results = helper.build_roof_closeout_examples(tmp_path)

    assert {item.preset_id for item in results} == {
        "jiangnan_dark_tile",
        "gray_brick_layered",
        "warm_spruce_garden",
    }
    assert len(results) == 3
    for result in results:
        project = load_project(result.project_path)
        model = generate_project_model(project)
        schematic = read_schematic(result.schematic_path)
        normalized_model = model.translated(-model.bounds.min_x, -model.bounds.min_y, -model.bounds.min_z)

        assert project.assembly.modules
        assert schematic.data_version == 4325
        assert schematic.offset == (model.bounds.min_x, model.bounds.min_y, model.bounds.min_z)
        assert schematic.model.blocks == normalized_model.blocks
        assert result.block_count == len(model.blocks)
        assert result.dimensions == model.bounds.size


def test_roof_closeout_refuses_existing_destination(tmp_path: Path, monkeypatch) -> None:
    helper = _load_closeout_module()
    run_id = "20261031T120000123456Z"
    existing_run = tmp_path / f"gen2-roof-closeout-{run_id}"
    existing_run.mkdir()
    sentinel = existing_run / "keep.txt"
    sentinel.write_text("user data", encoding="utf-8")
    monkeypatch.setattr(helper, "_timestamp", lambda: run_id)

    with pytest.raises(FileExistsError):
        helper.build_roof_closeout_examples(tmp_path)

    assert sentinel.read_text(encoding="utf-8") == "user data"
