from __future__ import annotations

import json
from dataclasses import replace

import pytest

from jiangnan_agent.generators.facade_profiles import (
    DoorProfile,
    FacadeOpening,
    FacadeProfile,
    TimberDetailProfile,
    WallPanelProfile,
    WindowProfile,
    decode_facade_profile,
    door_profile_from_mapping,
    door_profile_to_mapping,
    encode_facade_profile,
    facade_opening_from_mapping,
    facade_opening_to_mapping,
    facade_profile_from_mapping,
    facade_profile_to_mapping,
    timber_detail_profile_from_mapping,
    timber_detail_profile_to_mapping,
    wall_panel_profile_from_mapping,
    wall_panel_profile_to_mapping,
    window_profile_from_mapping,
    window_profile_to_mapping,
)
from jiangnan_agent.generators.hall import CorridorParameters, HallParameters


def _primary(opening_id: str = "entry.main", *, offset: int = 0) -> FacadeOpening:
    return FacadeOpening(
        opening_id=opening_id,
        face="front",
        kind="door",
        connection_use="primary_entry",
        segment_index=1,
        offset=offset,
        sill_offset=0,
    )


def _profile(*, openings: tuple[FacadeOpening, ...] | None = None) -> FacadeProfile:
    return FacadeProfile(
        profile_id="test_facade",
        version=1,
        wall=WallPanelProfile(thickness=2, expand_direction="inward", layer_roles=("wall", "wall_inner")),
        door=DoorProfile(width=2, height=2, frame_thickness=1),
        window=WindowProfile(width=2, height=2, sill_height=2, lattice_style="grid"),
        timber=TimberDetailProfile(exterior_posts=True, beam_layers=2),
        openings=(_primary(),) if openings is None else openings,
        materials={"wall": "white_terracotta", "wall_inner": "minecraft:calcite"},
        enclosed_faces=("rear", "front"),
    )


def test_every_typed_profile_has_deterministic_json_codec() -> None:
    profile = _profile()

    encoded = encode_facade_profile(profile)
    decoded = decode_facade_profile(encoded)

    assert decoded == profile
    assert encoded == encode_facade_profile(decoded)
    assert json.loads(encoded) == facade_profile_to_mapping(profile)
    assert facade_profile_from_mapping(facade_profile_to_mapping(profile)) == profile
    assert facade_opening_from_mapping(facade_opening_to_mapping(profile.openings[0])) == profile.openings[0]
    assert isinstance(profile.wall, WallPanelProfile)
    assert isinstance(profile.door, DoorProfile)
    assert isinstance(profile.window, WindowProfile)
    assert isinstance(profile.timber, TimberDetailProfile)


def test_each_profile_record_round_trips_through_its_canonical_mapping() -> None:
    profile = _profile()
    pairs = (
        (profile.openings[0], facade_opening_to_mapping, facade_opening_from_mapping),
        (profile.wall, wall_panel_profile_to_mapping, wall_panel_profile_from_mapping),
        (profile.door, door_profile_to_mapping, door_profile_from_mapping),
        (profile.window, window_profile_to_mapping, window_profile_from_mapping),
        (profile.timber, timber_detail_profile_to_mapping, timber_detail_profile_from_mapping),
    )

    for original, encode, decode in pairs:
        mapping = encode(original)
        serialized = json.dumps(mapping, sort_keys=True, separators=(",", ":"))
        assert decode(json.loads(serialized)) == original
        assert json.dumps(encode(decode(json.loads(serialized))), sort_keys=True, separators=(",", ":")) == serialized


@pytest.mark.parametrize("opening_id", ["", "   "])
def test_opening_rejects_empty_stable_id(opening_id: str) -> None:
    with pytest.raises(ValueError, match="opening_id"):
        FacadeOpening(opening_id, "front", "door", "non_connecting", 0, 0, 0)


def test_profile_rejects_duplicate_opening_ids() -> None:
    first = _primary("door.front")
    duplicate = FacadeOpening("door.front", "front", "window", "non_connecting", 0, 2, 2)

    with pytest.raises(ValueError, match="unique"):
        _profile(openings=(first, duplicate))


def test_profile_normalizes_and_validates_enclosed_faces() -> None:
    assert _profile().enclosed_faces == ("front", "rear")
    with pytest.raises(ValueError, match="enclosed_faces"):
        FacadeProfile(profile_id="duplicate-faces", enclosed_faces=("front", "front"))
    with pytest.raises(ValueError, match="enclosed_faces"):
        FacadeProfile(profile_id="invalid-face", enclosed_faces=("roof",))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("face", "top"),
        ("kind", "archway"),
        ("connection_use", "rear_anchor"),
    ],
)
def test_opening_rejects_unsupported_face_kind_or_connection_use(field: str, value: str) -> None:
    values = {
        "opening_id": "opening.invalid",
        "face": "front",
        "kind": "door",
        "connection_use": "non_connecting",
        "segment_index": 0,
        "offset": 0,
        "sill_offset": 0,
    }
    values[field] = value

    with pytest.raises(ValueError, match=field):
        FacadeOpening(**values)


@pytest.mark.parametrize(
    "factory",
    [
        lambda: WallPanelProfile(thickness=0),
        lambda: DoorProfile(width=3),
        lambda: DoorProfile(height=0),
        lambda: WindowProfile(width=0),
        lambda: WindowProfile(height=0),
        lambda: TimberDetailProfile(beam_layers=0),
    ],
)
def test_profiles_reject_invalid_dimensions(factory) -> None:
    with pytest.raises(ValueError):
        factory()


@pytest.mark.parametrize("openings", [(), (_primary(), _primary("entry.second", offset=3))])
def test_hall_profile_requires_exactly_one_primary_front_entry(openings: tuple[FacadeOpening, ...]) -> None:
    profile = _profile(openings=openings)

    with pytest.raises(ValueError, match="exactly one.*primary_entry"):
        HallParameters(facade_profile=profile)


def test_hall_door_width_default_remains_visible_and_only_explicit_conflict_errors() -> None:
    profile = _profile()
    single_door_profile = replace(profile, door=DoorProfile(width=1))

    assert HallParameters().door_width == 2
    assert HallParameters(facade_profile=profile).door_width == 2
    assert HallParameters(facade_profile=profile, door_width=2).door_width == 2
    assert HallParameters(facade_profile=single_door_profile).door_width == 2
    with pytest.raises(ValueError, match="door_width.*facade.*width"):
        HallParameters(facade_profile=profile, door_width=1)
    with pytest.raises(ValueError, match="door_width.*facade.*width"):
        HallParameters(facade_profile=single_door_profile, door_width=2)


def test_hall_and_corridor_parameters_coerce_profile_mappings_to_typed_values() -> None:
    profile_mapping = facade_profile_to_mapping(_profile())

    hall = HallParameters(facade_profile=profile_mapping)
    corridor = CorridorParameters(facade_profile=profile_mapping)

    assert isinstance(hall.facade_profile, FacadeProfile)
    assert isinstance(corridor.facade_profile, FacadeProfile)


def test_legacy_material_conflict_is_checked_only_for_explicit_overlapping_roles() -> None:
    profile = _profile()

    assert HallParameters(facade_profile=profile).materials is None
    with pytest.raises(ValueError, match="materials.*facade"):
        HallParameters(materials={"wall": "minecraft:calcite"}, facade_profile=profile)
    assert HallParameters(materials={"wall": "minecraft:white_terracotta"}, facade_profile=profile)


def test_profile_decoder_rejects_duplicate_json_keys() -> None:
    with pytest.raises(ValueError, match="duplicate JSON key"):
        decode_facade_profile('{"profile_id":"first","profile_id":"second"}')
