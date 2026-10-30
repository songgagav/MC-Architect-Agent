"""Convert Sponge schematics with Mine2Blend and render them in Blender."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import json
import math
from pathlib import Path
import re
import subprocess
from typing import Any

from ..core.scene import AIR
from ..io.schematic import SchematicDocument, read_schematic

_VIEWS = ("top", "front", "side", "perspective")
_COMPLETION_PREFIX = "JiangnanPreview: "
_RENDER_ASPECT_RATIO = 4 / 3  # blender_render.py renders at 1200 x 900


class PreviewError(ValueError):
    """An input, conversion, or render error with a user-facing explanation."""


@dataclass(frozen=True)
class ConvertedSchematic:
    label: str
    obj_path: Path
    manifest_path: Path
    manifest: Mapping[str, Any]
    bounds: tuple[tuple[float, float, float], tuple[float, float, float]]


@dataclass(frozen=True)
class PreviewResult:
    output_dir: Path
    render_paths: Mapping[str, Path]
    preview_report_path: Path
    comparison_report_path: Path | None
    converted_obj_paths: tuple[Path, ...]


def _read_document(path: str | Path) -> tuple[Path, SchematicDocument]:
    source = Path(path).expanduser()
    if source.suffix.lower() != ".schem":
        raise PreviewError(f"expected a Sponge .schem file: {source}")
    if not source.is_file():
        raise PreviewError(f"schematic file not found: {source}")
    try:
        return source.resolve(), read_schematic(source)
    except Exception as exc:
        raise PreviewError(f"unable to read schematic {source}: {exc}") from exc


def _prepare_output_directory(path: str | Path) -> Path:
    output = Path(path).expanduser().resolve()
    if output.exists():
        if not output.is_dir():
            raise PreviewError(f"preview output path is not a directory: {output}")
        if any(output.iterdir()):
            raise PreviewError(f"preview output directory is not empty: {output}")
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.mkdir()
    return output


def _resolve_tools(
    mine2blend_root: str | Path,
    blender_executable: str | Path,
) -> tuple[Path, Path, Path, Path, Path]:
    root = Path(mine2blend_root).expanduser().resolve()
    converter_dir = root / "resources" / "converter" / "win-x64"
    node = converter_dir / "node.exe"
    converter_script = converter_dir / "src" / "batch-obj-export.mjs"
    blender = Path(blender_executable).expanduser().resolve()
    missing = [path for path in (node, converter_script, blender) if not path.is_file()]
    if missing:
        raise PreviewError("preview tool file not found: " + ", ".join(str(path) for path in missing))
    return root, converter_dir, node, converter_script, blender


def _run_process(
    command: list[str],
    *,
    cwd: Path,
    timeout: int,
    runner: Callable[..., subprocess.CompletedProcess],
    stage: str,
) -> subprocess.CompletedProcess:
    try:
        return runner(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise PreviewError(f"{stage} timed out after {timeout} seconds") from exc
    except OSError as exc:
        raise PreviewError(f"unable to start {stage}: {exc}") from exc


def _convert_one(
    source: Path,
    label: str,
    output: Path,
    converter_dir: Path,
    node: Path,
    converter_script: Path,
    *,
    timeout: int,
    runner: Callable[..., subprocess.CompletedProcess],
) -> ConvertedSchematic:
    converted_dir = output / "converted" / label
    manifest_path = output / f"conversion_{label}.json"
    command = [
        str(node),
        str(converter_script),
        "import",
        "--input",
        str(source),
        "--output",
        str(converted_dir),
        "--format",
        "obj",
        "--metadata-json",
        str(manifest_path),
        "--preserve-adjacent-faces",
    ]
    completed = _run_process(command, cwd=converter_dir, timeout=timeout, runner=runner, stage="Mine2Blend conversion")
    if completed.returncode != 0:
        details = (completed.stderr or completed.stdout or "no converter output")[-1000:]
        raise PreviewError(f"Mine2Blend conversion failed with exit code {completed.returncode}: {details}")
    if not manifest_path.is_file():
        raise PreviewError("Mine2Blend conversion did not write its metadata manifest")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PreviewError(f"Mine2Blend wrote an invalid metadata manifest: {exc}") from exc
    if not isinstance(manifest, dict) or manifest.get("fail") != 0 or manifest.get("success") != 1:
        raise PreviewError("Mine2Blend manifest does not report exactly one successful schematic conversion")
    outputs = manifest.get("outputs")
    if not isinstance(outputs, list) or len(outputs) != 1 or not isinstance(outputs[0], dict):
        raise PreviewError("Mine2Blend manifest must contain one converted output")
    raw_obj = outputs[0].get("obj")
    if not isinstance(raw_obj, str) or not raw_obj:
        raise PreviewError("Mine2Blend manifest does not name an OBJ file")
    obj_path = Path(raw_obj)
    if not obj_path.is_absolute():
        obj_path = (converter_dir / obj_path).resolve()
    if not obj_path.is_file():
        raise PreviewError(f"Mine2Blend OBJ output not found: {obj_path}")
    bounds = _obj_bounds(obj_path)
    return ConvertedSchematic(label, obj_path, manifest_path, manifest, bounds)


def _obj_bounds(path: Path) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    minimum = [math.inf, math.inf, math.inf]
    maximum = [-math.inf, -math.inf, -math.inf]
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if not line.startswith("v "):
                    continue
                parts = line.split()
                if len(parts) < 4:
                    continue
                coordinates = tuple(float(value) for value in parts[1:4])
                for axis, coordinate in enumerate(coordinates):
                    minimum[axis] = min(minimum[axis], coordinate)
                    maximum[axis] = max(maximum[axis], coordinate)
    except (OSError, ValueError) as exc:
        raise PreviewError(f"unable to read OBJ vertex bounds from {path}: {exc}") from exc
    if not all(math.isfinite(value) for value in (*minimum, *maximum)):
        raise PreviewError(f"Mine2Blend OBJ contains no readable vertices: {path}")
    return tuple(minimum), tuple(maximum)


def _camera_scales(converted: tuple[ConvertedSchematic, ...]) -> dict[str, float]:
    extents = []
    for item in converted:
        extents.append(tuple(maximum - minimum for minimum, maximum in zip(*item.bounds)))
    max_x = max(value[0] for value in extents)
    max_y = max(value[1] for value in extents)
    max_z = max(value[2] for value in extents)
    max_dimension = max(max_x, max_y, max_z)
    return {
        # Blender's orthographic scale is the camera width. Expand the
        # projected height by the landscape aspect ratio before fitting.
        "top": max(max_x, max_y * _RENDER_ASPECT_RATIO) * 1.25,
        "front": max(max_x, max_z * _RENDER_ASPECT_RATIO) * 1.25,
        "side": max(max_y, max_z * _RENDER_ASPECT_RATIO) * 1.25,
        "perspective_distance": max_dimension * 3.0,
    }


def _run_blender(
    converted: ConvertedSchematic,
    blender: Path,
    output: Path,
    prefix: str,
    camera_scales: Mapping[str, float],
    *,
    timeout: int,
    runner: Callable[..., subprocess.CompletedProcess],
) -> tuple[str, dict[str, Path]]:
    render_script = Path(__file__).with_name("blender_render.py").resolve()
    if not render_script.is_file():
        raise PreviewError(f"Blender rendering script not found: {render_script}")
    command = [
        str(blender),
        "--background",
        "--factory-startup",
        "--python",
        str(render_script),
        "--",
        "--obj",
        str(converted.obj_path),
        "--output-dir",
        str(output),
        "--prefix",
        prefix,
        "--camera-scales",
        json.dumps(dict(camera_scales), separators=(",", ":")),
    ]
    completed = _run_process(command, cwd=output, timeout=timeout, runner=runner, stage="Blender render")
    if completed.returncode != 0:
        details = (completed.stderr or completed.stdout or "no Blender output")[-1000:]
        raise PreviewError(f"Blender render failed with exit code {completed.returncode}: {details}")
    marker_data: dict[str, Any] | None = None
    for line in completed.stdout.splitlines():
        if line.startswith(_COMPLETION_PREFIX):
            try:
                marker_data = json.loads(line[len(_COMPLETION_PREFIX):])
            except json.JSONDecodeError as exc:
                raise PreviewError("Blender returned an invalid completion marker") from exc
    if not isinstance(marker_data, dict) or not isinstance(marker_data.get("rendered"), list):
        raise PreviewError("Blender exited without its preview completion marker")
    expected_names = {f"{prefix}{view}.png" for view in _VIEWS}
    if set(marker_data["rendered"]) != expected_names:
        raise PreviewError("Blender completion marker does not list all four preview angles")
    paths = {name.removesuffix(".png"): output / name for name in sorted(expected_names)}
    missing = [path for path in paths.values() if not path.is_file() or path.stat().st_size == 0]
    if missing:
        raise PreviewError("Blender did not create expected preview images: " + ", ".join(str(path) for path in missing))
    return str(marker_data.get("blender_version", "unknown")), paths


def _block_diff(before: SchematicDocument, after: SchematicDocument) -> dict[str, int]:
    positions = set(before.model.blocks) | set(after.model.blocks)
    added = removed = replaced = changed = 0
    for position in positions:
        old_state = before.model.block_at(position)
        new_state = after.model.block_at(position)
        if old_state == new_state:
            continue
        changed += 1
        if old_state == AIR:
            added += 1
        elif new_state == AIR:
            removed += 1
        else:
            replaced += 1
    return {"added": added, "removed": removed, "replaced": replaced, "changed": changed}


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def render_schematic_previews(
    schematic_path: str | Path,
    output_dir: str | Path,
    *,
    mine2blend_root: str | Path,
    blender_executable: str | Path,
    compare_before: str | Path | None = None,
    timeout: int = 600,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> PreviewResult:
    """Render a schematic in four views, optionally paired with a prior schematic."""

    if isinstance(timeout, bool) or not isinstance(timeout, int) or timeout < 1:
        raise PreviewError("timeout must be a positive integer")
    current_path, current_document = _read_document(schematic_path)
    before_path: Path | None = None
    before_document: SchematicDocument | None = None
    if compare_before is not None:
        before_path, before_document = _read_document(compare_before)
    output = Path(output_dir).expanduser().resolve()
    if output.exists() and output.is_dir() and any(output.iterdir()):
        raise PreviewError(f"preview output directory is not empty: {output}")
    _root, converter_dir, node, converter_script, blender = _resolve_tools(mine2blend_root, blender_executable)
    output = _prepare_output_directory(output)

    converted: list[ConvertedSchematic] = []
    before: ConvertedSchematic | None = None
    if before_path is not None:
        before = _convert_one(
            before_path,
            "before",
            output,
            converter_dir,
            node,
            converter_script,
            timeout=timeout,
            runner=runner,
        )
        converted.append(before)
    current_label = "after" if before is not None else "current"
    current = _convert_one(
        current_path,
        current_label,
        output,
        converter_dir,
        node,
        converter_script,
        timeout=timeout,
        runner=runner,
    )
    converted.append(current)
    scales = _camera_scales(tuple(converted))
    render_paths: dict[str, Path] = {}
    blender_versions: set[str] = set()
    for item in converted:
        prefix = f"{item.label}_" if before is not None else ""
        blender_version, paths = _run_blender(
            item,
            blender,
            output,
            prefix,
            scales,
            timeout=timeout,
            runner=runner,
        )
        blender_versions.add(blender_version)
        render_paths.update(paths)

    comparison_path: Path | None = None
    if before_document is not None and before_path is not None:
        comparison_path = output / "comparison.json"
        _write_json(
            comparison_path,
            {
                "before": str(before_path),
                "after": str(current_path),
                "blocks": _block_diff(before_document, current_document),
                "camera_scales": scales,
                "renders": {name: str(path) for name, path in sorted(render_paths.items())},
            },
        )

    preview_report_path = output / "preview.json"
    _write_json(
        preview_report_path,
        {
            "source": str(current_path),
            "data_version": current_document.data_version,
            "dimensions": list(current_document.model.bounds.size),
            "block_count": len(current_document.model.blocks),
            "converter_version": current.manifest.get("converterVersion", "unknown"),
            "resource_version": current.manifest.get("resourceVersion", "unknown"),
            "blender_version": sorted(blender_versions),
            "camera_scales": scales,
            "renders": {name: str(path) for name, path in sorted(render_paths.items())},
            "comparison_report": str(comparison_path) if comparison_path else None,
        },
    )
    return PreviewResult(output, render_paths, preview_report_path, comparison_path, tuple(item.obj_path for item in converted))
