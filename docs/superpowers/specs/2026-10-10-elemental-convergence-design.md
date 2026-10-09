# Elemental Convergence Design

## Goal

Turn the single-file hand-tracking prototype into a modular Windows desktop portfolio game with a guided setup, an original five-level campaign, a polished Pygame interface, saved progression, a sandbox, and a definite ending.

## Product

The player is a Warden restoring four elemental seals before confronting the Rift Sovereign. Earth, Water, Air, Fire, Lightning, and the two-hand Convergence ability retain the prototype's gesture vocabulary. Five authored stages introduce powers and enemies in sequence; each stage has story panels, three waves, a climax, results, and persistent unlocks. Classic effects remain available in Sandbox.

Menus use keyboard and mouse. Gameplay uses the camera and gestures. The mirrored camera feed remains the arena, with a cinematic high-contrast HUD. Story, Balanced, and Master presets affect combat forgiveness but not recognition thresholds. A failed level can be retried without losing unlocked stages.

## Architecture

`elemental_convergence.vision` owns cameras, gesture classification, smoothing, and calibration. `elemental_convergence.game` owns typed state, campaign definitions, combat rules, and persistence-facing snapshots. `elemental_convergence.presentation` owns Pygame scenes, rendering, transitions, and audio. `elemental_convergence.platform` owns saves, settings, assets, and paths. `handTrack.py` remains a compatibility launcher.

A vision worker publishes immutable gesture snapshots. The Pygame main thread advances a `GameSession` with delta-time values, consumes game events, and renders a read-only snapshot at a logical 1280x720 resolution. Level content is validated JSON. User files are versioned JSON beneath `%LOCALAPPDATA%/ElementalConvergence` and are written atomically.

## Experience and Accessibility

First run selects a camera and confirms framing plus the five poses. Settings expose camera, recalibration, fullscreen/fill, aim assist, hand overlay, master/music/SFX volume, reduced flash, and reduced shake. Important information uses icons and text rather than color alone. Missing optional art or audio degrades gracefully.

## Delivery Constraints

- Python 3.10-3.12; Windows-first; Pygame 2.x plus existing OpenCV/cvzone/MediaPipe stack.
- No online services, voice acting, mid-level checkpoints, branching campaign, or full entity-component framework.
- Original names and assets only; asset origins and licenses are recorded.
- Automated tests do not require a physical camera or audio device.
