# MC-Architect-Agent GEN-3 Façade & Openings v1 Implementation Plan

> **For agentic workers:** Implement natively in this session. Follow the test-first steps in order; use `superpowers:test-driven-development` for every behavior change.

**Goal:** Reconcile and integrate DB-2/GEN-2, then add versioned, deterministic façade profiles for hall and corridor without changing legacy defaults or existing connection interfaces.

**Architecture:** Task 0 is a separate integration branch and PR based on the existing DB-2/GEN-2 branch plus a non-rewriting merge of the updated `main`. It fixes the SQLite/Asset Registry mismatch and creates independently reviewed roof-profile artifacts. After Task 0 passes Windows CI and is merged, create a fresh GEN-3 branch from the updated `main`; implement typed profiles, explicit wall/opening ownership, anchor derivation, versioned presets, and preview examples as incremental layers over existing generators.

**Tech Stack:** Windows 10/11 x64, Python 3.12, stdlib `sqlite3`, pytest, existing BlockState/VoxelModel/Assembly/ProjectEditor/Sponge v3/Mine2Blend/Blender pipeline.

**Spec:** `docs/superpowers/specs/2026-10-30-gen3-facade-openings-v1-design.md`

## Global Constraints

- Minecraft Java 1.21.5; use approximately 1 block per meter as a visual design scale.
- Windows is the formal development and acceptance platform; Python is 3.12.
- Task 0 must be delivered by its own PR, pass Windows CI and legacy regressions, and be merged before creating the GEN-3 branch.
- Do not rewrite or force-update existing remote branches; do not duplicate Phase 2, Phase 3, or DB-1 in later PRs.
- Keep old asset/schema snapshots immutable. Synchronize registry v4 and v5 records without rewriting the existing SQLite v3 row.
- No `facade_profile` means the current hall/corridor block maps and hashes remain identical.
- Only explicit wall replacement zones may be replaced. Structural, passage, roof, and connection-clearance cells are protected or produce explicit errors.
- Only the unique `primary_entry` drives the existing hall `front` anchor. `through_passage` derives the existing `rear` anchor from that same opening. No new anchor names are introduced.
- Every Profile must round-trip through deterministic JSON. Legacy `door_width` and `materials` conflict checks apply only when both old and new values were explicitly supplied.
- Do not use DB-2 `candidate` data as a generator template or historical fact. Presets are Minecraft creative profiles.
- Do not write Minecraft world saves. Report Minecraft/WorldEdit placement as `pending` unless actually performed.
- Do not add complex dougong, hipped/pyramidal roofs, large gate towers, AI models, or historical dimension constraints.
- Never stage, overwrite, or remove existing `workspace/` data; write new artifacts only to unique paths under `workspace/projects`, `workspace/exports`, and `workspace/previews`.

## Review Focus

- **Primary entrance identity and placement:** duplicate/missing IDs, multiple front doors, or moving the primary entry must preserve exactly one `front` anchor at the selected opening. Pin with adapter tests in Task 5.
- **Face coordinate and segment interpretation:** left/right use actual side-post segments, not `bay_count`; pin all four face normals and side segment placement in Task 3.
- **Ownership and clearances:** thick walls, frames, trim, roof, posts, passage, and connector clearances must not overwrite one another. Pin declared replacements and undeclared conflicts in Tasks 3–5.
- **State transforms:** lattice/window states must rotate and mirror without silently losing facing/axis/half/shape. Pin supported and rejected states in Task 4.
- **Old project and explicit-input compatibility:** legacy door/material values, v3 asset records, JSON snapshots, project history, and default hashes must remain stable. Pin in Tasks 0, 2, 5, and 6.

---

### Task 0.1: Reconcile Python assets and SQLite module catalog

**Files:**
- Modify: `jiangnan_agent/library/service.py`
- Create: `jiangnan_agent/library/catalog/v2/modules.json` (planned modules only; v1 remains immutable)
- Modify: `tests/test_library_database.py`
- Modify: `tests/test_library_cli.py` only if CLI output consumes the changed default list behavior

**Interfaces:**
- `LibraryService.list_modules(*, include_planned: bool = False, include_versions: bool = False)` returns latest module records by default and all stored versions when `include_versions=True`.
- `LibraryService.get_module_definition(asset_id, version=None)` retains its current latest-by-default and exact-version behavior.
- Implemented module metadata is sourced from the latest Python Asset Registry snapshot; planned entries are sourced from the highest discovered `library/catalog/v*/modules.json`.

- [x] **Write failing tests first**
  - Add `test_sqlite_module_catalog_matches_latest_python_asset_registry`: `get_asset("jiangnan.hall")` and SQLite hall record agree on asset version, schema version, kind, anchors, and source; repeat for corridor.
  - Add `test_module_catalog_preserves_v3_and_registers_v4`: an existing v3 `record_json` remains byte-for-byte unchanged, v4 is queryable, and exact v3 lookup still succeeds.
  - Add `test_list_modules_returns_latest_unless_versions_requested`: default lists hall/corridor once at v4; `include_versions=True` exposes older and current versions; `include_planned` continues to work.
  - Add an idempotence assertion: initializing the same database twice creates no duplicate rows or changed immutable snapshots.
- [x] **Run the tests and confirm they fail**
  - Run: `.\.venv\Scripts\python.exe -m pytest -q tests\test_library_database.py`
  - Expected: new version-discovery/query assertions fail against the current v1-only bootstrap.
- [x] **Implement minimal synchronization and query changes**
  - Discover the newest module-catalog directory rather than hardcoding `v1`.
  - Import the asset versions present in the newest Python Asset Registry snapshot; preserve an existing same-ID/version SQLite snapshot without updating it, and fail if stable identity fields conflict.
  - Keep planned records from the newest module catalog; keep historical catalog v1 and asset files unchanged.
  - Make `list_modules()` select the highest stored version per `asset_id` unless `include_versions=True`.
- [x] **Run focused tests, then the full baseline**
  - Run: `.\.venv\Scripts\python.exe -m pytest -q tests\test_library_database.py tests\test_library_cli.py`
  - Run: `.\.venv\Scripts\python.exe -m pytest -q`
  - Expected: focused tests and the full suite pass; prior baseline was 379 tests.
- [x] **Review the diff**
  - Run: `git diff --check`
  - Verify `library/catalog/v1/modules.json`, `assets/v1`–`assets/v4`, and old DB records are unchanged.
- [x] **Commit the catalog fix**
  - Stage only `jiangnan_agent/library/service.py`, `jiangnan_agent/library/catalog/v2/modules.json`, and `tests/test_library_database.py` plus any required CLI test edits.
  - Commit: `fix: synchronize sqlite modules with asset registry`

### Task 0.2: Generate and visually audit the three GEN-2 roof preset artifacts

**Files:**
- Create: `examples/gen2_roof_closeout.py`
- Create: `tests/test_gen2_roof_closeout.py`
- Create: `docs/gen2-roof-closeout-report.md`

**Interfaces:**
- `build_roof_closeout_examples(output_root: Path) -> tuple[RoofExampleResult, ...]` creates one saved hall project and Sponge v3 schematic for each existing roof preset; it refuses to overwrite any destination.
- The existing `jiangnan preview` command creates top/front/side/perspective images from each schematic.

- [x] **Write a failing generator/round-trip test first**
  - Add `test_roof_closeout_builds_all_presets_with_roundtrip_schematics`: run the helper under `tmp_path`, assert all three preset IDs appear once, each project reloads, each schematic reads as DataVersion 4325, and the readback block map equals the generated map.
  - Add `test_roof_closeout_refuses_existing_destination`: pre-create one destination and assert the helper raises without changing it.
- [x] **Run tests to confirm they fail**
  - Run: `.\.venv\Scripts\python.exe -m pytest -q tests\test_gen2_roof_closeout.py`
- [x] **Implement the example helper**
  - Use `jiangnan_dark_tile`, `gray_brick_layered`, and `warm_spruce_garden` through the existing parameter/preset and module APIs.
  - Generate distinct, timestamped paths below the supplied output root; do not use the user’s existing files as output paths.
- [x] **Run tests and produce the actual local artifacts**
  - Run focused tests and the complete pytest suite.
  - Generate the three `.jap.json` projects and `.schem` files under a new unique directory in `workspace/`.
  - Run the existing preview command for each file using `E:\MCbuild\Mine2Blend\mcblock_mine2blend` and `D:\SteamLibrary\steamapps\common\Blender\blender.exe`.
- [x] **Inspect all twelve images and record evidence**
  - Open top/front/side/perspective images for each roof preset.
  - Record dimensions, block counts, DataVersion, schematic round-trip, Blender/Mine2Blend versions, observed roof/ridge/eave/column-beam issues, and Minecraft/WorldEdit `pending` status in `docs/gen2-roof-closeout-report.md`.
  - Do not claim an issue-free result if visual review finds a defect; fix it with a failing test before proceeding.
- [x] **Commit the reproducible roof examples**
  - Stage only `examples/gen2_roof_closeout.py`, `tests/test_gen2_roof_closeout.py`, and `docs/gen2-roof-closeout-report.md`.
  - Commit: `test: add gen2 roof closeout examples`

### Task 0.3: Integrate Task 0 by PR before starting GEN-3

**Files:**
- Task 0 branch contains only the registry synchronization, its tests, the roof example runner/tests, and its report.
- Do not include the untracked GEN-3 design/plan or any `workspace/` outputs in the Task 0 commit.

- [x] Create a new Task 0 integration branch from the current DB-2/GEN-2 branch; merge the fetched `origin/main` commit using a normal merge. Do not rebase or force-push the existing remote branch.
- [x] Run the full Windows test suite and `git diff --check` on the merged Task 0 tree.
- [x] Commit only named Task 0 source/test/docs files; keep all existing and generated `workspace/` data unstaged.
- [x] Push the new branch and open a PR targeting `main`; describe the DB-2/GEN-2 dependency chain and explicitly state that Phase 2/3/DB-1 are already in `main`.
- [x] Wait for the required Windows CI and confirm legacy/default tests pass; then merge the Task 0 PR with the normal merge method, as authorized by the user.
- [x] Fetch the new `origin/main`, verify its merge commit and green Windows CI, then create `phase-gen3-facade-v1` from that updated `main`.

### Task 1: Typed façade profiles and deterministic JSON codec

**Files:**
- Create: `jiangnan_agent/generators/facade_profiles.py`
- Modify: `jiangnan_agent/generators/hall.py`
- Create: `tests/test_facade_profiles.py`
- Modify: `tests/test_hall.py`

**Interfaces:**
- Define `FacadeOpening(opening_id, face, kind, connection_use, segment_index, offset, sill_offset)` with `connection_use` limited to `primary_entry` or `non_connecting` in v1.
- Define `WallPanelProfile`, `DoorProfile`, `WindowProfile`, `TimberDetailProfile`, and `FacadeProfile` as frozen typed profiles with explicit validation.
- Define `facade_profile_from_mapping(value) -> FacadeProfile` and `facade_profile_to_mapping(profile) -> dict[str, object]` as the canonical deterministic JSON codec.
- Add optional `facade_profile` to hall/corridor parameter classes; add an explicit-input sentinel for `door_width` while preserving the public default value of 2.

- [x] **Write profile validation and codec tests first**
  - Test round-trip equality and stable JSON encoding for every profile type.
  - Test rejection of empty/duplicate `opening_id`, invalid face/use, invalid dimensions, and multiple/missing hall `primary_entry` when a façade profile is applied to a hall.
  - Test that legacy default `door_width == 2` remains observable and that only explicit old/new conflicts raise.
- [x] Run the focused tests and confirm the new API is missing or fails.
- [x] Implement typed records, parsers/serializers, and explicit-value conflict handling.
- [x] Run `pytest tests\test_facade_profiles.py tests\test_hall.py -q`; confirm all focused tests pass.
- [ ] Commit the typed profile layer with its tests and design/plan documents: stage `tests/test_facade_profiles.py`, `tests/test_hall.py`, `jiangnan_agent/generators/facade_profiles.py`, `jiangnan_agent/generators/hall.py`, `docs/superpowers/specs/2026-10-30-gen3-facade-openings-v1-design.md`, and `docs/superpowers/plans/2026-10-31-gen3-facade-openings-v1.md`; commit as `feat: add typed façade profiles`.

### Task 2: Face coordinates, wall layers, ownership, and opening masks

**Files:**
- Create: `jiangnan_agent/generators/facade_geometry.py`
- Modify: `jiangnan_agent/generators/components.py`
- Create: `tests/test_facade_geometry.py`
- Modify: `tests/test_components.py`

**Interfaces:**
- Define local face basis with `front=+Z`, `rear=-Z`, `left=-X`, `right=+X`; X increases across front/rear, Y upward, Z from rear to front.
- Define `resolve_facade_opening(opening, segment_bounds) -> BoundingBox` where segment bounds are supplied from the actual front/rear bay list or left/right side-post interval list.
- Extend `generate_wall(bounds, material, openings=(), *, profile=None, face=None)`; `profile=None` preserves the existing implementation and signature behavior.
- Define `BlockOwnershipMap` to record claimed cells and allowed replacement roles; define a strict merge operation that raises on undeclared overlap and refuses writes into protected passage/opening cells.

- [ ] **Write failing wall/ownership tests first**
  - Test each face’s outward normal and positive local offset.
  - Test front/rear bay segments and left/right segments derived from side posts with differing counts.
  - Test thickness 1 legacy occupancy; test inward/outward thickness 2 bounds for all four faces.
  - Test identical opening mask through every layer and rejection of a decoration/frame placed in opening or passage cells.
  - Test wall can be replaced by door/window only in explicitly replaceable cells; test column/beam/roof ownership conflict raises.
- [ ] Run the focused tests and confirm they fail.
- [ ] Implement face mapping, profile-aware wall fill, opening mask, ownership tracking, and conflict errors.
- [ ] Run `pytest tests\test_facade_geometry.py tests\test_components.py -q`; confirm pass.
- [ ] Commit the wall geometry/ownership layer: `feat: add owned wall panel generation`.

### Task 3: Profiled doors, windows, grid detail, and state transforms

**Files:**
- Create: `jiangnan_agent/generators/facade_components.py`
- Modify: `jiangnan_agent/core/transforms.py` only if tests expose a missing supported state mapping; preserve fail-closed behavior for unsupported states.
- Create: `tests/test_facade_components.py`

**Interfaces:**
- Define `generate_facade_door(origin, profile, face, ownership, opening_mask) -> VoxelModel`.
- Define `generate_facade_window(origin, profile, face, ownership, opening_mask) -> VoxelModel`.
- Support 1-block single doors and 2-block paired doors, frame/lintel roles, plain windows, discrete lattice windows, and a small decorative pattern set.

- [ ] **Write failing component tests first**
  - Test single/double door geometry, lower/upper/hinge/facing states, frame thickness, lintel, and four face orientations.
  - Test plain/lattice/decorative window sizes, frames, material roles, and opening mask.
  - Test rotated/mirrored lattice and door states produce correct states; unsupported properties raise.
  - Test frames and grille blocks cannot occupy reserved clear opening cells or replace structural ownership.
- [ ] Run focused tests and confirm they fail.
- [ ] Implement profile-based door/window components by reusing existing state parsing and block generators where compatible.
- [ ] Run `pytest tests\test_facade_components.py tests\test_assembly_transforms.py -q`; confirm pass.
- [ ] Commit the door/window components: `feat: add profiled doors and windows`.

### Task 4: Integrate profiles with hall/corridor and stable anchors

**Files:**
- Modify: `jiangnan_agent/generators/hall.py`
- Modify: `jiangnan_agent/assembly/adapters.py`
- Modify: `jiangnan_agent/assets/factory.py`
- Modify: `tests/test_hall.py`
- Modify: `tests/test_assembly_model.py`
- Modify: `tests/test_project_generation.py`

**Interfaces:**
- With no `facade_profile`, `generate_hall()` and `generate_corridor()` use the exact legacy code path.
- With a profile, hall resolves openings by explicit face/segment/offset, places wall and timber pieces through `BlockOwnershipMap`, and requires exactly one front-facing `primary_entry`.
- `hall_module()` computes the existing `front` anchor from the primary opening specification, never by scanning all door states. `through_passage` creates the existing rear opening/anchor from the same primary opening.
- Corridor accepts explicit enclosure/profile settings without changing its no-profile open gallery output or start/end anchors.

- [ ] **Write failing assembly integration tests first**
  - Lock current defaults before adding profile behavior: hall 522 blocks, bounds `min=(-1,0,-1)`, `max-exclusive=(17,10,8)`, SHA-256 `af86496dad80003d609d31a98e24a50957da419d32ca39a9ca622e8e61bc41b3`; corridor 150 blocks, bounds `min=(-1,0,-1)`, `max-exclusive=(12,7,4)`, SHA-256 `6b99402a56bb31b35e6209d64a8ac4f4f83b3b452171ea53a39bd6b1aef0d707`.
  - Test multiple front doors with only the stable `primary_entry` supplying `front`; move it and assert the existing anchor name and exact coordinates update.
  - Test `through_passage` front/rear anchors remain paired to the primary opening; nonconnecting openings add no anchors.
  - Test side windows resolve against actual side-post segments, walls of thickness 2 respect inside/outside direction, and roof/post/passage/anchor clearances reject conflict.
  - Test corridor profile enclosure preserves `start`/`end` anchors and open-gallery preset remains open.
- [ ] Run tests and confirm they fail against door scanning and current single-material walls.
- [ ] Implement opt-in hall/corridor profile integration and strict ownership merge; keep legacy `None` path byte-identical.
- [ ] Run focused hall/assembly tests and assert old hashes remain identical.
- [ ] Commit the hall/corridor integration: `feat: integrate façade profiles with buildings`.

### Task 5: Register v4 schemas, v5 assets, sources, and style presets

**Files:**
- Create: `jiangnan_agent/parameters/v4/hall.json`
- Create: `jiangnan_agent/parameters/v4/corridor.json`
- Create: `jiangnan_agent/parameters/v4/facade_profiles.json`
- Create: `jiangnan_agent/assets/v5/assets.json`
- Create: `jiangnan_agent/knowledge/v5/sources.json`
- Create: `jiangnan_agent/knowledge/v5/rules.json`
- Create: `jiangnan_agent/knowledge/v5/regions.json`
- Create: `jiangnan_agent/library/styles/v2/jiangnan_whitewall_timber.json`
- Create: `jiangnan_agent/library/styles/v2/huizhou_graybrick_entry.json`
- Create: `jiangnan_agent/library/styles/v2/garden_open_gallery.json`
- Modify: `jiangnan_agent/library/service.py`
- Modify: `tests/test_parameter_registry.py`
- Modify: `tests/test_knowledge_parametric_foundation.py`
- Modify: `tests/test_library_database.py`

- [ ] **Write failing registry tests first**
  - Test asset v5/schema v4 loading and explicit v4 compatibility.
  - Test each preset is independently registered, deterministic, can combine with each GEN-2 roof preset, and contains only verified block-state configurations.
  - Test style query returns the three creative profiles with proper version/status; assert no DB-2 candidate component is used.
  - Test old asset/schema snapshots and module history are unchanged.
- [ ] Run focused tests and confirm failures.
- [ ] Add v4 schema/v5 asset and code-source snapshots plus three style records; make style catalog version discovery automatic.
- [ ] Connect `facade_profile` parsing to `resolve_parameters`, and ensure JSON values are canonicalized before generator construction.
- [ ] Run parameter/library tests and full suite; confirm schema v1-v3 and current Task 0 rows remain readable.
- [ ] Commit versioned schemas and style presets: `feat: register gen3 façade assets and styles`.

### Task 6: Project JSON, history, and default compatibility

**Files:**
- Modify: `jiangnan_agent/assembly/adapters.py`
- Modify: `jiangnan_agent/io/project_editor.py` only if current parameter merge cannot preserve typed Profile updates.
- Modify: `tests/test_project_json.py`
- Modify: `tests/test_project_editor.py`
- Modify: `tests/test_project_history.py`
- Modify: `tests/test_project_generation.py`
- Modify: `tests/test_readme_examples.py`

- [ ] **Write failing project/editor tests first**
  - Test save/reload round-trips every typed profile to stable JSON and regenerates the same block map.
  - Test local wall/window/profile edits, undo, redo, and reopening preserve all unaffected modules and stable opening IDs.
  - Test legacy projects lacking `facade_profile` regenerate to the known hall/corridor hashes.
  - Test old explicit `door_width`/`materials` aliases conflict only when both inputs were explicit and differ after BlockState normalization.
- [ ] Run focused tests and confirm failures.
- [ ] Implement adapter JSON mapping and minimal editor changes; keep project format top-level structure unchanged.
- [ ] Run project/history/readme tests and confirm pass.
- [ ] Commit compatibility and history coverage: `test: cover façade project history compatibility`.

### Task 7: Generate three GEN-3 buildings, inspect views, and submit final PR

**Files:**
- Create: `examples/gen3_facade_examples.py`
- Create: `tests/test_gen3_facade_examples.py`
- Create: `docs/gen3-facade-validation-report.md`
- Modify: `README.md`
- Modify: `docs/windows-acceptance.md`

- [ ] **Write failing example/export tests first**
  - Test three complete example projects use the three façade presets, produce Sponge v3 files, read back identically, and refuse overwriting destinations.
  - Test the set includes 3-bay and 5-bay halls, all three GEN-2 roof presets across examples, and the open-gallery/corridor enclosure scenario in focused tests.
- [ ] Run focused tests and confirm failures.
- [ ] Implement the reproducible example runner and docs for profile selection, opening IDs/anchor rules, and safe generation.
- [ ] Generate actual three example projects, `.schem` files, and Blender top/front/side/perspective previews in fresh unique `workspace/` paths.
- [ ] Inspect every view manually; record geometry, material, roof/wall/timber joins, collision findings, tool versions, schematic readback, and game-test `pending` status in the report.
- [ ] Run the targeted MCP stdio test, all new focused tests, full Windows pytest, and `git diff --check`.
- [ ] Request an independent final code review; fix any findings with tests before publishing.
- [ ] Commit the reproducible examples and final acceptance report: `docs: add gen3 façade examples and validation`.
- [ ] Push the new GEN-3 feature branch and open a PR against its current dependency base (the merged Task 0 `main`); attach the PR to this task. Leave it open for user review; do not merge it automatically.
