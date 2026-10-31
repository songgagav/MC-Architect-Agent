"""Reproduce and compare the GEN-3.1 roof/eave visual quality gate."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import csv
import hashlib
import json
from pathlib import Path
import re
import uuid

from jiangnan_agent.assembly.model import Assembly
from jiangnan_agent.assets import module_from_asset
from jiangnan_agent.core.block import BlockState
from jiangnan_agent.io.project_generation import generate_project_model
from jiangnan_agent.io.project_json import JiangnanProject, load_project, save_project
from jiangnan_agent.io.schematic import read_schematic, write_schematic
from jiangnan_agent.preview import PreviewResult, render_schematic_previews


_CASES = ("jiangnan-hall-3bay", "huizhou-hall-5bay")
_VIEWS = ("top", "front", "side", "perspective")


def _run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid.uuid4().hex[:8]


def _validate_run_id(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", value) or ".." in value:
        raise ValueError("run_id must be a short filesystem-safe name")
    return value


def _thaw(value: object) -> object:
    if hasattr(value, "items"):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw(item) for item in value]
    return value


def _normalized_blocks(model) -> dict[tuple[int, int, int], BlockState]:
    bounds = model.bounds
    return {
        (x - bounds.min_x, y - bounds.min_y, z - bounds.min_z): state
        for (x, y, z), state in model.blocks.items()
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _block_diff(before, after) -> dict[str, int]:
    before_blocks = before.blocks
    after_blocks = after.blocks
    shared = before_blocks.keys() & after_blocks.keys()
    return {
        "added": len(after_blocks.keys() - before_blocks.keys()),
        "removed": len(before_blocks.keys() - after_blocks.keys()),
        "state_changed": sum(before_blocks[position] != after_blocks[position] for position in shared),
        "unchanged": sum(before_blocks[position] == after_blocks[position] for position in shared),
        "before_total": len(before_blocks),
        "after_total": len(after_blocks),
    }


def _update_candidate_parameters(example_id: str, source_module) -> tuple[dict[str, object], dict[str, object]]:
    parameters = _thaw(source_module.parameters)
    assert isinstance(parameters, dict)
    eave = parameters["eave_profile"]
    palette = parameters["material_palette"]
    assert isinstance(eave, dict) and isinstance(palette, dict)

    eave["surface_connection"] = "edge_liner"
    eave["surface_connection_role"] = "edge_liner"
    eave["layer_roles"] = ["eaves"]
    eave["thickness"] = 1
    eave["side_overhang"] = 1

    if example_id == "jiangnan-hall-3bay":
        palette["eaves"] = "minecraft:deepslate_tile_slab[type=top,waterlogged=false]"
        palette["edge_liner"] = "minecraft:polished_deepslate"
        variant = {
            "variant_id": "jiangnan_roof_edge_liner_v1",
            "basis": "Existing three-bay project parameters and jiangnan_dark_tile v1; explicit visual-gate override.",
            "changed": [
                "eave_profile.surface_connection=edge_liner",
                "eaves material uses a top slab to touch the liner across the upper half-block",
                "edge_liner uses a full polished-deepslate block at the previously empty edge course",
            ],
            "historical_claim": False,
        }
        return parameters, variant

    if example_id != "huizhou-hall-5bay":
        raise ValueError(f"unsupported visual gate case: {example_id}")

    roof = parameters["roof_profile"]
    ridge = parameters["ridge_profile"]
    facade = parameters["facade_profile"]
    assert isinstance(roof, dict) and isinstance(ridge, dict) and isinstance(facade, dict)
    window = facade["window"]
    assert isinstance(window, dict)
    timber = facade["timber"]
    assert isinstance(timber, dict)
    window["width"] = 3
    window["lattice_style"] = "grid"
    timber["column_bases"] = True
    timber["column_capitals"] = True
    openings = facade["openings"]
    assert isinstance(openings, list)
    for opening in openings:
        if opening["kind"] == "window":
            opening["offset"] = 0
    roof["section_points"] = [[0, 0], [1000, 1000]]
    ridge["cap_width"] = 0
    ridge["cap_height"] = 0
    palette["eaves"] = "minecraft:stone_brick_slab[type=top,waterlogged=false]"
    palette["edge_liner"] = "minecraft:stone_bricks"
    variant = {
        "variant_id": "huizhou_roof_light_v2",
        "basis": "New Minecraft creative example configuration; gray_brick_layered v1 remains unchanged.",
        "changed": [
            "eave thickness 2 to 1",
            "side overhang 2 to 1",
            "ridge cap removed",
            "roof section changed to a straight sampled profile at the same two-block rise",
            "edge liner added with explicit full-block material",
            "example-only windows widened from 2 to 3 blocks and changed from vertical to grid lattice",
            "example-only column base and capital accents enabled to strengthen the bay rhythm",
        ],
        "historical_claim": False,
    }
    return parameters, variant


def _write_sections(model, path: Path, *, base_y: int, ridge_height: int) -> None:
    bounds = model.bounds
    y_start = max(bounds.min_y, base_y - 2)
    y_stop = min(bounds.max_y, base_y + ridge_height + 3)
    x_positions = (bounds.min_x, (bounds.min_x + bounds.max_x - 1) // 2, bounds.max_x - 1)
    z_positions = (bounds.min_z, (bounds.min_z + bounds.max_z - 1) // 2, bounds.max_z - 1)
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.writer(stream)
        writer.writerow(("section", "fixed_x", "fixed_z", "x", "y", "z", "block_state"))
        for fixed_x in x_positions:
            for z in range(bounds.min_z, bounds.max_z):
                for y in range(y_start, y_stop):
                    state = model.block_at((fixed_x, y, z))
                    writer.writerow(("z_plane", fixed_x, "", fixed_x, y, z, state.to_string()))
        for fixed_z in z_positions:
            for x in range(bounds.min_x, bounds.max_x):
                for y in range(y_start, y_stop):
                    state = model.block_at((x, y, fixed_z))
                    writer.writerow(("x_plane", "", fixed_z, x, y, fixed_z, state.to_string()))


def _seam_samples(model, parameters: dict[str, object], *, base_y: int) -> dict[str, object]:
    bounds = model.bounds
    depth = int(parameters["depth"])
    x_positions = (bounds.min_x, (bounds.min_x + bounds.max_x - 1) // 2, bounds.max_x - 1)
    result: dict[str, object] = {}
    for face_name, edge_z, inner_z in (
        ("rear", 0, 1),
        ("front", depth - 1, depth - 2),
    ):
        rows = []
        for x in x_positions:
            cells = {}
            for name, z in (("edge", edge_z), ("inner_course", inner_z)):
                cells[name] = {
                    str(y): model.block_at((x, y, z)).to_string()
                    for y in range(base_y - 1, base_y + 3)
                }
            rows.append({"x": x, "edge_z": edge_z, "inner_z": inner_z, **cells})
        result[face_name] = rows
    return result


def _roof_state_counts(model, parameters: dict[str, object], *, base_y: int) -> dict[str, int]:
    roof = parameters["roof_profile"]
    palette = parameters["material_palette"]
    assert isinstance(roof, dict) and isinstance(palette, dict)
    ridge_height = int(roof["ridge_height"])
    roof_ids = {BlockState.parse(value).block_id for value in palette.values()}
    counts = Counter(
        state.to_string()
        for (x, y, z), state in model.blocks.items()
        if base_y - 2 <= y <= base_y + ridge_height + 2 and state.block_id in roof_ids
    )
    return dict(sorted(counts.items()))


def _variant_project(source_project: JiangnanProject, source_module, parameters: dict[str, object], variant: dict[str, object]):
    module = module_from_asset(source_module.module_id, "jiangnan.hall", parameters)
    settings = dict(source_project.settings)
    settings["gen3_1_visual_gate"] = variant
    settings["gen3_1_source_project_id"] = source_project.project_id
    return JiangnanProject(
        name=f"GEN-3.1 {source_project.name}",
        minecraft_version=source_project.minecraft_version,
        data_version=source_project.data_version,
        settings=settings,
        assembly=Assembly((module,)),
    ), module


def build_visual_gate(
    source_run: str | Path,
    output_root: str | Path,
    *,
    run_id: str | None = None,
    mine2blend_root: str | Path,
    blender_executable: str | Path,
    build_only: bool = False,
) -> tuple[Path, dict[str, object]]:
    source_root = Path(source_run).expanduser().resolve()
    if not source_root.is_dir():
        raise FileNotFoundError(f"GEN-3 source run directory not found: {source_root}")
    root = Path(output_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    run_root = root / f"gen3-1-roof-visual-gate-{_validate_run_id(run_id or _run_id())}"
    run_root.mkdir(exist_ok=False)
    for name in ("projects", "exports", "previews", "sections", "configs"):
        (run_root / name).mkdir()

    records: dict[str, object] = {
        "run_id": run_root.name,
        "source_run": str(source_root),
        "target_minecraft_version": "1.21.5",
        "target_data_version": 4325,
        "cases": {},
    }
    for example_id in _CASES:
        source_project_path = source_root / "projects" / f"{example_id}.jap.json"
        source_schematic = source_root / "exports" / f"{example_id}.schem"
        source_project = load_project(source_project_path)
        if len(source_project.assembly.modules) != 1:
            raise ValueError(f"expected exactly one source module in {source_project_path}")
        source_module = next(iter(source_project.assembly.modules.values()))
        source_model = generate_project_model(source_project)
        source_document = read_schematic(source_schematic)
        if source_document.model.blocks != _normalized_blocks(source_model):
            raise ValueError(f"source project does not reproduce its original schematic: {example_id}")

        parameters, variant = _update_candidate_parameters(example_id, source_module)
        candidate_project, candidate_module = _variant_project(source_project, source_module, parameters, variant)
        candidate_model = generate_project_model(candidate_project)
        candidate_id = f"{example_id}-gen3-1"
        project_path = run_root / "projects" / f"{candidate_id}.jap.json"
        schematic_path = run_root / "exports" / f"{candidate_id}.schem"
        config_path = run_root / "configs" / f"{candidate_id}.json"
        save_project(candidate_project, project_path)
        config_path.write_text(
            json.dumps(
                {
                    "variant": variant,
                    "module_id": candidate_module.module_id,
                    "parameters": parameters,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        write_schematic(
            candidate_model,
            schematic_path,
            data_version=source_project.data_version,
            name=candidate_project.name,
            author="MC-Architect-Agent",
        )
        candidate_document = read_schematic(schematic_path)
        if candidate_document.data_version != 4325:
            raise ValueError(f"candidate schematic has unexpected DataVersion for {example_id}")
        if candidate_document.model.blocks != _normalized_blocks(candidate_model):
            raise ValueError(f"Sponge v3 readback changed candidate block states for {example_id}")

        bounds = candidate_module.model.bounds
        module_parameters = _thaw(candidate_module.parameters)
        assert isinstance(module_parameters, dict)
        base_y = int(module_parameters["plinth_height"]) + int(module_parameters["column_height"]) + 1
        roof_profile = module_parameters["roof_profile"]
        assert isinstance(roof_profile, dict)
        source_parameters = _thaw(source_module.parameters)
        assert isinstance(source_parameters, dict)
        source_base_y = int(source_parameters["plinth_height"]) + int(source_parameters["column_height"]) + 1
        source_roof_profile = source_parameters["roof_profile"]
        assert isinstance(source_roof_profile, dict)
        before_section_path = run_root / "sections" / f"{example_id}-before.csv"
        after_section_path = run_root / "sections" / f"{candidate_id}-after.csv"
        _write_sections(
            source_model,
            before_section_path,
            base_y=source_base_y,
            ridge_height=int(source_roof_profile["ridge_height"]),
        )
        _write_sections(
            candidate_model,
            after_section_path,
            base_y=base_y,
            ridge_height=int(roof_profile["ridge_height"]),
        )

        preview_result: PreviewResult | None = None
        if not build_only:
            preview_dir = run_root / "previews" / example_id
            preview_result = render_schematic_previews(
                schematic_path,
                preview_dir,
                compare_before=source_schematic,
                mine2blend_root=mine2blend_root,
                blender_executable=blender_executable,
            )

        record: dict[str, object] = {
            "source_project": str(source_project_path),
            "source_schematic": str(source_schematic),
            "source_project_sha256": _sha256(source_project_path),
            "source_schematic_sha256": _sha256(source_schematic),
            "source_data_version": source_document.data_version,
            "source_dimensions": list(source_document.model.bounds.size),
            "source_block_count": len(source_model.blocks),
            "candidate_project": str(project_path),
            "candidate_schematic": str(schematic_path),
            "candidate_config": str(config_path),
            "candidate_schematic_sha256": _sha256(schematic_path),
            "candidate_data_version": candidate_document.data_version,
            "candidate_dimensions": list(candidate_document.model.bounds.size),
            "candidate_block_count": len(candidate_model.blocks),
            "candidate_bounds_absolute": [
                [bounds.min_x, bounds.min_y, bounds.min_z],
                [bounds.max_x, bounds.max_y, bounds.max_z],
            ],
            "block_diff_absolute_coordinates": _block_diff(source_model, candidate_model),
            "eave_seam_samples": {
                "before": _seam_samples(source_model, source_parameters, base_y=source_base_y),
                "after": _seam_samples(candidate_model, parameters, base_y=base_y),
            },
            "upper_roof_material_states": {
                "before": _roof_state_counts(source_model, source_parameters, base_y=source_base_y),
                "after": _roof_state_counts(candidate_model, parameters, base_y=base_y),
            },
            "sections_csv": {"before": str(before_section_path), "after": str(after_section_path)},
            "preview_dir": str(preview_result.output_dir) if preview_result else None,
            "preview_report": str(preview_result.preview_report_path) if preview_result else None,
            "render_paths": {
                key: str(value) for key, value in sorted(preview_result.render_paths.items())
            } if preview_result else {},
            "variant": variant,
        }
        records["cases"][example_id] = record

    report_path = run_root / "visual-gate-report.json"
    report_path.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return run_root, records


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-run", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=Path("workspace"))
    parser.add_argument("--run-id")
    parser.add_argument("--mine2blend-root", type=Path, default=Path("Mine2Blend/mcblock_mine2blend"))
    parser.add_argument(
        "--blender",
        type=Path,
        default=Path(r"D:\SteamLibrary\steamapps\common\Blender\blender.exe"),
    )
    parser.add_argument("--build-only", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    run_root, report = build_visual_gate(
        args.source_run,
        args.output_root,
        run_id=args.run_id,
        mine2blend_root=args.mine2blend_root,
        blender_executable=args.blender,
        build_only=args.build_only,
    )
    print(json.dumps({"run_root": str(run_root), "report": report}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
