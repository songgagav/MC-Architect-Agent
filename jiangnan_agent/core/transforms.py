"""Block model transforms that preserve directional block states."""

from __future__ import annotations

from .scene import VoxelModel


def rotate_model_y(model: VoxelModel, quarter_turns: int) -> VoxelModel:
    turns = quarter_turns % 4
    bounds = model.bounds
    rotated = VoxelModel()
    width, _height, depth = bounds.size
    for (x, y, z), state in model.blocks.items():
        local_x, local_z = x - bounds.min_x, z - bounds.min_z
        if turns == 0:
            new_x, new_z = local_x, local_z
        elif turns == 1:
            new_x, new_z = depth - 1 - local_z, local_x
        elif turns == 2:
            new_x, new_z = width - 1 - local_x, depth - 1 - local_z
        else:
            new_x, new_z = local_z, width - 1 - local_x
        rotated.set_block((bounds.min_x + new_x, y, bounds.min_z + new_z), state.rotate_y(turns))
    return rotated
