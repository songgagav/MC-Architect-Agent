"""Command-line entry point for Jiangnan Architect Agent."""

from __future__ import annotations

import argparse
from pathlib import Path
import re

from .generators.simple_house import SimpleHouseConfig, generate_simple_house
from .io.project_json import JiangnanProject, load_project, save_project
from .io.schematic import write_schematic


def main() -> int:
    parser = argparse.ArgumentParser(description="Jiangnan Architect Agent project tools.")
    parser.add_argument("--version", action="version", version="jiangnan-architect-agent 0.1.0")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="create a new Jiangnan project JSON")
    init_parser.add_argument("--name", required=True, help="project display name")
    init_parser.add_argument("--output", required=True, type=Path, help="path for the new project JSON")

    validate_parser = subparsers.add_parser("validate", help="load and validate a project JSON")
    validate_parser.add_argument("project", type=Path, help="project JSON path")

    info_parser = subparsers.add_parser("info", help="show project metadata")
    info_parser.add_argument("project", type=Path, help="project JSON path")

    generate_parser = subparsers.add_parser("generate", help="generate a simple house as Sponge v3 .schem")
    generate_parser.add_argument("--project", required=True, type=Path, help="project JSON path")
    generate_parser.add_argument("--output", type=Path, help="output Sponge schematic path")

    args = parser.parse_args()
    try:
        if args.command == "init":
            project = JiangnanProject(
                name=args.name,
                settings={"building": {"type": "simple_house", "width": 9, "length": 11, "wall_height": 4}},
            )
            destination = save_project(project, args.output)
            print(f"已创建工程: {destination.resolve()}")
            return 0

        project = load_project(args.project)
        if args.command == "validate":
            print(f"工程有效: {project.name} ({project.minecraft_version})")
        elif args.command == "info":
            print(f"名称: {project.name}")
            print(f"工程 ID: {project.project_id}")
            print(f"Minecraft: Java {project.minecraft_version} (DataVersion {project.data_version})")
            print(f"模块数: {len(project.modules)}")
        else:
            building = project.settings.get("building", {})
            if building.get("type", "simple_house") != "simple_house":
                raise ValueError(f"unsupported building type: {building.get('type')!r}")
            allowed = {"width", "length", "wall_height", "roof_overhang", "materials"}
            config = SimpleHouseConfig(**{key: value for key, value in building.items() if key in allowed})
            model = generate_simple_house(config)
            safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", project.name).strip("_") or "jiangnan_building"
            output = args.output or Path("workspace") / "exports" / f"{safe_name}.schem"
            destination = write_schematic(
                model,
                output,
                data_version=project.data_version,
                name=project.name,
            )
            print(f"已生成 Sponge v3 投影: {destination.resolve()}")
            print(f"占用方块: {len(model.blocks)} | 尺寸: {model.bounds.size}")
        return 0
    except (KeyError, OSError, TypeError, ValueError) as exc:
        parser.exit(2, f"错误: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
