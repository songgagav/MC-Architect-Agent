# Phase 3 Modular Assembly Implementation Plan

> **For agentic workers:** Use the executing-plans workflow and complete each task with a red-green test cycle.

**Goal:** Compose the Phase 2 building models as independently editable modules with anchors, transforms, connections, split/replace operations, and actionable validation.

**Architecture:** `Module` owns a sparse model, typed connection anchors, and clearance volumes. `Assembly` retains modules and connection edges. Pure transform helpers update geometry and metadata together; connection and validation functions operate on the graph; rendering creates a deterministic merged `VoxelModel` only at export time.

**Tech Stack:** Python 3.12 dataclasses, existing `BlockState`, `BoundingBox`, `VoxelModel`, `rotate_model_y`, pytest, and Sponge v3 IO.

**Spec:** `docs/superpowers/specs/2026-10-29-phase3-modular-assembly-design.md`; phase goals in `docs/roadmap.md`.

## Global Constraints

- Keep Minecraft Java 1.21.5 / DataVersion 4325 and the established X/Y/Z convention.
- Keep modules independently addressable until explicit render/export.
- Treat anchors as exact integer connection planes; do not silently bridge vertical offsets.
- Never write output into an existing Minecraft world.
- Keep project persistence/history out of this phase; those belong to Phase 4.
- Use explicit adapter metadata for openings and clearances; do not infer architectural facts from arbitrary block names.
- Do not commit or push Phase 3 changes unless the user asks.

## Review Focus

- Transform all anchor positions and clearance boxes with the same pivot/extents as their block model.
- Mirror facing, rail-direction properties, stair handedness, door hinge, and 16-way rotation consistently.
- Reject duplicate IDs, missing anchors, mismatched types or opening dimensions, non-opposed facings, and height offsets without partially changing an assembly.
- Report collisions deterministically and avoid mutating source modules during rendering or replacement.
- Keep `split_assembly` output stable regardless of insertion order.

---

### Task 1: Module and assembly contracts

**Files:** Create `jiangnan_agent/assembly/model.py`, `tests/test_assembly_model.py`; update `jiangnan_agent/assembly/__init__.py`.

- [x] Define validated `ConnectionAnchor`, `ClearanceZone`, `Module`, `Connection`, and `Assembly` types.
- [x] Test nonempty IDs/kinds, unique anchor names, valid cardinal facing, positive opening size, and duplicate module IDs.
- [x] Verify model data is copied at module/assembly boundaries where needed to prevent accidental aliasing.

### Task 2: Module transforms

**Files:** Create `jiangnan_agent/assembly/transforms.py`, modify `jiangnan_agent/core/block.py`, create `tests/test_assembly_transforms.py`, extend `tests/test_block_model.py`.

- [x] Add failing tests for module translation, 90-degree rotations, X/Z mirror, anchor/clearance transforms, and stair/door/rail/head rotation state reflection.
- [x] Implement pure transforms that return a new module and preserve its ID and semantic metadata.
- [x] Verify source models and anchors remain unchanged.

### Task 3: Anchored connection and assembly editing

**Files:** Create `jiangnan_agent/assembly/operations.py`, modify `jiangnan_agent/assembly/__init__.py`, create `tests/test_assembly_operations.py`.

- [x] Test connecting two modules by selecting the quarter-turn that makes their anchor facings oppose, aligning X/Z, and rejecting elevation/type/size mismatches.
- [x] Implement deterministic `connect_modules` and `disconnect_modules` operations without partial mutation on errors.
- [x] Implement `replace_module` by stable ID and `split_assembly` by connection-graph components; verify non-target module models remain unchanged.

### Task 4: Assembly validation and rendering

**Files:** Create `jiangnan_agent/assembly/validation.py`, `tests/test_assembly_validation.py`, `tests/test_assembly_render.py`.

- [x] Test structured validation issues for block overlap, stale/missing anchors, connection mismatch, opening mismatch, height mismatch, and eaves clearance intersections.
- [x] Implement deterministic validation and `render_assembly`; reject conflicting block writes at render time instead of silently overwriting.
- [x] Test that clean assemblies render to the expected sparse model and invalid ones retain inspectable issue details.

### Task 5: Two-courtyard integration example

**Files:** Create `examples/two_courtyard.py`, `tests/test_two_courtyard.py`; update `README.md`, `docs/roadmap.md`.

- [x] Add explicit hall/corridor adapter anchors and eaves clearances, then construct a repeatable two-courtyard assembly from independent generators.
- [x] Test clean connections, no collision/clearance issues, module replacement isolation, stable block output, and Sponge v3 write/read dimensions and block count.
- [x] Document Phase 3 API/example and mark only automated geometry checks complete; leave Minecraft/WorldEdit placement unverified.

## Plan Self-Review

- Each required operation has a dedicated test owner; invalid input paths are included in Tasks 1–4.
- Phase 2 generators and existing Sponge IO remain unchanged unless integration tests reveal a concrete interface defect.
- Persistence, version history, and local UI remain deferred to Phase 4/8.
