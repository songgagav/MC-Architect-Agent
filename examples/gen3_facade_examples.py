"""Create reproducible GEN-3 façade projects, Sponge v3 exports, and previews."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import uuid

from jiangnan_agent.assembly.model import Assembly
from jiangnan_agent.assets import module_from_asset
from jiangnan_agent.io.project_generation import generate_project_model
from jiangnan_agent.io.project_json import JiangnanProject, save_project
from jiangnan_agent.io.schematic import read_schematic, write_schematic
from jiangnan_agent.parameters import load_facade_preset, load_roof_preset
from jiangnan_agent.generators.facade_profiles import facade_profile_to_mapping
from jiangnan_agent.generators.facade_profiles import FacadeProfile
from jiangnan_agent.preview import PreviewResult, render_schematic_previews


@dataclass(frozen=True)
class Gen3ExampleResult:
    example_id: str
    preset_id: str
    roof_preset_id: str
    module_id: str
    bay_count: int
    project_path: Path
    schematic_path: Path
    block_count: int
    dimensions: tuple[int, int, int]


_EXAMPLE_CONFIGS = (
    {
        "example_id": "jiangnan-hall-3bay",
        "preset_id": "jiangnan_whitewall_timber",
        "roof_preset_id": "jiangnan_dark_tile",
        "bay_count": 3,
        "depth": 7,
    },
    {
        "example_id": "huizhou-hall-5bay",
        "preset_id": "huizhou_graybrick_entry",
        "roof_preset_id": "gray_brick_layered",
        "bay_count": 5,
        "depth": 9,
    },
    {
        "example_id": "garden-hall-3bay",
        "preset_id": "garden_open_gallery",
        "roof_preset_id": "warm_spruce_garden",
        "bay_count": 3,
        "depth": 7,
    },
)


def _run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid.uuid4().hex[:8]


def _validate_run_id(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", value):
        raise ValueError("run_id must be a short filesystem-safe name")
    if ".." in value:
        raise ValueError("run_id cannot contain parent path segments")
    return value


def _normalized_blocks(model):
    bounds = model.bounds
    return {
        (position[0] - bounds.min_x, position[1] - bounds.min_y, position[2] - bounds.min_z): state
        for position, state in model.blocks.items()
    }


def _profile_for_bay_count(profile: FacadeProfile, bay_count: int) -> FacadeProfile:
    """Center a primary entry and its paired front windows for odd bay grids."""

    if bay_count < 3 or bay_count % 2 == 0:
        raise ValueError("GEN-3 façade examples require an odd bay_count of at least 3")
    center = bay_count // 2
    front_windows = sorted(
        (
            opening for opening in profile.openings
            if opening.face == "front" and opening.kind == "window"
        ),
        key=lambda opening: (opening.segment_index, opening.opening_id),
    )
    window_segments = (center - 1, center + 1) if len(front_windows) == 2 else ()
    replacements = {
        opening.opening_id: center
        for opening in profile.openings
        if opening.face == "front" and opening.connection_use == "primary_entry"
    }
    replacements.update(
        {opening.opening_id: segment for opening, segment in zip(front_windows, window_segments)}
    )
    return replace(
        profile,
        openings=tuple(
            replace(opening, segment_index=replacements[opening.opening_id])
            if opening.opening_id in replacements else opening
            for opening in profile.openings
        ),
    )


def build_gen3_facade_examples(
    output_root: str | Path,
    *,
    run_id: str | None = None,
) -> tuple[Gen3ExampleResult, ...]:
    """Create three immutable example runs with parameterized projects and v3 exports."""

    root = Path(output_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    run_name = _validate_run_id(run_id if run_id is not None else _run_id())
    run_root = root / f"gen3-facade-v1-{run_name}"
    run_root.mkdir(exist_ok=False)
    projects_dir = run_root / "projects"
    exports_dir = run_root / "exports"
    projects_dir.mkdir()
    exports_dir.mkdir()

    results: list[Gen3ExampleResult] = []
    for config in _EXAMPLE_CONFIGS:
        example_id = str(config["example_id"])
        profile_id = str(config["preset_id"])
        roof_id = str(config["roof_preset_id"])
        bay_count = int(config["bay_count"])
        module_id = f"{example_id}-main"
        profile = _profile_for_bay_count(load_facade_preset(profile_id), bay_count)
        example_overrides = {}
        if profile_id == "garden_open_gallery":
            profile = replace(
                profile,
                window=replace(profile.window, width=3, lattice_style="vertical"),
                openings=tuple(opening for opening in profile.openings if opening.face == "front"),
            )
            example_overrides = {
                "window": {"width": 3, "height": 2, "lattice_style": "vertical"},
                "removed_side_openings": ["left-window", "right-window"],
            }
        roof = load_roof_preset(roof_id)
        parameters = {
            "bay_count": bay_count,
            "bay_spacing": 5,
            "depth": int(config["depth"]),
            "facade_profile": facade_profile_to_mapping(profile),
            "roof_profile": asdict(roof.roof_profile),
            "eave_profile": asdict(roof.eave_profile),
            "ridge_profile": asdict(roof.ridge_profile),
            "material_palette": dict(roof.material_palette.roles),
        }
        module = module_from_asset(module_id, "jiangnan.hall", parameters)
        project = JiangnanProject(
            name=f"GEN-3 {example_id}",
            settings={
                "gen3_example_id": example_id,
                "facade_preset_id": profile_id,
                "facade_profile_version": profile.version,
                "facade_example_overrides": example_overrides,
                "roof_preset_id": roof_id,
            },
            assembly=Assembly((module,)),
        )
        project_path = projects_dir / f"{example_id}.jap.json"
        schematic_path = exports_dir / f"{example_id}.schem"
        if project_path.exists() or schematic_path.exists():
            raise FileExistsError(f"GEN-3 example output already exists for {example_id}")
        model = generate_project_model(project)
        save_project(project, project_path)
        write_schematic(
            model,
            schematic_path,
            data_version=4325,
            name=project.name,
            author="MC-Architect-Agent",
        )
        document = read_schematic(schematic_path)
        if document.model.blocks != _normalized_blocks(model):
            raise ValueError(f"Sponge v3 readback changed block states for {example_id}")
        results.append(
            Gen3ExampleResult(
                example_id,
                profile_id,
                roof_id,
                module_id,
                bay_count,
                project_path,
                schematic_path,
                len(model.blocks),
                model.bounds.size,
            )
        )
    return tuple(results)


def render_gen3_example_previews(
    examples: tuple[Gen3ExampleResult, ...],
    *,
    mine2blend_root: str | Path,
    blender_executable: str | Path,
) -> dict[str, PreviewResult]:
    """Render actual Mine2Blend/Blender four-view previews for every example."""

    rendered: dict[str, PreviewResult] = {}
    for item in examples:
        output = item.project_path.parent.parent / "previews" / item.example_id
        rendered[item.example_id] = render_schematic_previews(
            item.schematic_path,
            output,
            mine2blend_root=mine2blend_root,
            blender_executable=blender_executable,
        )
    return rendered


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=Path("workspace"))
    parser.add_argument(
        "--mine2blend-root",
        type=Path,
        default=Path("Mine2Blend/mcblock_mine2blend"),
    )
    parser.add_argument(
        "--blender",
        type=Path,
        default=Path(r"D:\SteamLibrary\steamapps\common\Blender\blender.exe"),
    )
    parser.add_argument("--build-only", action="store_true", help="create projects and schematics without rendering")
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    examples = build_gen3_facade_examples(args.output_root)
    previews = {}
    if not args.build_only:
        previews = render_gen3_example_previews(
            examples,
            mine2blend_root=args.mine2blend_root,
            blender_executable=args.blender,
        )
    records = []
    for item in examples:
        record = {
            "example_id": item.example_id,
            "facade_preset_id": item.preset_id,
            "roof_preset_id": item.roof_preset_id,
            "bay_count": item.bay_count,
            "project": str(item.project_path),
            "schematic": str(item.schematic_path),
            "block_count": item.block_count,
            "dimensions": list(item.dimensions),
        }
        if item.example_id in previews:
            record["previews"] = {
                name: str(path) for name, path in sorted(previews[item.example_id].render_paths.items())
            }
        records.append(record)
    print(json.dumps({"examples": records}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
