# Phase DB-2 Semantic Annotation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add reviewable semantic annotations, deterministic component analysis, static reference components, and versioned style-analysis reports to the DB-1 library.

**Architecture:** SQLite schema v4 stores append-only annotation revisions, static component snapshots, and style-analysis snapshots. A focused semantics module validates geometry and derives block summaries from the existing read-only Litematic parser after SHA-256 verification; `LibraryService` and CLI expose the operations without changing generators or project APIs.

**Tech Stack:** Python 3.12, stdlib `sqlite3`, existing `nbtlib`, pytest, Windows 10/11 x64.

**Spec:** [docs/superpowers/specs/2026-10-30-phase-db2-semantic-annotations.md](../specs/2026-10-30-phase-db2-semantic-annotations.md)

## Global Constraints

- Target Minecraft Java 1.21.5 / DataVersion 4325; older Litematic versions may be analyzed without being converted.
- Keep original `.litematic` files read-only and verify SHA-256 before and after analysis.
- Do not change generators, Assembly, ProjectEditor, project history, Schematic output, MCP interfaces, or Minecraft saves.
- Keep `huizhou_core` and `jiangnan_suzhou` as the only active style targets; reference assets remain region-unassigned absent provenance.
- Rule-based semantic outputs remain `candidate` until a human review records verification.
- Reference components are static and must not be labeled as implemented parameterized generators.
- Keep style JSON versions immutable; do not feed candidate findings into profile recommendations.

## Review Focus

- Negative signed Region sizes map selectors to the same absolute source coordinates produced by the parser; pin with geometry tests.
- Half-open boxes select edge blocks predictably and reject empty/reversed/out-of-Region ranges; pin with boundary tests.
- Exact block sets reject duplicate, air, and off-Region coordinates and round-trip X-runs deterministically; pin with validation tests.
- Annotation edits create a new revision and clear prior verification; pin with revision lifecycle tests.
- Component registration rejects candidates/rejected annotations and preserves source/version snapshots; pin with status and foreign-key tests.
- A style-analysis candidate cannot change either existing style profile version or palette; pin with query regression tests.
- Reanalysis rejects changed source bytes and does not write to source paths; pin with real-file hash checks and corruption tests.

---

### Task 1: Schema v4 and immutable annotation models

**Files:**
- Create: `jiangnan_agent/library/migrations/004_semantic_annotations.sql`
- Modify: `jiangnan_agent/library/database.py`, `jiangnan_agent/library/models.py`, `jiangnan_agent/library/__init__.py`
- Test: `tests/test_library_semantics.py`, `tests/test_library_database.py`

**Interfaces:**
- Add `SemanticAnnotation`, `ReferenceComponent`, and `StyleAnalysis` immutable models.
- Migration creates revisioned annotation, reference component, and style-analysis tables with foreign keys to exact source asset and annotation versions.
- `LibraryDatabase.CURRENT_SCHEMA_VERSION` becomes 4; repeated migration is idempotent.

- [x] Write failing tests for v3→v4 migration, DB-1 row preservation, foreign keys, allowed labels/statuses, and repeat initialization.
- [x] Run the migration test and confirm it fails because schema v4 is missing (`database.initialize()` returns 3).
- [x] Implement migration and immutable models, preserving every DB-1 row and API.
- [x] Run focused migration/model tests (26 library tests passed).
- [x] Commit the task (`db7c11c feat(library): add semantic annotation schema`).

### Task 2: Geometry selectors and deterministic component analysis

**Files:**
- Create: `jiangnan_agent/library/semantics.py`
- Modify: `jiangnan_agent/library/models.py`
- Test: `tests/test_library_semantics.py`

**Interfaces:**
- `normalize_annotation_geometry(region, kind, geometry) -> dict[str, object]`
- `encode_x_runs(positions) -> tuple[tuple[int, int, int, int], ...]`
- `decode_x_runs(runs) -> tuple[Position3, ...]`
- `summarize_annotation(region, component_type, geometry_type, geometry) -> ComponentSummary`
- Coordinates are absolute Litematica source coordinates; boxes are half-open; exact sets contain occupied positions only.

- [x] Write failing geometry tests for Region, negative signed size, half-open boxes, exact sets, off-Region/air/duplicate blocks, and X-run round trips.
- [x] Run tests and verify expected failures.
- [x] Implement the focused geometry and summary functions using existing parser iteration.
- [x] Run focused geometry tests.
- [x] Commit the task (`3df4205 feat(library): add semantic geometry analysis`).

### Task 3: Annotation lifecycle, candidate rules, and verified components

**Files:**
- Modify: `jiangnan_agent/library/service.py`
- Create: `jiangnan_agent/library/annotation_rules.py`
- Test: `tests/test_library_semantics.py`, `tests/test_library_database.py`

**Interfaces:**
- Add `propose_annotations`, `create_annotation`, `update_annotation`, `review_annotation`, `list_annotations`, `analyze_annotation`, `register_reference_component`, `list_reference_components`, and `get_reference_component` to `LibraryService`.
- Rule proposals use stable IDs derived from asset/version/rule/Region/selection and are idempotent; all start `candidate` with rule provenance.
- Human review appends a revision; edits append a pending candidate revision.
- Component registration requires a verified annotation revision and writes an immutable `static_reference` snapshot marked `not_parameterized`.

- [x] Write failing tests for idempotent rule proposals, candidate-only auto status, revision transitions, analysis reproducibility, verified-only registration, and static/not-parameterized state.
- [x] Run tests and verify failures are for missing lifecycle behavior.
- [x] Implement the minimal rule set, persistence, and verified component snapshots.
- [x] Run focused database and semantics tests.
- [x] Commit the annotation lifecycle and style-analysis services together (`abf0659 feat(library): add reviewable semantic components and style reports`).

### Task 4: Versioned style extraction and reports

**Files:**
- Modify: `jiangnan_agent/library/service.py`
- Create: `jiangnan_agent/library/reports.py`
- Test: `tests/test_library_semantics.py`

**Interfaces:**
- Add `create_style_analysis`, `list_style_analyses`, `get_style_analysis`, and `review_style_analysis`.
- A report pins profile version and source asset versions, includes measured dimensions/material/layer distributions, distinguishes verified annotations from candidate interpretations, and never updates style JSON.
- Export report JSON without overwriting an existing path.

- [x] Write failing tests for deterministic reports, pinned references, verified/candidate separation, immutable existing style versions, and non-overwriting export.
- [x] Run tests to verify expected failures.
- [x] Implement report creation, review snapshots, and safe JSON export.
- [x] Run focused style/report tests.
- [x] Commit style reporting with the annotation lifecycle (`abf0659 feat(library): add reviewable semantic components and style reports`).

### Task 5: CLI, actual-template acceptance, and documentation

**Files:**
- Modify: `jiangnan_agent/cli.py`, `README.md`, `docs/library-db-1.md`
- Create: `docs/library-db-2.md`, local ignored `workspace/library/db2-structure-analysis-20261030.json`
- Test: `tests/test_library_cli.py`, `tests/test_library_semantics.py`, full `tests/` suite

**Interfaces:**
- Add nested CLI commands for annotation, component, and style-analysis queries and review operations.
- Provide analysis output for `reference.fangtang` and `reference.liusufang-frame` without assigning regions or marking heuristic labels verified.
- Add exact Windows instructions for creating a review, inspecting component analysis, and exporting a report.

- [x] Write failing CLI tests for proposal/list/review/analyze/component/report round trips.
- [x] Run CLI tests and verify expected failures.
- [x] Implement the CLI over `LibraryService`; keep parsing and persistence out of argparse handlers.
- [x] Run focused CLI tests and analyze both real templates, confirming before/after SHA equality.
- [x] Verify the DB-1 snapshot copied into a disposable DB migrates to schema 4 with DB-1 references, materials, styles, and knowledge unchanged.
- [x] Run Windows Python 3.12 full suite, MCP protocol test, `pip check`, wheel content check, and `git diff --check`.
- [x] Commit source/docs only; do not add `Template/` or user workspace files.
- [x] Request final read-only code review and resolve actionable findings: source hashes are rechecked when reviewing style reports; empty Regions are preserved; overlapping Region occupancy is counted consistently; populated DB-1 migration coverage is added.
- [x] Publish the DB-2 branch and open [PR #4](https://github.com/songgagav/MC-Architect-Agent/pull/4) against `phase-db1-reference-library`; leave it open for review and do not merge.

## Completion Gate

Stop at DB-2. Report real-template measurements, candidate/verified/unclassified component counts, style-analysis status, SHA-256 before/after, DB-1 migration evidence, Windows/CI results, and the limitations still requiring manual review. Do not begin GEN-2.
