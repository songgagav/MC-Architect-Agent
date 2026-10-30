# Phase 7 Knowledge Tools Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Expose scoped, cited Knowledge Base records through one read-only local MCP tool.

**Architecture:** `ProjectToolService` loads the requested/default `KnowledgeBase`, validates optional filters, and serializes each matching rule with its full source record. A strict FastMCP wrapper delegates directly to the service; AGENTS and README describe when the tool should be used.

**Tech Stack:** Python 3.12, existing knowledge dataclasses, FastMCP, pytest.

**Spec:** `docs/superpowers/specs/2026-10-29-phase7-knowledge-tools.md`

## Global Constraints

- Region matching is exact and does not infer geographic inheritance.
- Knowledge v1 remains queryable; omitted version resolves to the latest packaged knowledge base.
- This read-only tool does not load or write a project and does not change block generation.
- Preserve `literature_fact`, `minecraft_adaptation`, and `user_preference` distinctions.

## Review Focus

- A user preference must never be returned as a literature fact.
- A narrow UNESCO site tag must not match the broader Huizhou tag.
- Unknown evidence-kind names must fail explicitly instead of silently returning an empty list.
- An explicit v1 request must not resolve to v2.
- MCP calls must not create project or export files.

---

### Task 1: Read-only service query

**Files:**
- Modify: `tests/test_agent_tool_service.py`
- Modify: `jiangnan_agent/agent_tools/service.py`

**Interfaces:**
- `list_knowledge_rules(region: str | None = None, building_type: str | None = None, evidence_kind: str | None = None, knowledge_version: int | None = None) -> dict[str, Any]`.
- Each returned rule includes its `source` object from the selected knowledge base.

- [x] **Step 1: Write failing tests** for exact region/type matching, full source details, explicit v1, invalid evidence kind, and no workspace writes.
- [x] **Step 2: Run the service tests and confirm the new method is missing.**
- [x] **Step 3: Implement the service query** using `load_knowledge_base` and `KnowledgeBase.rules_for` only.
- [x] **Step 4: Run the focused service tests.**

### Task 2: MCP exposure and user instructions

**Files:**
- Modify: `tests/test_mcp_server.py`
- Modify: `jiangnan_agent/agent_tools/mcp_server.py`
- Modify: `AGENTS.md`
- Modify: `README.md`

- [x] **Step 1: Add an MCP contract test** for the strict schema and a cited, region-scoped response.
- [x] **Step 2: Run it red** to confirm `list_knowledge_rules` is not registered.
- [x] **Step 3: Add the typed MCP wrapper and document** that regional claims must retain source, confidence, evidence kind, and scope.
- [x] **Step 4: Run MCP and README contract tests.**

### Task 3: Full verification

- [x] **Step 1: Run the full test suite** with `\.venv\Scripts\python.exe -m pytest -q`.
- [x] **Step 2: Review the staged diff** and keep Phase 7 data changes separate from Phase 6 commit `9eec9fa`.
