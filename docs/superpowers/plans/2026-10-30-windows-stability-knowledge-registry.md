# MC-Architect-Agent Windows Stability and Knowledge Registry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stabilize the current feature line on Windows, then publish a traceable v3 knowledge base and compatible v2 parameter/v3 asset registries for hall and corridor.

**Architecture:** Keep current generators and project APIs. Make path and state transforms fail closed, make Windows the required CI job, and add new versioned JSON/model layers while retaining old registry readers. Attach provenance and region/rule references to parameter and asset metadata without claiming unverified historical dimensions.

**Tech Stack:** Python 3.12, pytest, GitHub Actions, JSON, MCP Python SDK, Sponge Schematic v3.

**Spec:** `docs/superpowers/specs/2026-10-30-windows-stability-knowledge-registry.md`

## Global Constraints

- Target Minecraft Java Edition 1.21.5.
- Windows 10/11 x64 is the only formal runtime and required CI platform.
- Do not generate towns; retain individual buildings, garden components, and modules.
- Preserve Assembly-first generation, empty-Assembly legacy behavior, and no implicit fallback.
- Preserve Assembly, ProjectEditor, revision history, and Schematic interfaces.
- Only `huizhou_core` and `jiangnan_suzhou` are active; other regions are `catalog_only`.
- Do not invent historical dimensions or citations; unverifiable material is pending and not active.
- Preserve knowledge v1/v2, parameter schema v1, and asset catalog v1/v2 compatibility.
- Mark real-app gates pending unless actually verified in the named Windows applications.

## Review Focus

- Windows-rooted, drive-relative, UNC, and backslash traversal paths on Windows and Linux: rejected by `tests/test_agent_tool_paths.py`.
- External links and link loops: rejected without writing outside workspace by `tests/test_agent_tool_paths.py`.
- Unknown `facing`, `orientation`, `axis`, `rotation`, `shape`, and directional connection values: rejected by `tests/test_block_model.py`.
- Catalog-only region tags and pending sources: never returned as active rules by `tests/test_knowledge_parametric_foundation.py`.
- Older serialized module metadata and registry versions: keep loading/generating by compatibility and Schematic round-trip tests.

---

### Task 1: Windows stability and required CI

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `jiangnan_agent/agent_tools/project_access.py`
- Modify: `jiangnan_agent/core/block.py`
- Test: `tests/test_agent_tool_paths.py`, `tests/test_block_model.py`, `tests/test_mcp_server.py`, `tests/test_project_generation.py`, `tests/test_readme_examples.py`
- Documentation: `docs/windows-acceptance.md`

**Interfaces:**
- Keep `ProjectAccess.resolve_project_path` / `resolve_export_path` signatures.
- Keep `BlockState.rotate_y` / `mirror` signatures; unsupported directional states raise `ValueError`.
- CI check name for the required job is stable and runs on `windows-latest`, Python 3.12, with `[dev,mcp]` installed and UTF-8 environment variables set. Ubuntu is `continue-on-error` compatibility coverage.

- [x] Add failing path tests for `\root`, `C:relative`, `C:\absolute`, UNC/device paths, mixed-separator traversal, external symlink, and symlink loop; include Windows-shaped inputs on Linux.
- [x] Run targeted tests and confirm each new case fails for the expected unsafe behavior.
- [x] Add failing state tests for 1.21.5 `orientation`, horizontal/vertical facing, axis, stair/rail shape, boolean connection properties, plus unsupported enum/range values.
- [x] Run targeted tests and confirm unsupported states are currently retained or malformed rather than rejected.
- [x] Implement fail-closed path checks and explicit deterministic state transforms.
- [x] Update CI to required Windows + optional Ubuntu, install `[dev,mcp]`, and force UTF-8; verify the MCP stdio protocol test is not skipped.
- [x] Re-run generation precedence, README fixture, path, state-transform, MCP, and full pytest suite.
- [x] Commit the stability/CI deliverable separately.

### Task 2: Versioned knowledge sources, rules, and region profiles

**Files:**
- Modify: `jiangnan_agent/knowledge/models.py`, `jiangnan_agent/knowledge/__init__.py`
- Create: `jiangnan_agent/knowledge/v3/sources.json`, `rules.json`, `regions.json`
- Test: `tests/test_knowledge_parametric_foundation.py`, `tests/test_mcp_server.py`
- Modify: `docs/knowledge-regions.md`, `docs/roadmap.md`

**Interfaces:**
- Add optional source metadata and rule verification status with defaults that continue loading v1/v2.
- Add immutable `RegionProfile` records and `KnowledgeBase.regions`; `rules_for` matches exact region IDs and returns verified active rules by default.
- `load_knowledge_base(version=None)` discovers v3; explicit versions 1 and 2 remain loadable.

- [x] Add failing tests for complete citation metadata, exact region filtering, two active profiles, catalog-only profiles, and pending-rule exclusion.
- [x] Verify the new tests fail against current v2 behavior.
- [x] Add v3 JSON and a loader that accepts split source/rule/profile files while retaining legacy v1/v2 combined files.
- [x] Populate rules only from verified UNESCO pages or code/user records; label municipality pages blocked from full-text verification as pending, and exclude them from normal active queries.
- [x] Document source locators, dates as published or explicitly unstated, access date, confidence, profile scope, and unresolved evidence. Do not register unverified dimensions.
- [x] Run knowledge, regional filter, MCP knowledge protocol, and legacy-version tests.
- [x] Commit the knowledge deliverable separately.

### Task 3: Parameter provenance and hall/corridor asset registry

**Files:**
- Modify: `jiangnan_agent/parameters/registry.py`, `jiangnan_agent/parameters/__init__.py`, `jiangnan_agent/assets/registry.py`, `jiangnan_agent/assets/factory.py`
- Create: `jiangnan_agent/parameters/v2/hall.json`, `corridor.json`, `jiangnan_agent/assets/v3/assets.json`
- Test: `tests/test_knowledge_parametric_foundation.py`, `tests/test_project_editor.py`, `tests/test_project_json.py`

**Interfaces:**
- Existing parameter resolution and module factory call signatures remain valid; additive provenance inputs are optional.
- Parameter categories are `user_input`, `literature_reference`, `survey_data`, `derived`, and `minecraft_adaptation`.
- New assets cite active region profiles and knowledge rules, declare Minecraft 1.21.5 compatibility, and preserve v1/v2 catalog reads.

- [x] Add failing tests for parameter-category validation, field source references, derived provenance, regional/rule integrity, asset/schema version compatibility, deterministic module output, and metadata persistence through edit/save/reopen.
- [x] Verify the new tests fail before implementation.
- [x] Add v2 schemas with defaults clearly marked as game-grid adaptation or unspecified input, not historical standards; link only evidence actually supported by rules.
- [x] Add v3 hall/corridor assets with region scope explicitly labeled as a design target, not historical validation.
- [x] Preserve old v1/v2 module generation and metadata contracts.
- [x] Run schema, asset, edit/history, serialization, determinism, and schematic round-trip tests.
- [x] Commit the parameter/asset deliverable separately.

### Task 4: Windows acceptance and final review

**Files:**
- Modify: `docs/windows-acceptance.md`, `README.md`, `docs/roadmap.md`
- Test: full `tests/` suite and GitHub Actions Windows job

- [x] Document reproducible Windows commands for `[dev,mcp]`, MCP stdio, Blender/Mine2Blend import/render, and Minecraft 1.21.5 + WorldEdit placement/readback.
- [x] Identify which app-level gates were run and leave all others `pending`.
- [ ] Run full pytest from the project `.venv`, inspect final diff and Git status, and record the actual Windows CI check URL/result.
- [ ] Push the feature branch and create a PR for integration only after the required Windows check passes; never push directly to `main`.
- [ ] Keep Task 1/2/3 commits separate and summarize tests, sample JSON, change report, and follow-up work in the PR description.
