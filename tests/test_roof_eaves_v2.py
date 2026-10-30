from __future__ import annotations

import hashlib
import importlib

import pytest

from jiangnan_agent.core.block import BlockState
from jiangnan_agent.core.transforms import rotate_model_y
from jiangnan_agent.generators.hall import CorridorParameters, HallParameters, generate_corridor, generate_hall
from jiangnan_agent.generators.roof_profiles import (
    EaveProfile,
    MaterialPalette,
    RidgeProfile,
    RoofProfile,
    SurfaceBand,
)
from jiangnan_agent.io.schematic import read_schematic, write_schematic


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


def test_full_block_bands_fill_each_one_block_roof_slope_transition() -> None:
    generate = _builder("generate_roof_surface")
    roof = generate(
        1,
        5,
        10,
        RoofProfile(
            ridge_height=2,
            surface_bands=(SurfaceBand(0, 1000, "full_block", "roof_block"),),
        ),
        EaveProfile(
            side_overhang=0,
            gable_end_treatment="hard_gable",
            gable_end_projection=0,
            thickness=0,
            layer_roles=(),
        ),
        _palette(),
    )

    full = BlockState.parse("minecraft:stone_bricks")
    assert roof.block_at((0, 11, 0)) == full
    assert roof.block_at((0, 12, 1)) == full
    assert roof.block_at((0, 12, 3)) == full
    assert roof.block_at((0, 11, 4)) == full


@pytest.mark.parametrize(
    ("bands", "bridge_positions"),
    (
        (
            (SurfaceBand(0, 1000, "slab", "roof_slab"),),
            ((0, 11, 0), (0, 12, 1), (0, 12, 3), (0, 11, 4)),
        ),
        (
            (
                SurfaceBand(0, 500, "slab", "roof_slab"),
                SurfaceBand(500, 1000, "stair", "roof_stair"),
            ),
            ((0, 11, 0), (0, 11, 4)),
        ),
    ),
    ids=("slab-slope", "slab-stair-boundaries"),
)
def test_slab_transitions_use_double_slab_bridges(bands, bridge_positions) -> None:
    generate = _builder("generate_roof_surface")
    roof = generate(
        1,
        5,
        10,
        RoofProfile(ridge_height=2, surface_bands=bands),
        EaveProfile(
            side_overhang=0,
            gable_end_treatment="hard_gable",
            gable_end_projection=0,
            thickness=0,
            layer_roles=(),
        ),
        _palette(),
    )

    bridge = BlockState.parse("minecraft:stone_brick_slab[type=double,waterlogged=false]")
    assert all(roof.block_at(position) == bridge for position in bridge_positions)


@pytest.mark.parametrize(
    "material",
    (
        "minecraft:glass_pane",
        "minecraft:oak_fence",
        "minecraft:oak_door",
        "minecraft:torch",
    ),
)
def test_full_block_surface_rejects_known_non_full_block_materials(material: str) -> None:
    generate = _builder("generate_roof_surface")
    roles = dict(_palette().roles)
    roles["roof_block"] = material
    with pytest.raises(ValueError, match="must be a full block"):
        generate(
            1,
            3,
            0,
            RoofProfile(ridge_height=1, surface_bands=(SurfaceBand(0, 1000, "full_block", "roof_block"),)),
            EaveProfile(
                side_overhang=0,
                gable_end_treatment="hard_gable",
                gable_end_projection=0,
                thickness=0,
                layer_roles=(),
            ),
            MaterialPalette(roles),
        )


@pytest.mark.parametrize(
    "material",
    (
        "minecraft:sea_lantern",
        "minecraft:glass",
        "minecraft:cobblestone",
        "minecraft:stone_brick_slab[type=double,waterlogged=false]",
    ),
)
def test_full_block_surface_accepts_registered_full_cube_materials(material: str) -> None:
    generate = _builder("generate_roof_surface")
    roles = dict(_palette().roles)
    roles["roof_block"] = material
    roof = generate(
        1,
        3,
        0,
        RoofProfile(ridge_height=1, surface_bands=(SurfaceBand(0, 1000, "full_block", "roof_block"),)),
        EaveProfile(
            side_overhang=0,
            gable_end_treatment="hard_gable",
            gable_end_projection=0,
            thickness=0,
            layer_roles=(),
        ),
        MaterialPalette(roles),
    )

    assert roof.block_at((0, 1, 1)) == BlockState.parse(material)


@pytest.mark.parametrize(
    "material",
    (
        "minecraft:unregistered_stairs",
        "minecraft:oak_stairs[shape=invalid]",
        "minecraft:stone_bricks[unknown=true]",
        "example:stone_bricks",
    ),
)
def test_roof_palette_rejects_block_states_outside_the_1_21_5_material_catalog(material: str) -> None:
    generate = _builder("generate_roof_surface")
    roles = dict(_palette().roles)
    roles["roof_stair"] = material
    with pytest.raises(ValueError, match="Minecraft Java 1.21.5"):
        generate(
            1,
            7,
            0,
            RoofProfile(),
            EaveProfile(
                side_overhang=0,
                gable_end_treatment="hard_gable",
                gable_end_projection=0,
                thickness=0,
                layer_roles=(),
            ),
            MaterialPalette(roles),
        )


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


def test_ridge_cap_rejects_a_non_solid_surface_material() -> None:
    generate = _builder("generate_ridge_cap")
    roles = dict(_palette().roles)
    roles["ridge"] = "minecraft:glass_pane"
    with pytest.raises(ValueError, match="ridge cap material must be a full block"):
        generate(
            3,
            5,
            10,
            RoofProfile(ridge_height=2),
            EaveProfile(
                side_overhang=0,
                gable_end_treatment="hard_gable",
                gable_end_projection=0,
                thickness=0,
                layer_roles=(),
            ),
            RidgeProfile(cap_width=1, cap_height=1),
            MaterialPalette(roles),
        )


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


def _canonical_hash(model) -> str:
    records = "".join(
        f"{x},{y},{z}:{state.to_string()}\n"
        for (x, y, z), state in sorted(model.blocks.items())
    )
    return hashlib.sha256(records.encode("utf-8")).hexdigest()


def _legacy_roof_profiles(ridge_height: int):
    return {
        "roof_profile": RoofProfile(ridge_height=ridge_height),
        "eave_profile": EaveProfile(
            side_overhang=1,
            gable_end_treatment="overhanging_gable",
            gable_end_projection=1,
            thickness=1,
            layer_roles=("eaves",),
        ),
        "ridge_profile": RidgeProfile(),
        "material_palette": MaterialPalette(
            {
                "roof_stair": "minecraft:polished_deepslate_stairs",
                "eaves": "minecraft:deepslate_tile_slab[type=bottom,waterlogged=false]",
            }
        ),
    }


def _bounds_tuple(model) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    bounds = model.bounds
    return (
        (bounds.min_x, bounds.min_y, bounds.min_z),
        (bounds.max_x, bounds.max_y, bounds.max_z),
    )


def test_default_hall_and_corridor_match_literal_legacy_hashes() -> None:
    hall = generate_hall()
    corridor = generate_corridor()

    assert len(hall.blocks) == 522
    assert _bounds_tuple(hall) == ((-1, 0, -1), (17, 10, 8))
    assert _canonical_hash(hall) == "af86496dad80003d609d31a98e24a50957da419d32ca39a9ca622e8e61bc41b3"
    assert len(corridor.blocks) == 150
    assert _bounds_tuple(corridor) == ((-1, 0, -1), (12, 7, 4))
    assert _canonical_hash(corridor) == "6b99402a56bb31b35e6209d64a8ac4f4f83b3b452171ea53a39bd6b1aef0d707"
    assert (HallParameters().roof_rise, HallParameters().eaves) == (3, 1)
    assert (CorridorParameters().roof_rise, CorridorParameters().eaves) == (1, 1)


def test_explicit_default_profiles_match_the_legacy_hall_and_corridor_hashes() -> None:
    hall = generate_hall(HallParameters(**_legacy_roof_profiles(3)))
    corridor = generate_corridor(CorridorParameters(**_legacy_roof_profiles(1)))

    assert _canonical_hash(hall) == "af86496dad80003d609d31a98e24a50957da419d32ca39a9ca622e8e61bc41b3"
    assert _canonical_hash(corridor) == "6b99402a56bb31b35e6209d64a8ac4f4f83b3b452171ea53a39bd6b1aef0d707"


def test_eave_decoration_does_not_replace_wall_or_column_blocks() -> None:
    eave = EaveProfile(
        side_overhang=1,
        gable_end_treatment="overhanging_gable",
        gable_end_projection=1,
        thickness=1,
        layer_roles=("eaves",),
        decoration_role="decoration",
        decoration_spacing=2,
    )
    palette = _palette()
    hall = generate_hall(HallParameters(eave_profile=eave, material_palette=palette))
    corridor = generate_corridor(CorridorParameters(eave_profile=eave, material_palette=palette))
    default_hall = generate_hall()
    default_corridor = generate_corridor()

    assert hall.block_at((0, 4, 0)) == default_hall.block_at((0, 4, 0))
    assert corridor.block_at((0, 4, 0)) == default_corridor.block_at((0, 4, 0))
    assert hall.block_at((-1, 7, 0)) == BlockState.parse("minecraft:gold_block")
    assert corridor.block_at((-1, 6, 0)) == BlockState.parse("minecraft:gold_block")


@pytest.mark.parametrize("generator,parameters", [(generate_hall, HallParameters), (generate_corridor, CorridorParameters)])
def test_eaves_reject_layers_that_extend_from_beam_into_wall(generator, parameters) -> None:
    eave = EaveProfile(
        side_overhang=1,
        gable_end_treatment="overhanging_gable",
        gable_end_projection=1,
        thickness=3,
        layer_roles=("eaves", "eaves", "eaves"),
    )
    with pytest.raises(ValueError, match="roof component overlaps existing structure"):
        generator(parameters(eave_profile=eave, material_palette=_palette()))


@pytest.mark.parametrize("bay_count,expected_width", [(3, 18), (5, 28)])
def test_profiled_hall_supports_three_and_five_bays(bay_count: int, expected_width: int) -> None:
    model = generate_hall(HallParameters(bay_count=bay_count, **_legacy_roof_profiles(3)))

    assert model.bounds.size[0] == expected_width
    assert _canonical_hash(model) == _canonical_hash(
        generate_hall(HallParameters(bay_count=bay_count, **_legacy_roof_profiles(3)))
    )


@pytest.mark.parametrize("length", [7, 17])
def test_profiled_corridor_supports_different_lengths(length: int) -> None:
    model = generate_corridor(CorridorParameters(length=length, **_legacy_roof_profiles(1)))

    assert model.bounds.size == (length + 2, 7, 5)
    assert _canonical_hash(model) == _canonical_hash(
        generate_corridor(CorridorParameters(length=length, **_legacy_roof_profiles(1)))
    )


def test_increasing_hall_column_height_moves_the_profiled_roof_up_one_block() -> None:
    profiles = _legacy_roof_profiles(3)
    short = generate_hall(HallParameters(column_height=4, **profiles))
    tall = generate_hall(HallParameters(column_height=5, **profiles))

    assert short.block_at((1, 7, 1)).block_id.endswith("_stairs")
    assert tall.block_at((1, 8, 1)) == short.block_at((1, 7, 1))


def test_invalid_explicit_roof_profile_does_not_fall_back_to_legacy_roof() -> None:
    with pytest.raises(ValueError, match="step|height|rise"):
        generate_hall(HallParameters(roof_profile=RoofProfile(ridge_height=4)))


def test_equal_legacy_roof_values_are_accepted_but_conflicts_are_explicit() -> None:
    profiles = _legacy_roof_profiles(3)
    HallParameters(roof_rise=3, eaves=1, **profiles)

    with pytest.raises(ValueError, match="roof_rise conflicts"):
        HallParameters(roof_rise=2, roof_profile=RoofProfile(ridge_height=3))
    with pytest.raises(ValueError, match="eaves conflicts"):
        HallParameters(eaves=0, eave_profile=profiles["eave_profile"])


@pytest.mark.parametrize(
    "building_type,ridge_height",
    [
        ("hall", 3),
        ("corridor", 1),
    ],
)
def test_profiled_buildings_roundtrip_sponge_v3(
    building_type: str,
    ridge_height: int,
    tmp_path,
) -> None:
    if building_type == "hall":
        model = generate_hall(HallParameters(**_legacy_roof_profiles(ridge_height)))
    else:
        model = generate_corridor(CorridorParameters(**_legacy_roof_profiles(ridge_height)))
    path = tmp_path / "profiled-building.schem"

    write_schematic(model, path, data_version=4325)
    loaded = read_schematic(path)
    expected_local = model.translated(-model.bounds.min_x, -model.bounds.min_y, -model.bounds.min_z)

    assert loaded.data_version == 4325
    assert loaded.offset == (model.bounds.min_x, model.bounds.min_y, model.bounds.min_z)
    assert loaded.model.blocks == expected_local.blocks
