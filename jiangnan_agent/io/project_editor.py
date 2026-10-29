"""Module-scoped project regeneration and revision navigation."""

from __future__ import annotations

from collections.abc import Mapping

from ..assembly.adapters import corridor_module, hall_module
from ..assembly.model import Assembly, Module
from ..assembly.operations import connect_modules as connect_assembly_modules
from ..assembly.operations import replace_module as replace_assembly_module
from ..assembly.transforms import mirror_module, rotate_module, translate_module
from ..assets import module_from_asset
from ..core.geometry import Position
from ..generators.hall import CorridorParameters, HallParameters
from .assembly_json import assembly_to_dict
from .project_history import ProjectRevision, diff_assemblies
from .project_json import JiangnanProject


class ProjectEditor:
    """Edit one module at a time while keeping other module data intact."""

    def __init__(self, project: JiangnanProject) -> None:
        if not isinstance(project, JiangnanProject):
            raise ValueError("project must be a JiangnanProject")
        self.project = project

    @property
    def can_undo(self) -> bool:
        return self.project.revision_cursor > 0

    @property
    def can_redo(self) -> bool:
        return self.project.revision_cursor + 1 < len(self.project.revision_history)

    @property
    def current_revision(self) -> ProjectRevision:
        return self.project.revision_history[self.project.revision_cursor]

    def add_module(self, module: Module, message: str) -> ProjectRevision:
        """Add one module and record its complete block delta as a revision."""

        self._ensure_current_snapshot()
        if not isinstance(module, Module):
            raise ValueError("module must be a Module")
        next_assembly = Assembly((*self.project.assembly.modules.values(), module), self.project.assembly.connections)
        return self._record(next_assembly, module.module_id, message)

    def transform_module(
        self,
        module_id: str,
        operation: str,
        message: str,
        *,
        offset: Position | None = None,
        quarter_turns: int | None = None,
        axis: str | None = None,
    ) -> ProjectRevision:
        """Apply one recorded geometric transform to exactly one module."""

        self._ensure_current_snapshot()
        if module_id not in self.project.assembly.modules:
            raise ValueError(f"unknown module ID: {module_id!r}")
        if operation not in ("translate", "rotate_y", "mirror"):
            raise ValueError("operation must be translate, rotate_y, or mirror")

        supplied = {
            "offset": offset,
            "quarter_turns": quarter_turns,
            "axis": axis,
        }
        required = {
            "translate": "offset",
            "rotate_y": "quarter_turns",
            "mirror": "axis",
        }[operation]
        if supplied[required] is None or any(name != required and value is not None for name, value in supplied.items()):
            raise ValueError(f"operation {operation!r} requires only {required}")

        current = self.project.assembly.modules[module_id]
        if operation == "translate":
            assert offset is not None
            transformed = translate_module(current, offset)
        elif operation == "rotate_y":
            assert quarter_turns is not None
            transformed = rotate_module(current, quarter_turns)
        else:
            assert axis is not None
            transformed = mirror_module(current, axis)
        next_assembly = replace_assembly_module(self.project.assembly, module_id, transformed)
        return self._record(next_assembly, module_id, message)

    def connect_modules(
        self,
        first_module_id: str,
        first_anchor_name: str,
        second_module: Module | str,
        second_anchor_name: str,
        message: str,
    ) -> ProjectRevision:
        """Connect existing aligned modules or attach and auto-place a new module."""

        self._ensure_current_snapshot()
        next_assembly = connect_assembly_modules(
            self.project.assembly,
            first_module_id,
            first_anchor_name,
            second_module,
            second_anchor_name,
        )
        return self._record(next_assembly, first_module_id, message)

    def replace_module(self, module_id: str, replacement: Module, message: str) -> ProjectRevision:
        self._ensure_current_snapshot()
        if module_id not in self.project.assembly.modules:
            raise ValueError(f"unknown module ID: {module_id!r}")
        next_assembly = replace_assembly_module(self.project.assembly, module_id, replacement)
        return self._record(next_assembly, module_id, message)

    def regenerate_module(
        self,
        module_id: str,
        parameter_updates: Mapping[str, object],
        message: str,
    ) -> ProjectRevision:
        self._ensure_current_snapshot()
        if module_id not in self.project.assembly.modules:
            raise ValueError(f"unknown module ID: {module_id!r}")
        if not isinstance(parameter_updates, Mapping) or any(not isinstance(key, str) for key in parameter_updates):
            raise ValueError("parameter_updates must be a mapping with string keys")

        current = self.project.assembly.modules[module_id]
        kind = current.kind
        try:
            asset_id = current.metadata.get("asset_id")
            parameter_config = current.metadata.get("parameter_config")
            parameter_provenance = current.metadata.get("parameter_provenance")
            schema_version = current.metadata.get("parameter_schema_version")
            asset_version = current.metadata.get("asset_version")
            if isinstance(asset_id, str) and isinstance(parameter_config, Mapping):
                if isinstance(schema_version, bool) or not isinstance(schema_version, int):
                    raise ValueError(f"versioned module {module_id!r} has invalid parameter schema metadata")
                if isinstance(asset_version, bool) or not isinstance(asset_version, int):
                    raise ValueError(f"versioned module {module_id!r} has invalid asset version metadata")
                replacement = module_from_asset(
                    module_id,
                    asset_id,
                    parameter_updates,
                    schema_version=schema_version,
                    asset_version=asset_version,
                    base_config=parameter_config,
                    base_provenance=parameter_provenance,
                )
            else:
                parameters = dict(current.parameters)
                parameters.update(parameter_updates)
                if kind == "hall":
                    through_passage = parameters.pop("through_passage", False)
                    if not isinstance(through_passage, bool):
                        raise ValueError("through_passage must be a boolean")
                    replacement = hall_module(
                        module_id,
                        HallParameters(**parameters),
                        through_passage=through_passage,
                    )
                elif kind == "corridor":
                    passage_width = parameters.pop("passage_width", None)
                    replacement = corridor_module(
                        module_id,
                        CorridorParameters(**parameters),
                        passage_width=passage_width,
                    )
                else:
                    raise ValueError(f"module kind {kind!r} cannot be regenerated")
        except TypeError as exc:
            raise ValueError(f"invalid parameters for {kind} module: {exc}") from exc

        for step in current.transform_steps:
            operation = step.get("op")
            if operation == "translate":
                offset = step.get("offset")
                if not isinstance(offset, (list, tuple)) or len(offset) != 3:
                    raise ValueError("recorded translate step has an invalid offset")
                replacement = translate_module(replacement, tuple(offset))  # type: ignore[arg-type]
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

        return self.replace_module(module_id, replacement, message)

    def undo(self) -> bool:
        if not self.can_undo:
            return False
        self._ensure_current_snapshot()
        self.project.revision_cursor -= 1
        self.project.assembly = self.current_revision.restore_assembly()
        return True

    def redo(self) -> bool:
        if not self.can_redo:
            return False
        self._ensure_current_snapshot()
        self.project.revision_cursor += 1
        self.project.assembly = self.current_revision.restore_assembly()
        return True

    def _record(self, assembly: Assembly, module_id: str, message: str) -> ProjectRevision:
        before = self.current_revision.restore_assembly()
        changed_module_ids, block_changes = diff_assemblies(before, assembly)
        changed_module_ids = tuple(sorted(set(changed_module_ids) | {module_id}))
        parent = self.current_revision
        revision = ProjectRevision.create(
            parent.revision_id + 1,
            parent.revision_id,
            message,
            changed_module_ids,
            assembly,
            block_changes=block_changes,
        )
        history = self.project.revision_history[: self.project.revision_cursor + 1]
        self.project.assembly = assembly
        self.project.revision_history = [*history, revision]
        self.project.revision_cursor = len(self.project.revision_history) - 1
        return revision

    def _ensure_current_snapshot(self) -> None:
        committed = self.current_revision.restore_assembly()
        if assembly_to_dict(committed) != assembly_to_dict(self.project.assembly):
            raise ValueError(
                "current Assembly has unrecorded changes that differ from the selected revision snapshot"
            )
