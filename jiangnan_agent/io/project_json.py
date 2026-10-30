"""Load and save the versioned Jiangnan Architect project document."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import tempfile
from typing import Any
from uuid import uuid4

from ..assembly.model import Assembly
from .assembly_json import assembly_from_dict, assembly_to_dict
from .project_history import ProjectRevision

PROJECT_FORMAT_VERSION = 2
LEGACY_PROJECT_FORMAT_VERSION = 1
DEFAULT_MINECRAFT_VERSION = "1.21.5"
DEFAULT_DATA_VERSION = 4325


@dataclass
class JiangnanProject:
    name: str
    project_id: str = field(default_factory=lambda: str(uuid4()))
    minecraft_version: str = DEFAULT_MINECRAFT_VERSION
    data_version: int = DEFAULT_DATA_VERSION
    modules: list[dict[str, Any]] = field(default_factory=list)
    settings: dict[str, Any] = field(default_factory=dict)
    format_version: int = PROJECT_FORMAT_VERSION
    assembly: Assembly = field(default_factory=Assembly)
    revision_history: list[ProjectRevision] = field(default_factory=list)
    revision_cursor: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("project name cannot be empty")
        if self.format_version != PROJECT_FORMAT_VERSION:
            raise ValueError(f"unsupported project format version: {self.format_version}")
        if self.data_version <= 0:
            raise ValueError("data_version must be a positive integer")
        if not isinstance(self.modules, list) or not all(isinstance(item, dict) for item in self.modules):
            raise ValueError("modules must be a list of JSON objects")
        if not isinstance(self.settings, dict):
            raise ValueError("settings must be a JSON object")
        if not isinstance(self.assembly, Assembly):
            raise ValueError("assembly must be an Assembly")
        if not isinstance(self.revision_history, list) or any(
            not isinstance(revision, ProjectRevision) for revision in self.revision_history
        ):
            raise ValueError("revision_history must be a list of ProjectRevision values")
        if not self.revision_history:
            self.revision_history = [ProjectRevision.create(0, None, "Initial project state", (), self.assembly)]
            self.revision_cursor = 0
        if (
            isinstance(self.revision_cursor, bool)
            or not isinstance(self.revision_cursor, int)
            or not 0 <= self.revision_cursor < len(self.revision_history)
        ):
            raise ValueError("revision_cursor must select an existing revision")
        previous_id: int | None = None
        for index, revision in enumerate(self.revision_history):
            if revision.parent_revision_id != previous_id:
                raise ValueError(f"revision {index} has an invalid parent link")
            previous_id = revision.revision_id
        if assembly_to_dict(self.revision_history[self.revision_cursor].restore_assembly()) != assembly_to_dict(self.assembly):
            raise ValueError("current assembly does not match the selected revision snapshot")

    def to_dict(self) -> dict[str, Any]:
        if assembly_to_dict(self.revision_history[self.revision_cursor].restore_assembly()) != assembly_to_dict(self.assembly):
            raise ValueError("current assembly does not match the selected revision snapshot")
        return {
            "format_version": self.format_version,
            "project_id": self.project_id,
            "name": self.name,
            "minecraft_version": self.minecraft_version,
            "data_version": self.data_version,
            "modules": self.modules,
            "settings": self.settings,
            "assembly": assembly_to_dict(self.assembly),
            "revision_history": [revision.to_dict() for revision in self.revision_history],
            "revision_cursor": self.revision_cursor,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JiangnanProject:
        if not isinstance(data, dict):
            raise ValueError("project JSON root must be an object")
        missing = {"name"}.difference(data)
        if missing:
            raise ValueError(f"project JSON is missing required fields: {', '.join(sorted(missing))}")
        try:
            source_version = data.get("format_version", LEGACY_PROJECT_FORMAT_VERSION)
            if isinstance(source_version, bool) or not isinstance(source_version, int):
                raise ValueError(f"unsupported project format version: {source_version!r}")
            if source_version not in (LEGACY_PROJECT_FORMAT_VERSION, PROJECT_FORMAT_VERSION):
                raise ValueError(f"unsupported project format version: {source_version}")
            assembly = (
                assembly_from_dict(data["assembly"])
                if source_version == PROJECT_FORMAT_VERSION and "assembly" in data
                else Assembly()
            )
            if source_version == PROJECT_FORMAT_VERSION and "assembly" not in data:
                raise ValueError("project JSON is missing required field: assembly")
            raw_history = data.get("revision_history", [])
            if not isinstance(raw_history, (list, tuple)):
                raise ValueError("revision_history must be a list")
            revision_history = [ProjectRevision.from_dict(item) for item in raw_history]
            revision_cursor = data.get("revision_cursor", max(0, len(revision_history) - 1))
            return cls(
                name=str(data["name"]),
                project_id=str(data.get("project_id") or uuid4()),
                minecraft_version=str(data.get("minecraft_version", DEFAULT_MINECRAFT_VERSION)),
                data_version=int(data.get("data_version", DEFAULT_DATA_VERSION)),
                modules=data.get("modules", []),
                settings=data.get("settings", {}),
                format_version=PROJECT_FORMAT_VERSION,
                assembly=assembly,
                revision_history=revision_history,
                revision_cursor=revision_cursor,
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid project JSON: {exc}") from exc


def save_project(project: JiangnanProject, path: str | Path) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(project.to_dict(), ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n"
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", newline="\n", dir=destination.parent, delete=False
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, destination)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    return destination


def load_project(path: str | Path) -> JiangnanProject:
    source = Path(path)
    try:
        with source.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {source}: {exc}") from exc
    return JiangnanProject.from_dict(data)
