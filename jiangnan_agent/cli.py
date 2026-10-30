"""Command-line entry point for Jiangnan Architect Agent."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys
import json
from dataclasses import fields
from collections.abc import Mapping
import sqlite3

from .io.project_generation import generate_project_model
from .io.project_json import JiangnanProject, load_project, save_project
from .io.project_editor import ProjectEditor
from .io.schematic import write_schematic
from .preview import render_schematic_previews
from .library import LibraryService
from .library.database import LibraryDatabase
from .library.service import DEFAULT_DATABASE_PATH


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

    history_parser = subparsers.add_parser("history", help="show project revision history")
    history_parser.add_argument("project", type=Path, help="project JSON path")

    undo_parser = subparsers.add_parser("undo", help="restore the previous project revision")
    undo_parser.add_argument("project", type=Path, help="project JSON path")

    redo_parser = subparsers.add_parser("redo", help="restore the next project revision")
    redo_parser.add_argument("project", type=Path, help="project JSON path")

    generate_parser = subparsers.add_parser("generate", help="generate a building as Sponge v3 .schem")
    generate_parser.add_argument("--project", required=True, type=Path, help="project JSON path")
    generate_parser.add_argument("--output", type=Path, help="output Sponge schematic path")

    preview_parser = subparsers.add_parser("preview", help="render a Sponge schematic with Mine2Blend and Blender")
    preview_parser.add_argument("--schematic", required=True, type=Path, help="input Sponge .schem file")
    preview_parser.add_argument("--output-dir", required=True, type=Path, help="new or empty preview directory")
    preview_parser.add_argument("--mine2blend-root", required=True, type=Path, help="Mine2Blend add-on root directory")
    preview_parser.add_argument("--blender", required=True, type=Path, help="Blender executable path")
    preview_parser.add_argument("--compare-before", type=Path, help="optional earlier .schem to render beside the current version")
    preview_parser.add_argument("--timeout", type=int, default=600, help="per-process timeout in seconds")

    library_parser = subparsers.add_parser("library", help="query the local architecture reference library")
    library_parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE_PATH, help="SQLite database path")
    library_commands = library_parser.add_subparsers(dest="library_command", required=True)

    def add_library_database_option(command_parser: argparse.ArgumentParser) -> None:
        command_parser.add_argument(
            "--database", dest="command_database", type=Path, default=argparse.SUPPRESS,
            help="SQLite database path",
        )

    library_init_parser = library_commands.add_parser("init", help="initialize or migrate the local library")
    add_library_database_option(library_init_parser)

    import_parser = library_commands.add_parser("import", help="import and analyze a Litematic reference")
    import_parser.add_argument("source", type=Path, help="source .litematic file; it is read-only")
    import_parser.add_argument("--asset-id", required=True, help="stable reference asset ID")
    import_parser.add_argument("--name", help="display name (defaults to embedded name or file name)")
    import_parser.add_argument("--building-type", default="unspecified")
    import_parser.add_argument("--region-profile", help="assign one enabled region profile explicitly")
    import_parser.add_argument("--style-tag", action="append", default=[])
    import_parser.add_argument("--provenance-note")
    add_library_database_option(import_parser)

    list_parser = library_commands.add_parser("list", help="list registered references, regions, styles, modules, or rules")
    list_parser.add_argument("category", choices=("references", "regions", "sources", "parameters", "styles", "modules", "rules"))
    list_parser.add_argument("--region", help="filter rules by an active region profile")
    list_parser.add_argument("--building-type")
    list_parser.add_argument("--include-planned", action="store_true")
    list_parser.add_argument("--include-pending", action="store_true")
    add_library_database_option(list_parser)

    show_parser = library_commands.add_parser("show", help="show one reference asset")
    show_parser.add_argument("asset_id")
    show_parser.add_argument("--version", type=int)
    add_library_database_option(show_parser)

    materials_parser = library_commands.add_parser("materials", help="show measured block-state counts")
    materials_parser.add_argument("asset_id")
    materials_parser.add_argument("--version", type=int)
    add_library_database_option(materials_parser)

    layers_parser = library_commands.add_parser("layers", help="show occupied blocks and materials by Y layer")
    layers_parser.add_argument("asset_id")
    layers_parser.add_argument("--version", type=int)
    add_library_database_option(layers_parser)

    previews_parser = library_commands.add_parser("previews", help="register existing local preview images")
    previews_parser.add_argument("asset_id")
    previews_parser.add_argument("--file", dest="preview_files", action="append", type=Path, required=True)
    previews_parser.add_argument("--version", type=int)
    add_library_database_option(previews_parser)

    module_parser = library_commands.add_parser("module", help="show a module definition and its parameter schema")
    module_parser.add_argument("asset_id")
    module_parser.add_argument("--version", type=int)
    add_library_database_option(module_parser)

    parameter_parser = library_commands.add_parser("parameter", help="show a parameter schema")
    parameter_parser.add_argument("schema_id")
    parameter_parser.add_argument("--version", type=int)
    add_library_database_option(parameter_parser)

    style_parser = library_commands.add_parser("style", help="show a style profile and measured palette candidates")
    style_parser.add_argument("profile_id")
    style_parser.add_argument("--version", type=int)
    style_parser.add_argument("--require-references", action="store_true")
    add_library_database_option(style_parser)

    verify_parser = library_commands.add_parser("verify", help="verify reference files against stored SHA-256")
    verify_parser.add_argument("--asset-id")
    add_library_database_option(verify_parser)

    backup_parser = library_commands.add_parser("backup", help="create a non-overwriting SQLite backup")
    backup_parser.add_argument("--output", required=True, type=Path)
    add_library_database_option(backup_parser)

    annotations_parser = library_commands.add_parser("annotations", help="propose, review, and inspect semantic annotations")
    annotation_commands = annotations_parser.add_subparsers(dest="annotation_command", required=True)
    annotation_propose = annotation_commands.add_parser("propose", help="create candidate annotations from explicit block identities")
    annotation_propose.add_argument("asset_id")
    annotation_propose.add_argument("--version", type=int)
    add_library_database_option(annotation_propose)
    annotation_list = annotation_commands.add_parser("list", help="list current semantic annotation revisions")
    annotation_list.add_argument("--asset-id")
    annotation_list.add_argument("--version", type=int)
    annotation_list.add_argument("--component-type")
    annotation_list.add_argument("--status", choices=("candidate", "verified", "rejected"))
    annotation_list.add_argument("--include-history", action="store_true")
    add_library_database_option(annotation_list)
    annotation_create = annotation_commands.add_parser("create", help="create a manual candidate annotation")
    annotation_create.add_argument("--annotation-id", required=True)
    annotation_create.add_argument("--asset-id", required=True)
    annotation_create.add_argument("--version", type=int)
    annotation_create.add_argument("--region", required=True)
    annotation_create.add_argument("--component-type", required=True)
    annotation_create.add_argument("--geometry-type", required=True, choices=("region", "box", "block_set"))
    annotation_create.add_argument("--geometry", required=True, help="JSON selector, e.g. '{\"positions\":[[0,0,0]]}'")
    annotation_create.add_argument("--confidence", type=float)
    add_library_database_option(annotation_create)
    annotation_update = annotation_commands.add_parser("update", help="append a pending annotation revision")
    annotation_update.add_argument("annotation_id")
    annotation_update.add_argument("--component-type")
    annotation_update.add_argument("--geometry-type", choices=("region", "box", "block_set"))
    annotation_update.add_argument("--geometry", help="replacement JSON selector")
    annotation_update.add_argument("--confidence", type=float)
    annotation_update.add_argument("--note")
    add_library_database_option(annotation_update)
    annotation_review = annotation_commands.add_parser("review", help="record a human annotation decision")
    annotation_review.add_argument("annotation_id")
    annotation_review.add_argument("--reviewer", required=True)
    annotation_review.add_argument("--decision", required=True, choices=("verified", "rejected"))
    annotation_review.add_argument("--note")
    add_library_database_option(annotation_review)
    annotation_analyze = annotation_commands.add_parser("analyze", help="measure the selected component blocks")
    annotation_analyze.add_argument("annotation_id")
    annotation_analyze.add_argument("--revision", type=int)
    add_library_database_option(annotation_analyze)

    components_parser = library_commands.add_parser("components", help="register and query static reference components")
    component_commands = components_parser.add_subparsers(dest="component_command", required=True)
    component_list = component_commands.add_parser("list")
    component_list.add_argument("--source-asset")
    component_list.add_argument("--component-type")
    add_library_database_option(component_list)
    component_show = component_commands.add_parser("show")
    component_show.add_argument("component_id")
    component_show.add_argument("--version", type=int)
    add_library_database_option(component_show)
    component_report = component_commands.add_parser("report", help="export a verified component analysis without overwriting")
    component_report.add_argument("component_id")
    component_report.add_argument("--version", type=int)
    component_report.add_argument("--output", required=True, type=Path)
    add_library_database_option(component_report)
    component_register = component_commands.add_parser("register", help="register a verified annotation as a static component")
    component_register.add_argument("annotation_id")
    component_register.add_argument("--name", required=True)
    component_register.add_argument("--style-tag", action="append", default=[])
    component_register.add_argument("--parameterization-status", choices=("not_parameterized", "planned"), default="not_parameterized")
    component_register.add_argument("--revision", type=int)
    add_library_database_option(component_register)

    style_analysis_parser = library_commands.add_parser("style-analysis", help="extract and review a measured Minecraft style report")
    style_analysis_commands = style_analysis_parser.add_subparsers(dest="style_analysis_command", required=True)
    style_analysis_create = style_analysis_commands.add_parser("create")
    style_analysis_create.add_argument("profile_id")
    style_analysis_create.add_argument("--profile-version", type=int)
    style_analysis_create.add_argument("--source", action="append", help="restrict to a pinned ASSET_ID@VERSION")
    style_analysis_create.add_argument("--analysis-id")
    add_library_database_option(style_analysis_create)
    style_analysis_list = style_analysis_commands.add_parser("list")
    style_analysis_list.add_argument("--profile-id")
    style_analysis_list.add_argument("--status", choices=("candidate", "verified", "rejected"))
    style_analysis_list.add_argument("--include-history", action="store_true")
    add_library_database_option(style_analysis_list)
    style_analysis_show = style_analysis_commands.add_parser("show")
    style_analysis_show.add_argument("analysis_id")
    style_analysis_show.add_argument("--revision", type=int)
    add_library_database_option(style_analysis_show)
    style_analysis_review = style_analysis_commands.add_parser("review")
    style_analysis_review.add_argument("analysis_id")
    style_analysis_review.add_argument("--reviewer", required=True)
    style_analysis_review.add_argument("--decision", required=True, choices=("verified", "rejected"))
    style_analysis_review.add_argument("--note")
    add_library_database_option(style_analysis_review)
    style_analysis_export = style_analysis_commands.add_parser("export")
    style_analysis_export.add_argument("analysis_id")
    style_analysis_export.add_argument("--output", required=True, type=Path)
    add_library_database_option(style_analysis_export)

    args = parser.parse_args()
    try:
        if args.command == "library":
            database_path = getattr(args, "command_database", None) or args.database
            library = LibraryService(LibraryDatabase(database_path))
            if args.library_command != "init" and not database_path.is_file():
                raise ValueError(
                    f"library database not found: {database_path}; run 'jiangnan library init' first"
                )
            library.initialize()
            if args.library_command == "init":
                result: object = {"database": str(database_path.resolve()), "schema_version": library.database.schema_version}
            elif args.library_command == "import":
                result = _reference_to_json(
                    library.import_litematic(
                        args.source,
                        asset_id=args.asset_id,
                        name=args.name,
                        building_type=args.building_type,
                        region_profile_id=args.region_profile,
                        style_tags=args.style_tag,
                        provenance_note=args.provenance_note,
                    )
                )
            elif args.library_command == "list":
                if args.category == "references":
                    result = [_reference_to_json(item) for item in library.list_references(building_type=args.building_type)]
                elif args.category == "regions":
                    result = list(library.list_regions())
                elif args.category == "sources":
                    result = list(library.list_sources())
                elif args.category == "parameters":
                    result = list(library.list_parameter_schemas())
                elif args.category == "styles":
                    result = list(library.list_styles())
                elif args.category == "modules":
                    result = list(library.list_modules(include_planned=args.include_planned))
                else:
                    result = library.list_knowledge_rules(
                        region=args.region,
                        building_type=args.building_type,
                        include_pending=args.include_pending,
                    )
            elif args.library_command == "show":
                result = _reference_to_json(library.get_reference(args.asset_id, args.version))
            elif args.library_command == "materials":
                result = {
                    "materials": library.material_totals(args.asset_id, args.version),
                    "block_states": library.material_counts(args.asset_id, args.version),
                }
            elif args.library_command == "layers":
                result = {str(y): counts for y, counts in library.layer_material_counts(args.asset_id, args.version).items()}
            elif args.library_command == "previews":
                result = _reference_to_json(
                    library.register_preview_files(args.asset_id, args.preview_files, args.version)
                )
            elif args.library_command == "module":
                result = library.get_module_definition(args.asset_id, args.version)
            elif args.library_command == "parameter":
                result = library.get_parameter_schema(args.schema_id, args.version)
            elif args.library_command == "style":
                result = library.get_style_profile(
                    args.profile_id,
                    args.version,
                    require_references=args.require_references,
                )
            elif args.library_command == "annotations":
                if args.annotation_command == "propose":
                    result = [_record_to_json(item) for item in library.propose_annotations(args.asset_id, args.version)]
                elif args.annotation_command == "list":
                    result = [
                        _record_to_json(item)
                        for item in library.list_annotations(
                            asset_id=args.asset_id,
                            version=args.version,
                            component_type=args.component_type,
                            status=args.status,
                            include_history=args.include_history,
                        )
                    ]
                elif args.annotation_command == "create":
                    geometry = json.loads(args.geometry)
                    if not isinstance(geometry, Mapping):
                        raise ValueError("annotation geometry JSON must be an object")
                    result = _record_to_json(
                        library.create_annotation(
                            annotation_id=args.annotation_id,
                            asset_id=args.asset_id,
                            version=args.version,
                            region_name=args.region,
                            component_type=args.component_type,
                            geometry_type=args.geometry_type,
                            geometry=geometry,
                            confidence=args.confidence,
                        )
                    )
                elif args.annotation_command == "update":
                    geometry = json.loads(args.geometry) if args.geometry is not None else None
                    if geometry is not None and not isinstance(geometry, Mapping):
                        raise ValueError("annotation geometry JSON must be an object")
                    result = _record_to_json(
                        library.update_annotation(
                            args.annotation_id,
                            component_type=args.component_type,
                            geometry_type=args.geometry_type,
                            geometry=geometry,
                            confidence=args.confidence,
                            review_note=args.note,
                        )
                    )
                elif args.annotation_command == "review":
                    result = _record_to_json(
                        library.review_annotation(
                            args.annotation_id,
                            reviewer=args.reviewer,
                            decision=args.decision,
                            note=args.note,
                        )
                    )
                else:
                    result = _record_to_json(library.analyze_annotation(args.annotation_id, args.revision))
            elif args.library_command == "components":
                if args.component_command == "list":
                    result = [
                        _record_to_json(item)
                        for item in library.list_reference_components(
                            source_asset_id=args.source_asset,
                            component_type=args.component_type,
                        )
                    ]
                elif args.component_command == "show":
                    result = _record_to_json(library.get_reference_component(args.component_id, args.version))
                elif args.component_command == "report":
                    result = {
                        "exported": str(
                            library.export_component_report(args.component_id, args.output, args.version)
                        )
                    }
                else:
                    result = _record_to_json(
                        library.register_reference_component(
                            args.annotation_id,
                            name=args.name,
                            style_tags=args.style_tag,
                            parameterization_status=args.parameterization_status,
                            revision=args.revision,
                        )
                    )
            elif args.library_command == "style-analysis":
                if args.style_analysis_command == "create":
                    sources = [_parse_asset_reference(item) for item in args.source] if args.source else None
                    result = _record_to_json(
                        library.create_style_analysis(
                            args.profile_id,
                            profile_version=args.profile_version,
                            source_assets=sources,
                            analysis_id=args.analysis_id,
                        )
                    )
                elif args.style_analysis_command == "list":
                    result = [
                        _record_to_json(item)
                        for item in library.list_style_analyses(
                            profile_id=args.profile_id,
                            status=args.status,
                            include_history=args.include_history,
                        )
                    ]
                elif args.style_analysis_command == "show":
                    result = _record_to_json(library.get_style_analysis(args.analysis_id, args.revision))
                elif args.style_analysis_command == "review":
                    result = _record_to_json(
                        library.review_style_analysis(
                            args.analysis_id,
                            reviewer=args.reviewer,
                            decision=args.decision,
                            note=args.note,
                        )
                    )
                else:
                    result = {"exported": str(library.export_style_analysis(args.analysis_id, args.output))}
            elif args.library_command == "verify":
                result = list(library.verify_files(args.asset_id))
            else:
                result = {"backup": str(library.backup_to(args.output).resolve())}
            print(json.dumps(result, ensure_ascii=False, indent=2, default=_json_default))
            return 0

        if args.command == "init":
            project = JiangnanProject(
                name=args.name,
                settings={"building": {"type": "simple_house", "width": 9, "length": 11, "wall_height": 4}},
            )
            destination = save_project(project, args.output)
            print(f"已创建工程: {destination.resolve()}")
            return 0

        if args.command == "preview":
            result = render_schematic_previews(
                args.schematic,
                args.output_dir,
                mine2blend_root=args.mine2blend_root,
                blender_executable=args.blender,
                compare_before=args.compare_before,
                timeout=args.timeout,
            )
            print(json.dumps({
                "output_dir": str(result.output_dir),
                "renders": {name: str(path) for name, path in sorted(result.render_paths.items())},
                "preview_report": str(result.preview_report_path),
                "comparison_report": str(result.comparison_report_path) if result.comparison_report_path else None,
            }, ensure_ascii=False, indent=2))
            return 0

        project = load_project(args.project)
        if args.command == "validate":
            print(f"工程有效: {project.name} ({project.minecraft_version})")
        elif args.command == "info":
            print(f"名称: {project.name}")
            print(f"工程 ID: {project.project_id}")
            print(f"Minecraft: Java {project.minecraft_version} (DataVersion {project.data_version})")
            print(f"模块数: {len(project.assembly.modules)}")
            revision = project.revision_history[project.revision_cursor]
            print(f"当前版本: {revision.revision_id} | {revision.message}")
        elif args.command == "history":
            for index, revision in enumerate(project.revision_history):
                marker = "（当前）" if index == project.revision_cursor else ""
                affected = ", ".join(revision.changed_module_ids) or "无"
                print(f"版本 {revision.revision_id}{marker}: {revision.message}")
                print(f"  受影响模块: {affected} | 方块变更: {len(revision.block_changes)}")
        elif args.command in ("undo", "redo"):
            editor = ProjectEditor(project)
            changed = editor.undo() if args.command == "undo" else editor.redo()
            if not changed:
                verb = "撤销" if args.command == "undo" else "重做"
                print(f"没有可{verb}的更改", file=sys.stderr)
                return 1
            save_project(project, args.project)
            revision = editor.current_revision
            verb = "撤销" if args.command == "undo" else "重做"
            print(f"已{verb}至版本 {revision.revision_id}: {revision.message}")
        else:
            model = generate_project_model(project)
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
    except (KeyError, OSError, TypeError, ValueError, sqlite3.Error) as exc:
        parser.exit(2, f"错误: {exc}\n")


def _reference_to_json(asset: object) -> dict[str, object]:
    return {
        field.name: getattr(asset, field.name)
        for field in fields(asset)
    }


def _record_to_json(record: object) -> dict[str, object]:
    if not hasattr(record, "__dataclass_fields__"):
        raise TypeError(f"cannot serialize record {type(record).__name__}")
    return {field.name: getattr(record, field.name) for field in fields(record)}


def _parse_asset_reference(value: str) -> tuple[str, int]:
    asset_id, separator, raw_version = value.rpartition("@")
    if not separator or not asset_id:
        raise ValueError(f"source reference must use ASSET_ID@VERSION syntax: {value!r}")
    try:
        version = int(raw_version)
    except ValueError as exc:
        raise ValueError(f"source reference version must be an integer: {value!r}") from exc
    if version < 1:
        raise ValueError(f"source reference version must be positive: {value!r}")
    return asset_id, version


def _json_default(value: object) -> object:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, tuple):
        return list(value)
    raise TypeError(f"cannot serialize {type(value).__name__}")


if __name__ == "__main__":
    raise SystemExit(main())
