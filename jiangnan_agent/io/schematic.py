"""Sponge Schematic v3 gzip-NBT reader and writer."""

from __future__ import annotations

from dataclasses import dataclass
import gzip
from pathlib import Path
from typing import Any

from nbtlib import ByteArray, Compound, File, Int, IntArray, List, Short, String

from ..core.block import BlockState
from ..core.geometry import Position
from ..core.scene import AIR, VoxelModel

SPONGE_SCHEMATIC_VERSION = 3
MAX_DIMENSION = 65535


@dataclass(frozen=True)
class SchematicDocument:
    model: VoxelModel
    data_version: int
    offset: Position = (0, 0, 0)
    name: str = ""
    author: str = ""


def encode_varint(value: int) -> bytes:
    if value < 0:
        raise ValueError("palette indices must be nonnegative")
    encoded = bytearray()
    while value & ~0x7F:
        encoded.append((value & 0x7F) | 0x80)
        value >>= 7
    encoded.append(value)
    return bytes(encoded)


def decode_varints(data: bytes) -> list[int]:
    values: list[int] = []
    value = shift = 0
    for byte in data:
        value |= (byte & 0x7F) << shift
        if byte & 0x80:
            shift += 7
            if shift >= 35:
                raise ValueError("invalid VarInt in schematic block data")
        else:
            values.append(value)
            value = shift = 0
    if shift:
        raise ValueError("truncated VarInt in schematic block data")
    return values


def _palette_byte_array(data: bytes) -> ByteArray:
    return ByteArray([byte if byte < 128 else byte - 256 for byte in data])


def write_schematic(
    model: VoxelModel,
    path: str | Path,
    *,
    data_version: int = 4325,
    name: str = "",
    author: str = "",
    offset: Position | None = None,
) -> Path:
    """Write a model as Sponge Schematic v3, compressed with gzip."""

    if not model.blocks:
        raise ValueError("cannot write a schematic with no blocks")
    if data_version <= 0:
        raise ValueError("data_version must be a positive integer")

    bounds = model.bounds
    width, height, length = bounds.size
    if any(dimension < 1 or dimension > MAX_DIMENSION for dimension in (width, height, length)):
        raise ValueError(f"Sponge v3 dimensions must be between 1 and {MAX_DIMENSION}")
    schematic_offset = offset if offset is not None else (bounds.min_x, bounds.min_y, bounds.min_z)
    if len(schematic_offset) != 3:
        raise ValueError("offset must contain exactly three integers")

    states = sorted(set(model.blocks.values()) | {AIR}, key=BlockState.to_string)
    palette = {state: index for index, state in enumerate(states)}
    palette_tag = Compound({state.to_string(): Int(index) for state, index in palette.items()})

    block_data = bytearray()
    for y in range(bounds.min_y, bounds.max_y):
        for z in range(bounds.min_z, bounds.max_z):
            for x in range(bounds.min_x, bounds.max_x):
                state = model.block_at((x, y, z))
                block_data.extend(encode_varint(palette[state]))

    metadata = Compound()
    if name:
        metadata["Name"] = String(name)
    if author:
        metadata["Author"] = String(author)
    biome_count = width * height * length
    def nbt_unsigned_short(value: int) -> Short:
        return Short(value if value < 32768 else value - 65536)

    root = File(
        {
            "Version": Int(SPONGE_SCHEMATIC_VERSION),
            "DataVersion": Int(data_version),
            "Metadata": metadata,
            "Width": nbt_unsigned_short(width),
            "Height": nbt_unsigned_short(height),
            "Length": nbt_unsigned_short(length),
            "Offset": IntArray([Int(value) for value in schematic_offset]),
            "Blocks": Compound(
                {
                    "Palette": palette_tag,
                    "Data": _palette_byte_array(bytes(block_data)),
                    "BlockEntities": List[Compound]([]),
                }
            ),
            "Biomes": Compound({
                "Palette": Compound({"minecraft:plains": Int(0)}),
                "Data": _palette_byte_array(encode_varint(0) * biome_count),
            }),
            "Entities": List[Compound]([]),
        },
        root_name="Schematic",
    )

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    root.save(destination, gzipped=True, byteorder="big")
    return destination


def read_schematic(path: str | Path) -> SchematicDocument:
    """Read Sponge Schematic v3 into a local-coordinate voxel model."""

    source = Path(path)
    try:
        root = File.load(source, gzipped=True, byteorder="big")
    except (OSError, gzip.BadGzipFile, ValueError) as exc:
        raise ValueError(f"could not read Sponge schematic {source}: {exc}") from exc

    version = int(root.get("Version", -1))
    if version != SPONGE_SCHEMATIC_VERSION:
        raise ValueError(f"expected Sponge schematic version 3, found {version}")
    try:
        width = int(root["Width"]) & 0xFFFF
        height = int(root["Height"]) & 0xFFFF
        length = int(root["Length"]) & 0xFFFF
        data_version = int(root["DataVersion"])
        blocks_tag = root["Blocks"]
        palette_tag = blocks_tag["Palette"]
        raw_data = bytes(int(value) & 0xFF for value in blocks_tag["Data"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"schematic is missing required Sponge v3 fields: {exc}") from exc

    if any(dimension < 1 or dimension > MAX_DIMENSION for dimension in (width, height, length)):
        raise ValueError("schematic dimensions are outside the supported range")
    palette_by_index: dict[int, BlockState] = {}
    for state_string, raw_index in palette_tag.items():
        index = int(raw_index)
        if index < 0 or index in palette_by_index:
            raise ValueError(f"invalid duplicate or negative palette index: {index}")
        palette_by_index[index] = BlockState.parse(str(state_string))
    if not palette_by_index or sorted(palette_by_index) != list(range(len(palette_by_index))):
        raise ValueError("block palette indices must be contiguous starting at zero")

    palette_indices = decode_varints(raw_data)
    volume = width * height * length
    if len(palette_indices) != volume:
        raise ValueError(f"block data contains {len(palette_indices)} values; expected {volume}")

    model = VoxelModel()
    for index, palette_index in enumerate(palette_indices):
        if palette_index not in palette_by_index:
            raise ValueError(f"block data references missing palette index {palette_index}")
        state = palette_by_index[palette_index]
        if state == AIR:
            continue
        x = index % width
        z = (index // width) % length
        y = index // (width * length)
        model.set_block((x, y, z), state)

    if "Offset" in root:
        raw_offset = root["Offset"]
    else:
        raw_offset = IntArray([0, 0, 0])
    if len(raw_offset) != 3:
        raise ValueError("schematic Offset must contain exactly three integers")
    offset = tuple(int(value) for value in raw_offset)
    metadata: Any = root["Metadata"] if "Metadata" in root else Compound()
    return SchematicDocument(
        model=model,
        data_version=data_version,
        offset=offset,
        name=str(metadata.get("Name", "")),
        author=str(metadata.get("Author", "")),
    )
