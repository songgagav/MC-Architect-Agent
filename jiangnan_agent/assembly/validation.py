"""Deterministic assembly checks and conflict-safe voxel rendering."""

from __future__ import annotations

from dataclasses import dataclass

from ..core.geometry import BoundingBox, Position
from ..core.scene import VoxelModel
from .model import Assembly, Connection, Module


@dataclass(frozen=True)
class ValidationIssue:
    """One actionable geometry or connection problem in an assembly."""

    code: str
    message: str
    module_ids: tuple[str, ...]
    position: Position | None = None
    count: int = 1


def _box_intersection(first: BoundingBox, second: BoundingBox) -> BoundingBox | None:
    min_x, min_y, min_z = max(first.min_x, second.min_x), max(first.min_y, second.min_y), max(first.min_z, second.min_z)
    max_x, max_y, max_z = min(first.max_x, second.max_x), min(first.max_y, second.max_y), min(first.max_z, second.max_z)
    if min_x >= max_x or min_y >= max_y or min_z >= max_z:
        return None
    return BoundingBox(min_x, min_y, min_z, max_x, max_y, max_z)


def _module_pair_issues(first: Module, second: Module) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    first_positions = set(first.model.blocks)
    second_positions = set(second.model.blocks)
    overlaps = first_positions & second_positions
    if overlaps:
        issues.append(
            ValidationIssue(
                "block_overlap",
                f"{len(overlaps)} occupied block position(s) overlap between {first.module_id} and {second.module_id}",
                (first.module_id, second.module_id),
                min(overlaps),
                len(overlaps),
            )
        )

    for zone in first.clearance_zones:
        hits = sorted(position for position in second_positions if zone.bounds.contains(position))
        if hits:
            issues.append(
                ValidationIssue(
                    "clearance_conflict",
                    f"{second.module_id} intersects {first.module_id} {zone.purpose} clearance {zone.name!r}",
                    (first.module_id, second.module_id),
                    hits[0],
                    len(hits),
                )
            )
    for zone in second.clearance_zones:
        hits = sorted(position for position in first_positions if zone.bounds.contains(position))
        if hits:
            issues.append(
                ValidationIssue(
                    "clearance_conflict",
                    f"{first.module_id} intersects {second.module_id} {zone.purpose} clearance {zone.name!r}",
                    (first.module_id, second.module_id),
                    hits[0],
                    len(hits),
                )
            )
    for first_zone in first.clearance_zones:
        for second_zone in second.clearance_zones:
            overlap = _box_intersection(first_zone.bounds, second_zone.bounds)
            if overlap is not None:
                issues.append(
                    ValidationIssue(
                        "clearance_conflict",
                        f"{first.module_id} {first_zone.purpose} clearance {first_zone.name!r} overlaps "
                        f"{second.module_id} {second_zone.purpose} clearance {second_zone.name!r}",
                        (first.module_id, second.module_id),
                        (overlap.min_x, overlap.min_y, overlap.min_z),
                        1,
                    )
                )
    return issues


def _connection_issues(assembly: Assembly, connection: Connection) -> list[ValidationIssue]:
    first = assembly.modules.get(connection.first_module_id)
    second = assembly.modules.get(connection.second_module_id)
    ids = (connection.first_module_id, connection.second_module_id)
    if first is None or second is None:
        missing = [module_id for module_id, module in zip(ids, (first, second)) if module is None]
        return [
            ValidationIssue("missing_module", f"connection references missing module {module_id!r}", ids)
            for module_id in missing
        ]

    issues: list[ValidationIssue] = []
    try:
        first_anchor = first.anchor(connection.first_anchor)
    except KeyError:
        issues.append(
            ValidationIssue(
                "missing_anchor",
                f"{first.module_id} has no anchor {connection.first_anchor!r}",
                ids,
            )
        )
        first_anchor = None
    try:
        second_anchor = second.anchor(connection.second_anchor)
    except KeyError:
        issues.append(
            ValidationIssue(
                "missing_anchor",
                f"{second.module_id} has no anchor {connection.second_anchor!r}",
                ids,
            )
        )
        second_anchor = None
    if first_anchor is None or second_anchor is None:
        return issues

    if first_anchor.connection_type != second_anchor.connection_type:
        issues.append(ValidationIssue("connection_type_mismatch", "connected anchors have different types", ids))
    if (first_anchor.width, first_anchor.height) != (second_anchor.width, second_anchor.height):
        issues.append(ValidationIssue("opening_size_mismatch", "connected openings have different dimensions", ids))
    if first_anchor.position[1] != second_anchor.position[1]:
        issues.append(
            ValidationIssue(
                "height_mismatch",
                f"connected anchors differ in height by {second_anchor.position[1] - first_anchor.position[1]} block(s)",
                ids,
                first_anchor.position,
            )
        )
    if first_anchor.position != second_anchor.position:
        issues.append(
            ValidationIssue(
                "anchor_misalignment",
                "connected anchor positions do not coincide",
                ids,
                first_anchor.position,
            )
        )
    opposite = {"north": "south", "east": "west", "south": "north", "west": "east"}
    if first_anchor.facing != opposite[second_anchor.facing]:
        issues.append(ValidationIssue("anchor_facing_mismatch", "connected anchors do not face each other", ids))
    return issues


def validate_assembly(assembly: Assembly) -> tuple[ValidationIssue, ...]:
    """Report collisions, clearance conflicts, and invalid connection edges."""

    issues: list[ValidationIssue] = []
    modules = [assembly.modules[module_id] for module_id in sorted(assembly.modules)]
    for index, first in enumerate(modules):
        for second in modules[index + 1 :]:
            issues.extend(_module_pair_issues(first, second))
    for connection in assembly.connections:
        issues.extend(_connection_issues(assembly, connection))
    return tuple(
        sorted(
            issues,
            key=lambda issue: (
                issue.module_ids,
                issue.code,
                issue.position if issue.position is not None else (-1, -1, -1),
                issue.message,
            ),
        )
    )


def render_assembly(assembly: Assembly) -> VoxelModel:
    """Merge module voxels by stable ID without mutating source module models."""

    rendered = VoxelModel()
    owners: dict[Position, str] = {}
    for module_id in sorted(assembly.modules):
        module = assembly.modules[module_id]
        for position, state in sorted(module.model.blocks.items()):
            previous = rendered.block_at(position)
            if previous != state and position in owners:
                raise ValueError(
                    f"conflicting blocks at {position}: {owners[position]} has {previous.to_string()}, "
                    f"{module_id} has {state.to_string()}"
                )
            rendered.set_block(position, state)
            owners.setdefault(position, module_id)
    return rendered
