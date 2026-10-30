"""Immutable project revisions and exact per-block change records."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from typing import Any

from ..assembly.model import Assembly
from ..core.block import BlockState
from ..core.geometry import Position
from .assembly_json import assembly_from_dict, assembly_to_dict


def _snapshot_json(assembly: Assembly) -> str:
    return json.dumps(
        assembly_to_dict(assembly),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


@dataclass(frozen=True)
class BlockChange:
    """One module cell added, removed, or changed between two revisions."""

    module_id: str
    position: Position
    before_state: str | None
    after_state: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.module_id, str) or not self.module_id.strip():
            raise ValueError("block change module_id must be a non-empty string")
        if (
            not isinstance(self.position, tuple)
            or len(self.position) != 3
            or any(isinstance(value, bool) or not isinstance(value, int) for value in self.position)
        ):
            raise ValueError("block change position must contain three integers")
        for state in (self.before_state, self.after_state):
            if state is not None:
                if not isinstance(state, str):
                    raise ValueError("block change states must be strings or None")
                BlockState.parse(state)
        if self.before_state == self.after_state:
            raise ValueError("block change must change the block state")

    def to_dict(self) -> dict[str, Any]:
        return {
            "module_id": self.module_id,
            "position": list(self.position),
            "before_state": self.before_state,
            "after_state": self.after_state,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> BlockChange:
        if not isinstance(data, Mapping):
            raise ValueError("block change must be a JSON object")
        position = data.get("position")
        if not isinstance(position, (list, tuple)) or len(position) != 3:
            raise ValueError("block change position must contain three integers")
        coordinates = tuple(position)
        return cls(
            data.get("module_id"),
            coordinates,  # type: ignore[arg-type]
            data.get("before_state"),
            data.get("after_state"),
        )


@dataclass(frozen=True)
class ProjectRevision:
    """A full immutable Assembly snapshot plus its concise change record."""

    revision_id: int
    parent_revision_id: int | None
    created_at: str
    message: str
    changed_module_ids: tuple[str, ...]
    block_changes: tuple[BlockChange, ...]
    snapshot_json: str

    def __post_init__(self) -> None:
        if isinstance(self.revision_id, bool) or not isinstance(self.revision_id, int) or self.revision_id < 0:
            raise ValueError("revision_id must be a non-negative integer")
        if self.parent_revision_id is not None and (
            isinstance(self.parent_revision_id, bool)
            or not isinstance(self.parent_revision_id, int)
            or self.parent_revision_id < 0
            or self.parent_revision_id >= self.revision_id
        ):
            raise ValueError("parent_revision_id must be smaller than revision_id")
        if not isinstance(self.message, str) or not self.message.strip():
            raise ValueError("revision message must be a non-empty string")
        try:
            timestamp = datetime.fromisoformat(self.created_at.replace("Z", "+00:00"))
        except (AttributeError, ValueError) as exc:
            raise ValueError("revision created_at must be an ISO-8601 timestamp") from exc
        if timestamp.tzinfo is None or timestamp.utcoffset() != timezone.utc.utcoffset(timestamp):
            raise ValueError("revision created_at must be in UTC")
        raw_module_ids = tuple(self.changed_module_ids)
        if any(not isinstance(module_id, str) or not module_id.strip() for module_id in raw_module_ids):
            raise ValueError("changed_module_ids must contain non-empty strings")
        changed_module_ids = tuple(sorted(set(raw_module_ids)))
        raw_block_changes = tuple(self.block_changes)
        if any(not isinstance(change, BlockChange) for change in raw_block_changes):
            raise ValueError("block_changes must contain BlockChange values")
        block_changes = tuple(sorted(raw_block_changes, key=lambda item: (item.module_id, item.position)))
        try:
            snapshot = json.loads(self.snapshot_json)
            assembly = assembly_from_dict(snapshot)
        except (TypeError, json.JSONDecodeError, ValueError) as exc:
            raise ValueError(f"revision snapshot is invalid: {exc}") from exc
        object.__setattr__(self, "changed_module_ids", changed_module_ids)
        object.__setattr__(self, "block_changes", block_changes)
        object.__setattr__(self, "snapshot_json", _snapshot_json(assembly))

    @classmethod
    def create(
        cls,
        revision_id: int,
        parent_revision_id: int | None,
        message: str,
        changed_module_ids: tuple[str, ...],
        assembly: Assembly,
        *,
        block_changes: tuple[BlockChange, ...] = (),
        created_at: str | None = None,
    ) -> ProjectRevision:
        return cls(
            revision_id,
            parent_revision_id,
            created_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
            message,
            changed_module_ids,
            block_changes,
            _snapshot_json(assembly),
        )

    def restore_assembly(self) -> Assembly:
        """Return fresh module/model objects from this revision's snapshot."""

        return assembly_from_dict(json.loads(self.snapshot_json))

    def to_dict(self) -> dict[str, Any]:
        return {
            "revision_id": self.revision_id,
            "parent_revision_id": self.parent_revision_id,
            "created_at": self.created_at,
            "message": self.message,
            "changed_module_ids": list(self.changed_module_ids),
            "block_changes": [change.to_dict() for change in self.block_changes],
            "snapshot": json.loads(self.snapshot_json),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ProjectRevision:
        if not isinstance(data, Mapping):
            raise ValueError("project revision must be a JSON object")
        snapshot = data.get("snapshot")
        if not isinstance(snapshot, Mapping):
            raise ValueError("project revision snapshot must be an Assembly JSON object")
        changed_ids = data.get("changed_module_ids", [])
        raw_changes = data.get("block_changes", [])
        if not isinstance(changed_ids, (list, tuple)) or any(not isinstance(item, str) for item in changed_ids):
            raise ValueError("revision changed_module_ids must be a list of strings")
        if not isinstance(raw_changes, (list, tuple)):
            raise ValueError("revision block_changes must be a list")
        assembly = assembly_from_dict(snapshot)
        return cls(
            revision_id=data.get("revision_id"),
            parent_revision_id=data.get("parent_revision_id"),
            created_at=data.get("created_at"),
            message=data.get("message"),
            changed_module_ids=tuple(changed_ids),
            block_changes=tuple(BlockChange.from_dict(change) for change in raw_changes),
            snapshot_json=_snapshot_json(assembly),
        )


def diff_assemblies(before: Assembly, after: Assembly) -> tuple[tuple[str, ...], tuple[BlockChange, ...]]:
    """Return changed module IDs and the deterministic sparse block diff."""

    before_dict = assembly_to_dict(before)
    after_dict = assembly_to_dict(after)
    before_modules = {item["module_id"]: item for item in before_dict["modules"]}
    after_modules = {item["module_id"]: item for item in after_dict["modules"]}
    changed_ids = {
        module_id
        for module_id in before_modules.keys() | after_modules.keys()
        if before_modules.get(module_id) != after_modules.get(module_id)
    }

    connection_fields = ("first_module_id", "first_anchor", "second_module_id", "second_anchor")
    before_connections = Counter(
        tuple(connection[field] for field in connection_fields)
        for connection in before_dict["connections"]
    )
    after_connections = Counter(
        tuple(connection[field] for field in connection_fields)
        for connection in after_dict["connections"]
    )
    for connection in before_connections.keys() | after_connections.keys():
        if before_connections[connection] != after_connections[connection]:
            changed_ids.add(connection[0])
            changed_ids.add(connection[2])

    changes: list[BlockChange] = []
    for module_id in sorted(before_modules.keys() | after_modules.keys()):
        old_module = before.modules.get(module_id)
        new_module = after.modules.get(module_id)
        old_blocks = old_module.model.blocks if old_module is not None else {}
        new_blocks = new_module.model.blocks if new_module is not None else {}
        for position in sorted(old_blocks.keys() | new_blocks.keys()):
            old_state = old_blocks.get(position)
            new_state = new_blocks.get(position)
            if old_state != new_state:
                changes.append(
                    BlockChange(
                        module_id,
                        position,
                        old_state.to_string() if old_state is not None else None,
                        new_state.to_string() if new_state is not None else None,
                    )
                )
    return tuple(sorted(changed_ids)), tuple(changes)
