from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from jiangnan_agent.cli import main
from jiangnan_agent.core.scene import VoxelModel
from jiangnan_agent.io.schematic import write_schematic
from jiangnan_agent.preview import PreviewError, render_schematic_previews
from jiangnan_agent.preview.mine2blend import ConvertedSchematic, _camera_scales


PNG_STUB = b"\x89PNG\r\n\x1a\n"


def test_orthographic_camera_scales_account_for_landscape_aspect_ratio(tmp_path: Path) -> None:
    converted = ConvertedSchematic(
        "current",
        tmp_path / "hall.obj",
        tmp_path / "manifest.json",
        {},
        ((0.0, 0.0, 0.0), (20.0, 8.0, 10.0)),
    )

    scales = _camera_scales((converted,))

    assert scales["top"] == 25.0
    assert scales["front"] == 25.0
    assert scales["side"] == pytest.approx(10.0 * (4 / 3) * 1.25)


def make_schematic(path: Path, blocks: dict[tuple[int, int, int], str]) -> Path:
    model = VoxelModel()
    for position, state in blocks.items():
        model.set_block(position, state)
    write_schematic(model, path)
    return path


def make_tool_paths(root: Path) -> tuple[Path, Path]:
    converter = root / "resources" / "converter" / "win-x64"
    node = converter / "node.exe"
    script = converter / "src" / "batch-obj-export.mjs"
    blender = root / "blender.exe"
    for path in (node, script, blender):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"test tool")
    return converter.parent.parent.parent, blender


def fake_runner_factory(*, converter_exit: int = 0, blender_exit: int = 0):
    calls: list[list[str]] = []

    def runner(command, **kwargs):
        calls.append([str(arg) for arg in command])
        command = [str(arg) for arg in command]
        if command[0].lower().endswith("node.exe"):
            output = Path(command[command.index("--output") + 1])
            source = Path(command[command.index("--input") + 1])
            manifest = Path(command[command.index("--metadata-json") + 1])
            if converter_exit:
                return subprocess.CompletedProcess(command, converter_exit, "", "converter failed")
            model_dir = output / source.stem
            model_dir.mkdir(parents=True, exist_ok=True)
            obj = model_dir / f"{source.stem}.obj"
            obj.write_text("v 0 0 0\nv 10 0 0\nv 0 10 10\n", encoding="utf-8")
            manifest.parent.mkdir(parents=True, exist_ok=True)
            manifest.write_text(
                json.dumps(
                    {
                        "converterVersion": "test-1",
                        "success": 1,
                        "fail": 0,
                        "outputs": [{"obj": str(obj), "size": [1, 1, 1], "blockCount": 1}],
                    }
                ),
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(command, 0, "converted", "")

        if blender_exit:
            return subprocess.CompletedProcess(command, blender_exit, "", "blender failed")
        args = command[command.index("--") + 1:]
        output = Path(args[args.index("--output-dir") + 1])
        prefix = args[args.index("--prefix") + 1]
        output.mkdir(parents=True, exist_ok=True)
        rendered = []
        for view in ("top", "front", "side", "perspective"):
            path = output / f"{prefix}{view}.png"
            path.write_bytes(PNG_STUB)
            rendered.append(path.name)
        marker = {"rendered": rendered, "blender_version": "test"}
        return subprocess.CompletedProcess(command, 0, f"JiangnanPreview: {json.dumps(marker)}", "")

    return runner, calls


def test_preview_calls_converter_and_blender_and_writes_four_views(tmp_path: Path) -> None:
    source = make_schematic(tmp_path / "hall.schem", {(0, 0, 0): "minecraft:stone"})
    root, blender = make_tool_paths(tmp_path / "Mine2Blend")
    output = tmp_path / "preview"
    runner, calls = fake_runner_factory()

    result = render_schematic_previews(
        source,
        output,
        mine2blend_root=root,
        blender_executable=blender,
        runner=runner,
    )

    assert len(calls) == 2
    assert all(isinstance(call, list) for call in calls)
    assert calls[0][1:3] == [str((root / "resources/converter/win-x64/src/batch-obj-export.mjs")), "import"]
    assert all(path.is_file() and path.read_bytes().startswith(PNG_STUB) for path in result.render_paths.values())
    report = json.loads(result.preview_report_path.read_text(encoding="utf-8"))
    assert report["converter_version"] == "test-1"
    assert set(report["renders"]) == {"top", "front", "side", "perspective"}


def test_preview_rejects_missing_or_invalid_schematic_before_process_launch(tmp_path: Path) -> None:
    root, blender = make_tool_paths(tmp_path / "Mine2Blend")
    runner, calls = fake_runner_factory()

    with pytest.raises(PreviewError, match="schematic.*not found"):
        render_schematic_previews(
            tmp_path / "missing.schem",
            tmp_path / "preview",
            mine2blend_root=root,
            blender_executable=blender,
            runner=runner,
        )
    assert calls == []


def test_preview_refuses_nonempty_output_directory(tmp_path: Path) -> None:
    source = make_schematic(tmp_path / "hall.schem", {(0, 0, 0): "minecraft:stone"})
    root, blender = make_tool_paths(tmp_path / "Mine2Blend")
    output = tmp_path / "preview"
    output.mkdir()
    (output / "existing.png").write_bytes(PNG_STUB)
    runner, calls = fake_runner_factory()

    with pytest.raises(PreviewError, match="not empty"):
        render_schematic_previews(
            source,
            output,
            mine2blend_root=root,
            blender_executable=blender,
            runner=runner,
        )
    assert calls == []


def test_preview_propagates_converter_and_blender_failures(tmp_path: Path) -> None:
    source = make_schematic(tmp_path / "hall.schem", {(0, 0, 0): "minecraft:stone"})
    root, blender = make_tool_paths(tmp_path / "Mine2Blend")
    converter_runner, converter_calls = fake_runner_factory(converter_exit=7)

    with pytest.raises(PreviewError, match="Mine2Blend conversion failed"):
        render_schematic_previews(
            source,
            tmp_path / "converter-failed",
            mine2blend_root=root,
            blender_executable=blender,
            runner=converter_runner,
        )
    assert len(converter_calls) == 1

    blender_runner, blender_calls = fake_runner_factory(blender_exit=9)
    with pytest.raises(PreviewError, match="Blender render failed"):
        render_schematic_previews(
            source,
            tmp_path / "blender-failed",
            mine2blend_root=root,
            blender_executable=blender,
            runner=blender_runner,
        )
    assert len(blender_calls) == 2


def test_before_after_report_counts_added_removed_and_replaced_blocks(tmp_path: Path) -> None:
    before = make_schematic(
        tmp_path / "before.schem",
        {(0, 0, 0): "minecraft:stone", (1, 0, 0): "minecraft:dirt"},
    )
    after = make_schematic(
        tmp_path / "after.schem",
        {(0, 0, 0): "minecraft:diamond_block", (2, 0, 0): "minecraft:stone"},
    )
    root, blender = make_tool_paths(tmp_path / "Mine2Blend")
    runner, calls = fake_runner_factory()

    result = render_schematic_previews(
        after,
        tmp_path / "comparison",
        mine2blend_root=root,
        blender_executable=blender,
        compare_before=before,
        runner=runner,
    )

    assert len(calls) == 4
    assert result.comparison_report_path is not None
    comparison = json.loads(result.comparison_report_path.read_text(encoding="utf-8"))
    assert comparison["blocks"] == {"added": 1, "removed": 1, "replaced": 1, "changed": 3}
    assert (tmp_path / "comparison" / "before_top.png").is_file()
    assert (tmp_path / "comparison" / "after_top.png").is_file()


def test_preview_cli_help_exposes_local_tool_paths(monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "argv", ["jiangnan", "preview", "--help"])

    with pytest.raises(SystemExit) as exc:
        main()

    assert exc.value.code == 0
    help_text = capsys.readouterr().out
    assert "--mine2blend-root" in help_text
    assert "--blender" in help_text
    assert "--compare-before" in help_text
