# Changelog

## 0.2.0

### Story and theme
- A real campaign arc: *The Hollow Dawn*. A prologue, a named keeper for each seal, per-wave titles, guardian
  dialogue (intro, two phase lines, defeat) shown in-game, stage outros, and an epilogue before the credits.
- Veyra, the Rift Sovereign, is the Warden who taught you; the finale recasts Convergence as a bond, not a weapon.
- A Codex with a lore tab (unlocked per cleared seal) and a bestiary (unlocked per enemy met).
- Story text lives in `story.py` and `data/levels.json`, separate from the rules.

### Levels and mechanics
- New wave type: **hunt** (defeat a quota while enemies keep arriving). Every stage is now defeat-all, hunt, survive, guardian.
- **Elite enemies** (tougher, gold-ringed, guaranteed loot) join the survive wave.
- **Stage hazards**, each telegraphed: rockfall, tidal surge, lightning storm, forge flare, and the Eclipse's mix.
- **Guardian phases** at two thirds and one third health: new dialogue, a banner and called minions.
- **Combo scoring** (chain kills within 3 s, up to x5) and a **three-star rating** per stage, saved with best scores.
- Survive waves keep the arena populated; blasts block orbs, defuse bombs and interrupt charging enemies;
  loot pick-ups (heart, regen, shield, boost, per-element mana); Convergence needs 10 kills and a held two-palm gesture.

### Audio
- The beeps are gone. Every sound effect (34) and music track (9) is synthesised in code, with no asset files:
  a distinct sound for each spell and event, a theme per stage, a boss theme, and victory/defeat stingers.
- Music crossfades between screens, ducks while paused, and a heartbeat plays when health is low.
- Fast-fire sounds are throttled; a failing sound device never affects play. Drop `assets/audio/<name>.ogg` to override any sound.
- `tools/export_audio.py` writes everything out as WAV files.

### Menus and settings
- Menus are now a reusable model (buttons, sliders, toggles, choices) with keyboard **and mouse** support, including slider dragging.
- Settings: master / music / effects volume, difficulty, fullscreen, reduced flash, reduced shake, gesture labels, camera, recalibrate, reset progress (confirmed).
- Pause menu (resume, restart, settings, quit), results screen with stars and stats, level select cards with stars and locks,
  paged How to Play, animated story scenes.

### Quality
- Camera and hands now fill any window shape; hand positions use the same crop as the picture (no stretching).
- Rendering is about 2.5x faster (a slow scalar add in the tint path was replaced), measured at 1080p.
- Save format v2 (stars, bestiary, prologue flag) loads v1 saves unchanged.
- 228 automated tests (campaign rules, audio synthesis, menu model, full-app headless flows) and a clean `ruff` check.
