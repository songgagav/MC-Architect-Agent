# Phase 2 Parametric Components Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add reusable Minecraft building component generators and parameterized hall/corridor assemblies while preserving the existing schematic workflow.

**Architecture:** Pure generators create sparse `VoxelModel` fragments from integer coordinates and block states. `HallParameters` and `CorridorParameters` validate structural dimensions and compose those fragments. The CLI routes `building.type = "hall"` through the existing Sponge v3 writer; `simple_house` remains compatible.

**Tech Stack:** Python 3.12, dataclasses, pytest, existing `BlockState`, `BoundingBox`, `VoxelModel`, and Sponge v3 IO.

**Spec:** `docs/superpowers/specs/2026-10-29-phase2-parametric-components-design.md`; project-wide scope in `docs/roadmap.md`.

## Global Constraints

- Target Minecraft Java 1.21.5 and DataVersion 4325.
- Keep X as hall width, Y as vertical, and Z as hall depth; hall front is positive Z and ridge runs along X.
- Preserve the existing simple-house CLI input and Sponge v3 file format.
- Do not write generated content into a Minecraft save.
- Use `Template/芳堂-茯茯角.litematic` and `Template/流苏坊框架-茯茯角.litematic` only as material/component references; their DataVersion is 3465, while generated output remains 4325.
- Validate `BlockState` syntax and generator-created known states; a complete versioned registry for arbitrary Minecraft states is out of Phase 2 scope.
- Do not commit or push automatically; the user requested the initial Phase 0–1 upload only.

## Review Focus

- Invalid sizes, non-axis-aligned beams, out-of-wall openings, unknown material roles, and syntactically invalid states fail with clear `ValueError`; cover in `tests/test_components.py` and `tests/test_hall.py`.
- Door width 1/2 emits lower and upper states with correct facing/hinge; panes keep explicit waterlogging and connected faces; cover in `tests/test_components.py`.
- Roof rows cover the full overhanging width without gaps and never rise more than one block per depth row; cover in `tests/test_components.py` and `tests/test_hall.py`.
- Three/five-bay halls preserve front door and window openings, place columns under continuous beams, and generate deterministically; cover in `tests/test_hall.py`.
- CLI output round-trips through the existing Sponge reader with matching dimensions and block states; cover in `tests/test_cli.py`.

---

### Task 1: Reusable component generators

**Files:**
- Create: `jiangnan_agent/generators/components.py`
- Test: `tests/test_components.py`

**Interfaces:**
- Consumes: `BlockState`, `Position`, `BoundingBox`, `VoxelModel`.
- Produces: `generate_column(x, base_y, z, height, material)`, `generate_beam(start, end, material)`, `generate_wall(bounds, material, openings=())`, `generate_plinth(bounds, material)`, `generate_door(x, base_y, z, width, material, facing="south")`, `generate_window(x, y, z, width, height, material, connected_faces=())`, `generate_eaves(start, end, material, overhang=0)`, and `generate_gable_roof(width, depth, base_y, rise, eaves, material)`; each returns `VoxelModel`.

- [ ] Write failing tests for inclusive straight beams, wood axis states, walls with bounded rectangular openings, filled plinths, one/two-wide door states, connected glass panes, axis-aligned eaves, symmetric gable rows, and invalid geometry/material input.
- [ ] Run `\.venv\Scripts\python.exe -m pytest tests\test_components.py -q`; expect import/attribute failure because `components.py` does not exist.
- [ ] Implement the listed pure generators. Use X as a beam's `axis=x`, Z as `axis=z`, and set wood-log/wood/stem/hyphae axes only on block IDs that support the `axis` property. Gable depth must be odd and at least 3, and rise must be from 1 through `(depth - 1) // 2`.
- [ ] Re-run the targeted test; expect every component assertion to pass.

### Task 2: Parameterized hall and straight corridor

**Files:**
- Create: `jiangnan_agent/generators/hall.py`
- Modify: `jiangnan_agent/generators/__init__.py`
- Test: `tests/test_hall.py`

**Interfaces:**
- Consumes: all Task 1 component functions.
- Produces: frozen `HallParameters` and `CorridorParameters` dataclasses, plus `generate_hall(parameters=None)` and `generate_corridor(parameters=None)` returning `VoxelModel`.

- [ ] Write failing tests for 3- and 5-bay dimensions, center two-block doors, flank windows, post/beam continuity, continuous roof rows, deterministic output, material overrides, invalid hall dimensions, and a repeated two-sided corridor post/roof layout.
- [ ] Run `\.venv\Scripts\python.exe -m pytest tests\test_hall.py -q`; expect import/attribute failure because `hall.py` does not exist.
- [ ] Implement parameter validation and composition. Hall defaults: 3 bays, 5 blocks per bay, depth 7, column height 4, plinth 1, roof rise 3, eaves 1, and double door width 2. Corridor defaults: length 11, width 3, spacing 3, column height 3, roof rise 1, and eaves 1. Use template-derived material examples (spruce timber, stone/deepslate roof pieces and calcite walls); reject even/<3 bay counts, bay widths too narrow for the door and side wall, even/<5 depths, column heights below 3, plinths below 1, negative eaves, and roof rise above the half-depth limit.
- [ ] Re-run the targeted test; expect all assembly and validation assertions to pass.

### Task 3: CLI, examples, and Phase 2 documentation

**Files:**
- Modify: `jiangnan_agent/cli.py`
- Modify: `tests/test_cli.py`
- Modify: `README.md`, `docs/roadmap.md`
- Create: `examples/three_bay_hall.jap.json`

**Interfaces:**
- Consumes: `HallParameters` and `generate_hall` from Task 2.
- Produces: `jiangnan generate` support for project settings with `building.type = "hall"`, while keeping `simple_house` as the default and preserving its existing options.

- [ ] Add a failing CLI test that loads a hall JSON, generates `.schem`, re-reads it with `read_schematic`, and compares block count and dimensions to `generate_hall`.
- [ ] Run `\.venv\Scripts\python.exe -m pytest tests\test_cli.py::test_generate_hall_writes_readable_schematic -q`; expect failure because the CLI rejects the `hall` type.
- [ ] Add the hall routing, a 3-bay sample, README command/parameter documentation, and accurate Phase 2 status in the roadmap. Do not claim in-game or architectural-source validation.
- [ ] Run the CLI test and expect the Sponge v3 dimensions, name, and block count to match the in-memory model.
- [ ] Run `\.venv\Scripts\python.exe -m pytest`; expect all existing and Phase 2 tests to pass.

## Plan Self-Review

- Coverage: standalone pillars, beams, walls/openings, doors, windows, plinths, eaves, roofs, straight corridors, 3/5-bay halls, material overrides, CLI generation, and schematic readback each have an owning task and tests.
- Interfaces: Task 2 consumes exactly the eight `components.py` functions declared by Task 1; Task 3 consumes the hall dataclass and generator declared by Task 2.
- Deferred items: modular anchors/collision checks, historical edits, reference-backed construction rules, AI, and Blender rendering remain in later phases.
- No implementation commits or remote pushes are included in this plan.
