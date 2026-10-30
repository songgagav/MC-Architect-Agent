from __future__ import annotations

import json

import pytest

from jiangnan_agent.cli import main


def test_library_cli_initializes_and_lists_regions(tmp_path, monkeypatch, capsys) -> None:
    database = tmp_path / "library.sqlite3"
    monkeypatch.setattr(
        "sys.argv",
        ["jiangnan", "library", "init", "--database", str(database)],
    )
    assert main() == 0
    assert json.loads(capsys.readouterr().out)["schema_version"] == 3

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
