"""Generate the voxel model represented by a saved Jiangnan project."""

from __future__ import annotations

from ..assembly.validation import render_assembly, validate_assembly
from ..core.scene import VoxelModel
from ..generators.hall import HallParameters, generate_hall
from ..generators.simple_house import SimpleHouseConfig, generate_simple_house
from .project_json import JiangnanProject


def generate_project_model(project: JiangnanProject) -> VoxelModel:
    """Generate the Assembly when present, otherwise use legacy building settings."""

    if not isinstance(project, JiangnanProject):
        raise ValueError("project must be a JiangnanProject")
    if project.assembly.modules:
        issues = validate_assembly(project.assembly)
        if issues:
            raise ValueError(f"assembly validation failed: {issues[0].message}")
        return render_assembly(project.assembly)

    building = project.settings.get("building", {})
    building_type = building.get("type", "simple_house")
    if building_type == "simple_house":
        allowed = {"width", "length", "wall_height", "roof_overhang", "materials"}
        config = SimpleHouseConfig(**{key: value for key, value in building.items() if key in allowed})
        return generate_simple_house(config)
    if building_type == "hall":
        allowed = {
            "bay_count",
            "bay_width",
            "depth",
            "column_height",
            "plinth_height",
            "roof_rise",
            "eaves",
            "door_width",
            "materials",
        }
        config = HallParameters(**{key: value for key, value in building.items() if key in allowed})
        return generate_hall(config)
    raise ValueError(f"unsupported building type: {building_type!r}")
