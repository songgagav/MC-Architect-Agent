from __future__ import annotations

import json

import pytest

from jiangnan_agent.cli import main
from test_litematic_parser import _palette_entry, _write_litematic


def test_library_cli_initializes_and_lists_regions(tmp_path, monkeypatch, capsys) -> None:
    database = tmp_path / "library.sqlite3"
    monkeypatch.setattr(
        "sys.argv",
        ["jiangnan", "library", "init", "--database", str(database)],
    )
    assert main() == 0
    assert json.loads(capsys.readouterr().out)["schema_version"] == 4

    monkeypatch.setattr(
        "sys.argv",
        ["jiangnan", "library", "list", "regions", "--database", str(database)],
    )
    assert main() == 0
    regions = json.loads(capsys.readouterr().out)
    assert {region["region_id"] for region in regions} >= {"huizhou_core", "jiangnan_suzhou"}

    monkeypatch.setattr(
        "sys.argv",
        ["jiangnan", "library", "list", "sources", "--database", str(database)],
    )
    assert main() == 0
    sources = json.loads(capsys.readouterr().out)
    assert sources and all(source["registry_version"] == 3 for source in sources)


def test_library_backup_does_not_create_a_database_as_a_side_effect(tmp_path, monkeypatch, capsys) -> None:
    database = tmp_path / "missing.sqlite3"
    backup = tmp_path / "backup.sqlite3"
    monkeypatch.setattr(
        "sys.argv",
        ["jiangnan", "library", "backup", "--output", str(backup), "--database", str(database)],
    )

    with pytest.raises(SystemExit) as error:
        main()

    assert error.value.code == 2
    assert "library database not found" in capsys.readouterr().err
    assert not database.exists()
    assert not backup.exists()


def test_library_semantic_annotation_component_and_style_analysis_cli(tmp_path, monkeypatch, capsys) -> None:
    database = tmp_path / "library.sqlite3"
    source = _write_litematic(
        tmp_path / "references" / "sample.litematic",
        regions={"west": ((-1, 0, 2), (3, 1, 1), [1, 2, 3], 4)},
        palette=[
            _palette_entry("minecraft:air"),
            _palette_entry("minecraft:stone"),
            _palette_entry("minecraft:oak_door", facing="north", half="lower", hinge="left", open="false"),
            _palette_entry("minecraft:glass_pane", east="true", north="false", south="false", west="false", waterlogged="false"),
        ],
    )

    def call(*arguments):
        monkeypatch.setattr("sys.argv", ["jiangnan", "library", *map(str, arguments), "--database", str(database)])
        assert main() == 0
        return json.loads(capsys.readouterr().out)

    call("init")
    for asset_id in ("reference.fangtang", "reference.liusufang-frame"):
        call("import", source, "--asset-id", asset_id, "--name", asset_id)
    proposals = call("annotations", "propose", "reference.fangtang")
    assert {item["component_type"] for item in proposals} == {"door", "window"}
    candidates = call("annotations", "list", "--asset-id", "reference.fangtang", "--status", "candidate")
    assert len(candidates) == 2

    annotation = call(
        "annotations", "create", "--annotation-id", "manual.floor", "--asset-id", "reference.fangtang",
        "--region", "west", "--component-type", "floor", "--geometry-type", "block_set",
        "--geometry", '{"positions":[[-1,0,2]]}',
    )
    reviewed = call("annotations", "review", annotation["annotation_id"], "--reviewer", "MOSS", "--decision", "verified")
    assert reviewed["status"] == "verified"
    edited = call(
        "annotations", "update", annotation["annotation_id"], "--geometry-type", "block_set",
        "--geometry", '{"positions":[[1,0,2]]}',
    )
    assert edited["revision"] == 3 and edited["status"] == "candidate"
    reviewed = call("annotations", "review", annotation["annotation_id"], "--reviewer", "MOSS", "--decision", "verified")
    assert reviewed["revision"] == 4
    summary = call("annotations", "analyze", "manual.floor")
    assert summary["block_count"] == 1
    component = call("components", "register", "manual.floor", "--name", "reference floor")
    assert component["parameterization_status"] == "not_parameterized"
    assert call("components", "list", "--source-asset", "reference.fangtang")
    assert call("components", "show", component["component_id"])["component_type"] == "floor"
    component_report = tmp_path / "reports" / "component.json"
    exported_component = call(
        "components", "report", component["component_id"], "--output", component_report
    )
    assert exported_component["exported"] == str(component_report)

    report = call("style-analysis", "create", "jiangnan_mc_classic")
    assert report["status"] == "candidate" and report["profile_version"] == 2
    assert call("style-analysis", "list", "--profile-id", "jiangnan_mc_classic")[0]["analysis_id"] == report["analysis_id"]
    assert call("style-analysis", "show", report["analysis_id"])["status"] == "candidate"
    reviewed_report = call(
        "style-analysis", "review", report["analysis_id"], "--reviewer", "MOSS", "--decision", "verified"
    )
    assert reviewed_report["status"] == "verified" and reviewed_report["revision"] == 2
    destination = tmp_path / "reports" / "style.json"
    exported = call("style-analysis", "export", report["analysis_id"], "--output", destination)
    assert exported["exported"] == str(destination)
    assert json.loads(destination.read_text(encoding="utf-8"))["analysis_id"] == report["analysis_id"]
