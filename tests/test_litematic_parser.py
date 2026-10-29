from __future__ import annotations

import gzip
from pathlib import Path

import pytest
from nbtlib import Compound, File, Int, List, LongArray, String

from jiangnan_agent.library.litematic import LitematicFormatError, analyze_litematic, read_litematic


MASK64 = (1 << 64) - 1


def _pack(values: list[int], palette_size: int) -> list[int]:
    bits = max(2, (palette_size - 1).bit_length())
    words = [0] * ((len(values) * bits + 63) // 64)
    mask = (1 << bits) - 1
    for index, value in enumerate(values):
        assert 0 <= value <= mask
        bit_index = index * bits
        word_index, bit_offset = divmod(bit_index, 64)
        words[word_index] |= (value & mask) << bit_offset
        if bit_offset + bits > 64:
            words[word_index + 1] |= value >> (64 - bit_offset)
    return [word if word <= (1 << 63) - 1 else word - (1 << 64) for word in words]


def _palette_entry(name: str, **properties: str) -> Compound:
    return Compound(
        {
            "Name": String(name),
            "Properties": Compound({key: String(value) for key, value in properties.items()}),
        }
    )


def _write_litematic(
    path: Path,
    *,
    regions: dict[str, tuple[tuple[int, int, int], tuple[int, int, int], list[int], int]],
    palette: list[Compound] | None = None,
    data_version: int = 4325,
    schematic_version: int = 6,
) -> Path:
    shared_palette = palette or [
        _palette_entry("minecraft:air"),
        _palette_entry("minecraft:stone"),
        _palette_entry("minecraft:oak_stairs", facing="east", half="bottom", shape="inner_left", waterlogged="false"),
        _palette_entry("minecraft:glass"),
        _palette_entry("minecraft:oak_log", axis="y"),
    ]
    region_tags = Compound()
    for name, (position, size, values, local_palette_size) in regions.items():
        region_volume = abs(size[0]) * abs(size[1]) * abs(size[2])
        assert len(values) == region_volume
        region_tags[name] = Compound(
            {
                "Position": Compound({axis: Int(value) for axis, value in zip("xyz", position)}),
                "Size": Compound({axis: Int(value) for axis, value in zip("xyz", size)}),
                "BlockStatePalette": List[Compound](shared_palette[:local_palette_size]),
                "BlockStates": LongArray(_pack(values, local_palette_size)),
            }
        )
    data = File(
        {
            "Version": Int(schematic_version),
            "SubVersion": Int(1),
            "MinecraftDataVersion": Int(data_version),
            "Metadata": Compound(
                {"Name": String("Synthetic fixture"), "Author": String("Fixture author")}
            ),
            "Regions": region_tags,
        }
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb") as compressed:
        data.write(compressed)
    return path


def test_parser_preserves_signed_coordinates_states_and_tightly_packed_values(tmp_path: Path) -> None:
    values = [0] * 12
    values[0] = 1
    values[1] = 2
    values[3] = 1
    values[11] = 3
    source = _write_litematic(
        tmp_path / "negative.litematic",
        regions={"main": ((2, 0, -3), (-3, 2, 2), values, 4)},
        data_version=3465,
    )

    document = read_litematic(source)
    region = document.regions[0]
    blocks = dict(region.iter_non_air_blocks())
    analysis = analyze_litematic(document, target_data_version=4325)

    assert document.schematic_version == 6
    assert document.minecraft_data_version == 3465
    assert document.author == "Fixture author"
    assert region.position == (2, 0, -3)
    assert region.signed_size == (-3, 2, 2)
    assert region.size == (3, 2, 2)
    assert blocks[(2, 0, -3)].name == "minecraft:stone"
    assert blocks[(1, 0, -3)].properties == {
        "facing": "east",
        "half": "bottom",
        "shape": "inner_left",
        "waterlogged": "false",
    }
    assert blocks[(2, 0, -2)].name == "minecraft:stone"
    assert blocks[(0, 1, -2)].name == "minecraft:glass"
    assert analysis.dimensions == (3, 2, 2)
    assert analysis.bounding_box == ((0, 0, -3), (3, 2, -1))
    assert analysis.block_count == 4
    assert analysis.compatibility_status == "older_than_target"
    assert analysis.layer_counts[0] == 3
    assert analysis.layer_counts[1] == 1


def test_parser_keeps_multiple_regions_and_union_bounds(tmp_path: Path) -> None:
    source = _write_litematic(
        tmp_path / "multi.litematic",
        regions={
            "west": ((-4, 2, 5), (-1, -1, 2), [1, 0], 2),
            "east": ((6, -3, -2), (1, 1, -1), [3], 4),
        },
    )

    document = read_litematic(source)
    analysis = analyze_litematic(document)

    assert {region.name for region in document.regions} == {"west", "east"}
    assert analysis.region_count == 2
    assert analysis.dimensions == (11, 6, 8)
    assert analysis.bounding_box == ((-4, -3, -2), (7, 3, 6))
    assert analysis.block_count == 2


def test_parser_rejects_palette_indices_outside_the_palette(tmp_path: Path) -> None:
    source = _write_litematic(
        tmp_path / "bad-index.litematic",
        regions={"bad": ((0, 0, 0), (1, 1, 1), [3], 2)},
    )

    with pytest.raises(LitematicFormatError, match="palette index"):
        read_litematic(source)


def test_parser_reports_newer_data_version_without_claiming_compatibility(tmp_path: Path) -> None:
    source = _write_litematic(
        tmp_path / "newer.litematic",
        regions={"newer": ((0, 0, 0), (1, 1, 1), [1], 2)},
        data_version=999999,
    )

    result = analyze_litematic(read_litematic(source), target_data_version=4325)

    assert result.compatibility_status == "newer_than_target"


def test_parser_accepts_nonempty_long_array_with_zero_first_word(tmp_path: Path) -> None:
    values = [0] * 40
    values[32] = 1
    source = _write_litematic(
        tmp_path / "leading-air.litematic",
        regions={"main": ((0, 0, 0), (40, 1, 1), values, 2)},
    )

    document = read_litematic(source)
    analysis = analyze_litematic(document)

    assert document.regions[0].packed_states[0] == 0
    assert len(document.regions[0].packed_states) == 2
    assert analysis.block_count == 1
    assert analysis.bounding_box == ((32, 0, 0), (33, 1, 1))


@pytest.mark.parametrize("payload", [b"", b"not an NBT file", gzip.compress(b"truncated")])
def test_parser_rejects_invalid_or_truncated_files(tmp_path: Path, payload: bytes) -> None:
    source = tmp_path / "corrupt.litematic"
    source.write_bytes(payload)

    with pytest.raises(LitematicFormatError):
        read_litematic(source)


def test_parser_rejects_unsupported_litematic_container_version(tmp_path: Path) -> None:
    source = _write_litematic(
        tmp_path / "future-container.litematic",
        regions={"main": ((0, 0, 0), (1, 1, 1), [1], 2)},
        schematic_version=99,
    )

    with pytest.raises(LitematicFormatError, match="unsupported Litematic format Version 99"):
        read_litematic(source)
