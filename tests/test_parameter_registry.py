from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path

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


def test_current_asset_catalog_v5_keeps_pinned_versions_readable() -> None:
    by_kind = {asset.kind: asset for asset in list_assets()}

    assert {kind: asset.version for kind, asset in by_kind.items()} == {"hall": 5, "corridor": 5}
    assert all(asset.parameter_schema_version == 4 for asset in by_kind.values())
    assert all(asset.knowledge_base_version == 5 for asset in by_kind.values())
    assert {asset.version for asset in list_assets(version=3)} == {1, 2, 3}
    assert {asset.version for asset in list_assets(version=4)} == {1, 2, 3, 4}
    assert {asset.version for asset in list_assets(version=5)} == {1, 2, 3, 4, 5}
    assert tuple(asset for asset in list_assets(version=5) if asset.version <= 4) == list_assets(version=4)
    for asset_version, schema_version in ((1, 1), (2, 1), (3, 2), (4, 3), (5, 4)):
        for asset_id in ("jiangnan.hall", "jiangnan.corridor"):
            schema = load_parameter_schema(asset_id, asset_version=asset_version)
            assert schema.version == schema_version


def test_v5_asset_catalog_registers_facade_profiles_without_mutating_older_versions() -> None:
    from jiangnan_agent.assets.registry import get_asset
    from jiangnan_agent.assets import module_from_asset
    from test_roof_eaves_v2 import _canonical_hash

    hall_v4 = get_asset("jiangnan.hall", 4, catalog_version=4)
    hall_v5 = get_asset("jiangnan.hall", 5)
    corridor_v4 = get_asset("jiangnan.corridor", 4, catalog_version=4)
    corridor_v5 = get_asset("jiangnan.corridor", 5)

    assert (hall_v4.parameter_schema_version, hall_v4.knowledge_base_version) == (3, 4)
    assert (corridor_v4.parameter_schema_version, corridor_v4.knowledge_base_version) == (3, 4)
    assert (hall_v5.parameter_schema_version, hall_v5.knowledge_base_version) == (4, 5)
    assert (corridor_v5.parameter_schema_version, corridor_v5.knowledge_base_version) == (4, 5)
    assert load_parameter_schema("jiangnan.hall").version == 4
    assert load_parameter_schema("jiangnan.corridor").version == 4
    for asset_id in ("jiangnan.hall", "jiangnan.corridor"):
        current = module_from_asset(f"{asset_id}-v5", asset_id)
        previous = module_from_asset(f"{asset_id}-v4", asset_id, asset_version=4)
        assert current.model.blocks == previous.model.blocks
        assert _canonical_hash(current.model) == _canonical_hash(previous.model)


def test_facade_profile_schema_round_trips_typed_profiles_and_preserves_legacy_defaults() -> None:
    from jiangnan_agent.assets import module_from_asset
    from jiangnan_agent.generators.facade_profiles import (
        FacadeProfile,
        encode_facade_profile,
        facade_profile_from_mapping,
        facade_profile_to_mapping,
    )

    profile = {
        "profile_id": "schema-test",
        "version": 1,
        "openings": [
            {
                "opening_id": "main-entry",
                "face": "front",
                "kind": "door",
                "connection_use": "primary_entry",
                "segment_index": 1,
                "offset": 1,
                "sill_offset": 0,
            }
        ],
    }
    resolved = resolve_parameters("jiangnan.hall", {"facade_profile": profile})
    module = module_from_asset("profiled", "jiangnan.hall", {"facade_profile": profile})
    legacy = module_from_asset("legacy", "jiangnan.hall", asset_version=4)
    from jiangnan_agent.assembly.adapters import hall_module
    from jiangnan_agent.generators.hall import HallParameters

    assert isinstance(resolved.normalized_inputs["facade_profile"], Mapping)
    assert isinstance(resolved.generator_parameters.facade_profile, FacadeProfile)
    assert facade_profile_from_mapping(module.parameters["facade_profile"]) == resolved.generator_parameters.facade_profile
    assert legacy.model.blocks == hall_module("legacy-direct", HallParameters()).model.blocks
    encoded = encode_facade_profile(resolved.generator_parameters.facade_profile)
    assert resolve_parameters("jiangnan.hall", {"facade_profile": encoded}).generator_parameters.facade_profile == (
        resolved.generator_parameters.facade_profile
    )
    assert facade_profile_to_mapping(resolved.generator_parameters.facade_profile) == profile | {
        "wall": {"thickness": 1, "expand_direction": "inward", "layer_roles": ["wall"]},
        "door": {
            "width": 2, "height": 2, "frame_thickness": 0, "door_material_role": "door",
            "frame_material_role": "column", "lintel_material_role": "beam", "lintel": True,
        },
        "window": {
            "width": 2, "height": 2, "sill_height": 2, "frame_thickness": 1,
            "frame_material_role": "beam", "glazing_material_role": "window",
            "lattice_material_role": "lattice", "lattice_style": "plain",
        },
        "timber": {
            "exterior_posts": True, "column_bases": False, "column_capitals": False,
            "beam_layers": 1, "trim_material_role": "beam",
        },
        "materials": {},
        "enclosed_faces": [],
    }


def test_facade_profile_conflicts_only_with_explicit_legacy_inputs() -> None:
    from jiangnan_agent.generators.facade_profiles import facade_profile_to_mapping

    profile = facade_profile_to_mapping(parameter_registry.load_facade_preset("jiangnan_whitewall_timber"))
    resolve_parameters("jiangnan.hall", {"facade_profile": profile})

    with pytest.raises(ValueError, match="explicit door_width conflicts"):
        resolve_parameters("jiangnan.hall", {"facade_profile": profile, "door_width": 1})
    with pytest.raises(ValueError, match="explicit materials role 'wall' conflicts"):
        resolve_parameters(
            "jiangnan.hall",
            {"facade_profile": profile, "materials": {"wall": "minecraft:stone"}},
        )
    with pytest.raises(ValueError, match="explicit materials role 'wall' conflicts"):
        resolve_parameters(
            "jiangnan.hall",
            {"facade_profile": profile},
            base_config={"materials": {"wall": "minecraft:stone"}},
            base_provenance={"materials": {"category": "user_input"}},
        )


def test_facade_presets_are_versioned_creative_configs_combinable_with_roof_presets(tmp_path: Path) -> None:
    from jiangnan_agent.library import LibraryService
    from jiangnan_agent.library.database import LibraryDatabase
    from jiangnan_agent.generators.facade_profiles import facade_profile_to_mapping
    from jiangnan_agent.parameters import load_facade_preset, list_facade_presets

    assert list_facade_presets() == (
        "garden_open_gallery",
        "huizhou_graybrick_entry",
        "jiangnan_whitewall_timber",
    )
    service = LibraryService(LibraryDatabase(tmp_path / "catalog.sqlite3"))
    service.initialize()
    assert set(item["profile_id"] for item in service.list_styles()) >= {
        "jiangnan_whitewall_timber",
        "huizhou_graybrick_entry",
        "garden_open_gallery",
    }
    listed_styles = {item["profile_id"]: item for item in service.list_styles()}
    for facade_id in list_facade_presets():
        style_record = service.get_style_profile(facade_id)
        assert listed_styles[facade_id]["status"] == "ready"
        assert style_record["facade_profile_id"] == facade_id
        assert style_record["reference_asset_ids"] == []
        for roof_id in parameter_registry.list_roof_presets():
            facade = load_facade_preset(facade_id)
            roof = parameter_registry.load_roof_preset(roof_id)
            parameters = {
                "facade_profile": facade_profile_to_mapping(facade),
                "roof_profile": asdict(roof.roof_profile),
                "eave_profile": asdict(roof.eave_profile),
                "ridge_profile": asdict(roof.ridge_profile),
                "material_palette": dict(roof.material_palette.roles),
            }
            first = module_from_asset("combined", "jiangnan.hall", parameters)
            second = module_from_asset("combined", "jiangnan.hall", parameters)
            assert first.model.blocks == second.model.blocks


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


def test_v4_accepts_versioned_edge_liner_profile_and_keeps_legacy_default() -> None:
    schema = load_parameter_schema("jiangnan.hall")
    assert schema.defaults["eave_profile"]["surface_connection"] == "legacy"
    assert schema.defaults["eave_profile"]["surface_connection_role"] is None

    resolved = resolve_parameters(
        "jiangnan.hall",
        {
            "eave_profile": {
                "side_overhang": 1,
                "gable_end_treatment": "hard_gable",
                "gable_end_projection": 0,
                "thickness": 1,
                "layer_roles": ["eaves"],
                "surface_connection": "edge_liner",
                "surface_connection_role": "edge_liner",
            },
            "material_palette": {
                "roof_stair": "minecraft:stone_brick_stairs",
                "eaves": "minecraft:stone_brick_slab[type=top,waterlogged=false]",
                "edge_liner": "minecraft:stone_bricks",
            },
        },
    )

    assert resolved.generator_parameters.eave_profile == EaveProfile(
        side_overhang=1,
        gable_end_treatment="hard_gable",
        gable_end_projection=0,
        thickness=1,
        layer_roles=("eaves",),
        surface_connection="edge_liner",
        surface_connection_role="edge_liner",
    )


def test_corridor_v3_derives_bounds_from_its_length_width_and_eave_projections() -> None:
    resolved = resolve_parameters(
        "jiangnan.corridor",
        {
            "length": 13,
            "width": 5,
            "eave_profile": {"gable_end_projection": 2, "side_overhang": 1},
            "derived": {"bounds_width": 17, "bounds_depth": 7},
        },
    )

    assert resolved.derived_parameters["bounds_width"] == 17
    assert resolved.derived_parameters["bounds_depth"] == 7


def test_corridor_v2_bounds_keep_using_the_legacy_eaves_parameter() -> None:
    resolved = resolve_parameters(
        "jiangnan.corridor",
        {"length": 13, "width": 5, "eaves": 1},
        schema_version=2,
        asset_version=3,
    )

    assert resolved.derived_parameters["platform_length"] == 13


def test_parameter_resolution_rejects_unregistered_target_block_states() -> None:
    with pytest.raises(ValueError, match="Minecraft Java 1.21.5"):
        resolve_parameters(
            "jiangnan.hall",
            {"material_palette": {"roof_stair": "minecraft:unregistered_stairs"}},
        )


@pytest.mark.parametrize(
    ("asset_version", "schema_version", "role", "state"),
    (
        (1, 1, "roof", "minecraft:unregistered_stairs"),
        (1, 1, "eaves", "minecraft:unregistered_slab"),
        (3, 2, "roof", "minecraft:unregistered_stairs"),
        (3, 2, "eaves", "minecraft:unregistered_slab"),
    ),
)
def test_legacy_parameter_resolution_rejects_unregistered_roof_materials(
    asset_version: int,
    schema_version: int,
    role: str,
    state: str,
) -> None:
    with pytest.raises(ValueError, match="Minecraft Java 1.21.5"):
        resolve_parameters(
            "jiangnan.hall",
            {"materials": {role: state}},
            asset_version=asset_version,
            schema_version=schema_version,
        )


def test_parameter_resolution_rejects_non_solid_ridge_cap_materials() -> None:
    with pytest.raises(ValueError, match="ridge cap material must be a full block"):
        resolve_parameters(
            "jiangnan.hall",
            {
                "ridge_profile": {"cap_width": 1, "cap_height": 1},
                "material_palette": {"ridge": "minecraft:glass_pane"},
            },
        )


def test_parameter_resolution_reports_a_missing_ridge_cap_palette_role() -> None:
    with pytest.raises(ValueError, match="missing material palette role 'custom_ridge'"):
        resolve_parameters(
            "jiangnan.hall",
            {
                "ridge_profile": {
                    "cap_width": 1,
                    "cap_height": 1,
                    "material_role": "custom_ridge",
                }
            },
        )


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
