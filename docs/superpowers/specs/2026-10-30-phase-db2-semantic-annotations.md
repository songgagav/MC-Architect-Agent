# Phase DB-2: Semantic Annotation and Reference Components

## Intent

Extend the DB-1 SQLite library so the two imported Litematic references can be analyzed into reviewable Minecraft component annotations, static reference components, and versioned style-analysis reports. Preserve the existing generator, Assembly, project, Schematic, MCP, and user-save interfaces. Read source projections without modifying them.

## Inputs and constraints

- Build on DB-1 schema v3 and the existing `LibraryService`, `LitematicDocument`, and `LitematicRegion.iter_non_air_blocks()` interfaces.
- Target Minecraft Java 1.21.5 / DataVersion 4325, while allowing older Litematic DataVersion files to be imported and analyzed. DataVersion remains source metadata; do not rewrite or claim conversion.
- Preserve both `reference.fangtang` and `reference.liusufang-frame` as unassigned regional inspirations unless the user supplies provenance.
- Automatic semantic findings are `candidate`; only a review operation with a human reviewer may create a `verified` revision.
- Static reference components remain separate from parameterized generators and are never marked implemented.
- Existing style JSON versions remain immutable. Candidate analysis is stored independently and cannot alter a style profile.

## Approaches

1. **One SQLite row per selected block.** Rejected because a region-wide annotation would duplicate thousands of voxels and make edits/queries unnecessarily large.
2. **Versioned annotation geometry with exact selections encoded as X-runs.** Selected. SQLite stores one row per annotation revision and its geometry; region and half-open box selectors remain compact, while exact block sets use deterministic `[y,z,x_start,x_end_exclusive]` runs. Analysis derives block counts and state data by reading the original file and checking its SHA-256.
3. **Sidecar JSON files as the only annotation store.** Rejected because review state, revision history, component foreign keys, and repeatable queries would lose SQLite's transaction and constraint guarantees.

## Data and behavior

- Add schema migration 004 for append-only semantic annotation revisions, static reference components, and style-analysis snapshots. Existing DB-1 tables and rows remain intact.
- Support three spatial selectors in source coordinates: a named Region's occupied cells; a half-open coordinate box `[min,max)` within a Region; or an exact occupied coordinate set. Reject unknown Regions, duplicate/off-Region/air coordinates, malformed bounds, and invalid labels.
- Use the requested semantic labels: `roof_surface`, `roof_ridge`, `eaves`, `column`, `beam`, `wall`, `door`, `window`, `floor`, `foundation`, `railing`, `decoration`, and `unknown`.
- Annotation creation and edits append a revision. Rule-generated annotations always start as `candidate`; manual annotations also remain pending until the explicit review operation records reviewer, decision, and note.
- Compute annotation summaries deterministically from the hash-verified original: occupied bounds, dimensions, exact selected block coordinates (X-runs), BlockState/material counts, and Y-layer distribution. Unknown or overlapping structural interpretations remain explicitly unresolved.
- Register a `ReferenceComponent` only from a verified annotation revision. Store source asset/version, label, source Region, local origin, dimensions, bounds, material/state summary, exact coordinate runs, review provenance, and style tags. Mark it `static_reference` and `not_parameterized`.
- Save style-analysis runs against exact style and asset versions. Include directly measured dimensions, palette counts, layer profiles, and only verified semantic summaries. Store heuristic interpretations as candidates. Do not change `jiangnan_mc_classic` or `huizhou_mc_classic` JSON in this phase; a later reviewed registry version can adopt accepted findings.
- Add Python service methods and small CLI commands for annotation proposal/list/create/update/review/analyze, component list/show/register/report, and style-analysis create/list/show/review/export.
- Keep file writes non-overwriting and scoped to explicit report paths. Database migrations and imports remain transactional; source Litematics stay read-only.

## Heuristic boundary

The first rule set may propose candidates from explicit Minecraft block identities and simple spatial/material patterns. Every proposal records a rule ID/version and explanation. A rule may return no candidate when the source does not support a defensible guess. No category is inferred from a filename, regional name, or historical assumption. The `unknown` label remains available for manual annotations and unclassified analysis output.

## Verification

Tests cover migration from DB-1 with rows preserved, geometry on negative signed Regions, exact X-run round trips, annotation revision/review gates, deterministic summaries, static-only component registration, style candidate isolation, CLI round trips, unchanged source SHA-256, and all existing Assembly/generate/project/Schematic/MCP regressions. Real local templates are analyzed by the production parser; reports state that semantic candidates are unverified and that no Minecraft version conversion was performed.
