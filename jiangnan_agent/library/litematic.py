"""Read-only reader and streaming analyzer for Litematica NBT schematics."""

from __future__ import annotations

from collections import Counter, defaultdict
import gzip
import math
from pathlib import Path
from typing import Mapping

from nbtlib import Compound, File, List, LongArray

from .errors import LitematicFormatError
from .models import (
    HorizontalSliceSummary,
    LitematicAnalysis,
    LitematicBlockState,
    LitematicDocument,
    LitematicRegion,
    Position3,
)

PARSER_VERSION = "1.0"
TARGET_MINECRAFT_DATA_VERSION = 4325
MAX_LITEMATIC_VERSION = 7
_U64_MASK = (1 << 64) - 1


def _integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise LitematicFormatError(f"{field} must be an NBT integer")
    return int(value)


def _compound_position(value: object, field: str) -> Position3:
    if not isinstance(value, Mapping):
        raise LitematicFormatError(f"{field} must be an NBT compound")
    try:
        return tuple(_integer(value[axis], f"{field}.{axis}") for axis in "xyz")  # type: ignore[return-value]
    except KeyError as exc:
        raise LitematicFormatError(f"{field} is missing axis {exc.args[0]!r}") from exc


def _read_palette(raw: object, region_name: str) -> tuple[LitematicBlockState, ...]:
    if not isinstance(raw, List) or not raw or any(not isinstance(item, Compound) for item in raw):
        raise LitematicFormatError(f"region {region_name!r} has an invalid BlockStatePalette")
    result: list[LitematicBlockState] = []
    for index, item in enumerate(raw):
        name = item.get("Name")
        if not isinstance(name, str) or not name.strip():
            raise LitematicFormatError(f"region {region_name!r} palette item {index} has no block Name")
        raw_properties = item.get("Properties", Compound())
        if not isinstance(raw_properties, Mapping):
            raise LitematicFormatError(f"region {region_name!r} palette item {index} Properties is not a compound")
        properties: dict[str, str] = {}
        for key, value in raw_properties.items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise LitematicFormatError(
                    f"region {region_name!r} palette item {index} property values must be strings"
                )
            properties[key] = str(value)
        result.append(LitematicBlockState(str(name), properties))
    return tuple(result)


def _parse_root(path: Path) -> File:
    try:
        with path.open("rb") as stream:
            magic = stream.read(2)
            stream.seek(0)
            if magic == b"\x1f\x8b":
                with gzip.GzipFile(fileobj=stream, mode="rb") as compressed:
                    return File.parse(compressed)
            return File.parse(stream)
    except Exception as exc:
        raise LitematicFormatError(f"not a valid Litematic NBT file: {exc}") from exc


def read_litematic(path: str | Path) -> LitematicDocument:
    """Read a Litematic source without modifying it or materializing per-block rows."""

    source = Path(path)
    if not source.is_file():
        raise LitematicFormatError(f"Litematic source file does not exist: {source}")
    root = _parse_root(source)
    try:
        schematic_version = _integer(root["Version"], "Version")
        data_version = _integer(root["MinecraftDataVersion"], "MinecraftDataVersion")
        metadata = root["Metadata"]
        regions_tag = root["Regions"]
    except (KeyError, TypeError) as exc:
        raise LitematicFormatError(f"Litematic root is missing required tags: {exc}") from exc
    if not 1 <= schematic_version <= MAX_LITEMATIC_VERSION:
        raise LitematicFormatError(
            f"unsupported Litematic format Version {schematic_version}; supported range is 1..{MAX_LITEMATIC_VERSION}"
        )
    if data_version <= 0:
        raise LitematicFormatError("MinecraftDataVersion must be a positive integer")
    if not isinstance(metadata, Compound):
        raise LitematicFormatError("Metadata must be an NBT compound")
    if not isinstance(regions_tag, Compound) or not regions_tag:
        raise LitematicFormatError("Regions must be a non-empty NBT compound")

    regions: list[LitematicRegion] = []
    for region_name, raw_region in regions_tag.items():
        if not isinstance(region_name, str) or not isinstance(raw_region, Compound):
            raise LitematicFormatError("Regions contains a non-compound entry")
        try:
            position = _compound_position(raw_region["Position"], f"Regions.{region_name}.Position")
            signed_size = _compound_position(raw_region["Size"], f"Regions.{region_name}.Size")
            raw_states = raw_region["BlockStates"]
            raw_region_version = raw_region.get("DataVersion", data_version)
        except KeyError as exc:
            raise LitematicFormatError(f"region {region_name!r} is missing tag {exc.args[0]!r}") from exc
        if any(value == 0 for value in signed_size):
            raise LitematicFormatError(f"region {region_name!r} Size axes must not be zero")
        size = tuple(abs(value) for value in signed_size)
        if any(value > 65535 for value in size):
            raise LitematicFormatError(f"region {region_name!r} dimension exceeds 65535 blocks")
        volume = math.prod(size)
        if volume > 2**31 - 1:
            raise LitematicFormatError(f"region {region_name!r} volume exceeds the supported index range")
        palette = _read_palette(raw_region.get("BlockStatePalette"), region_name)
        if not isinstance(raw_states, LongArray) or len(raw_states) == 0:
            raise LitematicFormatError(f"region {region_name!r} has an invalid or empty BlockStates long array")
        bits = max(2, (len(palette) - 1).bit_length())
        expected_words = (volume * bits + 63) // 64
        if len(raw_states) != expected_words:
            raise LitematicFormatError(
                f"region {region_name!r} BlockStates length is {len(raw_states)}, expected {expected_words}"
            )
        region_data_version = _integer(raw_region_version, f"Regions.{region_name}.DataVersion")
        if region_data_version <= 0:
            raise LitematicFormatError(f"region {region_name!r} DataVersion must be positive")
        region = LitematicRegion(
            name=region_name,
            position=position,
            signed_size=signed_size,
            palette=palette,
            packed_states=tuple(int(word) & _U64_MASK for word in raw_states),
            minecraft_data_version=region_data_version,
        )
        try:
            region.validate_palette_indexes()
        except (IndexError, ValueError) as exc:
            raise LitematicFormatError(f"region {region_name!r} has an invalid palette index: {exc}") from exc
        regions.append(region)

    name = metadata.get("Name", "")
    author = metadata.get("Author", "")
    if not isinstance(name, str) or not isinstance(author, str):
        raise LitematicFormatError("Metadata.Name and Metadata.Author must be strings when present")
    source_metadata = {
        key: value
        for key, value in metadata.items()
        if isinstance(value, (str, int, float))
    }
    return LitematicDocument(
        schematic_version=schematic_version,
        minecraft_data_version=data_version,
        name=str(name),
        author=str(author),
        regions=tuple(regions),
        source_metadata=source_metadata,
    )


def analyze_litematic(
    document: LitematicDocument,
    *,
    target_data_version: int = TARGET_MINECRAFT_DATA_VERSION,
) -> LitematicAnalysis:
    """Stream non-air block states into aggregate bounds, palette and Y-layer data."""

    if isinstance(target_data_version, bool) or not isinstance(target_data_version, int) or target_data_version <= 0:
        raise ValueError("target_data_version must be a positive integer")
    palette_counts: Counter[str] = Counter()
    layer_counts: Counter[int] = Counter()
    layer_material_counts: dict[int, Counter[str]] = defaultdict(Counter)
    slice_bounds: dict[int, list[int]] = {}
    occupied = 0
    min_x = min_y = min_z = None
    max_x = max_y = max_z = None
    for region in document.regions:
        for (x, y, z), state in region.iter_non_air_blocks():
            state_key = state.to_string()
            palette_counts[state_key] += 1
            layer_counts[y] += 1
            layer_material_counts[y][state_key] += 1
            occupied += 1
            min_x = x if min_x is None else min(min_x, x)
            min_y = y if min_y is None else min(min_y, y)
            min_z = z if min_z is None else min(min_z, z)
            max_x = x if max_x is None else max(max_x, x)
            max_y = y if max_y is None else max(max_y, y)
            max_z = z if max_z is None else max(max_z, z)
            bounds = slice_bounds.setdefault(y, [x, x, z, z])
            bounds[0] = min(bounds[0], x)
            bounds[1] = max(bounds[1], x)
            bounds[2] = min(bounds[2], z)
            bounds[3] = max(bounds[3], z)
    if occupied == 0 or None in (min_x, min_y, min_z, max_x, max_y, max_z):
        raise LitematicFormatError("Litematic contains no occupied non-air block positions")
    dimensions: Position3 = (max_x - min_x + 1, max_y - min_y + 1, max_z - min_z + 1)
    slices: list[HorizontalSliceSummary] = []
    for y in sorted(layer_counts):
        x_min, x_max, z_min, z_max = slice_bounds[y]
        area = (x_max - x_min + 1) * (z_max - z_min + 1)
        count = layer_counts[y]
        slices.append(
            HorizontalSliceSummary(
                y=y,
                occupied_blocks=count,
                xz_bounds=((x_min, z_min), (x_max + 1, z_max + 1)),
                coverage_ratio=count / area,
                material_counts=dict(sorted(layer_material_counts[y].items())),
            )
        )
    data_versions = [document.minecraft_data_version, *(region.minecraft_data_version for region in document.regions)]
    observed_data_version = max(data_versions)
    if observed_data_version < target_data_version:
        compatibility = "older_than_target"
    elif observed_data_version > target_data_version:
        compatibility = "newer_than_target"
    else:
        compatibility = "target"
    return LitematicAnalysis(
        region_count=len(document.regions),
        dimensions=dimensions,
        bounding_box=((min_x, min_y, min_z), (max_x + 1, max_y + 1, max_z + 1)),
        block_count=occupied,
        palette_counts=dict(sorted(palette_counts.items())),
        layer_counts=dict(sorted(layer_counts.items())),
        layer_material_counts={key: dict(sorted(value.items())) for key, value in sorted(layer_material_counts.items())},
        horizontal_slices=tuple(slices),
        compatibility_status=compatibility,
    )
