"""Confine tool-visible project and export paths to the workspace."""

from __future__ import annotations

from pathlib import Path, PureWindowsPath
from typing import Literal


class ProjectAccess:
    """Resolve workspace-relative paths without following links outside their roots."""

    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.projects_root = self.workspace_root / "workspace" / "projects"
        self.exports_root = self.workspace_root / "workspace" / "exports"

    def resolve_project_path(
        self,
        relative_path: str,
        *,
        operation: Literal["read", "edit", "create"],
    ) -> Path:
        """Resolve a `.json` project path and enforce operation-specific existence."""

        if operation not in ("read", "edit", "create"):
            raise ValueError("operation must be read, edit, or create")
        candidate = self._resolve_confined(relative_path, self.projects_root, ".json")
        exists = candidate.exists() or candidate.is_symlink()
        if operation in ("read", "edit") and not candidate.is_file():
            raise ValueError(f"project file does not exist: {relative_path!r}")
        if operation == "create" and exists:
            raise ValueError(f"project file already exists: {relative_path!r}")
        return candidate

    def resolve_export_path(self, relative_path: str) -> Path:
        """Resolve a new `.schem` export path without permitting overwrites."""

        candidate = self._resolve_confined(relative_path, self.exports_root, ".schem")
        if candidate.exists() or candidate.is_symlink():
            raise ValueError(f"schematic output already exists: {relative_path!r}")
        return candidate

    @staticmethod
    def _resolve_confined(relative_path: str, allowed_root: Path, suffix: str) -> Path:
        if not isinstance(relative_path, str) or not relative_path.strip():
            raise ValueError("path must be a non-empty workspace-relative string")
        issue = ProjectAccess._unsafe_relative_path_reason(relative_path)
        if issue is not None:
            raise ValueError(issue)
        if Path(relative_path).suffix.lower() != suffix:
            raise ValueError(f"path must use the {suffix} suffix")

        try:
            resolved = (allowed_root / relative_path).resolve()
            resolved.relative_to(allowed_root)
        except (OSError, RuntimeError, ValueError) as exc:
            raise ValueError("path resolves outside its allowed workspace directory") from exc
        return resolved

    @staticmethod
    def _is_unsafe_relative_path(relative_path: str) -> bool:
        """Classify native and Windows path anchors independent of host OS."""

        return ProjectAccess._unsafe_relative_path_reason(relative_path) is not None

    @staticmethod
    def _unsafe_relative_path_reason(relative_path: str) -> str | None:
        if not isinstance(relative_path, str) or not relative_path.strip():
            return "path must be a non-empty workspace-relative string"
        windows_path = PureWindowsPath(relative_path)
        if (
            Path(relative_path).is_absolute()
            or windows_path.is_absolute()
            or windows_path.drive
            or windows_path.root
        ):
            return "absolute paths are not allowed"
        if ".." in relative_path.replace("\\", "/").split("/"):
            return "parent traversal is not allowed"
        return None
