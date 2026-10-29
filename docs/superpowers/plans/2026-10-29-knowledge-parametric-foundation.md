# Knowledge & Parametric Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Add versioned, provenance-aware parameters and assets for existing hall/corridor modules without replacing current geometry or Assembly APIs.

**Architecture:** Load small versioned JSON catalogs through validated Python models. Resolve catalog configuration into the existing dataclasses, store version references in optional module metadata, and route existing service creation/edit calls through the factory when catalog metadata applies.

**Tech Stack:** Python 3.12, dataclasses, packaged JSON resources, pytest.

**Spec:** `docs/superpowers/specs/2026-10-29-knowledge-parametric-foundation.md`

## Files

- Add `jiangnan_agent/knowledge/{__init__.py,models.py,v1/rules.json}` for provenance records.
- Add `jiangnan_agent/parameters/{__init__.py,registry.py,v1/hall.json,v1/corridor.json}` for schema models and deterministic resolution.
- Add `jiangnan_agent/assets/{__init__.py,registry.py,factory.py,v1/assets.json}` for registered generator assets.
- Extend `jiangnan_agent/assembly/model.py`, `assembly/transforms.py`, and `io/assembly_json.py` with optional metadata preservation.
- Integrate the asset factory with `io/project_editor.py` and `agent_tools/service.py`; keep MCP signatures unchanged.
- Add `examples/hall_main_fixture.py`; update `README.md`, package-data configuration, and focused tests.

## Tasks

### Task 1 — Catalog models and resources

- [x] Write tests for supported evidence/confidence values, required provenance fields, schema classifications, and asset references.
- [x] Run the new tests and confirm they fail because catalogs/models do not exist.
- [x] Add the three versioned JSON resources and minimal validated models/loaders.
- [x] Run the catalog tests; confirm invalid version and missing source IDs are rejected.

### Task 2 — Deterministic parameter resolver

- [x] Test v1 hall/corridor defaults, parameter changes, derived footprint values, hard invalid values, soft warnings, unknown keys, alias conflicts, supplied-derived conflicts, and unsupported versions.
- [x] Run tests red, then implement normalization and resolution to `HallParameters`/`CorridorParameters`.
- [x] Assert repeated resolution produces equal normalized inputs, typed parameters, and warnings.

### Task 3 — Additive module metadata and compatibility

- [x] Test metadata freezing/validation, assembly JSON round trip, omission of empty metadata, and loading old project/module records without metadata.
- [x] Run tests red, then add optional metadata and preserve it across transforms and serialized history snapshots.
- [x] Re-run v1/v2 project compatibility tests.

### Task 4 — Asset creation and editing integration

- [x] Test service-created hall/corridor metadata, deterministic assets, and parameter edits that retain schema/version metadata.
- [x] Test a legacy unversioned module still follows the existing edit path.
- [x] Run tests red, then route hall/corridor service creation and versioned edit paths through the asset factory; do not change MCP signatures or `generate_project_model` precedence.

### Task 5 — README fixture and documentation

- [x] Replace the inline `hall-main` setup with `examples/hall_main_fixture.py`.
- [x] Keep the example test running from a clean temporary directory; assert version metadata and the edited five-bay result.
- [x] Document an example v1 config and clearly label all non-literature constraints as Minecraft-specific.

### Task 6 — Full verification

- [x] Run the focused foundation, editor, service, README, history, and generation regression tests.
- [x] Run the full pytest suite and inspect the exit status and failure count.
- [x] Review the diff for accidental changes to the user's untracked `workspace/` outputs and confirm no historical-standard claims were introduced.

## Review Focus

- Conflicting old/new parameter spellings must fail deterministically instead of silently choosing a value.
- An Assembly error must continue to raise even if legacy settings are also present.
- Old module and project JSON without metadata must still load and re-save.
- Versioned parameter edits must retain module asset/schema references through transform replay.
- Every knowledge rule must have a resolvable source ID and explicit scope; no unsourced historical facts.
