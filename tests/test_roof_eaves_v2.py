from __future__ import annotations

import importlib

import pytest

from jiangnan_agent.core.block import BlockState
from jiangnan_agent.core.transforms import rotate_model_y
from jiangnan_agent.generators.roof_profiles import (
    EaveProfile,
    MaterialPalette,
    RidgeProfile,
    RoofProfile,
    SurfaceBand,
)


def _builder(name: str):
    module = importlib.import_module("jiangnan_agent.generators.components")
    value = getattr(module, name, None)
    if not callable(value):
        pytest.fail(f"roof component builder {name} has not been implemented", pytrace=False)
    return value


def _palette() -> MaterialPalette:
    return MaterialPalette(
        {
            "roof_stair": "minecraft:stone_brick_stairs",
            "roof_slab": "minecraft:stone_brick_slab[type=bottom,waterlogged=false]",
            "roof_block": "minecraft:stone_bricks",
            "eaves": "minecraft:deepslate_tile_slab[type=bottom,waterlogged=false]",
            "eaves_outer": "minecraft:stone_brick_slab[type=bottom,waterlogged=false]",
            "eaves_inner": "minecraft:deepslate_tile_slab[type=bottom,waterlogged=false]",
            "ridge": "minecraft:polished_deepslate",
            "decoration": "minecraft:gold_block",
        }
    )


def test_surface_stairs_follow_both_slope_directions_and_rotate_with_the_model() -> None:
    generate = _builder("generate_roof_components")
    parts = generate(
        3,
        5,
        10,
        RoofProfile(ridge_height=2),
        EaveProfile(side_overhang=0, gable_end_treatment="hard_gable", gable_end_projection=0, thickness=0, layer_roles=()),
        RidgeProfile(),
        _palette(),
    )

    assert parts.surface.block_at((1, 10, 0)).to_string() == (
        "minecraft:stone_brick_stairs[facing=south,half=bottom,shape=straight,waterlogged=false]"
    )
    assert parts.surface.block_at((1, 11, 3)).to_string() == (
        "minecraft:stone_brick_stairs[facing=north,half=bottom,shape=straight,waterlogged=false]"
    )

    rotated = rotate_model_y(parts.combined, 1)
    assert rotated.block_at((4, 10, 1)).to_string() == (
        "minecraft:stone_brick_stairs[facing=west,half=bottom,shape=straight,waterlogged=false]"
    )


def test_surface_bands_choose_the_material_at_the_ridge_endpoint() -> None:
    generate = _builder("generate_roof_surface")
    roof = generate(
        2,
        5,
        8,
        RoofProfile(
            ridge_height=2,
            surface_bands=(
                SurfaceBand(0, 500, "stair", "roof_stair"),
                SurfaceBand(500, 1000, "full_block", "roof_block"),
            ),
        ),
        EaveProfile(side_overhang=0, gable_end_treatment="hard_gable", gable_end_projection=0, thickness=0, layer_roles=()),
        _palette(),
    )

    assert roof.block_at((0, 8, 0)).block_id == "minecraft:stone_brick_stairs"
    assert roof.block_at((0, 10, 2)) == BlockState.parse("minecraft:stone_bricks")


def test_roof_slab_band_uses_a_top_half_state() -> None:
    generate = _builder("generate_roof_surface")
    roof = generate(
        1,
        3,
        4,
        RoofProfile(ridge_height=1, surface_bands=(SurfaceBand(0, 1000, "slab", "roof_slab"),)),
        EaveProfile(side_overhang=0, gable_end_treatment="hard_gable", gable_end_projection=0, thickness=0, layer_roles=()),
        _palette(),
    )

    assert roof.block_at((0, 4, 0)).to_string() == (
        "minecraft:stone_brick_slab[type=top,waterlogged=false]"
    )


def test_eaves_apply_ordered_trim_layers_and_gable_end_projection() -> None:
    generate = _builder("generate_eaves_component")
    eaves, owned = generate(
        3,
        5,
        10,
        RoofProfile(ridge_height=2),
        EaveProfile(
            side_overhang=1,
            gable_end_treatment="overhanging_gable",
            gable_end_projection=1,
            thickness=2,
            layer_roles=("eaves_outer", "eaves_inner"),
        ),
        _palette(),
    )

    assert len(eaves.blocks) == 20
    assert owned == {(x, 10, z) for x in range(-1, 4) for z in (0, 4)}
    assert eaves.block_at((-1, 10, 0)).to_string() == (
        "minecraft:stone_brick_slab[type=bottom,waterlogged=false]"
    )
    assert eaves.block_at((3, 9, 4)).to_string() == (
        "minecraft:deepslate_tile_slab[type=bottom,waterlogged=false]"
    )


def test_hard_gable_does_not_extend_the_ridge_ends() -> None:
    generate = _builder("generate_eaves_component")
    eaves, _owned = generate(
        3,
        5,
        10,
        RoofProfile(ridge_height=2),
        EaveProfile(side_overhang=0, gable_end_treatment="hard_gable", gable_end_projection=0),
        _palette(),
    )

    assert set(eaves.blocks) == {(x, 10, z) for x in range(3) for z in (0, 4)}


def test_ridge_cap_uses_its_width_and_stacks_above_the_apex() -> None:
    generate = _builder("generate_ridge_cap")
    ridge, owned = generate(
        3,
        5,
        10,
        RoofProfile(ridge_height=2),
        EaveProfile(side_overhang=0, gable_end_treatment="hard_gable", gable_end_projection=0, thickness=0, layer_roles=()),
        RidgeProfile(cap_width=3, cap_height=2),
        _palette(),
    )

    assert len(ridge.blocks) == 18
    assert owned == {(x, 12, z) for x in range(3) for z in (1, 2, 3)}
    assert ridge.block_at((1, 12, 2)) == BlockState.parse("minecraft:polished_deepslate")
    assert ridge.block_at((1, 13, 2)) == BlockState.parse("minecraft:polished_deepslate")


def test_components_have_explicit_boundary_ownership_without_other_overlaps() -> None:
    generate = _builder("generate_roof_components")
    parts = generate(
        3,
        5,
        10,
        RoofProfile(ridge_height=2),
        EaveProfile(side_overhang=1, gable_end_treatment="overhanging_gable", gable_end_projection=1),
        RidgeProfile(cap_width=1, cap_height=1),
        _palette(),
    )

    assert set(parts.surface.blocks).isdisjoint(parts.eaves.blocks)
    assert set(parts.surface.blocks).isdisjoint(parts.ridge.blocks)
    assert set(parts.eaves.blocks).isdisjoint(parts.ridge.blocks)
    assert parts.combined.blocks == parts.surface.blocks | parts.eaves.blocks | parts.ridge.blocks
    assert parts.surface.block_at((0, 10, 0)) == BlockState.parse("minecraft:air")
    assert parts.surface.block_at((1, 12, 2)) == BlockState.parse("minecraft:air")


def test_surface_rejects_a_palette_state_that_does_not_match_its_band_form() -> None:
    generate = _builder("generate_roof_surface")
    wrong_palette = MaterialPalette({"roof_stair": "minecraft:stone_bricks"})

    with pytest.raises(ValueError, match="stair"):
        generate(
            1,
            3,
            0,
            RoofProfile(ridge_height=1),
            EaveProfile(side_overhang=0, gable_end_treatment="hard_gable", gable_end_projection=0, thickness=0, layer_roles=()),
            wrong_palette,
        )


def test_components_reject_a_missing_palette_role() -> None:
    generate = _builder("generate_roof_surface")
    missing_role = MaterialPalette({"roof_block": "minecraft:stone_bricks"})

    with pytest.raises(ValueError, match="palette role|material role"):
        generate(
            1,
            3,
            0,
            RoofProfile(ridge_height=1),
            EaveProfile(side_overhang=0, gable_end_treatment="hard_gable", gable_end_projection=0, thickness=0, layer_roles=()),
            missing_role,
        )


def test_material_palette_rejects_air_that_would_remove_roof_cells() -> None:
    with pytest.raises(ValueError, match="air cannot be used as a roof material"):
        MaterialPalette({"roof_stair": "minecraft:air"})
