# Phase 4 Project Editing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist complete modular projects and support module-scoped regeneration, history, undo, redo, and change inspection.

**Architecture:** Serialize the existing Assembly graph and every module's sparse block state into versioned `.jap.json`. Store immutable full Assembly snapshots and exact block deltas per revision; `ProjectEditor` updates one stable-ID module and replays its recorded transforms when regenerating hall/corridor geometry. The CLI exposes history navigation without touching Minecraft saves.

**Tech Stack:** Python 3.12, dataclasses, standard-library JSON/UUID/datetime/pathlib, existing Assembly/generators, pytest.

**Spec:** `docs/superpowers/specs/2026-10-29-phase4-project-editing-design.md`

## Global Constraints

- Minecraft target remains Java 1.21.5, DataVersion 4325.
- Do not write to Minecraft world saves; export remains an independent file operation.
- Keep Phase 0–3 project JSON and Python APIs readable; migrate format 1 on load and write format 2.
- Do not add runtime dependencies.
- Preserve module stable IDs, block states, anchors, clearance zones, parameters, transforms, and connections.

## Review Focus

- Format-1 documents and malformed/unsupported versions: migrate compatible documents; reject invalid structure with a clear error (Task 2).
- Empty modules, negative coordinates, and directional block-state properties: round-trip without coordinate or state loss (Task 2).
- Edit after undo: truncate the redo branch and keep revision IDs/parent links valid (Task 3).
- Regeneration that changes a connected module's dimensions: update only that module, retain the graph, and let assembly validation report broken joins (Task 4).
- Missing/invalid CLI history operations: return a nonzero result without changing the saved project (Task 5).

---

### Task 1: Preserve Module Parameters and Placement Transform Recipes

**Files:**
- Modify: `jiangnan_agent/assembly/model.py`
- Modify: `jiangnan_agent/assembly/transforms.py`
- Modify: `jiangnan_agent/assembly/adapters.py`
- Test: `tests/test_assembly_model.py`
- Test: `tests/test_assembly_transforms.py`

**Interfaces:**
- `Module.parameters: Mapping[str, JSONValue]` and `Module.transform_steps: tuple[Mapping[str, JSONValue], ...]` are immutable copies.
- Existing translate/rotate/mirror operations append canonical `translate`, `rotate_y`, or `mirror` steps and preserve parameters.
- Hall/corridor adapters store all effective generator parameters plus adapter options.

- [x] **Step 1: Write failing tests** for nested parameter immutability, adapter parameter capture, and transform-step ordering/preservation.
- [x] **Step 2: Run** `pytest tests/test_assembly_model.py tests/test_assembly_transforms.py -q`; confirm expected missing-field/metadata failures.
- [x] **Step 3: Implement** JSON-value freezing/validation, parameter fields, transform recipes, and adapter parameter capture.
- [x] **Step 4: Re-run** the focused tests and then `pytest -q`.
- [x] **Step 5: Commit** Task 1 as `feat: preserve module regeneration metadata`.

### Task 2: Serialize Full Assemblies and Migrate Project Format

**Files:**
- Create: `jiangnan_agent/io/assembly_json.py`
- Modify: `jiangnan_agent/io/project_json.py`
- Test: `tests/test_project_json.py`

**Interfaces:**
- `assembly_to_dict(assembly: Assembly) -> dict[str, Any]`
- `assembly_from_dict(data: Mapping[str, Any]) -> Assembly`
- Version-2 `JiangnanProject` carries the current `assembly`; version-1 documents remain readable. Revision history and cursor are added by Task 3.

- [x] **Step 1: Write failing tests** for complete assembly round-trip (including negative coordinates and directional states), format-1 migration, malformed assembly rejection, and deterministic key/list ordering.
- [x] **Step 2: Run** `pytest tests/test_project_json.py -q`; confirm the missing `assembly`/migration behavior.
- [x] **Step 3: Implement** deterministic assembly serializers and version-2 project fields/migration, keeping atomic save behavior.
- [x] **Step 4: Re-run** project JSON tests and `pytest -q`.
- [x] **Step 5: Commit** Task 2 as `feat: persist assembly in project files`.

### Task 3: Add Immutable Revision Snapshots and Exact Block Deltas

**Files:**
- Create: `jiangnan_agent/io/project_history.py`
- Modify: `jiangnan_agent/io/project_json.py`
- Test: `tests/test_project_history.py`
- Modify: `tests/test_project_json.py`

**Interfaces:**
- `BlockChange(module_id, position, before_state, after_state)` describes one changed cell; absent cells use `None`.
- `ProjectRevision` stores revision/parent IDs, timestamp, message, changed module IDs, block changes, and a serialized snapshot.
- Projects start with revision 0; `to_dict()` persists all history and the selected revision; loading restores the selected snapshot.

- [x] **Step 1: Write failing tests** for initial revision creation, exact additions/removals/state changes, snapshot isolation from mutable models, and history round-trip.
- [x] **Step 2: Run** `pytest tests/test_project_history.py tests/test_project_json.py -q`; confirm the revision APIs are absent.
- [x] **Step 3: Implement** immutable snapshot encoding, revision records, and project history serialization/validation.
- [x] **Step 4: Re-run** focused tests and `pytest -q`.
- [x] **Step 5: Commit** Task 3 as `feat: add project revision snapshots`.

### Task 4: Implement Module-Scoped Edit, Regeneration, Undo, and Redo

**Files:**
- Create: `jiangnan_agent/io/project_editor.py`
- Modify: `jiangnan_agent/io/__init__.py`
- Test: `tests/test_project_editor.py`

**Interfaces:**
- `ProjectEditor(project).replace_module(module_id, replacement, message) -> ProjectRevision`
- `ProjectEditor(project).regenerate_module(module_id, parameter_updates, message) -> ProjectRevision`
- `ProjectEditor(project).undo() -> bool`, `.redo() -> bool`, `.can_undo`, `.can_redo`.
- Regeneration supports `hall` and `corridor`, retains stable ID and transform recipes, and does not mutate other modules.

- [x] **Step 1: Write failing tests** for targeted regeneration, unchanged neighboring modules, changed block reports, persistence-ready undo/redo, redo-branch truncation, and connected-module validation after a size change.
- [x] **Step 2: Run** `pytest tests/test_project_editor.py -q`; confirm the editor APIs are absent.
- [x] **Step 3: Implement** immutable replacement, parameter regeneration with transform replay, revision recording, undo/redo, and change inspection.
- [x] **Step 4: Re-run** focused tests and `pytest -q`.
- [x] **Step 5: Commit** Task 4 as `feat: edit modules with project history`.

### Task 5: Expose History Navigation and Document Phase 4

**Files:**
- Modify: `jiangnan_agent/cli.py`
- Modify: `tests/test_cli.py`
- Modify: `README.md`
- Modify: `docs/roadmap.md`

**Interfaces:**
- `jiangnan history PROJECT`, `jiangnan undo PROJECT`, and `jiangnan redo PROJECT` operate on the saved `.jap.json`.
- `info` reports the selected revision and module count from the Assembly.
- `generate --project PROJECT` validates and exports a non-empty Assembly; an empty Assembly keeps the legacy `settings.building` path.

- [x] **Step 1: Write failing CLI tests** for history output, saved undo/redo round-trip, nonzero/no-write behavior when no undo/redo is available, and exporting a saved Assembly instead of legacy settings.
- [x] **Step 2: Run** `pytest tests/test_cli.py -q`; confirm the new commands are unrecognized.
- [x] **Step 3: Implement** history commands and Assembly-first generation, then update user documentation/roadmap with automated versus in-game acceptance status.
- [x] **Step 4: Run** `pytest -q` and the CLI history flow against a temporary project; run `git diff --check`.
- [x] **Step 5: Commit** Task 5 as `feat: expose project history commands`.

### Task 6: Whole-Branch Review and Commit

**Files:** all Phase 4 files above.

- [x] **Step 1:** Re-read this plan and the design spec; verify each acceptance requirement against an implementation or test.
- [x] **Step 2:** Run full pytest and `git diff --check`; inspect working tree and complete change summary.
- [x] **Step 3:** Perform the required whole-branch review; fix Critical/Important findings with regression tests, ledger deferred minors and rulings.
- [x] **Step 4:** Commit Phase 4 after verification; keep Phase 4 on its own branch.

