from __future__ import annotations

import gzip
from io import BytesIO
from pathlib import Path

from nbtlib import File

from jiangnan_agent.core.block import BlockState
from jiangnan_agent.core.scene import VoxelModel
from jiangnan_agent.io.schematic import read_schematic, write_schematic


def decode_varints(data: bytes) -> list[int]:
    values: list[int] = []
    value = shift = 0
    for raw_byte in data:
        byte = raw_byte & 0xFF
        value |= (byte & 0x7F) << shift
        if byte & 0x80:
            shift += 7
        else:
            values.append(value)
            value = shift = 0
    assert shift == 0
    return values


def test_sponge_v3_roundtrip_preserves_states_offset_and_data_version(tmp_path: Path) -> None:
    model = VoxelModel()
    model.set_block((0, 0, 0), BlockState.parse("minecraft:oak_stairs[facing=east,half=top]"))
    model.set_block((1, 0, 0), BlockState.parse("minecraft:oak_slab[type=top,waterlogged=false]"))
    model.set_block((0, 0, 1), "minecraft:stone")
    path = tmp_path / "house.schem"

    write_schematic(model, path, data_version=4325, name="House", offset=(4, 5, 6))
    loaded = read_schematic(path)

    assert loaded.data_version == 4325
    assert loaded.offset == (4, 5, 6)
    assert loaded.name == "House"
    assert loaded.model.blocks == model.blocks


def test_sponge_v3_uses_spec_palette_and_xzy_varint_order(tmp_path: Path) -> None:
    model = VoxelModel()
    model.set_block((0, 0, 0), "minecraft:stone")
    model.set_block((1, 0, 0), "minecraft:dirt")
    model.set_block((0, 0, 1), "minecraft:oak_planks")
    path = tmp_path / "ordered.schem"
    write_schematic(model, path, data_version=4325)

    with gzip.open(path, "rb") as stream:
        nbt = File.parse(BytesIO(stream.read()))
    root = nbt
    palette = root["Blocks"]["Palette"]
    data = bytes(int(value) & 0xFF for value in root["Blocks"]["Data"])
    palette_ids = {str(state): int(index) for state, index in palette.items()}

    assert int(root["Version"]) == 3
    assert int(root["Width"]) == 2
    assert int(root["Height"]) == 1
    assert int(root["Length"]) == 2
    assert list(root["Offset"]) == [0, 0, 0]
    assert len(root["Biomes"]["Data"]) == 2 * 1 * 2
    assert decode_varints(data) == [
        palette_ids["minecraft:stone"],
        palette_ids["minecraft:dirt"],
        palette_ids["minecraft:oak_planks"],
        palette_ids["minecraft:air"],
    ]


def test_sponge_v3_roundtrips_unsigned_short_dimensions(tmp_path: Path) -> None:
    model = VoxelModel()
    model.set_block((0, 0, 0), "minecraft:stone")
    model.set_block((39999, 0, 0), "minecraft:dirt")
    path = tmp_path / "wide.schem"

    write_schematic(model, path, data_version=4325)
    loaded = read_schematic(path)

    assert loaded.model.bounds.size == (40000, 1, 1)
    assert loaded.model.block_at((39999, 0, 0)) == BlockState.parse("minecraft:dirt")
