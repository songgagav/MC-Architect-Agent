# Huizhou Knowledge Evidence and Regional Scope

## Goal

Extend the existing traceable knowledge catalog with sourced records for the user-selected Jiangnan–Huizhou focus, while keeping unsupported historical dimensions and unselected regional styles out of executable generation rules.

## Design

- Keep `knowledge/v1/rules.json`, the v1 asset catalog, and their meaning unchanged.
- Add knowledge catalog v2 by carrying forward the existing records and adding sourced records from UNESCO's Xidi/Hongcun listing and Huangshan Municipal Gazetteer Office summaries. Record source, exact applicability, evidence kind, basis, confidence, and scope.
- Use exact region identifiers. The initial documented identifiers are `cn.anhui.south.huangshan.yixian.xidi-hongcun`, `cn.anhui.south.huizhou`, and `user.selected.lower_yangtze.jiangnan_huizhou`. Region matching is exact; no unstated geographic inheritance is inferred.
- Distinguish literature facts, Minecraft adaptations, and user preferences. The user's selected style scope and the two `.litematic` files are preferences/references, never historical evidence.
- Treat the files under `Template/` as visual references only. Store their relative names and SHA-256 digests in the source locator. Do not copy or modify the binary files.
- Add asset catalog v2 as a complete snapshot containing the existing v1 hall/corridor entries plus asset version 2 entries bound to knowledge base v2 and the unchanged parameter schema v1. Default lookups select the latest catalog/asset; explicit v1 lookups remain supported.
- Add exact-region and building-type filtering to `KnowledgeBase.rules_for` without changing existing evidence-kind calls.
- List other candidate regions in documentation only. They must not appear as active knowledge rules, asset rules, or generator behavior.
- Do not change voxel generation or infer traditional dimensions from qualitative descriptions.

## Evidence boundary

UNESCO's listing supports site-specific descriptions of Xidi and Hongcun, their settlement layout, architecture, decoration, waterways, and construction characteristics. Huangshan Municipal Gazetteer Office pages provide qualitative descriptions of Hui residential forms and details. These sources do not establish universal dimensions or a complete, uniform style across the whole middle/lower Yangtze region.

## Acceptance

- Knowledge v1 loads unchanged; the default loads the latest version.
- Knowledge v2 source IDs resolve, and region/building-type filtering returns only exact matches.
- Hall and corridor asset v2 entries reference knowledge v2 and parameter schema v1; explicit asset v1 modules remain reproducible with unchanged blocks and metadata after project editing.
- Both local template references are traceable by filename and SHA-256, and are categorized as user preferences.
- Candidate regions remain documentation-only.
- README and package data include the latest resources; the full test suite passes.
