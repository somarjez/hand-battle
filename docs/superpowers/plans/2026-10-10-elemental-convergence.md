# Elemental Convergence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deliver the approved modular campaign game, developer documentation, Windows packaging metadata, and a pull request.

**Architecture:** Extract the prototype behind typed domain, vision, persistence, content, and Pygame presentation boundaries. Preserve the old launcher while routing it to the new app.

**Tech Stack:** Python 3.10-3.12, pytest, Pygame 2.x, OpenCV, cvzone, MediaPipe, NumPy, PyInstaller.

**Spec:** `docs/superpowers/specs/2026-10-10-elemental-convergence-design.md`

## Global Constraints

- Work on `feat/elemental-convergence`; keep the app usable from `python handTrack.py`.
- Use typed dataclasses/enums and seconds-based timing; avoid an ECS or speculative abstractions.
- Headless tests must not open a camera, window, or audio device.
- Save files are versioned, atomic, and recover from malformed JSON.

## Review Focus

- Missing/disconnected camera must lead to a recoverable setup screen, not a crash.
- Unrecognized or stale gestures must not keep casting indefinitely.
- Variable render frame rates must not change cooldown or progression timing.
- Corrupt saves and missing optional assets must fall back safely.
- Pause must freeze combat while allowing the vision service to remain active.

### Task 1: Domain, content, and persistence foundations

Create typed gesture/game/content models, five validated level definitions, difficulty rules, atomic save/settings repositories, dependency metadata, and unit tests.

### Task 2: Vision extraction and calibration

Extract pose classification, smoothing, camera discovery/worker behavior, and calibration profiles behind `VisionService`; test with landmark and camera fakes.

### Task 3: Game session and campaign progression

Implement seconds-based health, mana, lives, gesture commands, wave objectives, ability unlocks, Convergence, win/failure events, and deterministic tests.

### Task 4: Pygame scenes and polished presentation

Implement the scene stack, menu/setup/story/briefing/gameplay/pause/results/settings/sandbox/credits flows, responsive HUD, audio manager, and asset fallbacks with headless scene tests.

### Task 5: Compatibility, assets, packaging, and documentation

Route `handTrack.py` to the new app, add original artwork and attribution, PyInstaller configuration, and a detailed developer README covering architecture, setup, controls, content authoring, tests, packaging, and troubleshooting.

### Task 6: Whole-branch verification and delivery

Run unit/integration tests, compilation, headless smoke tests, README command checks, diff checks, final self-review, then commit, push, and open a draft PR against `main`.
