from __future__ import annotations

import json
from pathlib import Path
import pytest

from jiangnan_agent.assembly.transforms import rotate_module, translate_module
from jiangnan_agent.assembly.model import Assembly
from jiangnan_agent.assets import list_assets, module_from_asset
from jiangnan_agent.io.assembly_json import assembly_from_dict, assembly_to_dict
from jiangnan_agent.io.project_editor import ProjectEditor
from jiangnan_agent.io.project_generation import generate_project_model
from jiangnan_agent.io.project_json import JiangnanProject, load_project, save_project
from jiangnan_agent.knowledge import EvidenceKind, load_knowledge_base
from jiangnan_agent.parameters import ParameterConflictError, load_parameter_schema, resolve_parameters
from jiangnan_agent.generators.hall import HallParameters


def test_knowledge_rules_keep_source_scope_and_evidence_distinct() -> None:
    knowledge = load_knowledge_base()

    assert knowledge.version == 2
    assert {rule.evidence_kind for rule in knowledge.rules} >= {
        EvidenceKind.LITERATURE_FACT,
        EvidenceKind.MINECRAFT_ADAPTATION,
        EvidenceKind.USER_PREFERENCE,
    }
    assert all(rule.source_id in knowledge.sources for rule in knowledge.rules)
    assert all(rule.applicable_regions and rule.building_types and rule.scope for rule in knowledge.rules)


def test_knowledge_v1_remains_immutable_and_v2_rules_are_scoped_to_huizhou() -> None:
    version_one = load_knowledge_base(1)
    version_two = load_knowledge_base(2)
    rules = {rule.rule_id: rule for rule in version_two.rules}

    assert version_one.version == 1
    assert not [rule for rule in version_one.rules if rule.evidence_kind is EvidenceKind.LITERATURE_FACT]
    assert rules["hui-location-xidi-hongcun"].source_id == "unesco.xidi-hongcun.ouval"
    assert rules["hui-materials-and-gable-decoration"].source_id == "huangshan.gazette.hui-residence-elements.2021"
    assert rules["hui-materials-and-gable-decoration"].confidence.value == "medium"
    assert rules["hui-materials-and-gable-decoration"].applicable_regions == ("cn.anhui.south.huizhou",)
    assert version_two.sources["unesco.xidi-hongcun.ouval"].locator == "https://whc.unesco.org/en/list/1002/"
    assert version_two.sources["huangshan.gazette.hui-residence-elements.2021"].locator == (
        "https://www.huangshan.gov.cn/zjhs/rwhz/hpjz/8294057.html"
    )
    assert rules["user-selected-style-scope"].evidence_kind is EvidenceKind.USER_PREFERENCE
    assert rules["template-fangtang-reference"].evidence_kind is EvidenceKind.USER_PREFERENCE
    assert version_two.rules_for(
        EvidenceKind.LITERATURE_FACT,
        region="cn.anhui.south.huizhou",
        building_type="residential_building",
    )
    assert not version_two.rules_for(region="cn.zhejiang.jiaxing.xitang")


def test_asset_registry_describes_existing_hall_and_corridor_anchors() -> None:
    assets = {asset.kind: asset for asset in list_assets()}
    legacy_assets = {asset.kind: asset for asset in list_assets(version=1)}

    assert set(assets) == {"hall", "corridor"}
    assert assets["hall"].asset_id == "jiangnan.hall"
    assert assets["hall"].anchor_interfaces == (
        "front",
        "rear",
        "court_west_front",
        "court_west_rear",
        "court_east_front",
        "court_east_rear",
    )
    assert assets["corridor"].anchor_interfaces == ("start", "end")
    assert all(asset.version == 2 and asset.knowledge_base_version == 2 for asset in assets.values())
    assert all(asset.version == 1 and asset.knowledge_base_version == 1 for asset in legacy_assets.values())
    assert all(asset.parameter_schema_version == 1 for asset in (*assets.values(), *legacy_assets.values()))
    with pytest.raises(ValueError, match="unknown asset ID.*version 3"):
        module_from_asset("hall-future", "jiangnan.hall", asset_version=3)


def test_parameter_schema_marks_independent_derived_hard_and_soft_rules() -> None:
    schema = load_parameter_schema("jiangnan.hall")

    assert {"building_type", "bay_count", "bay_spacing", "roof_section", "materials"} <= set(
        schema.independent_fields
    )
    assert {"plinth_width", "bounds_width"} <= set(schema.derived_fields)
    assert schema.hard_constraints[0]["validator"] == "HallParameters"
    assert schema.soft_constraints[0]["rule_id"] == "hall-front-window-width"


def test_hall_schema_defaults_match_existing_generator_defaults() -> None:
    schema = load_parameter_schema("jiangnan.hall")
    resolved = resolve_parameters("jiangnan.hall")
    existing = HallParameters()

    assert schema.defaults["depth"] == existing.depth
    assert schema.defaults["roof_section"]["rise"] == existing.roof_rise
    assert resolved.generator_parameters.depth == existing.depth
    assert resolved.generator_parameters.roof_rise == existing.roof_rise


def test_hall_parameters_resolve_to_existing_generator_and_derived_footprint() -> None:
    resolved = resolve_parameters(
        "jiangnan.hall",
        {
            "bay_count": 5,
            "bay_spacing": 6,
            "roof_section": {"profile": "symmetric_gable", "rise": 3},
            "style": "user-labeled-suzhou",
        },
    )

    assert resolved.generator_parameters.bay_count == 5
    assert resolved.generator_parameters.bay_width == 6
    assert resolved.generator_parameters.roof_rise == 3
    assert resolved.normalized_inputs["style"] == "user-labeled-suzhou"
    assert resolved.derived_parameters["plinth_width"] == 31
    assert resolved.derived_parameters["plinth_depth"] == 7
    assert resolved.derived_parameters["bounds_width"] == 33
    assert resolved.derived_parameters["bounds_depth"] == 9
    assert resolved.schema_version == 1


def test_corridor_derived_grid_matches_existing_post_placement_rule() -> None:
    resolved = resolve_parameters("jiangnan.corridor", {"length": 11, "column_spacing": 3})

    assert resolved.generator_parameters.length == 11
    assert resolved.derived_parameters["post_x_positions"] == (0, 3, 6, 9, 10)
    assert resolved.derived_parameters["post_count_per_side"] == 5


def test_legacy_and_canonical_parameter_names_conflict_explicitly() -> None:
    with pytest.raises(ParameterConflictError, match="bay_width.*bay_spacing"):
        resolve_parameters("jiangnan.hall", {"bay_width": 5, "bay_spacing": 6})

    with pytest.raises(ParameterConflictError, match="roof_rise.*roof_section"):
        resolve_parameters(
            "jiangnan.hall",
            {"roof_rise": 2, "roof_section": {"profile": "symmetric_gable", "rise": 3}},
        )


def test_hard_constraints_unknown_fields_and_versions_are_rejected() -> None:
    with pytest.raises(ValueError, match="odd.*at least 3|bay_count"):
        resolve_parameters("jiangnan.hall", {"bay_count": 4})
    with pytest.raises(ValueError, match="unknown parameter"):
        resolve_parameters("jiangnan.hall", {"mystery": 1})
    with pytest.raises(ValueError, match="building_type"):
        resolve_parameters("jiangnan.hall", {"building_type": "corridor"})
    with pytest.raises(ValueError, match="unsupported.*schema version"):
        resolve_parameters("jiangnan.hall", schema_version=2)
    with pytest.raises(ValueError, match="half the hall depth"):
        resolve_parameters("jiangnan.hall", {"roof_section": {"rise": 3}, "depth": 5})
    with pytest.raises(ValueError, match="odd for a centered roof ridge"):
        resolve_parameters("jiangnan.corridor", {"width": 4})


def test_supplied_derived_values_must_match_deterministic_result() -> None:
    with pytest.raises(ParameterConflictError, match="plinth_width"):
        resolve_parameters("jiangnan.hall", {"bay_count": 5, "derived": {"plinth_width": 999}})


def test_soft_constraint_is_a_minecraft_warning_and_does_not_block_generation() -> None:
    resolved = resolve_parameters("jiangnan.hall", {"bay_spacing": 4})

    assert resolved.generator_parameters.bay_width == 4
    assert len(resolved.warnings) == 1
    assert resolved.warnings[0].rule_id == "hall-front-window-width"
    assert resolved.warnings[0].evidence_kind is EvidenceKind.MINECRAFT_ADAPTATION


def test_asset_modules_are_deterministic_and_record_catalog_versions() -> None:
    first = module_from_asset("hall-main", "jiangnan.hall", {"bay_count": 5})
    second = module_from_asset("hall-main", "jiangnan.hall", {"bay_count": 5})
    legacy = module_from_asset("hall-legacy", "jiangnan.hall", {"bay_count": 5}, asset_version=1)

    assert first.model.blocks == second.model.blocks
    assert first.model.blocks == legacy.model.blocks
    assert first.parameters == second.parameters
    assert first.metadata["asset_id"] == "jiangnan.hall"
    assert first.metadata["asset_version"] == 2
    assert first.metadata["knowledge_base_version"] == 2
    assert legacy.metadata["asset_version"] == 1
    assert legacy.metadata["knowledge_base_version"] == 1
    assert first.metadata["parameter_schema_version"] == 1
    assert first.metadata["parameter_config"]["bay_count"] == 5
    assert first.model.bounds.size == (28, 10, 9)


def test_editing_an_asset_v1_module_keeps_its_recorded_knowledge_version() -> None:
    legacy = module_from_asset("hall-legacy", "jiangnan.hall", {"bay_count": 3}, asset_version=1)
    project = JiangnanProject(name="Legacy asset", assembly=Assembly((legacy,)))

    ProjectEditor(project).regenerate_module("hall-legacy", {"bay_count": 5}, "Resize legacy hall")
    edited = project.assembly.modules["hall-legacy"]

    assert edited.metadata["asset_version"] == 1
    assert edited.metadata["knowledge_base_version"] == 1
    assert edited.parameters["bay_count"] == 5
    assert edited.model.blocks != legacy.model.blocks


def test_metadata_survives_serialization_transforms_and_versioned_edits(tmp_path: Path) -> None:
    module = module_from_asset("hall-main", "jiangnan.hall", {"bay_count": 3})
    moved = rotate_module(translate_module(module, (12, 0, -4)), 1)
    loaded_assembly = assembly_from_dict(assembly_to_dict(Assembly((moved,))))
    loaded = loaded_assembly.modules["hall-main"]
    assert loaded.metadata["parameter_schema_version"] == 1

    project = JiangnanProject(name="Versioned hall", assembly=loaded_assembly)
    ProjectEditor(project).regenerate_module("hall-main", {"bay_count": 5}, "Set five bays")
    regenerated = project.assembly.modules["hall-main"]
    assert regenerated.metadata["asset_id"] == "jiangnan.hall"
    assert regenerated.metadata["parameter_schema_version"] == 1
    assert regenerated.metadata["parameter_config"]["bay_count"] == 5
    assert regenerated.transform_steps == loaded.transform_steps
    destination = tmp_path / "versioned-hall.jap.json"
    save_project(project, destination)
    reopened = load_project(destination)
    assert reopened.assembly.modules["hall-main"].metadata["asset_version"] == 2
    assert reopened.assembly.modules["hall-main"].metadata["parameter_config"]["bay_count"] == 5


def test_old_module_and_project_records_without_metadata_remain_compatible() -> None:
    from jiangnan_agent.assembly.adapters import hall_module

    raw_assembly = assembly_to_dict(Assembly((hall_module("hall-main"),)))
    assert "metadata" not in raw_assembly["modules"][0]
    loaded = JiangnanProject.from_dict(
        {"format_version": 2, "name": "Legacy v2", "assembly": raw_assembly}
    )
    module = next(iter(loaded.assembly.modules.values()))
    assert dict(module.metadata) == {}
    assert "metadata" not in loaded.to_dict()["assembly"]["modules"][0]

    v1_path = Path(__file__).resolve().parents[1] / "examples" / "three_bay_hall.jap.json"
    legacy_v1 = JiangnanProject.from_dict(json.loads(v1_path.read_text(encoding="utf-8")))
    assert legacy_v1.format_version == 2
    assert legacy_v1.assembly.modules == {}


def test_assembly_generation_uses_recorded_voxels_and_ignores_legacy_settings() -> None:
    module = module_from_asset("hall-main", "jiangnan.hall", {"bay_count": 5})
    project = JiangnanProject(
        name="Assembly takes precedence",
        settings={"building": {"type": "simple_house", "width": 5, "length": 5}},
        assembly=Assembly((module,)),
    )

    assert generate_project_model(project).blocks == module.model.blocks


def test_asset_registry_rejects_unregistered_provenance_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from jiangnan_agent.assets import registry

    catalog_dir = tmp_path / "assets" / "v1"
    catalog_dir.mkdir(parents=True)
    catalog = json.loads((Path(registry.__file__).parent / "v1" / "assets.json").read_text(encoding="utf-8"))
    catalog["assets"][0]["source_id"] = "missing.source"
    (catalog_dir / "assets.json").write_text(json.dumps(catalog), encoding="utf-8")
    monkeypatch.setattr(registry, "__file__", str(tmp_path / "assets" / "registry.py"))
    registry.list_assets.cache_clear()

    try:
        with pytest.raises(ValueError, match="unknown knowledge source"):
            registry.list_assets()
    finally:
        registry.list_assets.cache_clear()


def test_parameter_schema_must_match_registered_asset_kind_and_schema_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from jiangnan_agent.parameters import registry

    schema_dir = tmp_path / "parameters" / "v1"
    schema_dir.mkdir(parents=True)
    schema = json.loads((Path(registry.__file__).parent / "v1" / "hall.json").read_text(encoding="utf-8"))
    schema["kind"] = "corridor"
    schema["schema_id"] = "corridor"
    (schema_dir / "hall.json").write_text(json.dumps(schema), encoding="utf-8")
    monkeypatch.setattr(registry, "__file__", str(tmp_path / "parameters" / "registry.py"))

    with pytest.raises(ValueError, match="schema.*asset/version/kind"):
        registry.load_parameter_schema("jiangnan.hall")
