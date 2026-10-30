# GEN-2 Roof & Eaves v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend existing hall and corridor roof generation with deterministic, configurable gable profiles, eaves, ridge caps, materials, and versioned creative presets while keeping legacy defaults identical.

**Architecture:** Add immutable typed roof/eave/ridge profiles and an integer-rational section sampler. Keep `VoxelModel` and the existing hall/corridor composition path; add ownership-aware roof, eaves, and ridge builders, and preserve `generate_gable_roof` as the legacy-compatible entry point. Publish the new options through parameter schema v3 and asset/catalog v4, with provenance in knowledge base v4.

**Tech Stack:** Python 3.12, standard-library dataclasses and `fractions.Fraction`, SQLite-independent JSON registries, pytest, existing BlockState and Sponge Schematic v3 APIs.

**Spec:** `docs/superpowers/specs/2026-10-30-gen2-roof-eaves-v2-design.md`

## Global Constraints

- Windows 10/11 x64, Python 3.12, Minecraft Java 1.21.5 / DataVersion 4325.
- Keep the symmetric gable as the default; support hard-gable and projecting-gable end treatments; do not add hipped or pyramidal roofs.
- Treat 1 Minecraft block as approximately 1 meter for visual design, not historical measurement.
- Do not turn DB-2 candidate labels or unreviewed reference components into historical evidence or production templates.
- Preserve existing hall/corridor defaults and APIs, Assembly, ProjectEditor history, project JSON, MCP, Schematic v3, and save-protection behavior.
- Do not modify user reference files, write Minecraft saves, or add a large AI system.

## Review Focus

- **Short or steep cross-sections:** reject invalid rises and any sampled step taller than one block; cover in `test_roof_profiles.py::test_rejects_sampled_step_larger_than_one`.
- **Legacy and profile values supplied together:** accept equivalent normalized values and reject conflicting explicit values; cover in `test_parameter_registry.py::test_roof_profile_conflicts_with_legacy_alias`.
- **Shared edge coordinates:** roof surface must yield eave-owned edge cells and optional ridge-cap cells; all other overlaps fail; cover in `test_roof_eaves_v2.py::test_components_have_explicit_boundary_ownership`.
- **Rotated directional blocks:** rotate supported stairs and slabs correctly and reject unsupported directional states; cover in `test_roof_eaves_v2.py::test_roof_states_rotate_and_round_trip`.
- **Old saved projects and pinned assets:** retain v1-v3 asset/schema loading and project history; cover in `test_knowledge_parametric_foundation.py` and `test_project_generation.py`.

---

### Task 1: Typed profiles and deterministic section sampling

**Files:**
- Create: `jiangnan_agent/generators/roof_profiles.py`
- Create: `tests/test_roof_profiles.py`

**Interfaces:**
- Produces immutable `SurfaceBand`, `RoofProfile`, `EaveProfile`, `RidgeProfile`, and `MaterialPalette` types.
- Produces `RoofPreset` as the typed grouping of those four profiles plus a stable `preset_id`.
- Produces `sample_roof_section(half_run: int, ridge_height: int, points: tuple[tuple[int, int], ...]) -> tuple[int, ...]`.
- `RoofProfile.ridge_height` is the rise above the roof spring datum; section points are integer permille pairs with endpoints `(0, 0)` and `(1000, 1000)`.
- `SurfaceBand` carries `start`, `end`, `form` (`stair`, `slab`, `full_block`), and `material_role`; intervals are contiguous and the final band includes 1000.

- [x] **Step 1: Write failing tests** for the literal default sample `(0, 1, 2, 3)` at half-run 3/rise 3; the flattened sample `(0, 1, 1, 2)` at half-run 3/rise 2; equivalent samples at a different span; and invalid endpoints, unordered points, insufficient half-run, and height jumps above one.
- [x] **Step 2: Run `pytest tests/test_roof_profiles.py -q`** and confirm failures come from the missing profile API or validation behavior. First run exposed the missing module as fixture setup errors; moving the guard into the test call phase produced the intended RED: 12 failed because the API was absent.
- [x] **Step 3: Implement the immutable profile models and exact-rational sampler** in `roof_profiles.py`; use `Fraction` for sample position and interpolation, round only the final block height with halves upward, and reject invalid expanded profiles instead of reshaping them.
- [x] **Step 4: Run `pytest tests/test_roof_profiles.py -q`** and confirm all profile cases pass: 12 passed.
- [x] **Step 5: Commit** the profile model and its tests as `feat: add typed roof profiles`.

### Task 2: Independent roof, eaves, and ridge builders

**Files:**
- Modify: `jiangnan_agent/generators/components.py`
- Modify: `jiangnan_agent/generators/roof_profiles.py` (reject air states as occupied roof materials)
- Modify: `tests/test_components.py`
- Create: `tests/test_roof_eaves_v2.py`

**Interfaces:**
- Add `generate_roof_surface(width, depth, base_y, roof_profile, eave_profile, palette, excluded_cells=()) -> VoxelModel`; the eave profile supplies both the cross-slope overhang and the ridge-end projection needed to lay out the surface.
- Add `generate_eaves_component(width, depth, base_y, roof_profile, eave_profile, palette) -> tuple[VoxelModel, frozenset[Position]]`; the second value is the exact set of surface edge cells owned by the eaves.
- Add `generate_ridge_cap(width, depth, base_y, roof_profile, eave_profile, ridge_profile, palette) -> tuple[VoxelModel, frozenset[Position]]`; the second value is the exact set of surface cells owned by the cap, and the eave profile supplies its ridge-end span.
- Add immutable `RoofComponents(surface, eaves, ridge, combined)` and `generate_roof_components(width, depth, base_y, roof_profile, eave_profile, ridge_profile, palette) -> RoofComponents`. It passes the two ownership sets to the surface builder and rejects every other overlap.
- Keep the existing `generate_gable_roof(width, depth, base_y, rise, eaves, material) -> VoxelModel` signature as a wrapper that builds the legacy default profile.
- The roof builder samples each actual half-run position, applies surface bands, and skips cells owned by an enabled eave edge layer or ridge cap. Declared eave-to-beam connections are allowed; other overlaps are errors.

- [x] **Step 1: Write failing component tests** for stair facings on both slopes, permille band selection including the ridge endpoint, eave thickness and end projection, ridge cap width/height, ownership masks, no unintended overlap, invalid material BlockStates (including air states), and 90-degree rotation of the new component output.
- [x] **Step 2: Run `pytest tests/test_roof_eaves_v2.py tests/test_components.py -q`** and confirm expected missing behavior failures. Initial RED: 10 expected missing-builder failures, 14 legacy tests passed; the air-material regression was then added as a separate RED/GREEN check.
- [x] **Step 3: Implement the three pure builders** using the profile models from Task 1 and preserve the legacy function as an adapter.
- [x] **Step 4: Run those targeted tests** and confirm the new component and rotation cases pass; legacy wrapper output remains covered by Task 3's hash tests. Final expanded profile/component run: 37 passed.
- [x] **Step 5: Commit** as `feat: add composable roof eaves and ridge builders`.

### Task 3: Hall and corridor integration with default-output lock

**Files:**
- Modify: `jiangnan_agent/generators/hall.py`
- Modify: `tests/test_hall.py`
- Modify: `tests/test_roof_eaves_v2.py`

**Interfaces:**
- Extend `HallParameters` and `CorridorParameters` with optional roof/eave/ridge profiles and palette while preserving existing effective defaults.
- `generate_hall(parameters=None)` and `generate_corridor(parameters=None)` keep their public signatures and combine the independent component models.
- Default profiles reproduce the legacy construction exactly; explicit profiles never trigger fallback to the legacy shape when validation fails.

- [x] **Step 1: Write failing integration tests** for the literal baseline count/bounds/hash: hall `522`, `min=(-1,0,-1)`, `max-exclusive=(17,10,8)`, SHA-256 `af86496dad80003d609d31a98e24a50957da419d32ca39a9ca622e8e61bc41b3`; corridor `150`, `min=(-1,0,-1)`, `max-exclusive=(12,7,4)`, SHA-256 `6b99402a56bb31b35e6209d64a8ac4f4f83b3b452171ea53a39bd6b1aef0d707`. Compute each hash from UTF-8 lines `x,y,z:<BlockState>\n` sorted by `(x,y,z)`. Baseline values passed before integration.
- [x] **Step 2: Add failing generation tests** for an explicitly supplied default profile (same literal legacy hash), 3-bay and 5-bay halls, corridor lengths 7 and 17, roof-base movement when column height changes, explicit invalid-profile errors without legacy fallback, and Schematic v3 write/read equality for a profile-driven hall and corridor. Initial RED: all 9 profile-integration cases failed because parameter objects had no profile fields.
- [x] **Step 3: Run the focused hall and roof tests** and verify the compatibility assertions fail only because profiles are not integrated yet.
- [x] **Step 4: Integrate roof/eave/ridge builders** in `hall.py`; use an internal unspecified sentinel to tell omitted legacy values from explicitly supplied values, then normalize to the existing effective defaults after checking profile conflicts.
- [x] **Step 5: Run `pytest tests/test_hall.py tests/test_roof_profiles.py tests/test_roof_eaves_v2.py -q`** and confirm default hashes and new generation tests pass: 53 passed.
- [x] **Step 6: Commit** as `feat: integrate roof profiles into hall and corridor`.

### Task 4: Versioned parameters, assets, knowledge provenance, and presets

**Files:**
- Modify: `jiangnan_agent/parameters/registry.py`
- Modify: `jiangnan_agent/generators/hall.py` (mapping-to-profile normalization and resolve-time section validation)
- Modify: `jiangnan_agent/generators/roof_profiles.py` (validated profile mapping parsers)
- Modify: `jiangnan_agent/assembly/adapters.py` (JSON-safe profile serialization for legacy modules)
- Create: `jiangnan_agent/parameters/v3/hall.json`
- Create: `jiangnan_agent/parameters/v3/corridor.json`
- Create: `jiangnan_agent/parameters/v3/roof_profiles.json`
- Create: `jiangnan_agent/assets/v4/assets.json`
- Create: `jiangnan_agent/knowledge/v4/sources.json`
- Create: `jiangnan_agent/knowledge/v4/rules.json`
- Create: `jiangnan_agent/knowledge/v4/regions.json`
- Modify: `tests/test_knowledge_parametric_foundation.py`
- Modify: `tests/test_library_cli.py`
- Modify: `tests/test_library_database.py`
- Create: `tests/test_parameter_registry.py`

**Interfaces:**
- Register hall/corridor asset version 4 in catalog version 4, bound to parameter schema version 3 and knowledge base version 4; retain all v1-v3 catalog entries unchanged.
- Add source records for the new roof/eaves generator and deterministic resolver as project-code sources; preserve active region profiles and existing rule statuses without adding historical roof claims.
- Schema v3 accepts `roof_profile`, `eave_profile`, `ridge_profile`, and `material_palette`, and contains the three presets in the approved design.
- `list_roof_presets() -> tuple[str, ...]` and `load_roof_preset(preset_id: str) -> RoofPreset` expose the versioned creative presets through Python.
- Legacy inputs map to canonical values: `roof_rise` / `roof_section.rise` to `roof_profile.ridge_height`; `eaves` to side overhang and gable-end projection; `materials.roof` and `materials.eaves` to palette roles. A legacy `roof_section` object is accepted only when its profile is `symmetric_gable`. Explicit equal forms are accepted; explicit conflicts raise `ParameterConflictError` before defaults apply.

- [x] **Step 1: Write failing schema/registry tests** for v4 asset binding, v1-v3 pinned asset loading, all three preset query results, provenance categories, project round-trip/history, and explicit legacy/profile equivalence or conflict.
- [x] **Step 2: Run `pytest tests/test_parameter_registry.py tests/test_knowledge_parametric_foundation.py -q`** and confirm failures identify missing v4/schema behavior; initial RED had 7 expected registry failures and 31 existing passes.
- [x] **Step 3: Implement schema v3, registry v4, and knowledge base v4 snapshots**; add only project-code sources, retain existing regions/rules, normalize aliases before defaults, and preserve profile data through Module/ProjectEditor serialization.
- [x] **Step 4: Run the targeted registry tests** and confirm old asset/project metadata remains readable while current assets resolve to schema v3: 40 passed.
- [x] **Step 5: Commit** as `feat: register roof profiles and creative presets`.

### Task 5: User documentation and full regression

**Files:**
- Modify: `README.md`
- Modify: `docs/parameter-registry.md`
- Modify: `docs/knowledge-regions.md`
- Create: `docs/roof-eaves-v2.md`

**Interfaces:**
- Existing BlockState transforms, Assembly rotation, project generation, and Schematic v3 reader/writer are covered by Tasks 2–4; this task adds user-facing operating guidance without changing those APIs.

- [ ] **Step 1: Document** profile fields, aliases/conflicts, the three preset parameter sets, Windows usage examples, and the fact that Minecraft/WorldEdit/Mine2Blend live checks remain separate.
- [ ] **Step 2: Run `pytest -q`** from the repository root and confirm the complete existing and new suite passes; run `git diff --check`.
- [ ] **Step 3: Commit** as `docs: document roof and eaves profiles`.

## Final verification

- Re-run `pytest -q`; record the exact pass/fail counts and any skipped tests.
- Confirm the default hall/corridor hashes and 90-degree transform/Schematic round-trip assertions pass.
- Inspect `git status --short`; stage only plan-owned source/docs/tests, leaving untracked user `workspace/` data untouched.
- Obtain one fresh whole-branch review before reporting completion. Do not report Blender, Mine2Blend, WorldEdit, or in-game visual validation unless actually run.
