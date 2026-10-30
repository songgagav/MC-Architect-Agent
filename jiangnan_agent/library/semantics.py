"""Deterministic, read-only semantic geometry helpers for Litematic regions."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence

from .models import ComponentSummary, CoordinateRun, LitematicRegion, Position3, SEMANTIC_COMPONENT_TYPES


_GEOMETRY_TYPES = frozenset({"region", "box", "block_set"})


def _position(value: object, field: str) -> Position3:
    if (
        not isinstance(value, (list, tuple))
        or len(value) != 3
        or any(isinstance(axis, bool) or not isinstance(axis, int) for axis in value)
    ):
        raise ValueError(f"{field} must contain exactly three integer coordinates")
    return tuple(int(axis) for axis in value)  # type: ignore[return-value]


def _region_bounds(region: LitematicRegion) -> tuple[Position3, Position3]:
    """Return the region's half-open global bounds, including negative sizes."""
    lower: list[int] = []
    upper: list[int] = []
    for position, signed_size in zip(region.position, region.signed_size):
        if signed_size > 0:
            lower.append(position)
            upper.append(position + signed_size)
        else:
            lower.append(position + signed_size + 1)
            upper.append(position + 1)
    return tuple(lower), tuple(upper)  # type: ignore[return-value]


def _inside(position: Position3, bounds: tuple[Position3, Position3]) -> bool:
    lower, upper = bounds
    return all(lower[axis] <= position[axis] < upper[axis] for axis in range(3))


def normalize_annotation_geometry(
    region: LitematicRegion,
    kind: str,
    geometry: Mapping[str, object],
) -> dict[str, object]:
    """Validate an annotation selector and return its canonical JSON-compatible form.

    Coordinates refer to absolute Litematica source positions. Boxes use inclusive
    minima and exclusive maxima. Exact sets may contain occupied positions only.
    """
    if kind not in _GEOMETRY_TYPES:
        raise ValueError(f"unsupported annotation geometry type: {kind!r}")
    if not isinstance(geometry, Mapping):
        raise ValueError("annotation geometry must be an object")
    bounds = _region_bounds(region)

    if kind == "region":
        if geometry not in ({}, {"region_name": region.name}):
            raise ValueError("region geometry must be empty or name the selected region")
        return {"region_name": region.name}

    if kind == "box":
        if set(geometry) != {"min", "max"}:
            raise ValueError("box geometry requires exactly 'min' and 'max'")
        lower = _position(geometry["min"], "box.min")
        upper = _position(geometry["max"], "box.max")
        if any(lower[axis] >= upper[axis] for axis in range(3)):
            raise ValueError("box must be non-empty on every axis")
        if not _inside(lower, bounds) or any(upper[axis] > bounds[1][axis] for axis in range(3)):
            raise ValueError("box bounds are outside the selected region")
        return {"min": list(lower), "max": list(upper)}

    if set(geometry) == {"runs"}:
        positions = list(decode_x_runs(geometry["runs"], max_positions=region.volume))  # type: ignore[arg-type]
    elif set(geometry) == {"positions"}:
        raw_positions = geometry["positions"]
        if not isinstance(raw_positions, (list, tuple)) or not raw_positions:
            raise ValueError("block_set positions must be a non-empty list")
        positions = []
        seen: set[Position3] = set()
        for index, value in enumerate(raw_positions):
            position = _position(value, f"positions[{index}]")
            if position in seen:
                raise ValueError(f"duplicate block_set coordinate: {position}")
            seen.add(position)
            positions.append(position)
    else:
        raise ValueError("block_set geometry requires exactly 'positions' or canonical 'runs'")
    occupied = {position for position, _ in region.iter_non_air_blocks()}
    for position in positions:
        if not _inside(position, bounds):
            raise ValueError(f"block_set coordinate {position} is outside the selected region")
        if position not in occupied:
            raise ValueError(f"block_set coordinate {position} does not contain an occupied block")
    return {"runs": [list(run) for run in encode_x_runs(positions)]}


def encode_x_runs(positions: Iterable[Position3]) -> tuple[CoordinateRun, ...]:
    """Encode positions as sorted, coalesced `[y,z,x_start,x_end)` runs."""
    unique: set[Position3] = set()
    for index, raw in enumerate(positions):
        position = _position(raw, f"positions[{index}]")
        if position in unique:
            raise ValueError(f"duplicate coordinate: {position}")
        unique.add(position)
    ordered = sorted(unique, key=lambda p: (p[1], p[2], p[0]))
    result: list[CoordinateRun] = []
    for x, y, z in ordered:
        if result and result[-1][0] == y and result[-1][1] == z and result[-1][3] == x:
            previous = result[-1]
            result[-1] = (y, z, previous[2], x + 1)
        else:
            result.append((y, z, x, x + 1))
    return tuple(result)


def decode_x_runs(
    runs: Iterable[Sequence[int]], *, max_positions: int | None = None
) -> tuple[Position3, ...]:
    """Decode canonical X runs, rejecting malformed or overlapping rows."""
    if isinstance(runs, (str, bytes)) or not isinstance(runs, Iterable):
        raise ValueError("X runs must be a sequence of four-integer rows")
    if max_positions is not None and (
        isinstance(max_positions, bool) or not isinstance(max_positions, int) or max_positions < 0
    ):
        raise ValueError("max_positions must be a non-negative integer")
    result: list[Position3] = []
    previous: CoordinateRun | None = None
    position_count = 0
    for index, raw in enumerate(runs):
        if (
            not isinstance(raw, (list, tuple))
            or len(raw) != 4
            or any(isinstance(value, bool) or not isinstance(value, int) for value in raw)
        ):
            raise ValueError(f"runs[{index}] must contain four integers")
        run: CoordinateRun = tuple(int(value) for value in raw)  # type: ignore[assignment]
        y, z, start, end = run
        if start >= end:
            raise ValueError(f"runs[{index}] must have a non-empty X interval")
        if previous is not None:
            if (y, z) < (previous[0], previous[1]) or (
                y == previous[0] and z == previous[1] and start <= previous[3]
            ):
                raise ValueError("X runs must be sorted, disjoint, and coalesced")
        position_count += end - start
        if max_positions is not None and position_count > max_positions:
            raise ValueError(f"X runs expand beyond the allowed {max_positions} positions")
        result.extend((x, y, z) for x in range(start, end))
        previous = run
    return tuple(result)


def _selected(
    position: Position3,
    geometry_type: str,
    geometry: Mapping[str, object],
) -> bool:
    if geometry_type == "region":
        return True
    if geometry_type == "box":
        lower = tuple(geometry["min"])  # normalized by caller
        upper = tuple(geometry["max"])
        return all(lower[axis] <= position[axis] < upper[axis] for axis in range(3))
    raise ValueError(f"unsupported annotation geometry type: {geometry_type!r}")


def summarize_annotation(
    region: LitematicRegion,
    component_type: str,
    geometry_type: str,
    geometry: Mapping[str, object],
) -> ComponentSummary:
    """Derive deterministic block, material, layer, and local coordinate metrics."""
    if component_type not in SEMANTIC_COMPONENT_TYPES:
        raise ValueError(f"unsupported semantic component type: {component_type!r}")
    normalized = normalize_annotation_geometry(region, geometry_type, geometry)
    selected_positions = (
        set(decode_x_runs(normalized["runs"]))
        if geometry_type == "block_set"
        else None
    )
    block_states: Counter[str] = Counter()
    material_counts: Counter[str] = Counter()
    absolute_layer_counts: dict[int, Counter[str]] = defaultdict(Counter)
    positions: list[Position3] = []
    for position, state in region.iter_non_air_blocks():
        included = (
            position in selected_positions
            if selected_positions is not None
            else _selected(position, geometry_type, normalized)
        )
        if not included:
            continue
        state_key = state.to_string()
        block_states[state_key] += 1
        material_counts[state.name] += 1
        absolute_layer_counts[position[1]][state_key] += 1
        positions.append(position)
    if not positions:
        raise ValueError("annotation geometry contains no occupied blocks")

    minimum = tuple(min(position[axis] for position in positions) for axis in range(3))
    maximum = tuple(max(position[axis] for position in positions) + 1 for axis in range(3))
    relative_positions = [tuple(position[axis] - minimum[axis] for axis in range(3)) for position in positions]
    layers = {
        y - minimum[1]: dict(sorted(counts.items()))
        for y, counts in sorted(absolute_layer_counts.items())
    }
    return ComponentSummary(
        region_name=region.name,
        component_type=component_type,
        local_origin=minimum,  # type: ignore[arg-type]
        dimensions=tuple(maximum[axis] - minimum[axis] for axis in range(3)),  # type: ignore[arg-type]
        bounding_box=(minimum, maximum),  # type: ignore[arg-type]
        block_count=len(positions),
        block_states=dict(sorted(block_states.items())),
        materials=dict(sorted(material_counts.items())),
        layer_materials=layers,
        coordinate_runs=encode_x_runs(relative_positions),
    )
