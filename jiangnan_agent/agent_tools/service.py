"""Small JSON-friendly tools over the existing local building engine."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
import os
from pathlib import Path
import tempfile
from typing import Any

from ..assembly.model import Assembly, Module
from ..assembly.transforms import mirror_module, rotate_module, translate_module
from ..assembly.validation import ValidationIssue, validate_assembly
from ..assets import get_asset_for_kind, module_from_asset
from ..core.geometry import Position
from ..io.project_editor import ProjectEditor
from ..io.project_generation import generate_project_model
from ..io.project_history import BlockChange, ProjectRevision
from ..io.project_json import JiangnanProject, load_project, save_project
from ..knowledge import EvidenceKind, load_knowledge_base
from ..io.schematic import read_schematic, write_schematic
from .project_access import ProjectAccess


def _temporary_sibling(destination: Path) -> Path:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=destination.parent,
    )
    os.close(descriptor)
    return Path(temporary_name)


def _publish_new_file(temporary_path: Path, destination: Path, conflict_message: str) -> None:
    """Atomically add a completed file without replacing a concurrent winner."""

    try:
        os.link(temporary_path, destination)
    except FileExistsError as exc:
        raise ValueError(conflict_message) from exc


class ProjectToolService:
    """Expose bounded project and building operations within one workspace."""

    def __init__(self, workspace_root: Path) -> None:
        self.access = ProjectAccess(workspace_root)

    def list_knowledge_rules(
        self,
        region: str | None = None,
        building_type: str | None = None,
        evidence_kind: str | None = None,
        knowledge_version: int | None = None,
    ) -> dict[str, Any]:
        """Return source-backed knowledge records without accessing project files."""

        for field_name, value in (("region", region), ("building_type", building_type)):
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{field_name} must be a non-empty string when provided")
        try:
            evidence_filter = None if evidence_kind is None else EvidenceKind(evidence_kind)
        except (TypeError, ValueError) as exc:
            allowed = ", ".join(item.value for item in EvidenceKind)
            raise ValueError(f"unsupported evidence_kind; expected one of: {allowed}") from exc

        knowledge = load_knowledge_base(knowledge_version)
        rules = knowledge.rules_for(
            evidence_filter,
            region=region,
            building_type=building_type,
        )
        return {
            "knowledge_base_version": knowledge.version,
            "filters": {
                "region": region,
                "building_type": building_type,
                "evidence_kind": None if evidence_filter is None else evidence_filter.value,
                "knowledge_version": knowledge_version,
            },
            "rules": [
                {
                    "rule_id": rule.rule_id,
                    "source_id": rule.source_id,
                    "source": {
                        "source_id": source.source_id,
                        "source_type": source.source_type,
                        "title": source.title,
                        "locator": source.locator,
                    },
                    "applicable_regions": list(rule.applicable_regions),
                    "building_types": list(rule.building_types),
                    "evidence_kind": rule.evidence_kind.value,
                    "basis": rule.basis,
                    "confidence": rule.confidence.value,
                    "scope": rule.scope,
                    "statement": rule.statement,
                }
                for rule in rules
                for source in (knowledge.sources[rule.source_id],)
            ],
        }

    def list_projects(self) -> list[dict[str, Any]]:
        """List saved project summaries without exposing block maps."""

        root = self.access.projects_root
        if not root.is_dir():
            return []
        results: list[dict[str, Any]] = []
        for path in sorted(root.rglob("*.json")):
            project_path = path.relative_to(root).as_posix()
            try:
                resolved = self.access.resolve_project_path(project_path, operation="read")
                project = load_project(resolved)
            except (OSError, TypeError, ValueError) as exc:
                results.append({"project_path": project_path, "valid": False, "error": str(exc)})
                continue
            results.append({"valid": True, **self._project_summary(project_path, project)})
        return results

    def get_project(self, project_path: str) -> dict[str, Any]:
        project = self._load_project(project_path)
        return self._project_summary(project_path, project)

    def list_modules(self, project_path: str) -> list[dict[str, Any]]:
        project = self._load_project(project_path)
        modules = sorted(project.assembly.modules.values(), key=lambda item: item.module_id)
        return [self._module_summary(module) for module in modules]

    def get_module(self, project_path: str, module_id: str) -> dict[str, Any]:
        project = self._load_project(project_path)
        try:
            module = project.assembly.modules[module_id]
        except KeyError as exc:
            raise ValueError(f"unknown module ID: {module_id!r}") from exc
        return self._module_summary(module)

    def create_project(self, name: str, project_path: str) -> dict[str, Any]:
        destination = self.access.resolve_project_path(project_path, operation="create")
        project = JiangnanProject(name=name)
        self._save_new_project(destination, project, project_path)
        return self._project_summary(project_path, project)

    def create_module(
        self,
        project_path: str,
        module_id: str,
        kind: str,
        parameters: dict[str, Any],
        *,
        attach_to_module_id: str | None = None,
        attach_to_anchor_name: str | None = None,
        module_anchor_name: str | None = None,
    ) -> dict[str, Any]:
        project, destination = self._load_for_edit(project_path)
        module = self._build_module(module_id, kind, parameters)
        attach_fields = (attach_to_module_id, attach_to_anchor_name, module_anchor_name)
        if any(value is not None for value in attach_fields) and not all(value is not None for value in attach_fields):
            raise ValueError("module attachment requires all three anchor fields")
        editor = ProjectEditor(project)
        if all(value is None for value in attach_fields):
            revision = editor.add_module(module, f"Create {kind} module {module_id}")
        else:
            assert attach_to_module_id is not None
            assert attach_to_anchor_name is not None
            assert module_anchor_name is not None
            revision = editor.connect_modules(
                attach_to_module_id,
                attach_to_anchor_name,
                module,
                module_anchor_name,
                f"Create and attach {kind} module {module_id}",
            )
        save_project(project, destination)
        return self._mutation_result("create_module", project_path, project, revision)

    def set_parameters(
        self,
        project_path: str,
        module_id: str,
        parameter_updates: dict[str, Any],
    ) -> dict[str, Any]:
        project, destination = self._load_for_edit(project_path)
        if not isinstance(parameter_updates, Mapping):
            raise ValueError("parameter_updates must be a JSON object")
        revision = ProjectEditor(project).regenerate_module(
            module_id,
            parameter_updates,
            f"Update parameters for module {module_id}",
        )
        save_project(project, destination)
        return self._mutation_result("set_parameters", project_path, project, revision)

    def transform_module(
        self,
        project_path: str,
        module_id: str,
        operation: str,
        *,
        offset: tuple[int, int, int] | list[int] | None = None,
        quarter_turns: int | None = None,
        axis: str | None = None,
    ) -> dict[str, Any]:
        project, destination = self._load_for_edit(project_path)
        checked_offset = self._position(offset) if offset is not None else None
        revision = ProjectEditor(project).transform_module(
            module_id,
            operation,
            f"Transform module {module_id} ({operation})",
            offset=checked_offset,
            quarter_turns=quarter_turns,
            axis=axis,
        )
        save_project(project, destination)
        return self._mutation_result("transform_module", project_path, project, revision)

    def connect_modules(
        self,
        project_path: str,
        first_module_id: str,
        first_anchor_name: str,
        second_module_id: str,
        second_anchor_name: str,
    ) -> dict[str, Any]:
        project, destination = self._load_for_edit(project_path)
        revision = ProjectEditor(project).connect_modules(
            first_module_id,
            first_anchor_name,
            second_module_id,
            second_anchor_name,
            f"Connect {first_module_id}.{first_anchor_name} to {second_module_id}.{second_anchor_name}",
        )
        save_project(project, destination)
        return self._mutation_result("connect_modules", project_path, project, revision)

    def replace_module(
        self,
        project_path: str,
        module_id: str,
        kind: str,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        project, destination = self._load_for_edit(project_path)
        try:
            previous = project.assembly.modules[module_id]
        except KeyError as exc:
            raise ValueError(f"unknown module ID: {module_id!r}") from exc
        replacement = self._build_module(module_id, kind, parameters)
        for step in previous.transform_steps:
            operation = step.get("op")
            if operation == "translate":
                replacement = translate_module(replacement, self._position(step.get("offset")))
            elif operation == "rotate_y":
                turns = step.get("quarter_turns")
                if isinstance(turns, bool) or not isinstance(turns, int):
                    raise ValueError("recorded rotate_y step has invalid quarter_turns")
                replacement = rotate_module(replacement, turns)
            elif operation == "mirror":
                axis = step.get("axis")
                if not isinstance(axis, str):
                    raise ValueError("recorded mirror step has an invalid axis")
                replacement = mirror_module(replacement, axis)
            else:
                raise ValueError(f"unsupported recorded transform operation: {operation!r}")
        revision = ProjectEditor(project).replace_module(
            module_id,
            replacement,
            f"Replace module {module_id} with {kind}",
        )
        save_project(project, destination)
        return self._mutation_result("replace_module", project_path, project, revision)

    def validate_assembly(self, project_path: str) -> dict[str, Any]:
        project = self._load_project(project_path)
        return self._validation_summary(project_path, project.assembly)

    @classmethod
    def _validation_summary(cls, project_path: str, assembly: Assembly) -> dict[str, Any]:
        issues = validate_assembly(assembly)
        return {
            "project_path": project_path,
            "valid": not issues,
            "issue_count": len(issues),
            "issues": [cls._issue_summary(issue) for issue in issues[:100]],
            "truncated": len(issues) > 100,
        }

    def inspect_changes(
        self,
        project_path: str,
        revision_id: int | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        project = self._load_project(project_path)
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("limit must be an integer from 1 to 100")
        if revision_id is None:
            revision = project.revision_history[project.revision_cursor]
        else:
            if isinstance(revision_id, bool) or not isinstance(revision_id, int):
                raise ValueError("revision_id must be an integer")
            matches = [item for item in project.revision_history if item.revision_id == revision_id]
            if not matches:
                raise ValueError(f"unknown revision ID: {revision_id}")
            revision = matches[0]

        added = sum(change.before_state is None for change in revision.block_changes)
        removed = sum(change.after_state is None for change in revision.block_changes)
        updated = len(revision.block_changes) - added - removed
        changes = revision.block_changes[:limit]
        return {
            "project_path": project_path,
            "revision_id": revision.revision_id,
            "parent_revision_id": revision.parent_revision_id,
            "message": revision.message,
            "changed_module_ids": list(revision.changed_module_ids),
            "block_change_count": len(revision.block_changes),
            "blocks_added": added,
            "blocks_removed": removed,
            "blocks_updated": updated,
            "block_changes": [self._block_change_summary(change) for change in changes],
            "truncated": len(changes) < len(revision.block_changes),
        }

    def export_schematic(self, project_path: str, output_path: str) -> dict[str, Any]:
        project = self._load_project(project_path)
        destination = self.access.resolve_export_path(output_path)
        model = generate_project_model(project)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination = self.access.resolve_export_path(output_path)
        temporary_path = _temporary_sibling(destination)
        try:
            write_schematic(model, temporary_path, data_version=project.data_version, name=project.name)
            document = read_schematic(temporary_path)
            expected_offset = (model.bounds.min_x, model.bounds.min_y, model.bounds.min_z)
            expected_local_blocks = {
                (x - expected_offset[0], y - expected_offset[1], z - expected_offset[2]): state
                for (x, y, z), state in model.blocks.items()
            }
            if document.offset != expected_offset or document.model.blocks != expected_local_blocks:
                raise ValueError("schematic round-trip validation failed")
            _publish_new_file(
                temporary_path,
                destination,
                f"schematic output already exists: {output_path!r}",
            )
        finally:
            temporary_path.unlink(missing_ok=True)
        return {
            "operation": "export_schematic",
            "project_path": project_path,
            "output_path": (Path("workspace") / "exports" / output_path).as_posix(),
            "block_count": len(document.model.blocks),
            "dimensions": list(document.model.bounds.size) if document.model.blocks else [0, 0, 0],
            "offset": list(document.offset),
            "data_version": document.data_version,
        }

    def _load_project(self, project_path: str) -> JiangnanProject:
        return load_project(self.access.resolve_project_path(project_path, operation="read"))

    def _load_for_edit(self, project_path: str) -> tuple[JiangnanProject, Path]:
        destination = self.access.resolve_project_path(project_path, operation="edit")
        return load_project(destination), destination

    def _save_new_project(self, destination: Path, project: JiangnanProject, project_path: str) -> None:
        # Re-resolve for early feedback; the final hard-link publication also refuses races.
        destination = self.access.resolve_project_path(project_path, operation="create")
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = _temporary_sibling(destination)
        try:
            save_project(project, temporary_path)
            _publish_new_file(
                temporary_path,
                destination,
                f"project file already exists: {project_path!r}",
            )
        finally:
            temporary_path.unlink(missing_ok=True)

    def _project_summary(self, project_path: str, project: JiangnanProject) -> dict[str, Any]:
        revision = project.revision_history[project.revision_cursor]
        return {
            "project_path": project_path,
            "project_id": project.project_id,
            "name": project.name,
            "minecraft_version": project.minecraft_version,
            "data_version": project.data_version,
            "module_count": len(project.assembly.modules),
            "connection_count": len(project.assembly.connections),
            "revision_id": revision.revision_id,
            "revision_message": revision.message,
        }

    def _mutation_result(
        self,
        operation: str,
        project_path: str,
        project: JiangnanProject,
        revision: ProjectRevision,
    ) -> dict[str, Any]:
        return {
            "operation": operation,
            "project_path": project_path,
            "revision_id": revision.revision_id,
            "revision_message": revision.message,
            "affected_module_ids": list(revision.changed_module_ids),
            "module_count": len(project.assembly.modules),
            "connection_count": len(project.assembly.connections),
            "validation": self._validation_summary(project_path, project.assembly),
        }

    @classmethod
    def _build_module(cls, module_id: str, kind: str, parameters: dict[str, Any]) -> Module:
        if not isinstance(parameters, Mapping):
            raise ValueError("parameters must be a JSON object")
        try:
            asset = get_asset_for_kind(kind)
            return module_from_asset(module_id, asset.asset_id, parameters)
        except TypeError as exc:
            raise ValueError(f"invalid parameters for {kind!r} module: {exc}") from exc

    @classmethod
    def _module_summary(cls, module: Module) -> dict[str, Any]:
        bounds = module.model.bounds if module.model.blocks else None
        counts = Counter(state.to_string() for state in module.model.blocks.values())
        palette = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        return {
            "module_id": module.module_id,
            "kind": module.kind,
            "parameters": cls._json_value(module.parameters),
            "metadata": cls._json_value(module.metadata),
            "block_count": len(module.model.blocks),
            "bounds": None
            if bounds is None
            else {
                "minimum": [bounds.min_x, bounds.min_y, bounds.min_z],
                "maximum_exclusive": [bounds.max_x, bounds.max_y, bounds.max_z],
                "dimensions": list(bounds.size),
            },
            "palette": [{"state": state, "count": count} for state, count in palette[:16]],
            "palette_truncated": len(palette) > 16,
            "anchors": [
                {
                    "name": anchor.name,
                    "position": list(anchor.position),
                    "facing": anchor.facing,
                    "connection_type": anchor.connection_type,
                    "width": anchor.width,
                    "height": anchor.height,
                }
                for anchor in module.anchors
            ],
            "clearance_zones": [
                {
                    "name": zone.name,
                    "purpose": zone.purpose,
                    "bounds": {
                        "minimum": [zone.bounds.min_x, zone.bounds.min_y, zone.bounds.min_z],
                        "maximum_exclusive": [zone.bounds.max_x, zone.bounds.max_y, zone.bounds.max_z],
                    },
                }
                for zone in module.clearance_zones
            ],
            "transform_steps": cls._json_value(module.transform_steps),
        }

    @staticmethod
    def _issue_summary(issue: ValidationIssue) -> dict[str, Any]:
        return {
            "code": issue.code,
            "message": issue.message,
            "module_ids": list(issue.module_ids),
            "position": list(issue.position) if issue.position is not None else None,
            "count": issue.count,
        }

    @staticmethod
    def _block_change_summary(change: BlockChange) -> dict[str, Any]:
        return {
            "module_id": change.module_id,
            "position": list(change.position),
            "before_state": change.before_state,
            "after_state": change.after_state,
        }

    @classmethod
    def _json_value(cls, value: Any) -> Any:
        if isinstance(value, Mapping):
            return {key: cls._json_value(item) for key, item in value.items()}
        if isinstance(value, (tuple, list)):
            return [cls._json_value(item) for item in value]
        if value is None or isinstance(value, (bool, int, float, str)):
            return value
        raise ValueError(f"value of type {type(value).__name__} is not JSON-compatible")

    @staticmethod
    def _position(value: object) -> Position:
        if (
            not isinstance(value, (list, tuple))
            or len(value) != 3
            or any(isinstance(coordinate, bool) or not isinstance(coordinate, int) for coordinate in value)
        ):
            raise ValueError("offset must contain exactly three integer coordinates")
        return value[0], value[1], value[2]
