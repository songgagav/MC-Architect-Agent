"""Integer coordinates and half-open voxel bounds."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

Position = tuple[int, int, int]


@dataclass(frozen=True)
class BoundingBox:
    """A 3D box whose maximum coordinates are exclusive."""

    min_x: int
    min_y: int
    min_z: int
    max_x: int
    max_y: int
    max_z: int

    def __post_init__(self) -> None:
        if self.max_x < self.min_x or self.max_y < self.min_y or self.max_z < self.min_z:
            raise ValueError("bounding box maximums cannot be less than minimums")

    @classmethod
    def from_positions(cls, positions: Iterable[Position]) -> BoundingBox:
        values = list(positions)
        if not values:
            raise ValueError("cannot create a bounding box from no positions")
        xs, ys, zs = zip(*values)
        return cls(min(xs), min(ys), min(zs), max(xs) + 1, max(ys) + 1, max(zs) + 1)

    @property
    def size(self) -> Position:
        return self.max_x - self.min_x, self.max_y - self.min_y, self.max_z - self.min_z

    def contains(self, position: Position) -> bool:
        x, y, z = position
        return self.min_x <= x < self.max_x and self.min_y <= y < self.max_y and self.min_z <= z < self.max_z

    def translated(self, dx: int, dy: int, dz: int) -> BoundingBox:
        return BoundingBox(
            self.min_x + dx,
            self.min_y + dy,
            self.min_z + dz,
            self.max_x + dx,
            self.max_y + dy,
            self.max_z + dz,
        )
