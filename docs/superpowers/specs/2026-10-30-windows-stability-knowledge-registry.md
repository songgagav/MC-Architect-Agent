# MC-Architect-Agent Windows Stability and Knowledge Registry Spec

## Goal

Stabilize the existing `phase-3-modular-assembly` code line for Windows 10/11 x64 and Python 3.12, then add auditable, versioned regional knowledge and parameter/asset registry records for the existing hall and corridor generators.

## Fixed scope

- Minecraft Java Edition 1.21.5 is the output target.
- Windows is the only formal runtime and required CI platform. Ubuntu may run as non-blocking compatibility coverage.
- Continue generating individual buildings and garden components; do not add town planning.
- Preserve Assembly-first generation, empty-Assembly legacy generation, no implicit fallback, and existing Assembly, ProjectEditor, history, and Schematic APIs.
- Only `huizhou_core` and `jiangnan_suzhou` are active knowledge profiles. Other named regions are catalog-only and have no executable rules.
- Every active historical claim must cite a source and a specific locator. If a claim, date, or dimension cannot be verified, mark it pending and keep it out of normal active-rule queries. Do not present game-grid defaults as historical standards.
- Version additions must not invalidate the existing knowledge v1/v2, parameter schema v1, or asset catalog v1/v2.
- Real MCP, Blender/Mine2Blend, and Minecraft/WorldEdit acceptance is reported only when executed in those applications; otherwise provide a Windows checklist and mark the gate pending.

## Deliverables

1. Windows-required CI with UTF-8 output and `[dev,mcp]`; optional non-blocking Ubuntu compatibility job.
2. Cross-platform rejection of Windows absolute/root/drive/traversal paths and resolved symlink escapes.
3. Explicitly supported 1.21.5 directional state rotation/mirroring, including orientation; reject unsupported values rather than silently retaining or corrupting them.
4. Versioned source, rule, and region-profile records with complete provenance fields and active-region filtering.
5. Versioned hall/corridor parameter and asset registrations, provenance categories, region/rule links, and generator compatibility metadata.
6. Regression tests, source/region/parameter/compatibility/determinism/rotation/Schematic-readback coverage, and Windows real-application acceptance instructions.
