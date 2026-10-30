from __future__ import annotations

import pytest

from jiangnan_agent.assembly.transforms import mirror_module, rotate_module
from jiangnan_agent.assembly.model import Module
from jiangnan_agent.core.block import BlockState
from jiangnan_agent.core.geometry import BoundingBox
from jiangnan_agent.core.scene import VoxelModel
from jiangnan_agent.generators.facade_components import generate_facade_door, generate_facade_window
from jiangnan_agent.generators.facade_geometry import BlockOwnershipMap, OpeningMask
from jiangnan_agent.generators.facade_profiles import DoorProfile, WindowProfile


def _box(face: str, origin: tuple[int, int, int], width: int, height: int) -> BoundingBox:
    axis = 0 if face in {"front", "rear"} else 2
    positions = []
    for u in range(width):
        for y_offset in range(height):
            position = list(origin)
            position[axis] += u
            position[1] += y_offset
            positions.append(tuple(position))
    return BoundingBox.from_positions(positions)


def _context(face: str, origin: tuple[int, int, int], width: int, height: int, opening_id: str, kind: str):
    mask = OpeningMask()
    mask.reserve(opening_id, kind, _box(face, origin, width, height))
    return mask, BlockOwnershipMap(opening_mask=mask)


@pytest.mark.parametrize(
    ("face", "origin", "facing", "first_hinge"),
    [
        ("front", (2, 1, 6), "south", "left"),
        ("rear", (2, 1, 0), "north", "right"),
        ("left", (0, 1, 2), "west", "left"),
        ("right", (10, 1, 2), "east", "right"),
    ],
)
def test_double_door_has_correct_two_leaf_states_on_each_face(
    face: str,
    origin: tuple[int, int, int],
    facing: str,
    first_hinge: str,
) -> None:
    opening_id = f"entry.{face}"
    mask, ownership = _context(face, origin, 2, 2, opening_id, "door")

    door = generate_facade_door(
        origin,
        DoorProfile(width=2, frame_thickness=0, lintel=False),
        face,
        ownership,
        mask,
        opening_id=opening_id,
        materials={"door": "minecraft:spruce_door"},
    )

    assert len(door.blocks) == 4
    base = door.block_at(origin)
    assert dict(base.properties) == {
        "facing": facing,
        "half": "lower",
        "hinge": first_hinge,
        "open": "false",
        "powered": "false",
    }
    second = list(origin)
    second[0 if face in {"front", "rear"} else 2] += 1
    assert dict(door.block_at(tuple(second)).properties)["hinge"] == (
        "right" if first_hinge == "left" else "left"
    )
    assert all(ownership.owner_at(position) == "door" for position in door.blocks)


def test_single_door_has_two_halves_and_one_stable_opening_claim() -> None:
    origin = (4, 2, 5)
    mask, ownership = _context("front", origin, 1, 2, "entry.main", "door")

    door = generate_facade_door(
        origin,
        DoorProfile(width=1, frame_thickness=0, lintel=False),
        "front",
        ownership,
        mask,
        opening_id="entry.main",
        materials={"door": "minecraft:oak_door"},
    )

    assert len(door.blocks) == 2
    assert door.block_at(origin).to_string() == (
        "minecraft:oak_door[facing=south,half=lower,hinge=left,open=false,powered=false]"
    )
    assert dict(door.block_at((4, 3, 5)).properties)["half"] == "upper"


def test_door_frames_and_lintel_replace_only_explicitly_permitted_wall_cells() -> None:
    origin = (1, 1, 4)
    opening_id = "entry.frame-test"
    mask, ownership = _context("front", origin, 1, 2, opening_id, "door")
    frame_cells = {(0, 1, 4), (0, 2, 4), (2, 1, 4), (2, 2, 4), (0, 3, 4), (1, 3, 4), (2, 3, 4)}
    for position in frame_cells:
        ownership.claim(position, "wall")
        ownership.allow_replacement(position, "frame")

    door = generate_facade_door(
        origin,
        DoorProfile(width=1, frame_thickness=1),
        "front",
        ownership,
        mask,
        opening_id=opening_id,
        materials={
            "door": "minecraft:spruce_door",
            "column": "minecraft:stripped_spruce_log",
            "beam": "minecraft:stripped_spruce_log",
        },
    )

    assert len(door.blocks) == 9
    assert all(ownership.owner_at(position) == "frame" for position in frame_cells)
    assert ownership.owner_at(origin) == "door"


def test_frame_collision_with_another_reserved_opening_is_atomic() -> None:
    origin = (1, 1, 4)
    mask = OpeningMask()
    mask.reserve("entry.main", "door", _box("front", origin, 1, 2))
    mask.reserve("window.overlap", "window", BoundingBox(0, 1, 4, 1, 2, 5))
    ownership = BlockOwnershipMap(opening_mask=mask)

    with pytest.raises(ValueError, match="reserved opening"):
        generate_facade_door(
            origin,
            DoorProfile(width=1, frame_thickness=1),
            "front",
            ownership,
            mask,
            opening_id="entry.main",
            materials={
                "door": "minecraft:spruce_door",
                "column": "minecraft:stripped_spruce_log",
                "beam": "minecraft:stripped_spruce_log",
            },
        )

    assert ownership.owner_at(origin) is None


def test_door_frame_cannot_replace_undeclared_wall_cells() -> None:
    origin = (1, 1, 4)
    mask, ownership = _context("front", origin, 1, 2, "entry.undeclared", "door")
    wall_jamb = (0, 1, 4)
    ownership.claim(wall_jamb, "wall")

    with pytest.raises(ValueError, match="undeclared replacement"):
        generate_facade_door(
            origin,
            DoorProfile(width=1, frame_thickness=1),
            "front",
            ownership,
            mask,
            opening_id="entry.undeclared",
            materials={
                "door": "minecraft:spruce_door",
                "column": "minecraft:stripped_spruce_log",
                "beam": "minecraft:stripped_spruce_log",
            },
        )

    assert ownership.owner_at(wall_jamb) == "wall"
    assert ownership.owner_at(origin) is None


@pytest.mark.parametrize("face", ["front", "rear", "left", "right"])
def test_plain_and_grid_windows_keep_requested_dimensions_and_material_roles(face: str) -> None:
    origin = {"front": (2, 3, 6), "rear": (2, 3, 0), "left": (0, 3, 2), "right": (10, 3, 2)}[face]
    opening_id = f"window.{face}"
    mask, ownership = _context(face, origin, 3, 3, opening_id, "window")

    plain = generate_facade_window(
        origin,
        WindowProfile(width=3, height=3, frame_thickness=0, lattice_style="plain"),
        face,
        ownership,
        mask,
        opening_id=opening_id,
        materials={"window": "minecraft:white_stained_glass_pane"},
    )
    grid_mask, grid_ownership = _context(face, origin, 3, 3, opening_id, "window")
    grid = generate_facade_window(
        origin,
        WindowProfile(width=3, height=3, frame_thickness=0, lattice_style="grid"),
        face,
        grid_ownership,
        grid_mask,
        opening_id=opening_id,
        materials={"window": "minecraft:glass_pane", "lattice": "minecraft:iron_bars"},
    )

    assert len(plain.blocks) == len(grid.blocks) == 9
    assert set(state.block_id for state in grid.blocks.values()) == {
        "minecraft:glass_pane",
        "minecraft:iron_bars",
    }
    assert sum(state.block_id == "minecraft:iron_bars" for state in grid.blocks.values()) == 5
    for state in grid.blocks.values():
        properties = dict(state.properties)
        assert {"north", "east", "south", "west", "waterlogged"} == set(properties)
        assert properties["waterlogged"] == "false"


def test_window_frame_uses_only_declared_wall_replacements() -> None:
    origin = (1, 2, 4)
    opening_id = "window.frame-test"
    mask, ownership = _context("front", origin, 2, 2, opening_id, "window")
    frame_cells = {
        (x, y, 4)
        for x in (0, 3)
        for y in (2, 3)
    } | {(x, y, 4) for x in (0, 1, 2, 3) for y in (1, 4)}
    for position in frame_cells:
        ownership.claim(position, "wall")
        ownership.allow_replacement(position, "frame")

    window = generate_facade_window(
        origin,
        WindowProfile(width=2, height=2, frame_thickness=1, lattice_style="plain"),
        "front",
        ownership,
        mask,
        opening_id=opening_id,
        materials={"window": "minecraft:glass", "beam": "minecraft:stripped_spruce_log"},
    )

    assert all(ownership.owner_at(position) == "frame" for position in frame_cells)
    assert sum(state.block_id == "minecraft:glass" for state in window.blocks.values()) == 4


def test_rectangular_cross_lattice_tracks_both_diagonals() -> None:
    origin = (2, 1, 4)
    mask, ownership = _context("front", origin, 3, 5, "window.cross", "window")
    window = generate_facade_window(
        origin,
        WindowProfile(width=3, height=5, frame_thickness=0, lattice_style="cross"),
        "front",
        ownership,
        mask,
        opening_id="window.cross",
        materials={"window": "minecraft:glass_pane", "lattice": "minecraft:iron_bars"},
    )

    lattice = {
        (x - origin[0], y - origin[1])
        for (x, y, _z), state in window.blocks.items()
        if state.block_id == "minecraft:iron_bars"
    }
    assert lattice == {(0, 0), (2, 0), (1, 1), (1, 2), (0, 3), (2, 3), (0, 4), (2, 4)}


def test_grid_window_without_a_discrete_divider_needs_no_lattice_material() -> None:
    origin = (0, 1, 2)
    mask, ownership = _context("front", origin, 1, 1, "window.small-grid", "window")

    window = generate_facade_window(
        origin,
        WindowProfile(width=1, height=1, frame_thickness=0, lattice_style="grid"),
        "front",
        ownership,
        mask,
        opening_id="window.small-grid",
        materials={"window": "minecraft:glass_pane"},
    )

    assert len(window.blocks) == 1
    assert next(iter(window.blocks.values())).block_id == "minecraft:glass_pane"


def test_window_lattice_rotates_and_mirrors_directional_connections() -> None:
    origin = (0, 1, 4)
    mask, ownership = _context("front", origin, 3, 3, "window.transform", "window")
    window = generate_facade_window(
        origin,
        WindowProfile(width=3, height=3, frame_thickness=0, lattice_style="vertical"),
        "front",
        ownership,
        mask,
        opening_id="window.transform",
        materials={"window": "minecraft:glass_pane", "lattice": "minecraft:iron_bars"},
    )
    # At the left edge, the pane joins the right side of the face-local grid.
    original = window.block_at((0, 1, 4))
    assert dict(original.properties)["east"] == "true"

    module = Module("window", "component", window)
    rotated = rotate_module(module, 1).model.block_at((0, 1, 4))
    mirrored = mirror_module(module, "x").model.block_at((2, 1, 4))
    assert dict(rotated.properties)["south"] == "true"
    assert dict(rotated.properties)["east"] == "false"
    assert dict(mirrored.properties)["west"] == "true"
    assert dict(mirrored.properties)["east"] == "false"


def test_invalid_directional_lattice_state_fails_closed_on_transform() -> None:
    bad_state = BlockState("minecraft:iron_bars", (("north", "sideways"),))
    model = VoxelModel()
    model.set_block((0, 0, 0), bad_state)
    module = Module("bad-window", "component", model)

    with pytest.raises(ValueError, match="connection block state value"):
        rotate_module(module, 1)
