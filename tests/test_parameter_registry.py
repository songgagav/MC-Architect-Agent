from __future__ import annotations

from dataclasses import asdict

import pytest

from jiangnan_agent.assets import list_assets, module_from_asset
from jiangnan_agent.generators.roof_profiles import EaveProfile, RidgeProfile, RoofProfile
from jiangnan_agent.knowledge import load_knowledge_base
from jiangnan_agent.parameters import (
    ParameterConflictError,
    load_parameter_schema,
    resolve_parameters,
)
from jiangnan_agent.parameters import registry as parameter_registry


def test_current_asset_catalog_v4_keeps_pinned_versions_readable() -> None:
    by_kind = {asset.kind: asset for asset in list_assets()}

    assert {kind: asset.version for kind, asset in by_kind.items()} == {"hall": 4, "corridor": 4}
    assert all(asset.parameter_schema_version == 3 for asset in by_kind.values())
    assert all(asset.knowledge_base_version == 4 for asset in by_kind.values())
    assert {asset.version for asset in list_assets(version=3)} == {1, 2, 3}
    assert {asset.version for asset in list_assets(version=4)} == {1, 2, 3, 4}
    assert tuple(asset for asset in list_assets(version=4) if asset.version <= 3) == list_assets(version=3)
    for asset_version, schema_version in ((1, 1), (2, 1), (3, 2), (4, 3)):
        for asset_id in ("jiangnan.hall", "jiangnan.corridor"):
            schema = load_parameter_schema(asset_id, asset_version=asset_version)
            assert schema.version == schema_version


def test_v4_knowledge_adds_code_sources_without_enabling_new_regions() -> None:
    knowledge = load_knowledge_base(4)
    knowledge_v3 = load_knowledge_base(3)
    active = {key for key, profile in knowledge.regions.items() if profile.status.value == "active"}
    catalog_only = {key for key, profile in knowledge.regions.items() if profile.status.value == "catalog_only"}

    assert knowledge.version == 4
    assert {"generator.roof-eaves.v2", "resolver.parameters.v3"} <= set(knowledge.sources)
    assert knowledge.sources["generator.roof-eaves.v2"].source_type == "project_code"
    assert knowledge.sources["resolver.parameters.v3"].source_type == "project_code"
    assert knowledge.rules == knowledge_v3.rules
    assert knowledge.regions == knowledge_v3.regions
    assert all(knowledge.sources[key] == value for key, value in knowledge_v3.sources.items())
    assert active == {"huizhou_core", "jiangnan_suzhou"}
    assert catalog_only >= {
        "jiaxing_huzhou_water_towns",
        "ningbo_east_zhejiang",
        "yangzhou_canal",
        "shanghai_songjiang",
    }
    assert not knowledge.rules_for(region="jiaxing_huzhou_water_towns")


def test_v3_schema_contains_profiles_provenance_and_parameter_groups() -> None:
    hall = load_parameter_schema("jiangnan.hall", asset_version=4)
    corridor = load_parameter_schema("jiangnan.corridor", asset_version=4)

    assert hall.version == corridor.version == 3
    assert {"roof_profile", "eave_profile", "ridge_profile", "material_palette"} <= set(hall.defaults)
    assert {"roof_profile", "eave_profile", "ridge_profile", "material_palette"} <= set(corridor.defaults)
    assert hall.field_provenance["roof_profile"]["default_category"] == "minecraft_adaptation"
    assert hall.field_provenance["roof_profile"]["source_ids"] == ("generator.roof-eaves.v2",)
    assert hall.derived_provenance["source_id"] == "resolver.parameters.v3"
    assert "roof_rise" in hall.legacy_aliases
    assert "roof_section.rise" in hall.legacy_aliases
    assert hall.defaults["roof_profile"]["ridge_height"] == 3
    assert corridor.defaults["roof_profile"]["ridge_height"] == 1


def test_three_versioned_roof_presets_are_available_as_typed_values() -> None:
    list_roof_presets = getattr(parameter_registry, "list_roof_presets")
    load_roof_preset = getattr(parameter_registry, "load_roof_preset")
    assert list_roof_presets() == (
        "gray_brick_layered",
        "jiangnan_dark_tile",
        "warm_spruce_garden",
    )
    dark = load_roof_preset("jiangnan_dark_tile")
    gray = load_roof_preset("gray_brick_layered")
    warm = load_roof_preset("warm_spruce_garden")

    assert dark.roof_profile == RoofProfile(ridge_height=3)
    assert dark.eave_profile.gable_end_treatment == "hard_gable"
    assert dark.ridge_profile == RidgeProfile(cap_width=1, cap_height=1)
    assert gray.roof_profile.ridge_height == 2
    assert gray.eave_profile.thickness == 2
    assert warm.roof_profile.ridge_height == 1
    assert warm.eave_profile.gable_end_treatment == "overhanging_gable"
    assert warm.ridge_profile.cap_height == 0
    for preset_id in ("jiangnan_dark_tile", "gray_brick_layered", "warm_spruce_garden"):
        assert load_roof_preset(preset_id).material_palette.roles


def test_each_creative_roof_preset_generates_repeatably() -> None:
    for preset_id in ("jiangnan_dark_tile", "gray_brick_layered", "warm_spruce_garden"):
        preset = parameter_registry.load_roof_preset(preset_id)
        parameters = {
            "roof_profile": asdict(preset.roof_profile),
            "eave_profile": asdict(preset.eave_profile),
            "ridge_profile": asdict(preset.ridge_profile),
            "material_palette": dict(preset.material_palette.roles),
        }
        first = module_from_asset(f"hall-{preset_id}", "jiangnan.hall", parameters)
        second = module_from_asset(f"hall-{preset_id}", "jiangnan.hall", parameters)
        assert first.model.blocks
        assert first.model.blocks == second.model.blocks


def test_legacy_roof_values_normalize_to_canonical_profile_fields() -> None:
    resolved = resolve_parameters(
        "jiangnan.hall",
        {
            "roof_rise": 2,
            "eaves": 0,
            "materials": {
                "roof": "minecraft:spruce_stairs",
                "eaves": "minecraft:oak_slab[type=bottom,waterlogged=false]",
            },
        },
    )

    assert resolved.generator_parameters.roof_profile.ridge_height == 2
    assert resolved.generator_parameters.eave_profile == EaveProfile(
        side_overhang=0,
        gable_end_treatment="hard_gable",
        gable_end_projection=0,
        thickness=1,
        layer_roles=("eaves",),
    )
    assert resolved.generator_parameters.material_palette.roles["roof_stair"] == "minecraft:spruce_stairs"
    assert resolved.generator_parameters.material_palette.roles["eaves"] == (
        "minecraft:oak_slab[type=bottom,waterlogged=false]"
    )
    assert resolved.parameter_provenance["material_palette"]["category"] == "user_input"


def test_malformed_profile_records_are_reported_as_parameter_errors() -> None:
    with pytest.raises(ValueError, match="invalid roof_profile fields"):
        resolve_parameters(
            "jiangnan.hall",
            {"roof_profile": {"surface_bands": [{"start": 0, "end": 1000, "form": "stair"}]}},
        )


def test_legacy_material_alias_and_palette_state_compare_after_blockstate_normalization() -> None:
    resolved = resolve_parameters(
        "jiangnan.hall",
        {
            "materials": {
                "roof": "oak_stairs[half=bottom,facing=north,shape=straight,waterlogged=false]"
            },
            "material_palette": {
                "roof_stair": (
                    "minecraft:oak_stairs[waterlogged=false,shape=straight,facing=north,half=bottom]"
                )
            },
        },
    )

    assert resolved.generator_parameters.material_palette.roles["roof_stair"] == (
        "minecraft:oak_stairs[facing=north,half=bottom,shape=straight,waterlogged=false]"
    )


def test_legacy_roof_section_requires_symmetric_gable_and_maps_its_rise() -> None:
    resolved = resolve_parameters(
        "jiangnan.hall",
        {"roof_section": {"profile": "symmetric_gable", "rise": 2}},
    )

    assert resolved.generator_parameters.roof_profile.ridge_height == 2
    with pytest.raises(ValueError, match="symmetric_gable"):
        resolve_parameters(
            "jiangnan.hall",
            {"roof_section": {"profile": "hipped", "rise": 2}},
        )


def test_equal_legacy_and_profile_forms_are_accepted_and_conflicts_raise() -> None:
    resolved = resolve_parameters(
        "jiangnan.hall",
        {
            "roof_rise": 2,
            "roof_profile": {"ridge_height": 2},
            "eaves": 1,
            "eave_profile": {
                "side_overhang": 1,
                "gable_end_treatment": "overhanging_gable",
                "gable_end_projection": 1,
            },
            "materials": {"roof": "minecraft:polished_deepslate_stairs"},
            "material_palette": {"roof_stair": "minecraft:polished_deepslate_stairs"},
        },
    )
    assert resolved.generator_parameters.roof_profile.ridge_height == 2

    with pytest.raises(ParameterConflictError, match="roof_rise.*roof_profile"):
        resolve_parameters(
            "jiangnan.hall",
            {"roof_rise": 2, "roof_profile": {"ridge_height": 3}},
        )
    with pytest.raises(ParameterConflictError, match="eaves.*eave_profile"):
        resolve_parameters(
            "jiangnan.hall",
            {"eaves": 1, "eave_profile": {"side_overhang": 2}},
        )
    with pytest.raises(ParameterConflictError, match="materials.roof.*material_palette"):
        resolve_parameters(
            "jiangnan.hall",
            {
                "materials": {"roof": "minecraft:stone_brick_stairs"},
                "material_palette": {"roof_stair": "minecraft:polished_deepslate_stairs"},
            },
        )
