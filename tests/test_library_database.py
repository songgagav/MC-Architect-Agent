from __future__ import annotations

import json
from pathlib import Path
import sqlite3

import pytest

from jiangnan_agent.library.database import LibraryDatabase
from jiangnan_agent.library.errors import AssetIntegrityError, LibraryLookupError
from jiangnan_agent.library.service import LibraryService

from test_litematic_parser import _write_litematic


def test_database_migrations_and_catalog_seed_are_idempotent(tmp_path: Path) -> None:
    database = LibraryDatabase(tmp_path / "library.sqlite3")
    service = LibraryService(database, project_root=tmp_path)

    assert service.initialize() == 3
    assert service.initialize() == 3
    assert database.schema_version == 3
    assert [region["region_id"] for region in service.list_regions(active_only=True)] == [
        "huizhou_core",
        "jiangnan_suzhou",
    ]
    modules = {item["kind"]: item["status"] for item in service.list_modules(include_planned=True)}
    assert modules["hall"] == "implemented"
    assert modules["corridor"] == "implemented"
    assert modules["pavilion"] == "planned"
    assert set(item["profile_id"] for item in service.list_styles()) == {
        "jiangnan_mc_classic",
        "huizhou_mc_classic",
    }
    assert service.list_knowledge_rules(region="jiaxing_huzhou_water_towns")["rules"] == []


def test_reference_import_hash_counts_and_duplicate_import_are_reproducible(tmp_path: Path) -> None:
    source = _write_litematic(
        tmp_path / "references" / "sample.litematic",
        regions={"west": ((0, 0, 0), (2, 1, 2), [1, 2, 0, 1], 3)},
    )
    service = LibraryService(LibraryDatabase(tmp_path / "library.sqlite3"), project_root=tmp_path)
    service.initialize()

    first = service.import_litematic(source, asset_id="reference.sample", name="Sample")
    second = service.import_litematic(source, asset_id="reference.sample", name="Sample")

    assert first.asset_id == second.asset_id == "reference.sample"
    assert first.version == second.version == 1
    assert first.sha256 == second.sha256
    assert first.source_file == "references/sample.litematic"
    assert first.author == "Fixture author"
    assert first.region_profile_id is None
    assert first.region_assignment_status == "unverified"
    assert first.usage_rights["redistribution"] == "not_granted"
    assert service.reference_count() == 1
    assert service.file_count() == 1
    assert service.material_counts("reference.sample") == {
        "minecraft:stone": 2,
        "minecraft:oak_stairs[facing=east,half=bottom,shape=inner_left,waterlogged=false]": 1,
    }
    assert service.material_totals("reference.sample") == {
        "minecraft:stone": 2,
        "minecraft:oak_stairs": 1,
    }
    assert service.verify_files("reference.sample")[0]["status"] == "ok"
    alias = service.import_litematic(source, asset_id="reference.same-file", name="Same source")
    assert alias.sha256 == first.sha256
    assert service.reference_count() == 2
    assert service.file_count() == 1


def test_import_changed_file_creates_next_asset_version_and_detects_corruption(tmp_path: Path) -> None:
    source = _write_litematic(
        tmp_path / "references" / "sample.litematic",
        regions={"west": ((0, 0, 0), (1, 1, 1), [1], 2)},
    )
    service = LibraryService(LibraryDatabase(tmp_path / "library.sqlite3"), project_root=tmp_path)
    service.initialize()
    first = service.import_litematic(source, asset_id="reference.sample", name="Sample")
    _write_litematic(
        source,
        regions={"west": ((0, 0, 0), (1, 1, 1), [2], 3)},
    )
    second = service.import_litematic(source, asset_id="reference.sample", name="Sample")

    assert second.version == first.version + 1
    source.write_bytes(b"corrupt after import")
    with pytest.raises(AssetIntegrityError, match="SHA-256 mismatch"):
        service.verify_files("reference.sample")
    with pytest.raises(LibraryLookupError, match="unknown reference asset"):
        service.get_reference("reference.missing")


def test_import_failures_do_not_create_database_records(tmp_path: Path) -> None:
    service = LibraryService(LibraryDatabase(tmp_path / "library.sqlite3"), project_root=tmp_path)
    service.initialize()

    with pytest.raises(AssetIntegrityError, match="does not exist"):
        service.import_litematic(tmp_path / "missing.litematic", asset_id="reference.missing")
    invalid = tmp_path / "invalid.litematic"
    invalid.write_bytes(b"not litematic")
    with pytest.raises(AssetIntegrityError, match="not a valid Litematic"):
        service.import_litematic(invalid, asset_id="reference.invalid")
    assert service.reference_count() == 0
    assert service.file_count() == 0


def test_sqlite_transaction_rolls_back_and_backup_is_queryable(tmp_path: Path) -> None:
    database = LibraryDatabase(tmp_path / "library.sqlite3")
    database.initialize()

    with pytest.raises(RuntimeError, match="force rollback"):
        with database.transaction() as connection:
            connection.execute(
                "INSERT INTO library_meta(key, value) VALUES ('test', 'uncommitted')"
            )
            raise RuntimeError("force rollback")
    assert database.get_meta("test") is None

    backup = database.backup_to(tmp_path / "backup.sqlite3")
    assert backup.is_file()
    with pytest.raises(FileExistsError):
        database.backup_to(backup)
    saved = LibraryDatabase(backup)
    assert saved.schema_version == 3
    assert saved.get_meta("library_id") == database.get_meta("library_id")


def test_unknown_referenced_style_asset_is_reported_explicitly(tmp_path: Path) -> None:
    service = LibraryService(LibraryDatabase(tmp_path / "library.sqlite3"), project_root=tmp_path)
    service.initialize()

    with pytest.raises(LibraryLookupError, match="reference asset.*not imported"):
        service.get_style_profile("jiangnan_mc_classic", require_references=True)


def test_module_catalog_tracks_parameter_schema_as_a_definition_not_instance(tmp_path: Path) -> None:
    service = LibraryService(LibraryDatabase(tmp_path / "library.sqlite3"), project_root=tmp_path)
    service.initialize()
    hall = service.get_module_definition("jiangnan.hall")

    assert hall["asset_version"] == 3
    assert hall["parameter_schema_id"] == "hall"
    assert hall["parameter_schema_version"] == 2
    assert hall["parameter_schema"]["kind"] == "hall"
    assert "module_instance_id" not in hall
    assert hall["knowledge_rule_ids"] == ["hui-village-layout-and-architecture"]


def test_design_parameter_registry_covers_visual_inputs_without_fake_historical_defaults(tmp_path: Path) -> None:
    service = LibraryService(LibraryDatabase(tmp_path / "library.sqlite3"), project_root=tmp_path)
    service.initialize()

    schema = service.get_parameter_schema("minecraft_building_design")

    assert schema["grid_scale_meters_per_block"] == 1.0
    assert {
        "width_blocks", "depth_blocks", "height_blocks", "bay_count", "column_grid",
        "roof_type", "roof_slope", "ridge_contour", "eaves_projection", "corner_upturn",
        "roof_layers", "materials", "door_window_proportions", "ornament_density",
        "reference_asset_ids", "module_connection_constraints",
    } <= set(schema["parameters"])
    assert schema["parameters"]["corner_upturn"]["status"] == "planned"
    assert schema["parameters"]["roof_layers"]["default"] is None
    assert "literature_reference" in schema["source_categories"]


def test_material_totals_aggregate_block_states_by_block_identifier(tmp_path: Path) -> None:
    source = _write_litematic(
        tmp_path / "references" / "states.litematic",
        regions={"west": ((0, 0, 0), (2, 1, 2), [1, 2, 0, 1], 3)},
    )
    service = LibraryService(LibraryDatabase(tmp_path / "library.sqlite3"), project_root=tmp_path)
    service.initialize()
    service.import_litematic(source, asset_id="reference.states", name="States")

    assert service.material_totals("reference.states") == {
        "minecraft:stone": 2,
        "minecraft:oak_stairs": 1,
    }


def test_reference_previews_are_registered_and_checked_as_existing_files(tmp_path: Path) -> None:
    source = _write_litematic(
        tmp_path / "references" / "sample.litematic",
        regions={"west": ((0, 0, 0), (1, 1, 1), [1], 2)},
    )
    preview = tmp_path / "previews" / "front.png"
    preview.parent.mkdir()
    preview.write_bytes(b"local preview fixture")
    service = LibraryService(LibraryDatabase(tmp_path / "library.sqlite3"), project_root=tmp_path)
    service.initialize()
    service.import_litematic(source, asset_id="reference.preview", name="Preview")

    updated = service.register_preview_files("reference.preview", [preview])

    assert updated.preview_files == ("previews/front.png",)
    assert service.verify_files("reference.preview")[0]["status"] == "ok"
    preview.unlink()
    with pytest.raises(AssetIntegrityError, match="preview file is missing"):
        service.verify_files("reference.preview")


def test_style_profile_uses_measured_reference_palette_candidates_without_semantic_claims(tmp_path: Path) -> None:
    first_source = _write_litematic(
        tmp_path / "references" / "first.litematic",
        regions={"west": ((0, 0, 0), (1, 1, 1), [1], 2)},
    )
    second_source = _write_litematic(
        tmp_path / "references" / "second.litematic",
        regions={"west": ((0, 0, 0), (1, 1, 1), [2], 3)},
    )
    service = LibraryService(LibraryDatabase(tmp_path / "library.sqlite3"), project_root=tmp_path)
    service.initialize()
    service.import_litematic(first_source, asset_id="reference.fangtang", name="Fangtang")
    service.import_litematic(second_source, asset_id="reference.liusufang-frame", name="Liufang")

    profile = service.get_style_profile("jiangnan_mc_classic", require_references=True)

    assert profile["classification"] == "minecraft_visual_style"
    assert profile["reference_status"] == "ready"
    assert set(profile["palette_candidates"]) == {"reference.fangtang", "reference.liusufang-frame"}
    assert profile["palette_candidates"]["reference.fangtang"][0]["block_state"] == "minecraft:stone"
    assert profile["visual_preferences"]["silhouette"]["status"] == "unverified"


def test_catalog_only_regions_never_enter_default_module_or_rule_queries(tmp_path: Path) -> None:
    service = LibraryService(LibraryDatabase(tmp_path / "library.sqlite3"), project_root=tmp_path)
    service.initialize()

    assert all(region["status"] == "active" for region in service.list_regions(active_only=True))
    assert all(module["status"] == "implemented" for module in service.list_modules())
    for region in ("jiaxing_huzhou_water_towns", "ningbo_east_zhejiang", "yangzhou_canal"):
        assert service.list_knowledge_rules(region=region)["rules"] == []


def test_knowledge_registry_is_versioned_and_current_profile_queries_report_version(tmp_path: Path) -> None:
    service = LibraryService(LibraryDatabase(tmp_path / "library.sqlite3"), project_root=tmp_path)
    service.initialize()

    with service.database.connection() as connection:
        versions = connection.execute(
            "SELECT version, content_sha256 FROM knowledge_registry_versions ORDER BY version"
        ).fetchall()
    assert [(int(row["version"]), len(row["content_sha256"])) for row in versions] == [(3, 64)]
    assert all(region["registry_version"] == 3 for region in service.list_regions())
    assert service.list_knowledge_rules(region="huizhou_core")["knowledge_base_version"] == 3
    assert service.list_sources()[0]["registry_version"] == 3


def test_database_foreign_keys_and_module_version_history_are_enforced(tmp_path: Path) -> None:
    database = LibraryDatabase(tmp_path / "library.sqlite3")
    service = LibraryService(database, project_root=tmp_path)
    service.initialize()

    with pytest.raises(sqlite3.IntegrityError):
        with database.transaction() as connection:
            connection.execute(
                "INSERT INTO module_asset_regions(asset_id, asset_version, region_id) VALUES (?, ?, ?)",
                ("missing.module", 1, "huizhou_core"),
            )
    with database.transaction() as connection:
        connection.execute(
            """INSERT INTO module_assets(asset_id, version, kind, status, definition_path,
                       region_association_kind, anchor_interfaces_json, dependencies_json,
                       preview_files_json, record_json)
               VALUES ('test.versioned-module', 1, 'test_kind', 'planned', 'catalog.json',
                       'unclassified', '[]', '[]', '[]', '{}')"""
        )
        connection.execute(
            """INSERT INTO module_assets(asset_id, version, kind, status, definition_path,
                       region_association_kind, anchor_interfaces_json, dependencies_json,
                       preview_files_json, record_json)
               VALUES ('test.versioned-module', 2, 'test_kind', 'planned', 'catalog.json',
                       'unclassified', '[]', '[]', '[]', '{}')"""
        )
    assert database.schema_version == 3


def test_database_upgrades_an_existing_v1_file_in_order(tmp_path: Path) -> None:
    path = tmp_path / "legacy-v1.sqlite3"
    connection = sqlite3.connect(path)
    migration = Path(__file__).resolve().parents[1] / "jiangnan_agent/library/migrations/001_initial.sql"
    for statement in migration.read_text(encoding="utf-8").split(";"):
        if statement.strip():
            connection.execute(statement)
    connection.execute("INSERT INTO schema_migrations(version, applied_at) VALUES (1, '2026-10-30T00:00:00Z')")
    connection.execute("PRAGMA user_version = 1")
    connection.commit()
    connection.close()

    service = LibraryService(LibraryDatabase(path), project_root=tmp_path)

    assert service.initialize() == 3
    assert service.list_knowledge_rules(region="huizhou_core")["knowledge_base_version"] == 3


def test_versioned_module_parameter_and_style_definitions_are_immutable(tmp_path: Path) -> None:
    service = LibraryService(LibraryDatabase(tmp_path / "library.sqlite3"), project_root=tmp_path)
    service.initialize()
    module = {
        "asset_id": "test.versioned-module",
        "version": 1,
        "kind": "test_module",
        "status": "planned",
        "generator_source_id": None,
        "parameter_schema_id": None,
        "parameter_schema_version": None,
        "definition_path": "catalog/test.json",
        "region_association_kind": "unclassified",
        "region_ids": [],
        "anchor_interfaces": [],
        "dependencies": [],
        "preview_files": [],
        "knowledge_rule_ids": [],
        "notes": "version one",
    }
    parameter_path = Path(__file__).resolve().parents[1] / "jiangnan_agent/library/parameters/v1/minecraft_building_design.json"
    parameter_schema = json.loads(parameter_path.read_text(encoding="utf-8"))
    style = {
        "profile_id": "test.versioned-style",
        "version": 1,
        "label": "Version one",
        "design_target_region_id": "huizhou_core",
        "status": "draft",
        "parameter_schema": {"schema_id": "minecraft_building_design", "version": 1},
        "reference_asset_ids": [],
        "_definition_path": "styles/test.json",
    }

    with service.database.transaction() as connection:
        service._upsert_module_catalog(connection, [module])
        service._upsert_parameter_schema(connection, parameter_schema, parameter_path)
        service._upsert_style(connection, style)

    changed_module = {**module, "notes": "silent replacement"}
    changed_parameter_schema = {**parameter_schema, "grid_scale_meters_per_block": 0.5}
    changed_style = {**style, "label": "silent replacement"}
    with pytest.raises(ValueError, match="module .*version 1 is immutable"):
        with service.database.transaction() as connection:
            service._upsert_module_catalog(connection, [changed_module])
    with pytest.raises(ValueError, match="parameter schema .*version 1 is immutable"):
        with service.database.transaction() as connection:
            service._upsert_parameter_schema(connection, changed_parameter_schema, parameter_path)
    with pytest.raises(ValueError, match="style profile .*version 1 is immutable"):
        with service.database.transaction() as connection:
            service._upsert_style(connection, changed_style)
