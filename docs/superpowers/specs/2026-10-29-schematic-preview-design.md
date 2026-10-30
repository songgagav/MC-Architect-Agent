# Phase 6 — Schematic Preview and Visual Review

## Intent

Create local, repeatable 3D previews from Sponge `.schem` files using the existing Mine2Blend converter and the user's Blender installation. Support top, front, side, and perspective renders and a paired before/after review.

## Current Architecture and Feasibility

The project writes Sponge v3 `.schem` files. The local Mine2Blend Windows runtime accepts `import --input <file> --output <dir> --format obj --metadata-json <file> --preserve-adjacent-faces`, writes OBJ/MTL/atlas and a run manifest, and successfully converted a project hall schematic. Blender at `D:\SteamLibrary\steamapps\common\Blender\blender.exe` is 5.2.3. Its installed render engine identifier is `BLENDER_EEVEE`; the Mine2Blend importer uses `bpy.ops.wm.obj_import` with forward axis `NEGATIVE_Z` and up axis `Y`. A real background-render spike produced four PNG views.

The current installed Mine2Blend source is local and ignored by Git. The preview feature therefore accepts an explicit Mine2Blend root and Blender path; it does not package these binaries or require them for the ordinary Python test suite.

## Approaches

1. Reimplement schematic parsing and voxel rendering in this project. Rejected because it duplicates Mine2Blend's block meshes/materials and risks visual mismatch.
2. Reuse Mine2Blend's CLI output and let Blender's background Python import the OBJ and render cameras. Chosen because both stages are present locally and were exercised with the current `.schem` format.

## Interface

Add `jiangnan preview --schematic <file.schem> --output-dir <new-or-empty-dir> --mine2blend-root <addon-root> --blender <blender.exe> [--compare-before <file.schem>]`.

The command validates each schematic before invoking external tools, refuses to overwrite preview outputs, invokes the converter without a shell, checks its manifest and OBJ output, then launches Blender in factory-startup/background mode. It writes `top.png`, `front.png`, `side.png`, `perspective.png`, `preview.json`, and converter artifacts. When `--compare-before` is set, it renders the same four camera views for both models with a shared framing scale and writes `before_*.png`, `after_*.png`, and `comparison.json` with exact added/removed/replaced block counts.

Tool paths are passed by flags (and may later gain config-file defaults). The renderer imports the converter OBJ/MTL/atlas through Blender's OBJ importer, uses deterministic camera framing and render settings, and never opens or modifies a Minecraft save. Orthographic scale accounts for the 1200 x 900 landscape output aspect ratio so tall side views do not crop. External process errors are surfaced; there is no fallback renderer.

## Non-Goals

- No Blender GUI automation or automatic saving of editable `.blend` scenes in v1.
- No automatic aesthetic approval or claims that the renders validate historical accuracy.
- No dependency on Mine2Blend binaries for Python tests or package installation.
- No direct game-world changes.

## Validation

Unit tests mock process boundaries and cover missing tools, bad input, converter failure/malformed manifest, Blender failure, no-overwrite behavior, report contents, comparison counts, and aspect-aware framing. A local smoke run uses the installed converter and Blender and verifies all four renders are present and readable. Manual inspection checks the camera orientation and rendered materials; the initial side-view crop was fixed and the full-frame result re-rendered.
