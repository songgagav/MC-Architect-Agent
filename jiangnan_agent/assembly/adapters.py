"""Explicit metadata adapters for Phase 2 hall and corridor generators."""

from __future__ import annotations

from dataclasses import asdict, fields
from collections.abc import Mapping

from ..core.block import BlockState
from ..core.geometry import BoundingBox
from ..core.scene import AIR
from ..generators.components import generate_door
from ..generators.facade_profiles import facade_profile_to_mapping
from ..generators.hall import (
    CorridorParameters,
    DEFAULT_CORRIDOR_MATERIALS,
    DEFAULT_HALL_MATERIALS,
    HallParameters,
    generate_corridor,
    generate_hall,
    resolve_hall_primary_entry,
)
from ..generators.roof_profiles import MaterialPalette
from .model import ClearanceZone, ConnectionAnchor, Module

_OPPOSITE = {"north": "south", "east": "west", "south": "north", "west": "east"}


def _parameters_dict(parameters, defaults: Mapping[str, str]) -> dict[str, object]:
    values: dict[str, object] = {}
    for item in fields(parameters):
        if item.name.startswith("_"):
            continue
        value = getattr(parameters, item.name)
        if item.name == "materials":
            if parameters.facade_profile is not None:
                if value is None:
                    continue
                values[item.name] = dict(value)
                continue
            materials = dict(defaults)
            materials.update(value or {})
            if parameters.material_palette is not None:
                materials.pop("roof", None)
                materials.pop("eaves", None)
            values[item.name] = materials
        elif (
            item.name == "door_width"
            and parameters.facade_profile is not None
            and not parameters._door_width_explicit
        ):
            continue
        elif item.name == "facade_profile":
            if value is not None:
                values[item.name] = facade_profile_to_mapping(value)
        elif item.name in {"roof_profile", "eave_profile", "ridge_profile", "material_palette"}:
            if value is None:
                continue
            values[item.name] = dict(value.roles) if isinstance(value, MaterialPalette) else asdict(value)
        elif item.name == "roof_rise" and parameters.roof_profile is not None and not parameters._roof_rise_explicit:
            continue
        elif item.name == "eaves" and parameters.eave_profile is not None and not parameters._eaves_explicit:
            continue
        else:
            values[item.name] = value
    return values


def _roof_clearance(module_id: str, model) -> tuple[ClearanceZone, ...]:
    bounds = model.bounds
    if not model.blocks:
        return ()
    top = bounds.max_y - 1
    return (
        ClearanceZone(
            f"{module_id}-roof-eaves",
            BoundingBox(bounds.min_x, top, bounds.min_z, bounds.max_x, top + 2, bounds.max_z),
            "eaves",
        ),
    )


def hall_module(
    module_id: str,
    parameters: HallParameters | None = None,
    *,
    through_passage: bool = False,
) -> Module:
    """Wrap a generated hall with explicit front, and optional rear, door anchors."""

    parameters = parameters or HallParameters()
    if parameters.facade_profile is not None:
        model = generate_hall(parameters, through_passage=through_passage)
        primary_bounds = resolve_hall_primary_entry(parameters)
        door_x = primary_bounds.min_x
        door_y = primary_bounds.min_y
        door_width = primary_bounds.size[0]
        opening_height = primary_bounds.size[1]
        front_z = primary_bounds.min_z
    else:
        model = generate_hall(parameters)
        door_width = parameters.door_width
        door_x = (
            parameters.bay_count // 2 * parameters.bay_width
            + 1
            + (parameters.bay_width - 1 - door_width) // 2
        )
        door_y = parameters.plinth_height + 1
        opening_height = 2
        front_z = parameters.depth - 1
    x_positions = list(range(door_x, door_x + door_width))
    center_x = door_x + door_width // 2
    front_facing = "south"
    anchors = [
        ConnectionAnchor(
            "front",
            (center_x, door_y, front_z + 1),
            front_facing,
            "passage",
            door_width,
            opening_height,
        )
    ]
    bounds = model.bounds
    for edge, x in (
        ("west", bounds.min_x),
        ("east", bounds.max_x),
    ):
        anchors.extend(
            (
                ConnectionAnchor(f"court_{edge}_front", (x, 0, bounds.max_z), "south", "courtyard_edge", 1, 5),
                ConnectionAnchor(f"court_{edge}_rear", (x, 0, bounds.min_z), "north", "courtyard_edge", 1, 5),
            )
        )

    if through_passage:
        back_z = 0
        if parameters.facade_profile is None:
            for x in x_positions:
                for y in range(door_y, door_y + opening_height):
                    model.set_block((x, y, back_z), AIR)
            door_material = (parameters.materials or {}).get("door", DEFAULT_HALL_MATERIALS["door"])
            rear_model = generate_door(
                door_x,
                door_y,
                back_z,
                door_width,
                door_material,
                _OPPOSITE[front_facing],
            )
            for position, state in rear_model.blocks.items():
                model.set_block(position, state)
        anchors.append(
            ConnectionAnchor(
                "rear",
                (center_x, door_y, back_z - 1 if _OPPOSITE[front_facing] == "north" else back_z + 1),
                _OPPOSITE[front_facing],
                "passage",
                door_width,
                opening_height,
            )
        )

    saved_parameters = _parameters_dict(parameters, DEFAULT_HALL_MATERIALS)
    saved_parameters["through_passage"] = through_passage
    return Module(
        module_id,
        "hall",
        model,
        tuple(anchors),
        _roof_clearance(module_id, model),
        parameters=saved_parameters,
    )


def corridor_module(
    module_id: str,
    parameters: CorridorParameters | None = None,
    *,
    passage_width: int | None = None,
) -> Module:
    """Wrap a generated straight corridor with west/east passage anchors."""

    parameters = parameters or CorridorParameters()
    model = generate_corridor(parameters)
    bounds = model.bounds
    center_z = parameters.width // 2
    clear_width = max(1, parameters.width - 2)
    passage_width = clear_width if passage_width is None else passage_width
    if isinstance(passage_width, bool) or not isinstance(passage_width, int) or not 1 <= passage_width <= clear_width:
        raise ValueError(f"passage_width must be an integer between 1 and {clear_width}")
    anchor_y = 2
    anchors = (
        ConnectionAnchor("start", (bounds.min_x - 1, anchor_y, center_z), "west", "passage", passage_width, 2),
        ConnectionAnchor("end", (bounds.max_x, anchor_y, center_z), "east", "passage", passage_width, 2),
    )
    top = bounds.max_y - 1
    end_margin = min(2, max(0, (bounds.size[0] - 1) // 2))
    clearances = (
        ClearanceZone(
            f"{module_id}-roof-eaves",
            BoundingBox(
                bounds.min_x + end_margin,
                top,
                bounds.min_z,
                bounds.max_x - end_margin,
                top + 2,
                bounds.max_z,
            ),
            "eaves",
        ),
    )
    saved_parameters = _parameters_dict(parameters, DEFAULT_CORRIDOR_MATERIALS)
    saved_parameters["passage_width"] = passage_width
    return Module(
        module_id,
        "corridor",
        model,
        anchors,
        clearances,
        parameters=saved_parameters,
    )
