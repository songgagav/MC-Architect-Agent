"""Build and export a two-courtyard hall-and-gallery assembly example."""

from __future__ import annotations

from pathlib import Path

from jiangnan_agent.assembly.adapters import corridor_module, hall_module
from jiangnan_agent.assembly.model import Assembly, ConnectionAnchor, Module
from jiangnan_agent.assembly.operations import connect_modules, replace_module
from jiangnan_agent.assembly.validation import render_assembly, validate_assembly
from jiangnan_agent.core.block import BlockState
from jiangnan_agent.core.geometry import BoundingBox
from jiangnan_agent.core.scene import VoxelModel
from jiangnan_agent.generators.components import generate_wall
from jiangnan_agent.generators.hall import CorridorParameters, HallParameters
from jiangnan_agent.io.schematic import write_schematic


def build_two_courtyard() -> Assembly:
    """Compose three halls with two independently generated straight galleries."""

    hall_parameters = HallParameters(
        bay_count=3,
        bay_width=5,
        depth=7,
        column_height=4,
        plinth_height=1,
        roof_rise=3,
        eaves=1,
        door_width=2,
    )
    corridor_parameters = CorridorParameters(
        length=11,
        width=5,
        column_spacing=3,
        column_height=2,
        roof_rise=1,
        eaves=1,
    )
    front_hall = hall_module("front_hall", hall_parameters)
    front_walk = corridor_module("walk_front", corridor_parameters, passage_width=2)
    gate_hall = hall_module("gate_hall", hall_parameters, through_passage=True)
    rear_walk = corridor_module("walk_rear", corridor_parameters, passage_width=2)
    rear_hall = hall_module("rear_hall", hall_parameters)

    assembly = connect_modules(Assembly((front_hall,)), "front_hall", "front", front_walk, "start")
    assembly = connect_modules(assembly, "walk_front", "end", gate_hall, "front")
    assembly = connect_modules(assembly, "gate_hall", "rear", rear_walk, "start")
    assembly = connect_modules(assembly, "walk_rear", "end", rear_hall, "front")

    walls: list[Module] = []
    court_edges = (
        ("front_court", "front_hall", "gate_hall"),
        ("rear_court", "gate_hall", "rear_hall"),
    )
    for court_name, north_id, south_id in court_edges:
        north = assembly.modules[north_id].model.bounds
        south = assembly.modules[south_id].model.bounds
        for side, x in (("west", north.min_x), ("east", north.max_x)):
            wall = generate_wall(
                BoundingBox(x, 0, north.max_z, x + 1, 5, south.min_z),
                "minecraft:calcite",
            )
            anchors = (
                ConnectionAnchor("north", (x, 0, north.max_z), "north", "courtyard_edge", 1, 5),
                ConnectionAnchor("south", (x, 0, south.min_z), "south", "courtyard_edge", 1, 5),
            )
            walls.append(Module(f"{court_name}_{side}_wall", "courtyard_wall", wall, anchors))
    assembly = Assembly((*assembly.modules.values(), *walls), assembly.connections)
    for court_name, north_id, south_id in court_edges:
        for side in ("west", "east"):
            wall_id = f"{court_name}_{side}_wall"
            x = assembly.modules[wall_id].anchor("north").position[0]
            north_z = assembly.modules[wall_id].anchor("north").position[2]
            south_z = assembly.modules[wall_id].anchor("south").position[2]
            north_anchor = next(
                anchor.name
                for anchor in assembly.modules[north_id].anchors
                if anchor.position == (x, 0, north_z) and anchor.connection_type == "courtyard_edge"
            )
            south_anchor = next(
                anchor.name
                for anchor in assembly.modules[south_id].anchors
                if anchor.position == (x, 0, south_z) and anchor.connection_type == "courtyard_edge"
            )
            assembly = connect_modules(assembly, north_id, north_anchor, wall_id, "north")
            assembly = connect_modules(assembly, wall_id, "south", south_id, south_anchor)
    return assembly


def replace_corridor_roof(assembly: Assembly, module_id: str, roof_block_id: str) -> Assembly:
    """Replace one corridor roof material while keeping its placement and anchors."""

    if module_id not in assembly.modules:
        raise ValueError(f"unknown module ID: {module_id!r}")
    current = assembly.modules[module_id]
    if current.kind != "corridor":
        raise ValueError(f"module {module_id!r} is not a corridor")
    roof_state = BlockState.parse(roof_block_id)
    if not roof_state.block_id.endswith("_stairs"):
        raise ValueError("corridor roof replacement must be a stair block")

    model = VoxelModel()
    for position, state in current.model.blocks.items():
        model.set_block(
            position,
            BlockState(roof_state.block_id, state.properties)
            if state.block_id.endswith("_stairs")
            else state,
        )
    replacement = Module(
        module_id,
        current.kind,
        model,
        current.anchors,
        current.clearance_zones,
    )
    return replace_module(assembly, module_id, replacement)


def main() -> int:
    assembly = build_two_courtyard()
    issues = validate_assembly(assembly)
    if issues:
        for issue in issues:
            print(f"{issue.code}: {issue.message}")
        return 2
    output = write_schematic(
        render_assembly(assembly),
        Path("workspace") / "exports" / "two_courtyard.schem",
        data_version=4325,
        name="Jiangnan Two Courtyard",
    )
    print(f"已生成: {output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
