from __future__ import annotations

import pytest

from jiangnan_agent.core.geometry import BoundingBox
from jiangnan_agent.core.scene import VoxelModel
from jiangnan_agent.generators.facade_geometry import (
    BlockOwnershipMap,
    FaceSegmentBounds,
    OpeningMask,
    build_facade_segments,
    face_basis,
    point_on_face,
    resolve_facade_opening,
    wall_layer_bounds,
)
from jiangnan_agent.generators.facade_profiles import FacadeOpening, WallPanelProfile
from jiangnan_agent.generators.components import generate_wall


@pytest.mark.parametrize(
    ("face", "normal"),
    [
        ("front", (0, 0, 1)),
        ("rear", (0, 0, -1)),
        ("left", (-1, 0, 0)),
        ("right", (1, 0, 0)),
    ],
)
def test_face_basis_has_explicit_outward_normal_and_vertical_axis(face: str, normal: tuple[int, int, int]) -> None:
    basis = face_basis(face)

    assert basis.outward_normal == normal
    assert basis.vertical_axis == (0, 1, 0)


@pytest.mark.parametrize(
    ("face", "expected"),
    [
        ("front", (3, 2, 5)),
        ("rear", (3, 2, 3)),
        ("left", (3, 2, 3)),
        ("right", (5, 2, 3)),
    ],
)
def test_positive_face_offset_moves_outward(face: str, expected: tuple[int, int, int]) -> None:
    assert point_on_face(face, along=3, y=2, plane=4, outward_offset=1) == expected


def test_face_coordinates_allow_negative_world_origins() -> None:
    assert point_on_face("left", along=-3, y=-10, plane=-5, outward_offset=2) == (-7, -10, -3)


def test_front_and_rear_segments_are_resolved_between_actual_posts() -> None:
    bounds = BoundingBox(0, 2, 8, 13, 6, 9)

    segments = build_facade_segments("front", bounds, (0, 4, 8, 12))

    assert [segment.segment_index for segment in segments] == [0, 1, 2]
    assert [segment.bounds for segment in segments] == [
        BoundingBox(1, 2, 8, 4, 6, 9),
        BoundingBox(5, 2, 8, 8, 6, 9),
        BoundingBox(9, 2, 8, 12, 6, 9),
    ]


def test_side_segments_follow_actual_side_posts_not_front_bay_count() -> None:
    bounds = BoundingBox(0, 2, 0, 1, 6, 11)

    segments = build_facade_segments("left", bounds, (0, 3, 4, 10))

    assert [segment.segment_index for segment in segments] == [0, 2]
    assert [segment.bounds for segment in segments] == [
        BoundingBox(0, 2, 1, 1, 6, 3),
        BoundingBox(0, 2, 5, 1, 6, 10),
    ]


def test_side_opening_uses_segment_index_and_local_offset() -> None:
    opening = FacadeOpening("window.left.rear", "left", "window", "non_connecting", 2, 1, 1)
    segment = FaceSegmentBounds("left", 2, BoundingBox(0, 2, 5, 1, 6, 10))

    result = resolve_facade_opening(opening, segment, width=2, height=2)

    assert result == BoundingBox(0, 3, 6, 1, 5, 8)


@pytest.mark.parametrize(
    ("face", "bounds", "coordinate_index", "inward", "outward"),
    [
        ("front", BoundingBox(0, 0, 0, 4, 4, 1), 1, (0, -1), (0, 1)),
        ("rear", BoundingBox(0, 0, 5, 4, 4, 6), 1, (5, 6), (5, 4)),
        ("left", BoundingBox(0, 0, 0, 1, 4, 5), 0, (0, 1), (0, -1)),
        ("right", BoundingBox(5, 0, 0, 6, 4, 5), 0, (5, 4), (5, 6)),
    ],
)
def test_wall_thickness_expands_inward_and_outward_on_each_face(
    face: str,
    bounds: BoundingBox,
    coordinate_index: int,
    inward: tuple[int, int],
    outward: tuple[int, int],
) -> None:
    for direction, expected in (("inward", inward), ("outward", outward)):
        layers = wall_layer_bounds(bounds, face, thickness=2, expand_direction=direction)
        assert tuple((layer.min_x, layer.min_z)[coordinate_index] for layer in layers) == expected


def test_profile_wall_repeats_the_same_opening_mask_through_every_layer() -> None:
    wall = generate_wall(
        BoundingBox(0, 0, 0, 4, 4, 1),
        "minecraft:calcite",
        openings=(BoundingBox(1, 1, 0, 3, 3, 1),),
        profile=WallPanelProfile(thickness=2, expand_direction="inward", layer_roles=("outer", "inner")),
        face="front",
        material_roles={"outer": "minecraft:calcite", "inner": "minecraft:smooth_stone"},
    )

    assert wall.block_at((1, 1, 0)).block_id == "minecraft:air"
    assert wall.block_at((2, 2, -1)).block_id == "minecraft:air"
    assert wall.block_at((0, 1, 0)).block_id == "minecraft:calcite"
    assert wall.block_at((0, 1, -1)).block_id == "minecraft:smooth_stone"
    assert len(wall.blocks) == 24


def test_opening_mask_allows_only_the_matching_opening_component() -> None:
    opening_mask = OpeningMask()
    opening_mask.reserve("window.front.1", "window", BoundingBox(1, 2, 0, 3, 4, 1))
    ownership = BlockOwnershipMap(opening_mask=opening_mask)

    with pytest.raises(ValueError, match="reserved opening"):
        ownership.claim((1, 2, 0), "wall")
    with pytest.raises(ValueError, match="reserved opening"):
        ownership.claim((1, 2, 0), "decoration", opening_id="window.front.1")

    ownership.claim((1, 2, 0), "window", opening_id="window.front.1")
    assert ownership.owner_at((1, 2, 0)) == "window"


def test_one_opening_id_cannot_reserve_multiple_component_kinds() -> None:
    opening_mask = OpeningMask()
    opening_mask.reserve("opening.shared", "window", BoundingBox(0, 0, 0, 1, 1, 1))

    with pytest.raises(ValueError, match="multiple component kinds"):
        opening_mask.reserve("opening.shared", "door", BoundingBox(2, 0, 0, 3, 2, 1))


def test_profile_wall_uses_one_reserved_opening_mask_through_all_layers() -> None:
    opening_mask = OpeningMask()
    opening_mask.reserve("window.front.1", "window", BoundingBox(1, 1, 0, 3, 3, 1))
    opening_mask.reserve("window.front.1", "window", BoundingBox(1, 1, -1, 3, 3, 0))
    ownership = BlockOwnershipMap(opening_mask=opening_mask)
    wall = generate_wall(
        BoundingBox(0, 0, 0, 4, 4, 1),
        "minecraft:calcite",
        profile=WallPanelProfile(thickness=2, layer_roles=("wall", "wall")),
        face="front",
        opening_mask=opening_mask,
        ownership=ownership,
    )

    assert all(wall.block_at((x, y, z)).block_id == "minecraft:air" for z in (0, -1) for y in (1, 2) for x in (1, 2))
    assert all(ownership.owner_at((x, y, z)) is None for z in (0, -1) for y in (1, 2) for x in (1, 2))
    ownership.claim((1, 1, 0), "window", opening_id="window.front.1")


def test_wall_replacement_requires_cell_level_permission() -> None:
    ownership = BlockOwnershipMap()
    position = (1, 2, 3)
    ownership.claim(position, "wall")

    with pytest.raises(ValueError, match="undeclared replacement"):
        ownership.claim(position, "frame", replaces="wall")

    ownership.allow_replacement(position, "frame")
    ownership.claim(position, "frame", replaces="wall")
    assert ownership.owner_at(position) == "frame"


def test_structural_and_passage_cells_reject_wall_and_decoration_claims() -> None:
    ownership = BlockOwnershipMap()
    structure = (1, 2, 3)
    passage = (4, 2, 3)
    ownership.claim(structure, "column", protected=True)
    ownership.protect(passage, "assembly passage")

    with pytest.raises(ValueError, match="protected"):
        ownership.claim(structure, "decoration")
    with pytest.raises(ValueError, match="protected"):
        ownership.claim(passage, "wall")


def test_strict_model_merge_rejects_undeclared_overlap() -> None:
    ownership = BlockOwnershipMap()
    ownership.claim((0, 0, 0), "column")
    overlay = VoxelModel()
    overlay.set_block((0, 0, 0), "minecraft:calcite")

    with pytest.raises(ValueError, match="overlap"):
        ownership.merge(overlay, "wall")


def test_profile_wall_ownership_merge_rolls_back_after_a_conflict() -> None:
    ownership = BlockOwnershipMap()
    ownership.claim((1, 1, 0), "column", protected=True)

    with pytest.raises(ValueError, match="protected"):
        generate_wall(
            BoundingBox(0, 0, 0, 3, 3, 1),
            "minecraft:calcite",
            profile=WallPanelProfile(),
            face="front",
            ownership=ownership,
        )

    assert ownership.owner_at((0, 0, 0)) is None
    assert ownership.owner_at((1, 1, 0)) == "column"
