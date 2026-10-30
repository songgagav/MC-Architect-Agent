from __future__ import annotations

import importlib

import pytest


def _roof_profiles():
    try:
        return importlib.import_module("jiangnan_agent.generators.roof_profiles")
    except ModuleNotFoundError as exc:
        if exc.name == "jiangnan_agent.generators.roof_profiles":
            pytest.fail("typed roof profile API has not been implemented", pytrace=False)
        raise


def test_linear_roof_section_keeps_the_legacy_three_rise_shape() -> None:
    roof_profiles = _roof_profiles()
    assert roof_profiles.sample_roof_section(3, 3, ((0, 0), (1000, 1000))) == (0, 1, 2, 3)


def test_flattened_roof_section_keeps_two_upper_rows_at_the_same_height() -> None:
    roof_profiles = _roof_profiles()
    points = ((0, 0), (333, 500), (667, 500), (1000, 1000))

    assert roof_profiles.sample_roof_section(3, 2, points) == (0, 1, 1, 2)


def test_linear_section_resamples_deterministically_for_a_longer_span() -> None:
    roof_profiles = _roof_profiles()
    assert roof_profiles.sample_roof_section(4, 3, ((0, 0), (1000, 1000))) == (0, 1, 2, 2, 3)


def test_section_rejects_a_sample_that_would_rise_two_blocks_at_once() -> None:
    roof_profiles = _roof_profiles()
    with pytest.raises(ValueError, match="height step"):
        roof_profiles.sample_roof_section(2, 3, ((0, 0), (1000, 1000)))


def test_section_rejects_zero_half_run() -> None:
    roof_profiles = _roof_profiles()
    with pytest.raises(ValueError, match="half_run"):
        roof_profiles.sample_roof_section(0, 1, ((0, 0), (1000, 1000)))


@pytest.mark.parametrize(
    "points",
    [
        ((1, 0), (1000, 1000)),
        ((0, 0), (1000, 999)),
        ((0, 0), (700, 800), (600, 900), (1000, 1000)),
        ((0, 0), (500, 800), (1000, 700)),
        ((0, 0), (500, -1), (1000, 1000)),
    ],
)
def test_section_rejects_malformed_or_non_monotonic_control_points(points) -> None:
    roof_profiles = _roof_profiles()
    with pytest.raises(ValueError, match="control point|section point"):
        roof_profiles.sample_roof_section(3, 2, points)


def test_roof_profile_rejects_a_gapped_material_band_map() -> None:
    roof_profiles = _roof_profiles()
    bands = (
        roof_profiles.SurfaceBand(0, 400, "stair", "roof_stair"),
        roof_profiles.SurfaceBand(401, 1000, "full_block", "roof_block"),
    )

    with pytest.raises(ValueError, match="contiguous|cover"):
        roof_profiles.RoofProfile(surface_bands=bands)


def test_hard_gable_rejects_a_nonzero_gable_projection() -> None:
    roof_profiles = _roof_profiles()
    with pytest.raises(ValueError, match="hard_gable|projection"):
        roof_profiles.EaveProfile(gable_end_treatment="hard_gable", gable_end_projection=1)
