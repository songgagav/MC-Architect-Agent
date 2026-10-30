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
from jiangnan_agent.parameters import (
    ParameterConflictError,
    ParameterSchema,
    ResolvedParameters,
    load_parameter_schema,
    resolve_parameters,
)
from jiangnan_agent.generators.hall import HallParameters


def test_knowledge_rules_keep_source_scope_and_evidence_distinct() -> None:
    knowledge = load_knowledge_base()

    assert knowledge.version == 4
    assert {rule.evidence_kind for rule in knowledge.rules} >= {
        EvidenceKind.LITERATURE_FACT,
        EvidenceKind.MINECRAFT_ADAPTATION,
        EvidenceKind.USER_PREFERENCE,
    }
    assert all(rule.source_id in knowledge.sources for rule in knowledge.rules)
    assert all(rule.applicable_regions and rule.building_types and rule.scope for rule in knowledge.rules)


def test_knowledge_v1_v3_compatibility_and_v4_default_are_preserved() -> None:
    default = load_knowledge_base()
    version_one = load_knowledge_base(1)
    version_two = load_knowledge_base(2)
    version_three = load_knowledge_base(3)

    assert default.version == 4
    assert version_one.version == 1 and not version_one.regions
    assert version_two.version == 2 and not version_two.regions
    assert version_three.version == 3 and version_three.regions
    assert version_two.rules_for(region="cn.anhui.south.huizhou")
    assert not version_three.rules_for(region="jiaxing_huzhou_water_towns")


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


def test_knowledge_v3_activates_only_huizhou_and_suzhou_profiles() -> None:
    knowledge = load_knowledge_base(3)
    active = {region_id for region_id, profile in knowledge.regions.items() if profile.status == "active"}
    catalog_only = {
        region_id for region_id, profile in knowledge.regions.items() if profile.status == "catalog_only"
    }

    assert knowledge.version == 3
    assert active == {"huizhou_core", "jiangnan_suzhou"}
    assert catalog_only >= {
        "jiaxing_huzhou_water_towns",
        "ningbo_east_zhejiang",
        "yangzhou_canal",
        "shanghai_songjiang",
    }
    assert knowledge.rules_for(region="huizhou_core")
    assert knowledge.rules_for(region="jiangnan_suzhou")
    assert not knowledge.rules_for(region="jiaxing_huzhou_water_towns")
    assert not knowledge.rules_for(region="unregistered_region")


def test_knowledge_v3_records_complete_source_and_rule_verification_metadata() -> None:
    knowledge = load_knowledge_base(3)

    assert knowledge.sources
    for source in knowledge.sources.values():
        assert source.publisher_or_author
        assert source.date_note
        assert source.section_or_page
        assert source.verification_level
        assert source.accessed_date
        assert source.locator or source.url or source.doi or source.isbn
    for rule in knowledge.rules:
        assert rule.verification_level
        assert rule.status in {"active", "pending_verification"}
        assert rule.applicable_regions
        source = knowledge.sources[rule.source_id]
        assert source.title
        if rule.evidence_kind is EvidenceKind.LITERATURE_FACT and rule.status == "active":
            assert source.url or source.doi or source.isbn
            assert source.publication_date or "not stated" in source.date_note.lower()


def test_knowledge_v3_pending_rules_are_hidden_unless_explicitly_requested() -> None:
    knowledge = load_knowledge_base(3)
    pending = [rule for rule in knowledge.rules if rule.status == "pending_verification"]

    assert pending
    assert all(rule.verification_level == "pending_full_text" for rule in pending)
    assert not any(rule.status == "pending_verification" for rule in knowledge.rules_for(region="huizhou_core"))
    assert any(
        rule.status == "pending_verification"
        for rule in knowledge.rules_for(region="huizhou_core", include_pending=True)
    )


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
    assert all(asset.version == 4 and asset.knowledge_base_version == 4 for asset in assets.values())
    assert all(asset.version == 1 and asset.knowledge_base_version == 1 for asset in legacy_assets.values())
    assert all(asset.parameter_schema_version == 3 for asset in assets.values())
    assert all(asset.parameter_schema_version == 1 for asset in legacy_assets.values())
    assert {asset.version for asset in list_assets(version=2)} == {1, 2}
    assert {asset.version for asset in list_assets(version=3)} == {1, 2, 3}
    assert {asset.version for asset in list_assets(version=4)} == {1, 2, 3, 4}
    assert assets["hall"].region_ids == ("huizhou_core",)
    assert assets["corridor"].region_ids == ("huizhou_core", "jiangnan_suzhou")
    assert all(asset.region_association_kind == "design_target" for asset in assets.values())
    assert all(asset.minecraft_version == "1.21.5" for asset in assets.values())
    assert assets["hall"].knowledge_rule_ids == ("hui-village-layout-and-architecture",)
    assert assets["corridor"].knowledge_rule_ids == (
        "hui-street-building-water-context",
        "suzhou-garden-elements-context",
    )
    assert all("does not validate historical authenticity" in asset.region_association_note for asset in assets.values())
    with pytest.raises(ValueError, match="unknown asset ID.*version 5"):
        module_from_asset("hall-future", "jiangnan.hall", asset_version=5)


def test_parameter_schema_marks_independent_derived_hard_and_soft_rules() -> None:
    schema = load_parameter_schema("jiangnan.hall")

    assert {"building_type", "bay_count", "bay_spacing", "roof_profile", "materials"} <= set(
        schema.independent_fields
    )
    assert {"eave_profile", "ridge_profile", "material_palette"} <= set(schema.independent_fields)
    assert {"plinth_width", "bounds_width"} <= set(schema.derived_fields)
    assert schema.hard_constraints[0]["validator"] == "HallParameters"
    assert schema.soft_constraints[0]["rule_id"] == "hall-front-window-width"
    assert schema.version == 3
    assert set(schema.provenance_categories) == {
        "user_input",
        "literature_reference",
        "survey_data",
        "derived",
        "minecraft_adaptation",
    }
    assert set(schema.field_provenance) == set(schema.independent_fields)
    assert schema.field_provenance["bay_count"]["default_category"] == "minecraft_adaptation"
    assert schema.field_provenance["bay_count"]["source_ids"] == ("generator.hall.v1",)


def test_current_assets_bind_to_their_declared_schema_versions() -> None:
    for asset in list_assets():
        if asset.version != 4:
            continue
        schema = load_parameter_schema(asset.asset_id, asset_version=asset.version)
        assert schema.schema_id == asset.parameter_schema_id
        assert schema.version == asset.parameter_schema_version == 3
        assert schema.kind == asset.kind


def test_parameter_schema_rejects_malformed_provenance_policy_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from jiangnan_agent.parameters import registry as parameter_registry

    schema_dir = tmp_path / "parameters" / "v3"
    schema_dir.mkdir(parents=True)
    schema = json.loads(
        (Path(parameter_registry.__file__).parent / "v3" / "hall.json").read_text(encoding="utf-8")
    )
    schema["field_provenance"]["bay_count"] = "invalid policy"
    (schema_dir / "hall.json").write_text(json.dumps(schema), encoding="utf-8")
    monkeypatch.setattr(parameter_registry, "__file__", str(tmp_path / "parameters" / "registry.py"))

    with pytest.raises(ValueError, match="field provenance policy.*JSON object"):
        parameter_registry.load_parameter_schema("jiangnan.hall")


def test_parameter_schema_rejects_non_derived_provenance_category(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from jiangnan_agent.parameters import registry as parameter_registry

    schema_dir = tmp_path / "parameters" / "v3"
    schema_dir.mkdir(parents=True)
    schema = json.loads(
        (Path(parameter_registry.__file__).parent / "v3" / "hall.json").read_text(encoding="utf-8")
    )
    schema["derived_provenance"]["category"] = "user_input"
    (schema_dir / "hall.json").write_text(json.dumps(schema), encoding="utf-8")
    monkeypatch.setattr(parameter_registry, "__file__", str(tmp_path / "parameters" / "registry.py"))

    with pytest.raises(ValueError, match="derived_provenance must use the derived category"):
        parameter_registry.load_parameter_schema("jiangnan.hall")


def test_parameter_model_constructors_keep_legacy_call_shapes() -> None:
    loaded = load_parameter_schema("jiangnan.hall", version=1, asset_version=1)
    schema = ParameterSchema(
        loaded.schema_id,
        loaded.version,
        loaded.asset_id,
        loaded.kind,
        loaded.defaults,
        loaded.independent_fields,
        loaded.derived_fields,
        loaded.generator_fields,
        loaded.adapter_fields,
        loaded.legacy_aliases,
        loaded.hard_constraints,
        loaded.soft_constraints,
    )
    resolved = resolve_parameters("jiangnan.hall", asset_version=1)
    legacy_result = ResolvedParameters(
        resolved.asset_id,
        resolved.schema_version,
        resolved.normalized_inputs,
        resolved.derived_parameters,
        resolved.generator_parameters,
        resolved.adapter_options,
        resolved.warnings,
    )

    assert schema.field_provenance["bay_count"]["default_category"] == "minecraft_adaptation"
    assert not legacy_result.parameter_provenance
    assert not legacy_result.derived_provenance


def test_parameter_resolution_separates_user_defaults_and_derived_values() -> None:
    resolved = resolve_parameters("jiangnan.hall", {"bay_count": 5})

    assert resolved.parameter_provenance["bay_count"]["category"] == "user_input"
    assert resolved.parameter_provenance["bay_spacing"]["category"] == "minecraft_adaptation"
    assert resolved.parameter_provenance["bay_spacing"]["source_ids"] == ("generator.hall.v1",)
    assert resolved.derived_provenance["plinth_width"]["category"] == "derived"
    assert resolved.derived_provenance["plinth_width"]["expression"] == "bay_count * bay_spacing + 1"
    assert resolved.derived_provenance["plinth_width"]["source_ids"] == ("resolver.parameters.v3",)


def test_parameter_source_overrides_must_be_allowed_and_cited() -> None:
    with pytest.raises(ValueError, match="not an accepted provenance category"):
        resolve_parameters(
            "jiangnan.hall",
            {"bay_count": 5},
            provenance={
                "bay_count": {
                    "category": "literature_reference",
                    "source_id": "unesco.xidi-hongcun.ouval",
                    "rule_id": "hui-village-layout-and-architecture",
                }
            },
        )
    with pytest.raises(ValueError, match="unsupported provenance category"):
        resolve_parameters("jiangnan.hall", {"bay_count": 5}, provenance={"bay_count": {"category": "guess"}})
    with pytest.raises(ValueError, match="not an accepted provenance category"):
        resolve_parameters("jiangnan.corridor", {"length": 15}, provenance={"length": {"category": "survey_data"}})


def test_parameter_provenance_is_recorded_through_module_edit_and_save(tmp_path: Path) -> None:
    module = module_from_asset("hall-main", "jiangnan.hall", {"bay_count": 3})
    assert module.metadata["parameter_provenance"]["bay_count"]["category"] == "user_input"
    assert module.metadata["parameter_provenance"]["bay_spacing"]["category"] == "minecraft_adaptation"
    assert module.metadata["derived_provenance"]["plinth_width"]["category"] == "derived"

    project = JiangnanProject(name="Provenance hall", assembly=Assembly((module,)))
    ProjectEditor(project).regenerate_module("hall-main", {"bay_count": 5}, "Resize hall")
    destination = tmp_path / "provenance.jap.json"
    save_project(project, destination)
    reopened = load_project(destination)
    edited = reopened.assembly.modules["hall-main"]
    assert edited.metadata["asset_version"] == 4
    assert edited.metadata["parameter_provenance"]["bay_count"]["category"] == "user_input"
    assert edited.metadata["parameter_provenance"]["bay_spacing"]["category"] == "minecraft_adaptation"
    assert edited.metadata["parameter_provenance"]["bay_spacing"]["source_ids"] == ("generator.hall.v1",)
    assert edited.metadata["derived_provenance"]["plinth_width"]["category"] == "derived"


def test_hall_schema_defaults_match_existing_generator_defaults() -> None:
    schema = load_parameter_schema("jiangnan.hall")
    resolved = resolve_parameters("jiangnan.hall")
    existing = HallParameters()

    assert schema.defaults["depth"] == existing.depth
    assert schema.defaults["roof_profile"]["ridge_height"] == existing.roof_rise
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
    assert resolved.schema_version == 3


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
        resolve_parameters("jiangnan.hall", schema_version=4)
    with pytest.raises(ValueError, match="sampled roof section"):
        resolve_parameters(
            "jiangnan.hall",
            {"roof_section": {"profile": "symmetric_gable", "rise": 3}, "depth": 5},
        )
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
    asset_two = module_from_asset("hall-v2", "jiangnan.hall", {"bay_count": 5}, asset_version=2)

    assert first.model.blocks == second.model.blocks
    assert first.model.blocks == legacy.model.blocks
    assert first.parameters == second.parameters
    assert first.metadata["asset_id"] == "jiangnan.hall"
    assert first.metadata["asset_version"] == 4
    assert first.metadata["knowledge_base_version"] == 4
    assert legacy.metadata["asset_version"] == 1
    assert legacy.metadata["knowledge_base_version"] == 1
    assert first.metadata["parameter_schema_version"] == 3
    assert first.metadata["parameter_config"]["bay_count"] == 5
    assert first.model.bounds.size == (28, 10, 9)
    assert first.metadata["minecraft_version"] == "1.21.5"
    assert first.metadata["region_ids"] == ("huizhou_core",)
    assert first.metadata["region_association_kind"] == "design_target"
    assert "does not validate historical authenticity" in first.metadata["region_association_note"]
    assert first.metadata["knowledge_context_rule_ids"] == ("hui-village-layout-and-architecture",)
    assert asset_two.model.blocks == legacy.model.blocks
    assert asset_two.model.blocks == first.model.blocks
    assert asset_two.metadata["asset_version"] == 2
    assert asset_two.metadata["knowledge_base_version"] == 2
    assert "parameter_provenance" not in asset_two.metadata
    assert "region_ids" not in asset_two.metadata


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
    assert loaded.metadata["parameter_schema_version"] == 3

    project = JiangnanProject(name="Versioned hall", assembly=loaded_assembly)
    ProjectEditor(project).regenerate_module("hall-main", {"bay_count": 5}, "Set five bays")
    regenerated = project.assembly.modules["hall-main"]
    assert regenerated.metadata["asset_id"] == "jiangnan.hall"
    assert regenerated.metadata["parameter_schema_version"] == 3
    assert regenerated.metadata["parameter_config"]["bay_count"] == 5
    assert regenerated.transform_steps == loaded.transform_steps
    destination = tmp_path / "versioned-hall.jap.json"
    save_project(project, destination)
    reopened = load_project(destination)
    assert reopened.assembly.modules["hall-main"].metadata["asset_version"] == 4
    assert reopened.assembly.modules["hall-main"].metadata["parameter_config"]["bay_count"] == 5


def test_roof_profiles_survive_project_roundtrip_and_regeneration(tmp_path: Path) -> None:
    profile = {
        "roof_profile": {"ridge_height": 2},
        "eave_profile": {
            "side_overhang": 0,
            "gable_end_treatment": "hard_gable",
            "gable_end_projection": 0,
        },
        "ridge_profile": {"cap_width": 1, "cap_height": 1},
        "material_palette": {
            "roof_stair": "minecraft:stone_brick_stairs",
            "eaves": "minecraft:dark_oak_slab[type=bottom,waterlogged=false]",
            "ridge": "minecraft:polished_blackstone_bricks",
        },
    }
    module = module_from_asset("hall-profiled", "jiangnan.hall", profile)
    moved = rotate_module(translate_module(module, (12, 0, -4)), 1)
    loaded_assembly = assembly_from_dict(assembly_to_dict(Assembly((moved,))))
    loaded = loaded_assembly.modules["hall-profiled"]
    assert loaded.metadata["parameter_config"]["roof_profile"]["ridge_height"] == 2
    assert loaded.metadata["parameter_config"]["material_palette"]["ridge"] == (
        "minecraft:polished_blackstone_bricks"
    )

    project = JiangnanProject(name="Profiled hall", assembly=loaded_assembly)
    ProjectEditor(project).regenerate_module("hall-profiled", {"bay_count": 5}, "Resize profiled hall")
    regenerated = project.assembly.modules["hall-profiled"]
    assert regenerated.metadata["parameter_config"]["roof_profile"]["ridge_height"] == 2
    assert regenerated.metadata["parameter_config"]["eave_profile"]["gable_end_treatment"] == "hard_gable"
    assert regenerated.metadata["parameter_config"]["material_palette"]["ridge"] == (
        "minecraft:polished_blackstone_bricks"
    )
    assert regenerated.transform_steps == loaded.transform_steps

    destination = tmp_path / "profiled-hall.jap.json"
    save_project(project, destination)
    reopened = load_project(destination)
    reopened_module = reopened.assembly.modules["hall-profiled"]
    assert reopened_module.metadata["parameter_config"]["roof_profile"]["ridge_height"] == 2
    assert reopened_module.metadata["parameter_config"]["material_palette"]["ridge"] == (
        "minecraft:polished_blackstone_bricks"
    )
    editor = ProjectEditor(reopened)
    assert editor.undo()
    assert reopened.assembly.modules["hall-profiled"].model.blocks == loaded.model.blocks
    assert editor.redo()
    assert reopened.assembly.modules["hall-profiled"].model.blocks == regenerated.model.blocks


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


def test_asset_registry_rejects_unknown_region_rule_and_catalog_version_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from jiangnan_agent.assets import registry

    catalog_dir = tmp_path / "assets" / "v3"
    catalog_dir.mkdir(parents=True)
    catalog = json.loads((Path(registry.__file__).parent / "v3" / "assets.json").read_text(encoding="utf-8"))
    catalog["assets"][-2]["knowledge_rule_ids"] = ["missing.rule"]
    (catalog_dir / "assets.json").write_text(json.dumps(catalog), encoding="utf-8")
    monkeypatch.setattr(registry, "__file__", str(tmp_path / "assets" / "registry.py"))
    registry.list_assets.cache_clear()

    try:
        with pytest.raises(ValueError, match="unknown or inactive knowledge rule"):
            registry.list_assets()
    finally:
        registry.list_assets.cache_clear()


def test_v3_asset_generator_source_must_be_project_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from jiangnan_agent.assets import registry

    catalog_dir = tmp_path / "assets" / "v3"
    catalog_dir.mkdir(parents=True)
    catalog = json.loads((Path(registry.__file__).parent / "v3" / "assets.json").read_text(encoding="utf-8"))
    catalog["assets"][-2]["source_id"] = "unesco.xidi-hongcun.ouval"
    (catalog_dir / "assets.json").write_text(json.dumps(catalog), encoding="utf-8")
    monkeypatch.setattr(registry, "__file__", str(tmp_path / "assets" / "registry.py"))
    registry.list_assets.cache_clear()

    try:
        with pytest.raises(ValueError, match="must cite its generator source code"):
            registry.list_assets()
    finally:
        registry.list_assets.cache_clear()


def test_parameter_schema_must_match_registered_asset_kind_and_schema_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from jiangnan_agent.parameters import registry

    schema_dir = tmp_path / "parameters" / "v3"
    schema_dir.mkdir(parents=True)
    schema = json.loads((Path(registry.__file__).parent / "v3" / "hall.json").read_text(encoding="utf-8"))
    schema["kind"] = "corridor"
    schema["schema_id"] = "corridor"
    (schema_dir / "hall.json").write_text(json.dumps(schema), encoding="utf-8")
    monkeypatch.setattr(registry, "__file__", str(tmp_path / "parameters" / "registry.py"))

    with pytest.raises(ValueError, match="schema.*asset/version/kind"):
        registry.load_parameter_schema("jiangnan.hall")
