"""A small parameterized starter house for block-engine acceptance."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..core.block import BlockState
from ..core.geometry import BoundingBox
from ..core.scene import VoxelModel


@dataclass(frozen=True)
class SimpleHouseConfig:
    width: int = 9
    length: int = 11
    wall_height: int = 4
    roof_overhang: int = 1
    materials: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.width < 7 or self.length < 7:
            raise ValueError("house width and length must each be at least 7 blocks")
        if self.width % 2 == 0:
            raise ValueError("house width must be odd so the entrance is centered")
        if self.wall_height < 3:
            raise ValueError("wall_height must be at least 3 blocks")
        if self.roof_overhang < 0:
            raise ValueError("roof_overhang cannot be negative")


DEFAULT_MATERIALS: dict[str, Any] = {
    "foundation": "minecraft:stone_bricks",
    "floor": "minecraft:spruce_planks",
    "wall": "minecraft:white_terracotta",
    "roof": "minecraft:spruce_stairs",
    "window": "minecraft:glass_pane",
}


def generate_simple_house(config: SimpleHouseConfig | None = None) -> VoxelModel:
    config = config or SimpleHouseConfig()
    materials_raw = dict(DEFAULT_MATERIALS)
    materials_raw.update(config.materials or {})
    materials = {name: BlockState.parse(value) if isinstance(value, str) else BlockState(value["id"], tuple(value.get("properties", {}).items())) for name, value in materials_raw.items()}

    width, length = config.width, config.length
    center_x = width // 2
    front_z = length - 1
    model = VoxelModel()
    model.fill(BoundingBox(0, 0, 0, width, 1, length), materials["foundation"])
    model.fill(BoundingBox(1, 1, 1, width - 1, 2, length - 1), materials["floor"])

    for y in range(1, config.wall_height + 1):
        for x in range(width):
            for z in (0, front_z):
                if z == front_z and abs(x - center_x) <= 1 and y <= 2:
                    continue
                model.set_block((x, y, z), materials["wall"])
        for z in range(1, length - 1):
            model.set_block((0, y, z), materials["wall"])
            model.set_block((width - 1, y, z), materials["wall"])

    window_z = length // 2
    for z in (window_z - 1, window_z + 1):
        for y in (2, 3):
            model.set_block((0, y, z), materials["window"])
            model.set_block((width - 1, y, z), materials["window"])

    roof_edge = width // 2 + config.roof_overhang
    for x in range(-config.roof_overhang, width + config.roof_overhang):
        rise = max(0, roof_edge - abs(x - center_x))
        y = config.wall_height + rise
        facing = "east" if x <= center_x else "west"
        roof_state = BlockState(
            materials["roof"].block_id,
            tuple({**dict(materials["roof"].properties), "facing": facing, "half": "bottom", "shape": "straight", "waterlogged": "false"}.items()),
        )
        for z in range(-config.roof_overhang, length + config.roof_overhang):
            model.set_block((x, y, z), roof_state)

    return model
