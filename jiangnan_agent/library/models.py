"""Immutable models for references and Litematic source data."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

Position3 = tuple[int, int, int]
Bounds3 = tuple[Position3, Position3]

_AIR_STATES = frozenset({"minecraft:air", "minecraft:cave_air", "minecraft:void_air"})


@dataclass(frozen=True)
class LitematicBlockState:
    name: str
    properties: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise ValueError("block state name must be a non-empty string")
        if any(
            not isinstance(key, str) or not key or not isinstance(value, str) or not value
            for key, value in self.properties.items()
        ):
            raise ValueError("block state properties must map non-empty strings to non-empty strings")
        object.__setattr__(self, "properties", MappingProxyType(dict(sorted(self.properties.items()))))

    @property
    def is_air(self) -> bool:
        return self.name in _AIR_STATES

    def to_string(self) -> str:
        if not self.properties:
            return self.name
        properties = ",".join(f"{key}={value}" for key, value in self.properties.items())
        return f"{self.name}[{properties}]"


@dataclass(frozen=True)
class LitematicRegion:
    name: str
    position: Position3
    signed_size: Position3
    palette: tuple[LitematicBlockState, ...]
    packed_states: tuple[int, ...]
    minecraft_data_version: int

    @property
    def size(self) -> Position3:
        return tuple(abs(value) for value in self.signed_size)  # type: ignore[return-value]

    @property
    def volume(self) -> int:
        x, y, z = self.size
        return x * y * z

    @property
    def bits_per_block(self) -> int:
        return max(2, (len(self.palette) - 1).bit_length())

    def block_state_at_index(self, index: int) -> LitematicBlockState:
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < self.volume:
            raise IndexError("region block index is outside its volume")
        bits = self.bits_per_block
        bit_index = index * bits
        word_index, bit_offset = divmod(bit_index, 64)
        mask = (1 << bits) - 1
        value = (self.packed_states[word_index] & ((1 << 64) - 1)) >> bit_offset
        if bit_offset + bits > 64:
            value |= (self.packed_states[word_index + 1] & ((1 << 64) - 1)) << (64 - bit_offset)
        palette_index = value & mask
        try:
            return self.palette[palette_index]
        except IndexError as exc:
            raise ValueError(f"palette index {palette_index} is outside the region palette") from exc

    def validate_palette_indexes(self) -> None:
        for index in range(self.volume):
            self.block_state_at_index(index)

    def iter_blocks(self) -> Iterator[tuple[Position3, LitematicBlockState]]:
        """Yield all source cells in Litematica's Y, Z, X array order."""

        size_x, size_y, size_z = self.size
        sign_x, sign_y, sign_z = tuple(-1 if value < 0 else 1 for value in self.signed_size)
        for index in range(self.volume):
            local_x = index % size_x
            local_z = (index // size_x) % size_z
            local_y = index // (size_x * size_z)
            position = (
                self.position[0] + sign_x * local_x,
                self.position[1] + sign_y * local_y,
                self.position[2] + sign_z * local_z,
            )
            yield position, self.block_state_at_index(index)

    def iter_non_air_blocks(self) -> Iterator[tuple[Position3, LitematicBlockState]]:
        for position, state in self.iter_blocks():
            if not state.is_air:
                yield position, state


@dataclass(frozen=True)
class LitematicDocument:
    schematic_version: int
    minecraft_data_version: int
    name: str
    author: str
    regions: tuple[LitematicRegion, ...]
    source_metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.schematic_version < 1 or self.minecraft_data_version < 1:
            raise ValueError("Litematic and Minecraft data versions must be positive")
        if not self.regions:
            raise ValueError("Litematic document must contain at least one valid region")
        object.__setattr__(self, "source_metadata", MappingProxyType(dict(self.source_metadata)))


@dataclass(frozen=True)
class HorizontalSliceSummary:
    y: int
    occupied_blocks: int
    xz_bounds: tuple[tuple[int, int], tuple[int, int]]
    coverage_ratio: float
    material_counts: Mapping[str, int]

    def __post_init__(self) -> None:
        object.__setattr__(self, "material_counts", MappingProxyType(dict(self.material_counts)))


@dataclass(frozen=True)
class LitematicAnalysis:
    region_count: int
    dimensions: Position3
    bounding_box: Bounds3
    block_count: int
    palette_counts: Mapping[str, int]
    layer_counts: Mapping[int, int]
    layer_material_counts: Mapping[int, Mapping[str, int]]
    horizontal_slices: tuple[HorizontalSliceSummary, ...]
    compatibility_status: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "palette_counts", MappingProxyType(dict(self.palette_counts)))
        object.__setattr__(self, "layer_counts", MappingProxyType(dict(self.layer_counts)))
        object.__setattr__(
            self,
            "layer_material_counts",
            MappingProxyType({key: MappingProxyType(dict(value)) for key, value in self.layer_material_counts.items()}),
        )


@dataclass(frozen=True)
class ReferenceAsset:
    asset_id: str
    version: int
    name: str
    source_file: str
    file_format: str
    minecraft_data_version: int
    region_profile_id: str | None
    region_assignment_status: str
    building_type: str
    dimensions: Position3
    block_count: int
    block_palette: Mapping[str, int]
    bounding_box: Bounds3
    preview_files: tuple[str, ...]
    sha256: str
    import_status: str
    validation_status: str
    author: str
    provenance: Mapping[str, object]
    usage_rights: Mapping[str, object]
    created_at: str
    parser_version: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "block_palette", MappingProxyType(dict(self.block_palette)))
        object.__setattr__(self, "provenance", MappingProxyType(dict(self.provenance)))
        object.__setattr__(self, "usage_rights", MappingProxyType(dict(self.usage_rights)))
