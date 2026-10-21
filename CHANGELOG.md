# Changelog

## Unreleased - tutorial sandbox, illustrated How to Play, Codex portraits

- **Gesture Sandbox is now a guided lesson** (`sandbox.py`): show your hand, then make Earth, Water, Air, Fire and Lightning in turn and the Kalampag with two palms, then free practice. Each step shows a drawn hand-sign, a hold ring that fills as you keep it steady, live feedback ("I see Air. Spread your fingers wider"), tips, and a clickable step tracker. The storyteller coaches each step aloud. Enter skips, Left/Right changes step, R restarts.
- **How to Play is an illustrated lesson**: Lola Auring introduces each page, the rules sit beside an animated picture (hand-signs, element reactions, a Tikbalang charge being interrupted, pick-ups, the Kalampag against the Bakunawa, the four place hazards), and she reads each page aloud.
- **Codex shows the creatures**: every Bestiary and Seal entry has a breathing portrait with a glow and a pedestal, chips for what it is weak to and resists, and a thumbnail in the list. Creatures you have not met are dark silhouettes.
- **Sprites are polished**: top-left lighting, a shaded rim and a bright edge on every creature, plus idle breathing (and a sway for the ghostly ones) in battle.
- **Credits**: Main Creator Jezreel Ramos; Support Judeelyn Capili and Shaila Patrice Avellaneda.

## Earlier - narrator, creature and hazard art

- **Narrator:** the prologue, each place's introduction, the epilogue and the end-of-level story are now read aloud in your system's text-to-speech voice (Windows SAPI via `pyttsx3`). Each line of text fades in as the narrator reaches it; Enter skips; music lowers while it speaks. Settings has a **Narrator** toggle, and it follows the master volume. If no voice is available the story scenes work exactly as before. It falls back to the operating system's own speech command when `pyttsx3` is missing or fails, reports why in the terminal, and has a self-test: `python -m elemental_convergence.narrator`. `SINAG_VOICE=<part of a voice name>` picks a voice; `SINAG_NARRATOR=off` disables it.

- Every enemy and guardian is now a creature from Philippine folklore, drawn in `presentation/sprites.py` (supersampled vector art, cached): Manananggal (shooter), Tikbalang (charger), Bungisngis (sniper), Mandirigma with kalasag and lantaka (gunner), Duwende on his punso (bomber), Diwata with a sampaguita crown (caster), Sigbin (spinner), Santelmo (sweeper), Babaeng Puti (blinker); and the guardians Kapre among balete roots, Siyokoy King, the Typhoon with okir-carved feathers, Blaze of Taal rising from Taal Lake, and the Bakunawa swallowing the crescent moon. Tribal batok bands, okir curls and sampaguita appear as motifs. Health-bar labels and Codex entries use the folklore names.
- Hazards look like what they are: falling boulders with ground shadows (landslide), lobbed lava globs and pools (eruption), a thundercloud and forked lightning (strike), a foaming water wall (rapids).
- Walls now mark their gap with green chevrons and lane edges.
- Snapshots carry the extra info the view needs (`BombSnapshot.kind`, `LaserSnapshot.hazard`, `ShotSnapshot.vx/vy/style`).

## 0.3.0 - Sinag

### Identity and story
- The game is now **Sinag**, rebuilt around Philippine folklore. The Bakunawa has swallowed the sun and moon; five rays of light are
  hidden in real places: Mount Makiling, the Pagsanjan Gorge, the Basco Lighthouse in Batanes, and Taal Island, then the dragon itself.
- New, specific characters (Maria Makiling, Mang Amado the boatman, Ate Luz the lighthouse keeper, Tatay Berting the fish farmer,
  Lola Auring) and guardians (Kapre of the Balete, Siyokoy King, The Typhoon, Blaze of Taal, Bakunawa) replace the stock fantasy names.
- The ultimate is now **Kalampag**, the real remedy for the Bakunawa: make a racket. It plays a crowd of pots and pans.
- Plainer, warmer writing throughout, with an epilogue that lands on "Kumain ka na ba?".

### Design
- The AI-generated menu illustration is retired (kept in `images/legacy/`, unused). Every background is now drawn in code:
  six layered scenes with grain and their own animation.
- New interface: ink-and-gold palette, chamfered panels with a woven diamond band, an eight-ray sun as selection marker and rating,
  a SINAG wordmark, and the bundled Alegreya typeface (SIL OFL). Optional hand-made overrides: `assets/images/override/<stage>.png`.
- Play without a camera now shows the place's scene instead of a gradient.

### Mechanics
- **Weaknesses and resistances** for every enemy and guardian (shown as a coloured dot by the name and in the Codex).
- **Elemental reactions:** Water soaks; Lightning shocks a soaked enemy (damage + stun); Fire on a soaked enemy makes steam
  (area damage); Fire burns a dry one; Air spreads burning (firestorm); Earth slows. Guardians resist stuns.
- Stun, slow and burning affect movement, attacks and damage over time, with their own visuals.
- **Graphics: Auto / High / Fast**, with a governor that cannot flicker between modes.

### Audio
- Five-note scales, gong, bamboo-flute and hand-drum voices replace the generic synth sound; three new reaction sounds; Kalampag clatter.

### Quality
- 273+ automated tests, including scene rendering at any window shape, the reaction rules and the graphics governor.
- Rendering: cached glow sprites and a cheaper screen shake.

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
