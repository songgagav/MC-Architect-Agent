"""Create reproducible project and Sponge v3 artifacts for the GEN-2 roof presets."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from jiangnan_agent.assembly.adapters import hall_module
from jiangnan_agent.assembly.model import Assembly
from jiangnan_agent.generators.hall import HallParameters
from jiangnan_agent.io.project_generation import generate_project_model
from jiangnan_agent.io.project_json import JiangnanProject, save_project
from jiangnan_agent.io.schematic import write_schematic
from jiangnan_agent.parameters.registry import load_roof_preset


@dataclass(frozen=True)
class RoofExampleResult:
    preset_id: str
    project_path: Path
    schematic_path: Path
    block_count: int
    dimensions: tuple[int, int, int]


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def build_roof_closeout_examples(output_root: Path) -> tuple[RoofExampleResult, ...]:
    """Create one saved three-bay hall and round-trippable schematic per roof preset."""

    root = Path(output_root).expanduser().resolve()
    run_root = root / f"gen2-roof-closeout-{_timestamp()}"
    run_root.mkdir(parents=True, exist_ok=False)
    projects_dir = run_root / "projects"
    exports_dir = run_root / "exports"
    projects_dir.mkdir()
    exports_dir.mkdir()

    results: list[RoofExampleResult] = []
    for preset_id in ("jiangnan_dark_tile", "gray_brick_layered", "warm_spruce_garden"):
        preset = load_roof_preset(preset_id)
        parameters = HallParameters(
            bay_count=3,
            bay_width=5,
            depth=7,
            roof_profile=preset.roof_profile,
            eave_profile=preset.eave_profile,
            ridge_profile=preset.ridge_profile,
            material_palette=preset.material_palette,
        )
        module = hall_module(f"hall-{preset_id}", parameters)
        project = JiangnanProject(
            name=f"GEN-2 roof closeout — {preset_id}",
            settings={"roof_preset_id": preset_id},
            assembly=Assembly((module,)),
        )
        project_path = projects_dir / f"{preset_id}.jap.json"
        schematic_path = exports_dir / f"{preset_id}.schem"
        for destination in (project_path, schematic_path):
            if destination.exists():
                raise FileExistsError(f"roof closeout destination already exists: {destination}")
        model = generate_project_model(project)
        save_project(project, project_path)
        write_schematic(model, schematic_path, name=project.name, author="MC-Architect-Agent")
        results.append(
            RoofExampleResult(
                preset_id=preset_id,
                project_path=project_path,
                schematic_path=schematic_path,
                block_count=len(model.blocks),
                dimensions=model.bounds.size,
            )
        )
    return tuple(results)
