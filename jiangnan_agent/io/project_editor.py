"""Module-scoped project regeneration and revision navigation."""

from __future__ import annotations

from collections.abc import Mapping

from ..assembly.adapters import corridor_module, hall_module
from ..assembly.model import Assembly, Module
from ..assembly.operations import replace_module as replace_assembly_module
from ..assembly.transforms import mirror_module, rotate_module, translate_module
from ..generators.hall import CorridorParameters, HallParameters
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

    def replace_module(self, module_id: str, replacement: Module, message: str) -> ProjectRevision:
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
        if module_id not in self.project.assembly.modules:
            raise ValueError(f"unknown module ID: {module_id!r}")
        if not isinstance(parameter_updates, Mapping) or any(not isinstance(key, str) for key in parameter_updates):
            raise ValueError("parameter_updates must be a mapping with string keys")

        current = self.project.assembly.modules[module_id]
        parameters = dict(current.parameters)
        parameters.update(parameter_updates)
        kind = current.kind
        try:
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
        self.project.revision_cursor -= 1
        self.project.assembly = self.current_revision.restore_assembly()
        return True

    def redo(self) -> bool:
        if not self.can_redo:
            return False
        self.project.revision_cursor += 1
        self.project.assembly = self.current_revision.restore_assembly()
        return True

    def _record(self, assembly: Assembly, module_id: str, message: str) -> ProjectRevision:
        before = self.project.assembly
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
