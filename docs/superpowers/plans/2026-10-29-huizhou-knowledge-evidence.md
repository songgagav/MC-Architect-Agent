# Huizhou Knowledge Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Add a sourced, versioned Huizhou knowledge layer and local visual-reference records without changing the existing generators.

**Architecture:** Preserve v1 knowledge and asset records. Add a v2 knowledge directory and a v2 asset-catalog snapshot that carries forward v1 assets while binding current hall/corridor assets to knowledge v2. Extend exact-match rule filtering and latest-version discovery; keep templates and other regional candidates outside historical/executable claims.

**Tech Stack:** Python 3.12, JSON resource catalogs, pytest, Markdown documentation.

**Spec:** `docs/superpowers/specs/2026-10-29-huizhou-knowledge-evidence.md`

## Global Constraints

- Keep Minecraft 1.21.5 and the existing generator interfaces unchanged.
- Keep knowledge v1, asset v1, and parameter schema v1 readable.
- Do not encode unverified traditional dimensions or regional claims as historical facts.
- Do not modify or copy the user's `Template/*.litematic` files.
- Do not add candidate regions to executable knowledge rules.

## Review Focus

- Old projects selecting asset v1 must keep their recorded knowledge v1 and block output.
- Default discovery must select the latest package resource while explicit old versions still load.
- A narrow site-specific source must not become a broad regional rule through implicit hierarchy.
- User-provided projections must remain preferences, not literature facts.
- A packaged install must contain all versioned JSON resources required by latest-version discovery.

---

### Task 1: Versioned knowledge evidence and exact filtering

**Files:**
- Modify: `tests/test_knowledge_parametric_foundation.py`
- Modify: `jiangnan_agent/knowledge/models.py`
- Create: `jiangnan_agent/knowledge/v2/rules.json`

**Interfaces:**
- `load_knowledge_base(version: int | None = None) -> KnowledgeBase`; `None` discovers the latest packaged `vN/rules.json`.
- `KnowledgeBase.rules_for(evidence_kind=None, *, region=None, building_type=None)` preserves positional evidence-kind calls and filters optional region/building type by exact membership.

- [x] **Step 1: Add the failing version, evidence, and exact-filter tests**

Test that default loads v2, explicit v1 remains literature-free and unchanged, v2 has the cited Huizhou records and template preferences, region/building filters are exact, and an unintegrated Zhejiang region has no active result.

- [x] **Step 2: Run the focused tests and verify they fail for missing v2/filter behavior**

Run: `\.venv\Scripts\python.exe -m pytest tests\test_knowledge_parametric_foundation.py -q`

- [x] **Step 3: Add v2 data and latest-version/exact-filter support**

Copy v1 records without changing their content, add the UNESCO/Huangshan source records and scoped rules, then implement latest-version discovery and exact matching.

- [x] **Step 4: Re-run the focused tests**

Expected: all tests in `test_knowledge_parametric_foundation.py` pass.

### Task 2: Versioned executable assets and compatibility

**Files:**
- Modify: `tests/test_knowledge_parametric_foundation.py`
- Modify: `jiangnan_agent/assets/registry.py`
- Create: `jiangnan_agent/assets/v2/assets.json`
- Modify: `examples/hall_v1_parameters.json`

**Interfaces:**
- `list_assets(version: int | None = None)` selects the latest catalog when omitted.
- `get_asset(..., catalog_version: int | None = None)` and `get_asset_for_kind(kind, catalog_version=None)` preserve explicit historical lookup and default to the latest catalog.

- [x] **Step 1: Add failing asset v2 and old-project compatibility assertions**

Assert default hall/corridor assets use asset v2 + knowledge v2 + schema v1; explicit asset v1 still generates identical blocks and retains v1 metadata.

- [x] **Step 2: Run the focused tests and verify the missing asset-version behavior**

Run: `\.venv\Scripts\python.exe -m pytest tests\test_knowledge_parametric_foundation.py -q`

- [x] **Step 3: Add the full v2 catalog snapshot and latest catalog discovery**

Retain the two v1 entries verbatim and add v2 entries with unchanged generator kinds, schema v1, knowledge v2, and matching v2 source IDs.

- [x] **Step 4: Run the focused tests**

Expected: asset v1 and v2 lookup, deterministic geometry, and project editing tests pass.

### Task 3: Regional candidate and reference documentation

**Files:**
- Create: `docs/knowledge-regions.md`
- Modify: `README.md`
- Modify: `pyproject.toml`

- [x] **Step 1: Document active Huizhou scope, evidence limits, template observations, and documentation-only regional candidates**

Link UNESCO, Huangshan Municipal Gazetteer Office, and official candidate-region sources. Keep all candidate-region statuses explicit as not integrated.

- [x] **Step 2: Update README resource/version descriptions and package-data globs**

Describe knowledge v2 and asset v2 while retaining the existing schema-v1 fixture name and reproduction steps.

- [x] **Step 3: Run README and resource packaging checks**

Run: `\.venv\Scripts\python.exe -m pytest tests\test_readme_examples.py tests\test_knowledge_parametric_foundation.py -q`

### Task 4: Full verification and change report

**Files:**
- Verify: all changed Python, JSON, and Markdown resources.

- [x] **Step 1: Run the full test suite**

Run: `\.venv\Scripts\python.exe -m pytest -q`

- [x] **Step 2: Build and inspect the wheel resource list**

Confirm both v1 and v2 knowledge, parameter, and asset JSON resources are packaged. Do not commit because the worktree already contains unrelated in-progress Phase 5/6 changes.
