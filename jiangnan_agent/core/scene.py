"""Sparse block storage for generated Minecraft structures."""

from __future__ import annotations

from .block import BlockState
from .geometry import BoundingBox, Position

AIR = BlockState("minecraft:air")


class VoxelModel:
    """A sparse mapping from X/Y/Z integer coordinates to block states."""

    def __init__(self) -> None:
        self.blocks: dict[Position, BlockState] = {}

    def set_block(self, position: Position, state: BlockState | str) -> None:
        if len(position) != 3 or any(not isinstance(value, int) for value in position):
            raise ValueError("block position must contain three integers")
        parsed = BlockState.parse(state) if isinstance(state, str) else state
        if parsed == AIR:
            self.blocks.pop(position, None)
        else:
            self.blocks[position] = parsed

    def block_at(self, position: Position) -> BlockState:
        return self.blocks.get(position, AIR)

    @property
    def bounds(self) -> BoundingBox:
        if not self.blocks:
            return BoundingBox(0, 0, 0, 0, 0, 0)
        return BoundingBox.from_positions(self.blocks)

    def fill(self, bounds: BoundingBox, state: BlockState | str) -> None:
        parsed = BlockState.parse(state) if isinstance(state, str) else state
        for y in range(bounds.min_y, bounds.max_y):
            for z in range(bounds.min_z, bounds.max_z):
                for x in range(bounds.min_x, bounds.max_x):
                    self.set_block((x, y, z), parsed)

    def translated(self, dx: int, dy: int, dz: int) -> VoxelModel:
        translated = VoxelModel()
        for (x, y, z), state in self.blocks.items():
            translated.set_block((x + dx, y + dy, z + dz), state)
        return translated
