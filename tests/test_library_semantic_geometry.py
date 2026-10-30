from __future__ import annotations

from pathlib import Path

import pytest

from jiangnan_agent.library.litematic import read_litematic
from jiangnan_agent.library.semantics import (
    decode_x_runs,
    encode_x_runs,
    normalize_annotation_geometry,
    summarize_annotation,
)
from test_litematic_parser import _write_litematic


def test_exact_coordinate_runs_are_sorted_coalesced_and_round_trip() -> None:
    positions = [(-1, 0, -3), (0, 0, -3), (2, 0, -3), (0, 1, -3)]

    runs = encode_x_runs(positions)

    assert runs == ((0, -3, -1, 1), (0, -3, 2, 3), (1, -3, 0, 1))
    assert decode_x_runs(runs) == tuple(sorted(positions, key=lambda p: (p[1], p[2], p[0])))
    with pytest.raises(ValueError, match="allowed"):
        decode_x_runs(((0, 0, 0, 1_000_000_000),), max_positions=12)


def test_region_box_and_exact_selectors_summarize_negative_signed_coordinates(tmp_path: Path) -> None:
    source = _write_litematic(
        tmp_path / "references" / "negative.litematic",
        regions={"west": ((2, 0, -3), (-3, 2, 2), [1, 2, 0, 1, 0, 0, 0, 0, 0, 0, 0, 3], 4)},
        data_version=3465,
    )
    region = read_litematic(source).regions[0]

    whole_region = summarize_annotation(region, "unknown", "region", {})
    box = summarize_annotation(
        region,
        "roof_surface",
        "box",
        {"min": [1, 0, -3], "max": [3, 1, -2]},
    )
    exact_geometry = normalize_annotation_geometry(
        region,
        "block_set",
        {"positions": [[2, 0, -3], [1, 0, -3]]},
    )
    exact = summarize_annotation(region, "roof_surface", "block_set", exact_geometry)

    assert whole_region.block_count == 4
    assert whole_region.bounding_box == ((0, 0, -3), (3, 2, -1))
    assert box.block_count == 2
    assert box.block_states == {
        "minecraft:oak_stairs[facing=east,half=bottom,shape=inner_left,waterlogged=false]": 1,
        "minecraft:stone": 1,
    }
    assert exact.block_count == 2
    assert exact.local_origin == (1, 0, -3)
    assert exact.coordinate_runs == ((0, 0, 0, 2),)


@pytest.mark.parametrize(
    "geometry",
    [
        {"positions": [[2, 0, -3], [2, 0, -3]]},
        {"positions": [[1, 0, -2]]},
        {"positions": [[5, 0, 0]]},
    ],
    ids=("duplicate-coordinate", "air-coordinate", "off-region-coordinate"),
)
def test_exact_block_set_rejects_duplicate_air_and_off_region_coordinates(tmp_path: Path, geometry: dict) -> None:
    source = _write_litematic(
        tmp_path / "references" / "negative.litematic",
        regions={"west": ((2, 0, -3), (-3, 2, 2), [1, 2, 0, 1, 0, 0, 0, 0, 0, 0, 0, 3], 4)},
    )
    region = read_litematic(source).regions[0]

    with pytest.raises(ValueError):
        normalize_annotation_geometry(region, "block_set", geometry)


def test_half_open_box_rejects_empty_and_outside_region_bounds(tmp_path: Path) -> None:
    source = _write_litematic(
        tmp_path / "references" / "negative.litematic",
        regions={"west": ((2, 0, -3), (-3, 2, 2), [1] + [0] * 11, 2)},
    )
    region = read_litematic(source).regions[0]

    with pytest.raises(ValueError, match="non-empty"):
        normalize_annotation_geometry(region, "box", {"min": [1, 0, -3], "max": [1, 1, -2]})
    with pytest.raises(ValueError, match="outside"):
        normalize_annotation_geometry(region, "box", {"min": [-1, 0, -3], "max": [1, 1, -2]})
