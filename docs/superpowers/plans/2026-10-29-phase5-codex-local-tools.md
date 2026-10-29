# Phase 5 Codex Local Building Tools Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the current Codex session create, inspect, edit, validate, and export Jiangnan Minecraft projects through bounded local Python tools.

**Architecture:** A local stdio MCP server exposes a small tool service backed by the existing generators, Assembly, `ProjectEditor`, project serializer, and schematic IO. Codex remains the only natural-language orchestrator; project and export paths are confined to the repository workspace, and each project mutation creates a history revision before an atomic save.

**Tech Stack:** Python 3.12; existing package dependencies; optional Python MCP SDK `mcp>=1.26,<2`; `pytest`.

**Spec:** `docs/superpowers/specs/2026-10-29-phase5-codex-local-tools-design.md`

## Global Constraints

- Minecraft target is Java 1.21.5 / DataVersion 4325.
- Codex is the only model orchestrator; the Python project does not call an OpenAI model API or require `OPENAI_API_KEY`.
- MCP is optional; normal package, CLI, and dev/test installation remain usable without the MCP extra.
- The MCP process is stdio-only and is bound to `E:\MCbuild`.
- Reads and writes are limited to `workspace/projects/` and `workspace/exports/`; reject absolute paths, traversal, and symlink escapes.
- New project and `.schem` files refuse overwrite; no tool deletes project files or writes Minecraft saves.
- Every change to an existing project goes through `ProjectEditor`, records exact changed module IDs and block deltas, then saves atomically.
- Assembly-first generation behavior remains fixed; a nonempty invalid Assembly must fail without falling back to legacy settings.

## Review Focus

- **A path uses `..`, an absolute drive, or a symlink to escape an allowed root:** refuse before opening or writing; pin with `test_paths_reject_traversal_absolute_and_symlink_escape` in Task 2.
- **An edit targets a missing module, unsupported kind, or invalid generator parameter:** return an actionable error without saving or adding a revision; pin with `test_invalid_tool_edit_leaves_project_and_history_unchanged` in Task 2.
- **A new connected module is rotated/translated to an anchor or an existing module is transformed:** preserve state, anchors, and exact revision deltas; pin with `test_connect_new_module_records_aligned_module_and_connection` and `test_transform_module_records_exact_delta` in Task 1.
- **Adding/removing a connection when unrelated edges already exist:** report only endpoints of edges whose serialized connection actually changed; pin with `test_connect_new_module_only_marks_endpoints_of_the_new_connection`.
- **An Assembly is nonempty but invalid while legacy settings are also present:** report the Assembly failure and do not export the legacy building; pin with `test_export_schematic_does_not_fallback_from_invalid_assembly` in Task 2.
- **The destination project or schematic already exists:** refuse without changing its bytes; pin with `test_create_and_export_refuse_existing_files` in Task 2.
- **Concurrent clients pass the initial missing-path check for the same new destination:** only one may publish the project or schematic; pin with the concurrent create/export tests in Task 4.

---

### Task 1: Make project mutations revision-aware

**Files:**
- Modify: `jiangnan_agent/io/project_editor.py`
- Test: `tests/test_project_editor.py`

**Interfaces:**
- Add `ProjectEditor.add_module(module: Module, message: str) -> ProjectRevision`.
- Add `ProjectEditor.transform_module(module_id: str, operation: str, message: str, *, offset: Position | None = None, quarter_turns: int | None = None, axis: str | None = None) -> ProjectRevision`; accept only `translate`, `rotate_y`, or `mirror`, each with its required argument and no conflicting arguments.
- Add `ProjectEditor.connect_modules(first_module_id: str, first_anchor_name: str, second_module: Module | str, second_anchor_name: str, message: str) -> ProjectRevision`; a `Module` argument adds and auto-aligns a new module, while a string joins two existing, already aligned modules.
- Preserve `replace_module`, `regenerate_module`, undo, and redo contracts.

- [x] **Step 1: Add failing tests** named `test_connect_new_module_records_aligned_module_and_connection` and `test_transform_module_records_exact_delta`, plus cases for add-module history/block deltas, undo/redo after add and connect, and rejection of unrecorded Assembly mutation before any new operation.
- [x] **Step 2: Run** `.\.venv\Scripts\python.exe -m pytest tests/test_project_editor.py -q`; verify the new editor methods are missing or the new assertions fail for the intended behavior.
- [x] **Step 3: Implement** the three public editor methods by using the existing `Assembly`, `connect_modules`, and transform functions, then pass each result through `_record` only after `_ensure_current_snapshot` succeeds.
- [x] **Step 4: Run** `.\.venv\Scripts\python.exe -m pytest tests/test_project_editor.py tests/test_project_history.py -q`; expect all editor and history tests to pass.
- [x] **Step 5: Commit** as `feat: record assembly mutations in project history`.

### Task 2: Add bounded project tool service

**Files:**
- Create: `jiangnan_agent/agent_tools/__init__.py`
- Create: `jiangnan_agent/agent_tools/project_access.py`
- Create: `jiangnan_agent/agent_tools/service.py`
- Create: `jiangnan_agent/io/project_generation.py`
- Modify: `jiangnan_agent/cli.py`
- Test: `tests/test_agent_tool_paths.py`
- Test: `tests/test_agent_tool_service.py`
- Test: `tests/test_project_generation.py`

**Interfaces:**
- `ProjectAccess(workspace_root: Path)` derives `workspace/projects/` and `workspace/exports/` from the repository root. `resolve_project_path(relative_path: str, *, operation: Literal["read", "edit", "create"]) -> Path` requires an existing file for `read`/`edit` and a nonexistent file for `create`; `resolve_export_path(relative_path: str) -> Path` requires a nonexistent destination. Both reject absolute paths, traversal, wrong suffixes, and symlink escapes.
- `generate_project_model(project: JiangnanProject) -> VoxelModel` owns the current Assembly-first/legacy generation rule and is called by both CLI generation and the MCP service.
- `ProjectToolService(workspace_root: Path)` exposes JSON-serializable methods with relative `project_path` values: `list_projects() -> list[dict]`, `get_project(project_path: str) -> dict`, `list_modules(project_path: str) -> list[dict]`, `get_module(project_path: str, module_id: str) -> dict`, and `create_project(name: str, project_path: str) -> dict`.
- Its write methods are `create_module(project_path: str, module_id: str, kind: str, parameters: dict, *, attach_to_module_id: str | None = None, attach_to_anchor_name: str | None = None, module_anchor_name: str | None = None) -> dict`, `set_parameters(project_path: str, module_id: str, parameter_updates: dict) -> dict`, `transform_module(project_path: str, module_id: str, operation: str, *, offset: tuple[int, int, int] | None = None, quarter_turns: int | None = None, axis: str | None = None) -> dict`, `connect_modules(project_path: str, first_module_id: str, first_anchor_name: str, second_module_id: str, second_anchor_name: str) -> dict`, and `replace_module(project_path: str, module_id: str, kind: str, parameters: dict) -> dict`.
- Its read/delivery methods are `validate_assembly(project_path: str) -> dict`, `inspect_changes(project_path: str, revision_id: int | None = None, limit: int = 20) -> dict`, and `export_schematic(project_path: str, output_path: str) -> dict`. Result dictionaries contain JSON-compatible summaries, not full voxel maps.
- Module creation/regeneration/replacement supports only `hall` and `corridor`. `create_module` may accept all-or-none anchor connection fields to place a new module using the existing connection algorithm. `inspect_changes` returns revision metadata, changed IDs, and bounded counts/summaries, never the full project block map.
- Every mutating service method saves to the same explicit project file after recording history; output tool results include the operation, project, revision, affected IDs, validation result where relevant, and resulting file path/count.

- [x] **Step 1: Add failing path test** `test_paths_reject_traversal_absolute_and_symlink_escape` for valid workspace-relative paths, `..`, absolute Windows paths, wrong suffixes, and symlink escape; use a resolver stub if local Windows symlink permissions are unavailable. Cover existing output paths in `test_create_and_export_refuse_existing_files` in Step 5.
- [x] **Step 2: Run** `.\.venv\Scripts\python.exe -m pytest tests/test_agent_tool_paths.py -q`; confirm the path policy is not implemented.
- [x] **Step 3: Implement** `ProjectAccess` using resolved-path containment checks, project/export suffix checks, and an explicit no-overwrite check for new outputs.
- [x] **Step 4: Run** `.\.venv\Scripts\python.exe -m pytest tests/test_agent_tool_paths.py -q`; expect all boundary cases to pass.
- [x] **Step 5: Add failing service tests** named `test_invalid_tool_edit_leaves_project_and_history_unchanged`, `test_export_schematic_does_not_fallback_from_invalid_assembly`, and `test_create_and_export_refuse_existing_files`, plus cases for project/module discovery, creating a three-bay hall, parameter edits by stable ID, anchored module creation, transforms/connections, concise revision inspection, validation output, and schematic export/readback.
- [x] **Step 6: Run** `.\.venv\Scripts\python.exe -m pytest tests/test_agent_tool_service.py tests/test_project_generation.py -q`; confirm failures are due to missing service behavior.
- [x] **Step 7: Implement** the service by composing `ProjectAccess`, generators/adapters, `ProjectEditor`, validation, `generate_project_model`, `save_project`, and schematic IO; refactor `cli.py` to call the shared generation function without changing its behavior.
- [x] **Step 8: Run** `.\.venv\Scripts\python.exe -m pytest tests/test_agent_tool_paths.py tests/test_agent_tool_service.py tests/test_project_generation.py tests/test_cli.py tests/test_schematic_io.py -q`; expect all targeted tests to pass, including the no-fallback and no-overwrite cases.
- [x] **Step 9: Commit** as `feat: expose bounded local building tools`.

### Task 3: Expose the service over MCP stdio

**Files:**
- Create: `jiangnan_agent/agent_tools/mcp_server.py`
- Modify: `pyproject.toml`
- Test: `tests/test_mcp_server.py`

**Interfaces:**
- `create_mcp_server(workspace_root: Path) -> FastMCP` registers exactly the Task 2 service methods as MCP tools with strict, typed argument schemas.
- `main() -> int` parses `--workspace-root`, derives the allowed project/export directories, constructs the service, and runs stdio transport only; protocol output uses stdout and diagnostics use stderr.
- Add optional extra `mcp = ["mcp>=1.26,<2"]` and script `jiangnan-mcp = "jiangnan_agent.agent_tools.mcp_server:main"`; importing the regular CLI must not import the optional SDK.

- [x] **Step 1: Add failing MCP client tests** that start the server over stdio, discover the exact tool names and schemas, call `list_projects` and `create_module`, and verify unrelated stdout is absent; add `test_cli_import_succeeds_when_mcp_module_is_unavailable` using an import blocker.
- [x] **Step 2: Run** `.\.venv\Scripts\python.exe -m pytest tests/test_mcp_server.py -q`; confirm the server entry point or tool discovery is missing.
- [x] **Step 3: Implement** the FastMCP adapter as thin wrappers around `ProjectToolService`; declare strict arguments and keep MCP imports inside the optional server module.
- [x] **Step 4: Add** the optional dependency group and `jiangnan-mcp` script entry point.
- [x] **Step 5: Run** `.\.venv\Scripts\python.exe -m pip install -e ".[dev,mcp]"` and `.\.venv\Scripts\python.exe -m pytest tests/test_mcp_server.py tests/test_agent_tool_service.py -q`; expect install success and all protocol/service checks to pass.
- [x] **Step 6: Run** `pytest tests/test_mcp_server.py::test_cli_import_succeeds_when_mcp_module_is_unavailable -q`; expect the regular CLI import to succeed with imports of `mcp` blocked.
- [x] **Step 7: Commit** as `feat: serve building tools over local MCP`.

### Task 4: Connect the repository to Codex and document the workflow

**Files:**
- Create: `AGENTS.md`
- Modify: `README.md`
- Modify: `docs/roadmap.md`

**Interfaces:**
- `AGENTS.md` tells Codex to use the building tools for architecture tasks, read before editing, honor explicit project/module scope, ask when the target is ambiguous, and never write Minecraft saves.
- README instructions install `.[dev,mcp]`, register the local process with `codex mcp add jiangnan-architect -- "E:\MCbuild\.venv\Scripts\python.exe" -m jiangnan_agent.agent_tools.mcp_server --workspace-root "E:\MCbuild"`, verify with `codex mcp list`, and explain that Codex may need reload/restart to discover newly registered tools.
- Roadmap marks Phase 5 implementation complete only after automated and live Codex acceptance; actual Minecraft/WorldEdit placement remains a separate manual check.

- [x] **Step 1: Add a documentation check** that confirms the README command and declared MCP tool names match the server contract, and that `AGENTS.md` contains the explicit-scope/no-world-write instructions.
- [x] **Step 2: Run** `.\.venv\Scripts\python.exe -m pytest tests/test_readme_examples.py tests/test_mcp_server.py -q`; confirm the new documentation assertions fail before the instructions are added.
- [x] **Step 3: Implement** the README setup/usage section, repository instructions, and accurate roadmap status notes.
- [x] **Step 4: Run** `.\.venv\Scripts\python.exe -m pytest tests/test_readme_examples.py tests/test_mcp_server.py -q`; expect the documentation and MCP contract checks to pass.
- [x] **Step 5: Install and register** the MCP extra in the current `E:\MCbuild\.venv`, run `codex mcp add` for the bounded local server, and verify its registration with `codex mcp list`.
- [x] **Step 6: Run a live Codex acceptance**: create and inspect a three-bay hall through MCP, validate and export a `.schem`, change `hall-main` to five bays, verify both revisions, reread the schematic as Sponge v3/DataVersion 4325, then confirm undo/redo restores three/five bays and validation passes. No Minecraft save is touched.
- [x] **Step 7: Run the full suite** with `.\.venv\Scripts\python.exe -m pytest`; all 149 repository tests pass.
- [x] **Step 8: Commit** as `feat: connect Codex to Jiangnan building tools` (`8a292eb`, amended once to record final plan status).

## Execution Notes

- Work in the existing `phase-3-modular-assembly` checkout; do not create a worktree or push changes.
- Run commands from `E:\MCbuild` with the repository virtual environment.
- Keep API credentials out of the implementation and Codex MCP entry; this integration does not call a model API.
- Do not claim live Codex acceptance unless the registered server is visible to Codex and the natural-language tool sequence has actually run.
