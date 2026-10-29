# Phase DB-1 Reference Library Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a local, versioned SQLite reference library and read-only Litematic importer without changing the existing generator or project APIs.

**Architecture:** JSON stays canonical for knowledge, parameter schemas, module catalog entries, and creative style profiles. SQLite v3 indexes those definitions and stores file metadata plus material/layer aggregates, while original schematics and previews remain external read-only files. A query service is shared by the CLI and reserved for future MCP integration.

**Tech Stack:** Python 3.12, stdlib `sqlite3`, existing `nbtlib`, existing pytest setup, Windows 10/11 x64.

**Spec:** [docs/library-db-1.md](../../library-db-1.md), implementing the user-provided Phase DB-1 task brief.

## Global Constraints

- Target Minecraft Java 1.21.5 / DataVersion 4325.
- Windows 10/11 x64 is the sole formal runtime; Ubuntu CI remains nonblocking compatibility coverage.
- Do not add PostgreSQL, vector search, or a large ORM.
- Do not persist one SQLite row per voxel or modify original Litematic files.
- Do not rewrite generators, Assembly, ProjectEditor, project history, Schematic export, MCP tools, or saved Minecraft worlds.
- Only `huizhou_core` and `jiangnan_suzhou` are active; other region catalog entries cannot drive default selection.
- Treat historical sources as contextual references; user-facing proportion/style choices remain Minecraft creative settings.
- Preserve author/source information and default third-party redistribution permission to not granted.

## Review Focus

- Packed NBT values whose first long is zero or whose entries cross a 64-bit boundary: parser tests include both.
- Negative region dimensions and multiple regions: parser tests assert preserved origin/sign and union bounds.
- Old/new DataVersion values: parser and import tests assert explicit statuses, with no DataFixer claim.
- Duplicate or changed assets, corrupted files and absent previews: service tests assert idempotency, version increment and explicit errors.
- Inactive regions and planned modules: query tests assert they do not enter default rule/module results.

---

### Task 1: Litematic Models and Contract Tests

**Files:**
- Create: `jiangnan_agent/library/models.py`, `errors.py`, `litematic.py`
- Test: `tests/test_litematic_parser.py`

**Interfaces:**
- `read_litematic(path) -> LitematicDocument`
- `analyze_litematic(document, target_data_version=4325) -> LitematicAnalysis`
- Region models preserve signed size, position, palette properties, and packed states; analysis emits occupied bounds, material counts and Y layers.

- [x] Write synthetic NBT tests for packed boundaries/zero-first-word, signed sizes, multiple regions, bad palette indexes, corruption, and compatibility statuses.
- [x] Verify the new API is missing, then implement the parser and immutable models.
- [x] Run parser tests and read both actual local `.litematic` files.

### Task 2: SQLite Migrations and Library Service

**Files:**
- Create: `jiangnan_agent/library/database.py`, `service.py`, `migrations/001_initial.sql`, `002_module_knowledge_rules.sql`, `003_version_knowledge_registry.sql`
- Test: `tests/test_library_database.py`

**Interfaces:**
- `LibraryDatabase.initialize() -> int`, `transaction()`, `backup_to(path)`
- `LibraryService.initialize()`, `import_litematic(...)`, `verify_files(...)`, reference/material/region/rule/module/style queries.
- Database tables store relationships, immutable knowledge snapshots, file hashes, and aggregate counts; original block data remains in its source file.

- [x] Write failing tests for repeat migration, region/source/version queries, imports/deduplication, backup, rollback, and integrity errors.
- [x] Implement migrations, catalog synchronization, SHA-256 versioning, file verification, and transaction-safe backup.
- [x] Verify foreign keys, stable/versioned IDs, catalog-only isolation, and local reference style palette queries.

### Task 3: Catalogs, Style Profiles, and CLI

**Files:**
- Create: `jiangnan_agent/library/catalog/v1/modules.json`, `library/parameters/v1/minecraft_building_design.json`, `library/styles/v1/*.json`
- Modify: `jiangnan_agent/cli.py`, `pyproject.toml`, `.gitignore`, `README.md`
- Test: `tests/test_library_cli.py`

**Interfaces:**
- CLI prefix: `jiangnan library {init,import,list,show,materials,layers,previews,module,style,verify,backup}`.
- Default module listing exposes implemented assets only; planned module entries require explicit opt-in.
- `LibraryService` remains independent of CLI and suitable for a later MCP query adapter.

- [x] Add tests for library initialization and region listing from a clean temporary path.
- [x] Register current hall/corridor definitions and parameter schemas; leave unimplemented module families planned.
- [x] Add style profiles using measured palette candidates and keep semantic roof/wall labels unverified.
- [x] Run existing CLI and generate regression tests.

### Task 4: Real Imports, Documentation, and Release Verification

**Files:**
- Create: `docs/library-db-1.md`, `docs/superpowers/plans/2026-10-30-phase-db1-library.md`, local ignored `workspace/library/db1-import-report.json`
- Test: full `tests/` suite, MCP protocol test, Windows GitHub Actions.

- [x] Import both available local templates, compare dimensions/counts/SHA with existing conversion records, register existing preview paths, and leave source binaries untracked.
- [x] Write schema, CLI, backup, rights, regional status, and style semantics documentation.
- [x] Run full pytest and MCP stdio protocol test on the Windows virtual environment (284 passed; MCP protocol 1 passed).
- [x] Run wheel/package-data check; finish staged diff check after staging the explicit source files.
- [ ] Push the DB-1 branch and verify the required Windows CI run before review.
- [ ] Report actual imports, test/CI evidence, unverified game-world checks, and follow-up work; stop at DB-1.
