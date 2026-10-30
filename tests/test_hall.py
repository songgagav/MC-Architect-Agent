from __future__ import annotations

import pytest

from jiangnan_agent.core.block import BlockState
from jiangnan_agent.assembly.adapters import corridor_module, hall_module
from jiangnan_agent.generators.facade_profiles import (
    DoorProfile,
    FacadeOpening,
    FacadeProfile,
    TimberDetailProfile,
    WallPanelProfile,
    WindowProfile,
)
from jiangnan_agent.generators.roof_profiles import RoofProfile
from jiangnan_agent.generators.hall import (
    CorridorParameters,
    HallParameters,
    generate_corridor,
    generate_hall,
)


def test_default_hall_is_three_bays_with_openings_and_connected_frame() -> None:
    model = generate_hall()

    assert model.bounds.size == (18, 10, 9)
    assert model.block_at((0, 1, 0)).to_string() == "minecraft:stripped_spruce_log[axis=y]"
    assert model.block_at((7, 5, 6)).to_string() == "minecraft:stripped_spruce_log[axis=x]"
    assert model.block_at((7, 2, 6)).to_string().startswith("minecraft:spruce_door[")
    assert dict(model.block_at((2, 3, 6)).properties)["north"] == "true"
    assert model.block_at((7, 2, 6)).block_id == "minecraft:spruce_door"


def test_hall_keeps_legacy_public_door_width_default() -> None:
    assert HallParameters().door_width == 2
    assert HallParameters(door_width=1).door_width == 1


def test_five_bay_hall_expands_posts_and_is_deterministic() -> None:
    parameters = HallParameters(bay_count=5)

    first = generate_hall(parameters)
    second = generate_hall(parameters)

    assert first.bounds.size == (28, 10, 9)
    assert first.blocks == second.blocks
    for x in (0, 5, 10, 15, 20, 25):
        assert first.block_at((x, 1, 6)).block_id == "minecraft:stripped_spruce_log"
        assert first.block_at((x, 5, 6)).block_id == "minecraft:stripped_spruce_log"


def test_hall_material_overrides_apply_to_walls_and_roof() -> None:
    model = generate_hall(
        HallParameters(materials={"wall": "minecraft:white_terracotta", "roof": "minecraft:spruce_stairs"})
    )

    assert model.block_at((1, 2, 0)).block_id == "minecraft:white_terracotta"
    assert any(state.block_id == "minecraft:spruce_stairs" for state in model.blocks.values())


@pytest.mark.parametrize(
    "parameters",
    [
        {"bay_count": 2},
        {"bay_count": 3, "bay_width": 3},
        {"depth": 6},
        {"column_height": 2},
        {"plinth_height": 0},
        {"roof_rise": 4},
        {"eaves": -1},
        {"materials": {"unknown": "minecraft:stone"}},
        {"materials": {"roof": "minecraft:stone"}},
    ],
)
def test_hall_rejects_invalid_parameters(parameters: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        HallParameters(**parameters)


def test_corridor_has_repeated_two_sided_posts_and_continuous_roof() -> None:
    model = generate_corridor()

    assert model.bounds.size == (13, 7, 5)
    for x in (0, 3, 6, 9, 10):
        for z in (0, 2):
            assert model.block_at((x, 1, z)).to_string() == "minecraft:stripped_spruce_log[axis=y]"
            assert model.block_at((x, 4, z)).to_string() == "minecraft:stripped_spruce_log[axis=x]"
    assert all(model.block_at((x, 6, 1)).block_id == "minecraft:polished_deepslate_stairs" for x in range(11))


@pytest.mark.parametrize(
    "parameters",
    [
        {"length": 2},
        {"width": 4},
        {"column_spacing": 0},
        {"column_height": 1},
        {"roof_rise": 2},
        {"materials": {"wall": "minecraft:calcite"}},
    ],
)
def test_corridor_rejects_invalid_parameters(parameters: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        CorridorParameters(**parameters)


def test_hall_roof_and_door_states_survive_model_reads() -> None:
    model = generate_hall()

    assert dict(model.block_at((7, 2, 6)).properties) == {
        "facing": "south",
        "half": "lower",
        "hinge": "left",
        "open": "false",
        "powered": "false",
    }
    assert any(
        state == BlockState.parse(
            "minecraft:polished_deepslate_stairs[facing=north,half=bottom,shape=straight,waterlogged=false]"
        )
        for state in model.blocks.values()
    )


def _profiled_hall(*, primary_segment: int = 0, primary_offset: int = 0) -> FacadeProfile:
    return FacadeProfile(
        profile_id="test-hall-façade",
        wall=WallPanelProfile(thickness=2, expand_direction="inward", layer_roles=("wall", "wall")),
        door=DoorProfile(width=2, frame_thickness=0, lintel=False),
        window=WindowProfile(width=2, height=2, frame_thickness=0, lattice_style="plain"),
        openings=(
            FacadeOpening("entry.main", "front", "door", "primary_entry", primary_segment, primary_offset, 0),
            FacadeOpening("door.front.secondary", "front", "door", "non_connecting", 2, 1, 0),
            FacadeOpening("window.left", "left", "window", "non_connecting", 0, 0, 1),
        ),
        materials={
            "wall": "minecraft:calcite",
            "door": "minecraft:spruce_door",
            "window": "minecraft:white_stained_glass_pane",
        },
    )


@pytest.mark.parametrize(("primary_segment", "primary_offset", "expected_x"), [(0, 0, 1), (1, 1, 7)])
def test_hall_primary_entry_alone_drives_stable_front_anchor(
    primary_segment: int,
    primary_offset: int,
    expected_x: int,
) -> None:
    module = hall_module(
        "profiled-hall",
        HallParameters(facade_profile=_profiled_hall(primary_segment=primary_segment, primary_offset=primary_offset)),
    )

    front = module.anchor("front")
    assert front.position == (expected_x + 1, 2, 7)
    assert (front.facing, front.connection_type, front.width, front.height) == ("south", "passage", 2, 2)
    assert [anchor.name for anchor in module.anchors].count("front") == 1
    assert module.model.block_at((12, 2, 6)).block_id == "minecraft:spruce_door"
    assert module.model.block_at((0, 3, 1)).block_id == "minecraft:white_stained_glass_pane"
    assert module.model.block_at((expected_x, 2, 6)).block_id == "minecraft:spruce_door"
    assert module.model.block_at((expected_x, 2, 5)).block_id == "minecraft:air"
    assert module.model.block_at((3, 2, 5)).block_id == "minecraft:calcite"


def test_profiled_through_passage_pairs_rear_anchor_to_primary_entry() -> None:
    module = hall_module("through-hall", HallParameters(facade_profile=_profiled_hall()), through_passage=True)

    assert module.anchor("front").position == (2, 2, 7)
    assert module.anchor("rear").position == (2, 2, -1)
    assert (module.anchor("front").width, module.anchor("rear").width) == (2, 2)
    assert module.model.block_at((1, 2, 0)).block_id == "minecraft:spruce_door"
    assert module.model.block_at((2, 3, 0)).block_id == "minecraft:spruce_door"


def test_outward_wall_thickness_keeps_the_primary_passage_clear() -> None:
    profile = _profiled_hall()
    profile = FacadeProfile(
        profile_id="outward-thick-wall",
        wall=WallPanelProfile(thickness=2, expand_direction="outward", layer_roles=("wall", "wall")),
        door=profile.door,
        window=profile.window,
        openings=profile.openings,
        materials=dict(profile.materials),
    )
    module = hall_module("outward-hall", HallParameters(facade_profile=profile))

    assert module.anchor("front").position == (2, 2, 7)
    assert module.model.block_at((2, 2, 7)).block_id == "minecraft:air"
    assert module.model.block_at((3, 2, 7)).block_id == "minecraft:calcite"


def test_profile_frame_replaces_only_declared_wall_cells_and_preserves_roof() -> None:
    base = _profiled_hall()
    profile = FacadeProfile(
        profile_id="framed-entry",
        wall=base.wall,
        door=DoorProfile(width=2, frame_thickness=1, lintel=True),
        window=base.window,
        openings=(FacadeOpening("entry.main", "front", "door", "primary_entry", 1, 1, 0),),
        materials={
            "wall": "minecraft:calcite",
            "door": "minecraft:spruce_door",
            "column": "minecraft:stripped_spruce_log",
            "beam": "minecraft:stripped_spruce_log",
        },
    )
    module = hall_module(
        "framed-hall",
        HallParameters(facade_profile=profile, roof_profile=RoofProfile(ridge_height=2)),
    )

    assert module.model.block_at((6, 2, 6)).to_string() == "minecraft:stripped_spruce_log[axis=y]"
    assert module.model.block_at((7, 4, 6)).to_string() == "minecraft:stripped_spruce_log[axis=x]"
    assert any("stairs" in state.block_id for state in module.model.blocks.values())


def test_profile_frame_cannot_overwrite_a_structural_column() -> None:
    base = _profiled_hall()
    profile = FacadeProfile(
        profile_id="entry-at-post",
        wall=base.wall,
        door=DoorProfile(width=2, frame_thickness=1, lintel=False),
        openings=(FacadeOpening("entry.main", "front", "door", "primary_entry", 0, 0, 0),),
        materials={"wall": "minecraft:calcite", "door": "minecraft:spruce_door", "column": "minecraft:oak_log"},
    )

    with pytest.raises(ValueError, match="undeclared replacement|protected"):
        generate_hall(HallParameters(facade_profile=profile))


def test_timber_profile_adds_column_bases_capitals_and_beam_layers() -> None:
    base = _profiled_hall()
    profile = FacadeProfile(
        profile_id="timber-detail",
        wall=WallPanelProfile(layer_roles=("wall", "wall"), thickness=2),
        door=base.door,
        openings=(FacadeOpening("entry.main", "front", "door", "primary_entry", 1, 1, 0),),
        timber=TimberDetailProfile(
            column_bases=True,
            column_capitals=True,
            beam_layers=2,
            trim_material_role="trim",
        ),
        materials={
            "wall": "minecraft:calcite",
            "door": "minecraft:spruce_door",
            "trim": "minecraft:dark_oak_planks",
        },
    )
    model = generate_hall(HallParameters(facade_profile=profile))

    assert model.block_at((0, 1, 0)).block_id == "minecraft:dark_oak_planks"
    assert model.block_at((0, 4, 0)).block_id == "minecraft:dark_oak_planks"
    assert model.block_at((3, 4, 6)).block_id == "minecraft:dark_oak_planks"


def test_timber_beam_layers_fail_on_reserved_opening_cells() -> None:
    profile = FacadeProfile(
        profile_id="timber-opening-conflict",
        door=DoorProfile(width=2, lintel=False),
        window=WindowProfile(width=2, height=2, frame_thickness=0),
        openings=(
            FacadeOpening("entry.main", "front", "door", "primary_entry", 1, 1, 0),
            FacadeOpening("window.front", "front", "window", "non_connecting", 0, 0, 1),
        ),
        timber=TimberDetailProfile(beam_layers=2),
        materials={"wall": "minecraft:calcite", "window": "minecraft:glass_pane"},
    )

    with pytest.raises(ValueError, match="timber beam layer.*reserved opening"):
        generate_hall(HallParameters(facade_profile=profile))


def test_corridor_only_encloses_explicit_long_faces_and_keeps_end_anchors() -> None:
    profile = FacadeProfile(
        profile_id="corridor-side-wall",
        wall=WallPanelProfile(),
        window=WindowProfile(width=2, height=2, frame_thickness=0, lattice_style="plain"),
        openings=(FacadeOpening("window.front", "front", "window", "non_connecting", 0, 0, 0),),
        materials={"wall": "minecraft:white_terracotta", "window": "minecraft:glass_pane"},
        enclosed_faces=("front",),
    )
    module = corridor_module("profiled-corridor", CorridorParameters(facade_profile=profile))
    legacy = corridor_module("open-corridor")

    assert module.model.block_at((1, 2, 2)).block_id == "minecraft:glass_pane"
    assert module.model.block_at((4, 2, 2)).block_id == "minecraft:white_terracotta"
    assert tuple((a.name, a.position, a.facing, a.width, a.height) for a in module.anchors) == tuple(
        (a.name, a.position, a.facing, a.width, a.height) for a in legacy.anchors
    )
    assert legacy.model.block_at((1, 2, 2)).block_id == "minecraft:air"


def test_corridor_profile_cannot_close_connection_end_faces() -> None:
    profile = FacadeProfile(profile_id="closed-end", enclosed_faces=("left",))

    with pytest.raises(ValueError, match="start/end connection faces"):
        CorridorParameters(facade_profile=profile)


def test_inward_corridor_walls_preserve_a_clear_lane_or_fail_explicitly() -> None:
    profile = FacadeProfile(
        profile_id="thick-corridor-walls",
        wall=WallPanelProfile(thickness=2, expand_direction="inward", layer_roles=("wall", "wall")),
        materials={"wall": "minecraft:calcite"},
        enclosed_faces=("front", "rear"),
    )

    with pytest.raises(ValueError, match="clear corridor passage"):
        CorridorParameters(width=3, facade_profile=profile)

    parameters = CorridorParameters(length=7, width=5, facade_profile=profile)
    module = corridor_module("thick-profiled-corridor", parameters)
    legacy = corridor_module("same-size-open-corridor", CorridorParameters(length=7, width=5))

    assert all(module.model.block_at((x, 2, 2)).block_id == "minecraft:air" for x in range(1, 6))
    assert tuple(
        (anchor.name, anchor.position, anchor.facing, anchor.width, anchor.height)
        for anchor in module.anchors
    ) == tuple(
        (anchor.name, anchor.position, anchor.facing, anchor.width, anchor.height)
        for anchor in legacy.anchors
    )


@pytest.mark.parametrize(
    ("width", "enclosed_faces", "expand_direction", "clear_z"),
    (
        (3, ("front",), "inward", None),
        (5, ("front",), "inward", (1, 2)),
        (3, ("front", "rear"), "outward", (1,)),
        (3, (), "inward", (1,)),
    ),
    ids=("one-side-too-thick", "one-side-clearance", "outward-no-reduction", "no-walls"),
)
def test_corridor_clearance_only_counts_inward_walls_on_enclosed_long_sides(
    width: int,
    enclosed_faces: tuple[str, ...],
    expand_direction: str,
    clear_z: tuple[int, ...] | None,
) -> None:
    profile = FacadeProfile(
        profile_id="corridor-clearance-boundary",
        wall=WallPanelProfile(thickness=2, expand_direction=expand_direction, layer_roles=("wall", "wall")),
        materials={"wall": "minecraft:calcite"},
        enclosed_faces=enclosed_faces,
    )
    if clear_z is None:
        with pytest.raises(ValueError, match="clear corridor passage"):
            CorridorParameters(width=width, facade_profile=profile)
        return

    module = corridor_module("corridor-clearance-boundary", CorridorParameters(width=width, facade_profile=profile))
    assert all(module.model.block_at((1, 2, z)).block_id == "minecraft:air" for z in clear_z)


def test_garden_open_gallery_preset_can_be_adapted_to_an_enclosed_corridor_module() -> None:
    from dataclasses import replace

    from jiangnan_agent.assembly.adapters import corridor_module
    from jiangnan_agent.assets import module_from_asset
    from jiangnan_agent.generators.facade_profiles import (
        FacadeOpening,
        facade_profile_to_mapping,
    )
    from jiangnan_agent.parameters import load_facade_preset

    preset = load_facade_preset("garden_open_gallery")
    gallery = replace(
        preset,
        openings=(
            FacadeOpening("gallery.front-window", "front", "window", "non_connecting", 0, 0, 0),
            FacadeOpening("gallery.rear-window", "rear", "window", "non_connecting", 0, 0, 0),
        ),
        enclosed_faces=("front", "rear"),
    )
    module = module_from_asset(
        "garden-corridor",
        "jiangnan.corridor",
        {"facade_profile": facade_profile_to_mapping(gallery)},
    )
    open_default = corridor_module("open-default", CorridorParameters())

    assert module.parameters["facade_profile"]["enclosed_faces"] == ("front", "rear")
    assert tuple(anchor.name for anchor in module.anchors) == ("start", "end")
    assert module.model.blocks != open_default.model.blocks
