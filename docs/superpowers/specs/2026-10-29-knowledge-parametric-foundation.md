# Jiangnan Architect Agent — Knowledge & Parametric Foundation

## Intent

Add a versioned, traceable knowledge catalog, parameter registry, and module asset registry for the existing hall and corridor generators. Keep the current module and assembly APIs usable by existing callers, and make catalog-created modules reproducible after save, reload, edit, and transform.

## Current Architecture

- `HallParameters` and `CorridorParameters` validate generator inputs; `generate_hall` and `generate_corridor` build the voxel models.
- `hall_module` and `corridor_module` add stable anchors and save the generator parameters in `Module.parameters`.
- `ProjectToolService.create_module` and `ProjectEditor.regenerate_module` dispatch by the existing `kind` values `hall` and `corridor`.
- `Assembly` and project format v2 serialize module parameters, blocks, anchors, clearances, and transforms. Project format v1 remains readable.
- `generate_project_model` already prefers a non-empty Assembly and raises on Assembly failure; it only uses legacy settings when Assembly is empty.
- The README editor example currently constructs `hall-main` itself, and its test runs from a clean temporary directory. Replace this inline setup with a named, deterministic fixture and preserve the clean-workspace test.

## Approaches

1. **Add versioned catalogs and metadata (chosen).** Keep the current typed parameter classes and adapters as the execution authority. Resolve versioned JSON configuration into those classes, and store catalog references in an optional module metadata field. This keeps the generation surface stable and adds only an optional serialized field.
2. Replace the generator interfaces with a dynamic schema-driven engine. This would centralize more validation, but duplicate/rewrite stable geometry and editing paths and increase compatibility risk.

For previews, call the existing Mine2Blend converter CLI and Blender's background mode. This reuses the installed `.schem` parser, OBJ/MTL/atlas material pipeline, and existing Blender import behavior instead of adding a second schematic renderer.

## Data Model and Versioning

Ship small package resources under:

- `jiangnan_agent/knowledge/v1/rules.json`
- `jiangnan_agent/parameters/v1/hall.json` and `corridor.json`
- `jiangnan_agent/assets/v1/assets.json`

Python data models validate these files at load time. Each resource declares its integer version. Hall/corridor assets reference their parameter schema and current generator kind. Asset entries declare the actual existing anchor interfaces (`front`, optional `rear`, and `court_west_front`, `court_west_rear`, `court_east_front`, `court_east_rear` for halls; `start` and `end` for corridors) without replacing the existing `ConnectionAnchor` or `Connection` model.

Knowledge rules carry `rule_id`, `source_id`, applicable regions, building types, evidence kind, basis, confidence, and scope. Evidence kinds are `literature_fact`, `minecraft_adaptation`, and `user_preference`; confidence values are `high`, `medium`, `low`, and `unknown`. V1 contains only traceable generator behavior and the user's modular-design preference. No uncited historical dimensions are seeded; literature rules can be added when a source and locator are available.

Parameter resources describe independent inputs, derived outputs, hard constraints, and soft constraints. The hall schema covers building type, style label, bay count, bay spacing, depth, column height, roof type and section, eaves, materials, and passage interfaces. The corridor schema covers the corresponding fields plus length, width, and column spacing. `bay_spacing` maps to the existing hall `bay_width`; `roof_section.rise` maps to `roof_rise`; `interfaces` maps to the current passage options. Legacy generator field names remain accepted. Supplying conflicting canonical and legacy values is an explicit error.

The parser returns normalized inputs, deterministic derived values, typed generator parameters, and non-blocking soft-constraint warnings. It rejects unknown fields, unsupported schema versions, building-type mismatches, and inconsistent supplied derived values. Existing parameter dataclasses remain authoritative for hard geometry checks. A hall spacing below five blocks yields a Minecraft-specific warning because the current generator narrows its default front window; this is not a historical recommendation.

Catalog-created `Module` values store `asset_id`, asset version, knowledge version, parameter-schema ID/version, normalized input configuration, and derived values in a new optional `Module.metadata` mapping. `Module.parameters` keeps its existing generator-compatible shape. Empty metadata is omitted during serialization; older v2 module records load with empty metadata. The project format stays v2 because this is an additive optional module field. Transform operations and history snapshots preserve metadata.

The existing `create_module(kind=...)` MCP interface stays unchanged. Its hall/corridor path uses the versioned asset factory. Parameter edits to versioned modules merge into the normalized configuration and resolve against the recorded schema version; older unversioned modules retain their current edit path. Assembly-first generation behavior is unchanged.

## Non-Goals

- No replacement of `Module.parameters`, Assembly, or the geometry generators.
- No automatic city/block planning, vector database, or broad retrieval service.
- No style-specific geometry until supported by a generator and explicit evidence.
- No claim that current voxel constraints are regional or historical construction standards.
- No direct write into a Minecraft world.

## Validation

Tests cover catalog model validation and version loading; defaults and parameter changes; alias and derived-value conflicts; hard rejection and soft warnings; deterministic module output; metadata through edits/transforms/history; old project-v1/v2 loading; Assembly-first generation and no fallback; and README fixture execution from a clean directory.
