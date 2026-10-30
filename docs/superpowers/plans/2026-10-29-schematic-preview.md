# Schematic Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Render four deterministic Blender preview angles from a Sponge schematic and optionally create paired before/after images plus a block-difference report.

**Architecture:** Validate and read `.schem` through the existing schematic module, invoke the local Mine2Blend Node runtime with an argument list, validate its manifest, then invoke Blender background mode with a standalone Python rendering script. Keep every intermediate and report beneath the requested preview output directory.

**Tech Stack:** Python subprocess/pathlib/json, existing `nbtlib` schematic reader, Mine2Blend Node runtime, Blender 5.2.3 Python API, pytest.

**Spec:** `docs/superpowers/specs/2026-10-29-schematic-preview-design.md`

## Files

- Add `jiangnan_agent/preview/{__init__.py,mine2blend.py,blender_render.py}`.
- Extend `jiangnan_agent/cli.py` with `preview`.
- Add `tests/test_preview.py`; update README and roadmap for the verified Phase 6 CLI.

## Tasks

### Task 1 — Preview process contract

- [x] Write tests for schematic validation, tool discovery, no-overwrite behavior, process argument safety, converter manifest validation, and clear process errors.
- [x] Run the tests red before adding the preview implementation.
- [x] Implement the converter/Blender orchestration with injectable process execution and a result model.
- [x] Run focused tests and confirm no shell invocation is used.

### Task 2 — Blender four-view renderer

- [x] Add tests asserting the Blender command passes the standalone script and correct OBJ/output arguments.
- [x] Write `blender_render.py` to import OBJ with Mine2Blend axes, calculate mesh bounds, frame four cameras, render PNG files, and print a structured completion marker.
- [x] Validate all expected PNG paths after process exit; propagate Blender failure.

### Task 3 — Before/after comparison

- [x] Test exact added/removed/replaced block counts from `SchematicDocument` models.
- [x] Render before and after using a shared camera scale and separate images per angle.
- [x] Write deterministic `comparison.json` with source paths and counts.

### Task 4 — CLI, docs, and live acceptance

- [x] Test CLI argument validation and `--help`.
- [x] Document the user's local paths as an example without making them package defaults.
- [x] Run the preview command against an existing hall `.schem` and verify four images and `preview.json`.
- [x] Inspect the perspective and orthographic renders visually; correct framing/orientation before calling the phase complete.
- [x] If comparing two inputs, verify paired images and block counts against a direct schematic read.

## Review Focus

- Reject output collisions before spawning either external program.
- Do not use `shell=True`; preserve Windows paths with argument lists.
- Treat converter/Blender logs as diagnostics and never claim success without outputs and a completion marker.
- Keep preview outputs out of `workspace/exports` and outside Minecraft world directories.
- Ensure both comparison renders use the same camera scale so image differences are meaningful.
