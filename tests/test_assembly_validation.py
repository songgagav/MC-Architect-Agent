from __future__ import annotations

from jiangnan_agent.assembly.model import (
    Assembly,
    ClearanceZone,
    Connection,
    ConnectionAnchor,
    Module,
)
from jiangnan_agent.assembly.validation import validate_assembly
from jiangnan_agent.core.geometry import BoundingBox
from jiangnan_agent.core.scene import VoxelModel


def module(
    module_id: str,
    block_position: tuple[int, int, int],
    block: str,
    anchors: tuple[ConnectionAnchor, ...] = (),
    clearances: tuple[ClearanceZone, ...] = (),
) -> Module:
    model = VoxelModel()
    model.set_block(block_position, block)
    return Module(module_id, "room", model, anchors, clearances)


def test_validation_reports_exact_block_overlap() -> None:
    assembly = Assembly(
        (
            module("hall", (0, 0, 0), "minecraft:stone"),
            module("wing", (0, 0, 0), "minecraft:oak_planks"),
        )
    )

    issues = validate_assembly(assembly)

    assert [(issue.code, issue.module_ids, issue.position, issue.count) for issue in issues] == [
        ("block_overlap", ("hall", "wing"), (0, 0, 0), 1)
    ]


def test_validation_reports_connection_opening_height_facing_and_position() -> None:
    first = ConnectionAnchor("front", (1, 1, 1), "south", "doorway", 2, 3)
    second = ConnectionAnchor("entry", (2, 2, 1), "south", "passage", 1, 3)
    assembly = Assembly(
        (
            module("hall", (0, 0, 0), "minecraft:stone", (first,)),
            module("gallery", (3, 0, 0), "minecraft:stone", (second,)),
        ),
        (Connection("hall", "front", "gallery", "entry"),),
    )

    issues = validate_assembly(assembly)

    assert {issue.code for issue in issues} == {
        "connection_type_mismatch",
        "opening_size_mismatch",
        "height_mismatch",
        "anchor_misalignment",
        "anchor_facing_mismatch",
    }


def test_validation_reports_stale_connection_endpoints() -> None:
    front = ConnectionAnchor("front", (0, 0, 1), "south", "passage")
    hall = module("hall", (0, 0, 0), "minecraft:stone", (front,))
    assembly = Assembly((hall,), (Connection("hall", "front", "missing", "rear"),))

    issues = validate_assembly(assembly)

    assert [(issue.code, issue.module_ids) for issue in issues] == [
        ("missing_module", ("hall", "missing"))
    ]


def test_validation_reports_missing_named_anchor() -> None:
    hall = module("hall", (0, 0, 0), "minecraft:stone")
    gallery = module("gallery", (2, 0, 0), "minecraft:stone")
    assembly = Assembly((hall, gallery), (Connection("hall", "front", "gallery", "rear"),))

    issues = validate_assembly(assembly)

    assert [(issue.code, issue.message) for issue in issues] == [
        ("missing_anchor", "gallery has no anchor 'rear'"),
        ("missing_anchor", "hall has no anchor 'front'"),
    ]


def test_validation_reports_eaves_clearance_against_blocks_and_other_zones() -> None:
    eaves = ClearanceZone("eaves", BoundingBox(0, 2, 0, 3, 4, 3), "eaves")
    annex_zone = ClearanceZone("roof", BoundingBox(2, 3, 2, 4, 5, 4), "eaves")
    first = module("hall", (0, 0, 0), "minecraft:stone", clearances=(eaves,))
    second = module("wing", (2, 3, 2), "minecraft:oak_planks", clearances=(annex_zone,))

    issues = validate_assembly(Assembly((first, second)))

    assert len(issues) == 2
    assert all(issue.code == "clearance_conflict" for issue in issues)
    assert {issue.position for issue in issues} == {(2, 3, 2)}
