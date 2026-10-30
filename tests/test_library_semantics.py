from __future__ import annotations

from pathlib import Path
import sqlite3

import pytest

from jiangnan_agent.library.database import LibraryDatabase
from jiangnan_agent.library.errors import AssetIntegrityError, LibraryLookupError
from jiangnan_agent.library.service import LibraryService

from test_litematic_parser import _palette_entry, _write_litematic


def test_schema_v3_migration_preserves_populated_db1_reference_and_style_data(tmp_path: Path) -> None:
    database = LibraryDatabase(tmp_path / "library.sqlite3")
    service = LibraryService(database, project_root=tmp_path)
    service.initialize()
    source = _write_litematic(
        tmp_path / "references" / "sample.litematic",
        regions={"west": ((0, 0, 0), (2, 1, 2), [1, 2, 0, 1], 3)},
    )
    service.import_litematic(source, asset_id="reference.sample", name="Sample")
    reference_before = service.get_reference("reference.sample")
    materials_before = service.material_counts("reference.sample")
    styles_before = {item["profile_id"]: item for item in service.list_styles()}
    knowledge_before = service.list_knowledge_rules(region="huizhou_core")["rules"]

    # Reconstruct the DB-1 schema boundary after seeding realistic DB-1 records.
    # Migration 004 only adds these DB-2 tables, so dropping them leaves the
    # populated v3 schema and its records intact for the upgrade assertion.
    connection = sqlite3.connect(database.path)
    try:
        connection.execute("PRAGMA foreign_keys = OFF")
        for table in (
            "style_analysis_sources",
            "reference_components",
            "style_analysis_revisions",
            "semantic_annotation_revisions",
        ):
            connection.execute(f"DROP TABLE {table}")
        connection.execute("DELETE FROM schema_migrations WHERE version = 4")
        connection.execute("PRAGMA user_version = 3")
        connection.commit()
    finally:
        connection.close()

    assert database.schema_version == 3
    assert database.initialize() == 4
    assert service.initialize() == 4

    reference_after = service.get_reference("reference.sample")
    assert database.schema_version == 4
    assert service.reference_count() == 1
    assert reference_after.sha256 == reference_before.sha256
    assert reference_after.block_count == reference_before.block_count
    assert service.material_counts("reference.sample") == materials_before
    assert {item["profile_id"]: item for item in service.list_styles()} == styles_before
    assert service.list_knowledge_rules(region="huizhou_core")["rules"] == knowledge_before
    with database.connection() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM schema_migrations WHERE version = 4"
        ).fetchone()[0] == 1


def test_semantic_annotation_schema_enforces_label_status_and_source_foreign_keys(tmp_path: Path) -> None:
    database = LibraryDatabase(tmp_path / "library.sqlite3")
    service = LibraryService(database, project_root=tmp_path)
    service.initialize()
    source = _write_litematic(
        tmp_path / "references" / "sample.litematic",
        regions={"west": ((0, 0, 0), (1, 1, 1), [1], 2)},
    )
    service.import_litematic(source, asset_id="reference.sample", name="Sample")
    row = (
        "annotation-1", 1, "reference.sample", 1, "west", "column", "region", "{}",
        "manual", None, None, "candidate", None, None, None, "2026-10-30T00:00:00Z", "{}",
    )
    insert = """INSERT INTO semantic_annotation_revisions(
        annotation_id, revision, asset_id, asset_version, region_name, component_type,
        geometry_type, geometry_json, source_kind, rule_id, confidence, status,
        reviewer, reviewed_at, review_note, created_at, record_json
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""

    with database.transaction() as connection:
        connection.execute(insert, row)
    with database.connection() as connection:
        saved = connection.execute(
            "SELECT status, component_type FROM semantic_annotation_revisions WHERE annotation_id = 'annotation-1'"
        ).fetchone()
        assert (saved["status"], saved["component_type"]) == ("candidate", "column")

    with pytest.raises(sqlite3.IntegrityError):
        with database.transaction() as connection:
            connection.execute(
                insert,
                ("invalid-label", 1, "reference.sample", 1, "west", "roof", "region", "{}", "manual", None, None, "candidate", None, None, None, "2026-10-30T00:00:00Z", "{}"),
            )

    with pytest.raises(sqlite3.IntegrityError):
        with database.transaction() as connection:
            connection.execute(
                insert,
                ("invalid-source", 1, "reference.missing", 1, "west", "column", "region", "{}", "manual", None, None, "candidate", None, None, None, "2026-10-30T00:00:00Z", "{}"),
            )

    with pytest.raises(sqlite3.IntegrityError):
        with database.transaction() as connection:
            connection.execute(
                insert,
                ("unreviewed-verified", 1, "reference.sample", 1, "west", "column", "region", "{}", "manual", None, None, "verified", None, None, None, "2026-10-30T00:00:00Z", "{}"),
            )


def test_annotation_region_selection_preserves_multi_region_negative_positions(tmp_path: Path) -> None:
    service = LibraryService(LibraryDatabase(tmp_path / "library.sqlite3"), project_root=tmp_path)
    service.initialize()
    source = _write_litematic(
        tmp_path / "references" / "multi.litematic",
        regions={
            "west": ((-4, 2, 5), (-1, -1, 2), [1, 0], 2),
            "east": ((6, -3, -2), (1, 1, -1), [3], 4),
        },
        data_version=3465,
    )
    service.import_litematic(source, asset_id="reference.multi", name="Multi-region")

    annotation = service.create_annotation(
        annotation_id="manual.east-region",
        asset_id="reference.multi",
        region_name="east",
        component_type="unknown",
        geometry_type="block_set",
        geometry={"positions": [[6, -3, -2]]},
    )
    summary = service.analyze_annotation(annotation.annotation_id)

    assert summary.region_name == "east"
    assert summary.local_origin == (6, -3, -2)
    assert summary.bounding_box == ((6, -3, -2), (7, -2, -1))
    assert summary.block_states == {"minecraft:glass": 1}


def _semantic_service(tmp_path: Path, values: list[int] | None = None) -> tuple[LibraryService, Path]:
    service = LibraryService(LibraryDatabase(tmp_path / "library.sqlite3"), project_root=tmp_path)
    service.initialize()
    source = _write_litematic(
        tmp_path / "references" / "sample.litematic",
        regions={"west": ((-2, 4, 7), (5, 1, 1), values or [1, 1, 2, 2, 3], 4)},
        palette=[
            _palette_entry("minecraft:air"),
            _palette_entry("minecraft:oak_door", facing="north", half="lower", hinge="left", open="false"),
            _palette_entry("minecraft:glass_pane", east="true", north="false", south="false", west="false", waterlogged="false"),
            _palette_entry("minecraft:oak_fence", east="false", north="true", south="false", west="false", waterlogged="false"),
        ],
        data_version=3465,
    )
    service.import_litematic(source, asset_id="reference.sample", name="Sample")
    return service, source


def test_rule_proposals_are_idempotent_candidates_with_rule_provenance(tmp_path: Path) -> None:
    service, _ = _semantic_service(tmp_path)

    first = service.propose_annotations("reference.sample")
    second = service.propose_annotations("reference.sample")

    assert {item.component_type for item in first} == {"door", "window", "railing"}
    assert all(item.status == "candidate" and item.source_kind == "rule" for item in first)
    assert all(item.rule_id and item.confidence is not None for item in first)
    assert [(item.annotation_id, item.revision) for item in first] == [
        (item.annotation_id, item.revision) for item in second
    ]
    assert len(service.list_annotations(asset_id="reference.sample")) == 3


def test_annotation_revision_review_and_component_registration_gate(tmp_path: Path) -> None:
    service, _ = _semantic_service(tmp_path)
    annotation = service.create_annotation(
        annotation_id="manual.stone-floor",
        asset_id="reference.sample",
        region_name="west",
        component_type="floor",
        geometry_type="block_set",
        geometry={"positions": [[-2, 4, 7]]},
    )
    with pytest.raises(ValueError, match="verified"):
        service.register_reference_component(annotation.annotation_id, name="Stone floor")

    verified = service.review_annotation(
        annotation.annotation_id, reviewer="MOSS", decision="verified", note="人工确认的地面块"
    )
    component = service.register_reference_component(
        annotation.annotation_id, name="Stone floor", style_tags=("minecraft-reference",)
    )
    edited = service.update_annotation(
        annotation.annotation_id,
        geometry={"positions": [[-1, 4, 7]]},
    )

    assert verified.revision == 2 and verified.status == "verified"
    assert component.component_status == "static_reference"
    assert component.parameterization_status == "not_parameterized"
    assert component.source_asset_id == "reference.sample" and component.block_count == 1
    assert edited.revision == 3 and edited.status == "candidate" and edited.reviewer is None
    assert service.get_reference_component(component.component_id).coordinate_runs == ((0, 0, 0, 1),)
    report_path = tmp_path / "reports" / "component.json"
    assert service.export_component_report(component.component_id, report_path) == report_path
    assert '"parameterization_status": "not_parameterized"' in report_path.read_text(encoding="utf-8")
    with pytest.raises(FileExistsError):
        service.export_component_report(component.component_id, report_path)


def test_annotation_analysis_is_deterministic_and_rejects_changed_source(tmp_path: Path) -> None:
    service, source = _semantic_service(tmp_path)
    annotation = service.create_annotation(
        annotation_id="manual.whole-region",
        asset_id="reference.sample",
        region_name="west",
        component_type="unknown",
        geometry_type="region",
        geometry={},
    )
    before_sha = service.get_reference("reference.sample").sha256

    first = service.analyze_annotation(annotation.annotation_id)
    second = service.analyze_annotation(annotation.annotation_id)

    assert first == second
    assert first.block_count == 5
    assert service.verify_files("reference.sample")[0]["sha256"] == before_sha
    source.write_bytes(source.read_bytes() + b"changed")
    with pytest.raises(AssetIntegrityError, match="SHA-256 mismatch"):
        service.analyze_annotation(annotation.annotation_id)


def test_annotation_create_and_edit_reject_a_selector_with_no_occupied_blocks(tmp_path: Path) -> None:
    service, _ = _semantic_service(tmp_path, values=[1, 0, 0, 0, 0])
    empty_box = {"min": [0, 4, 7], "max": [2, 5, 8]}

    with pytest.raises(ValueError, match="no occupied blocks"):
        service.create_annotation(
            annotation_id="manual.empty",
            asset_id="reference.sample",
            region_name="west",
            component_type="wall",
            geometry_type="box",
            geometry=empty_box,
        )
    annotation = service.create_annotation(
        annotation_id="manual.stone",
        asset_id="reference.sample",
        region_name="west",
        component_type="unknown",
        geometry_type="block_set",
        geometry={"positions": [[-2, 4, 7]]},
    )
    with pytest.raises(ValueError, match="no occupied blocks"):
        service.update_annotation(
            annotation.annotation_id,
            geometry_type="box",
            geometry=empty_box,
        )
    assert service.get_annotation(annotation.annotation_id).revision == 1


def _style_service(tmp_path: Path) -> tuple[LibraryService, Path]:
    service, source = _semantic_service(tmp_path)
    service.import_litematic(source, asset_id="reference.fangtang", name="Fangtang")
    service.import_litematic(source, asset_id="reference.liusufang-frame", name="Liusufang frame")
    return service, source


def _multi_region_style_service(tmp_path: Path) -> LibraryService:
    service = LibraryService(LibraryDatabase(tmp_path / "library.sqlite3"), project_root=tmp_path)
    service.initialize()
    source = _write_litematic(
        tmp_path / "references" / "multi-region.litematic",
        regions={
            "empty": ((0, 0, 0), (2, 2, 2), [0] * 8, 5),
            "overlap-a": ((0, 0, 0), (1, 1, 1), [1], 5),
            "overlap-b": ((0, 0, 0), (1, 1, 1), [1], 5),
        },
    )
    service.import_litematic(source, asset_id="reference.fangtang", name="Fangtang")
    service.import_litematic(source, asset_id="reference.liusufang-frame", name="Liusufang frame")
    return service


def test_style_analysis_pins_real_sources_and_does_not_change_style_profile(tmp_path: Path) -> None:
    service, _ = _style_service(tmp_path)
    service.propose_annotations("reference.fangtang")
    profile_before = service.get_style_profile("jiangnan_mc_classic")
    with service.database.connection() as connection:
        stored_before = connection.execute(
            "SELECT profile_json FROM style_profiles WHERE profile_id = 'jiangnan_mc_classic' AND version = 2"
        ).fetchone()[0]

    first = service.create_style_analysis("jiangnan_mc_classic")
    repeated = service.create_style_analysis("jiangnan_mc_classic")

    assert first.status == "candidate"
    assert first.profile_id == "jiangnan_mc_classic" and first.profile_version == 2
    assert first.source_assets == (("reference.fangtang", 1), ("reference.liusufang-frame", 1))
    assert first.analysis == repeated.analysis
    asset_report = first.analysis["assets"][0]
    assert asset_report["measurement_status"] == "measured"
    assert asset_report["dimensions"] == [5, 1, 1]
    assert asset_report["annotations"]["candidates"]
    assert asset_report["annotations"]["verified"] == []
    assert "regional_attribution" in first.analysis and first.analysis["regional_attribution"] == "unverified"
    assert service.get_style_profile("jiangnan_mc_classic") == profile_before
    with service.database.connection() as connection:
        stored_after = connection.execute(
            "SELECT profile_json FROM style_profiles WHERE profile_id = 'jiangnan_mc_classic' AND version = 2"
        ).fetchone()[0]
    assert stored_after == stored_before


def test_style_report_review_is_versioned_and_export_never_overwrites(tmp_path: Path) -> None:
    service, _ = _style_service(tmp_path)
    report = service.create_style_analysis("huizhou_mc_classic")
    reviewed = service.review_style_analysis(
        report.analysis_id, reviewer="MOSS", decision="verified", note="只核验数据统计准确"
    )

    assert reviewed.revision == report.revision + 1 and reviewed.status == "verified"
    destination = tmp_path / "reports" / "style-analysis.json"
    destination.parent.mkdir()
    exported = service.export_style_analysis(reviewed.analysis_id, destination)
    assert exported == destination and destination.is_file()
    original = destination.read_bytes()
    with pytest.raises(FileExistsError):
        service.export_style_analysis(reviewed.analysis_id, destination)
    assert destination.read_bytes() == original


def test_style_report_review_rejects_a_changed_pinned_source(tmp_path: Path) -> None:
    service, source = _style_service(tmp_path)
    report = service.create_style_analysis("jiangnan_mc_classic")
    source.write_bytes(source.read_bytes() + b"changed after analysis")

    with pytest.raises(AssetIntegrityError, match="SHA-256 mismatch"):
        service.review_style_analysis(report.analysis_id, reviewer="MOSS", decision="verified")

    current = service.get_style_analysis(report.analysis_id)
    assert current.revision == report.revision
    assert current.status == "candidate"


def test_style_report_handles_empty_regions_and_counts_overlaps_per_region(tmp_path: Path) -> None:
    service = _multi_region_style_service(tmp_path)

    report = service.create_style_analysis("jiangnan_mc_classic")
    asset_report = report.analysis["assets"][0]
    regions = {item["region_name"]: item for item in asset_report["regions"]}

    assert regions["empty"]["dimensions"] == [2, 2, 2]
    assert regions["empty"]["block_count"] == 0
    assert regions["empty"]["layer_profile"] == {}
    assert regions["empty"]["block_palette"] == {}
    assert regions["overlap-a"]["block_count"] == regions["overlap-b"]["block_count"] == 1
    assert asset_report["block_count"] == 2
    assert asset_report["annotations"]["unclassified_occupied_blocks"] == 2
