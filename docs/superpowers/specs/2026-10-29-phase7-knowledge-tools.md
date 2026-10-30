# Phase 7 — Read-only Knowledge Tools

## Goal

Make the versioned, source-backed knowledge records usable by the current local Codex MCP workflow while preserving their evidence boundaries and leaving block generation unchanged.

## Approaches

1. **Read-only MCP query backed by the knowledge loader (chosen).** Return exact region/building/evidence matches with the source record, confidence, basis, and scope. It follows the existing local tool boundary and provides evidence on demand.
2. **Put all knowledge records into the MCP server instructions.** This avoids another tool but duplicates changing data into a static prompt and cannot select a requested region precisely.
3. **Translate every fact into generator defaults.** This would make rules actionable but is not justified by the current qualitative sources and would risk inventing traditional dimensions.

## Interface

Add `ProjectToolService.list_knowledge_rules(region=None, building_type=None, evidence_kind=None, knowledge_version=None) -> dict[str, Any]` and expose the same optional filters through a strict read-only MCP tool named `list_knowledge_rules`.

The result contains the resolved knowledge version, the applied filters, and matching rules. Each rule includes its evidence kind, region and building-type tags, basis, confidence, scope, statement, and its complete source record. Omitted version selects the latest packaged version. Region matching remains exact; no geography hierarchy is inferred. Unsupported evidence kinds fail explicitly.

## Constraints and Non-Goals

- Query packaged knowledge data only; do not read project files or write workspace files.
- Do not change generators, parameter defaults, module metadata, or project contents.
- Keep v1 knowledge queries available after v2 becomes the default.
- Keep user preferences, Minecraft adaptations, and literature facts distinguishable in the result.
- Candidate regions remain absent from executable rules until separately researched.

## Acceptance

- Service queries return region- and type-scoped v2 rules with verified source locators.
- Explicit v1 queries still return the v1 catalog.
- Invalid evidence-kind filters return a clear validation error.
- MCP advertises the strict tool and returns the same data as the service.
- The complete pytest suite passes.
