# Sinag

*Sinag* (Tagalog for a ray of light) is a Windows-first, gesture-controlled action game built with Python, OpenCV, MediaPipe/cvzone and Pygame. Your webcam is the arena: hand poses cast the elements while you travel the Philippines to find five pieces of a broken dawn.

> *In the old stories, the Bakunawa is a sea dragon that eats the moon. When it does, the elders bang pots and pans until it spits the moon back out. This time it swallowed the sun as well, and nobody's pots were loud enough.*

The code package is still called `elemental_convergence` (so existing saves and imports keep working); "Sinag" is the name players see. The project began as a single-file hand-effects prototype. It is now organized into independently testable vision, game, presentation, and persistence modules. The original `python handTrack.py` command remains the supported compatibility entrypoint.

## Game at a glance

- A 30-40 minute campaign with a prologue, named keepers, guardian dialogue, an epilogue and credits.
- Five gestures, five powers that react with each other, enemy weaknesses, loot pick-ups, combo scoring, and *Kalampag*, a two-palm ultimate.
- Three-star rating per stage, best scores, a lore and bestiary Codex.
- Five real places, each with its own hazard, hand-drawn scene, music and guardian that changes phase as it is hurt.
- Story, Balanced and Master difficulty presets.
- Guided camera/gesture calibration and a no-pressure recognition Sandbox.
- Full keyboard and mouse menus (settings with sliders, pause menu, level select, codex); webcam gestures are reserved for combat.
- The camera picture fills any window or fullscreen shape without stretching, and hand positions match it exactly.

### Campaign

| Place | Keeper | Power | Hazard | Guardian | Weak to | Music |
| --- | --- | --- | --- | --- | --- | --- |
| Mount Makiling, Laguna | Maria Makiling | Earth (fist) | Landslide | Kapre of the Balete | Fire | low drums, flute through the trees |
| Pagsanjan Gorge, Laguna | Mang Amado, the boatman | Water (spread palm) | Rapids surge | Siyokoy King | Lightning | flowing gongs |
| Basco Lighthouse, Batanes | Ate Luz, the lighthouse keeper | Air (closed palm) | Lightning strike | The Typhoon | Earth | open, airy, fast shimmer |
| Taal Island, Batangas | Tatay Berting, the fish farmer | Fire (two fingers) | Eruption | Blaze of Taal | Water | driving drums, struck gongs |
| The Bakunawa's mouth | Lola Auring (back home) | Lightning (point) | Eclipse (all of them) | Bakunawa | nothing: use everything | dark and heavy |

The writing is plain on purpose: specific places, specific people, a bit of humour. The real folklore (Maria Makiling, the kapre, the siyokoy, the Bakunawa) is used with respect, and the Tagalog is kept to words English-speaking players can follow from context.

Each stage plays out as four beats: **defeat everyone**, **hunt** a quota while reinforcements arrive, **survive** the clock (with an **elite** enemy), then the **guardian**, which opens a new phase (and calls minions) at two thirds and one third health and enrages at half. Losing all three lives restarts only the current stage; progress stays saved.

**Scoring.** Kills are worth 100 (elites 300, guardians 1000) multiplied by a combo: chain kills within three seconds and the multiplier climbs to x5. **Stars:** clear the stage (1), lose no life (2), and take five hits or fewer (3).

**Hazards** are always telegraphed (red circles, tightening lines, a banner): landslides drop bombs, the rapids send a wall of orbs with one gap, storms drop beams, forge flares cluster bombs around you.

### Combat & look

The battle screen is drawn exactly like the original `gesture_powers.py` prototype (OpenCV drawing, the same colours, Hershey fonts, additive glow, particles, projectiles, chain lightning, screen shake and HUD layout). See `presentation/battle_view.py`. The campaign (levels, waves, guardians, saves) runs underneath it.

Enemies fight back with real, dodgeable attacks aimed at your hands. Dodge with your hands, or shoot incoming orbs out of the air with your own blasts.

| Enemy | Attacks |
| --- | --- |
| Shooter | aimed orbs, 3-orb fans |
| Charger | winds up (red lane), then body-slams your hand |
| Sniper | tracking laser beam |
| Gunner | rapid bursts, a wall of orbs with a gap |
| Bomber | delayed bombs (leave the red circle) |
| Caster | rings of orbs, homing orbs (orange, shoot them down) |
| Spinner | spiral orb streams |
| Sweeper | sweeping beam, cross of beams |
| Blinker | teleports next to you, then fires |
| Guardians | all of the above plus summons, and an enrage at half health |

**Blocking.** Your blasts are also your shield: they shoot down enemy orbs along their path (Air has the widest reach), defuse bombs they cross, and *interrupt* any non-guardian enemy that is still charging (dash wind-up, beam warning, spiral, burst). You'll see BLOCKED, DEFUSED and INTERRUPTED pop up. A beam that is already firing can't be stopped, so dodge it.

**Kalampag.** The old remedy for the Bakunawa is to make a racket, and so is yours. Defeat 10 enemies to fill the meter (a guardian counts as 5), then press both palms together and hold for about half a second; a ring fills between your hands while it charges. It only fires for two distinct hands that are almost touching: one hand, a hand the tracker detects twice, or hands that are merely close will not trigger it, and it can't fire while the meter is below full. For about 1.8 seconds everything on screen is struck, including minions, summons and reinforcements that arrive during it, and a crowd of pots and pans plays. The ultimate's own kills do not recharge the meter. `CONVERGENCE_BOSS_FRACTION` in `session.py` controls how much of a guardian's health it removes (1.0 defeats it, 0.5 takes half). The tuning constants (`TOGETHER_NEAR`, `TOGETHER_HOLD`, `CONVERGENCE_KILLS`, ...) are at the top of `session.py`; the internal name predates the story.

**Elements react.** Every enemy is weak to one element (x1.4 damage) and resists another (x0.7), and a coloured dot beside its name shows the weakness. Statuses combine: Water *soaks*; Lightning on a soaked enemy *shocks* it (extra damage and a stun); Fire on a soaked enemy makes *steam* (a burst around it); Fire on a dry enemy sets it *burning*; Air on a burning enemy starts a *firestorm* that spreads the flames; Earth *slows*. Guardians are stunned and slowed for less time, and the Bakunawa has no weakness at all. The tables are `WEAKNESS`, `RESISTANCE` and the constants at the top of `session.py`.

**Loot.** Pick-ups float in the arena (and sometimes drop from defeated enemies). Touch them with a hand before they fade (12 s, the ring around each shows the time left):

| Pick-up | Effect |
| --- | --- |
| Heart | +25 HP |
| Regen | +5 HP per second for 6 s |
| Shield | blocks every hit for 8 s (ring around your hands) |
| Boost | blasts do 1.5x damage and fire 35% faster for 10 s |
| Earth / Water / Air / Fire / Lightning mana | refills that element's mana (only elements you have unlocked appear) |

What spawns is weighted by need: hearts are more likely when you're hurt, and mana for an element is more likely when it is low. All the numbers are constants near the top of `session.py`.

### Screen & camera

* The camera picture fills the whole screen. It is cropped to fit, never stretched, and fullscreen uses your monitor's own resolution.
* The game canvas always has the same shape as the window, so there are no black bars on 16:10, 4:3 or ultrawide screens.
* Hand positions are mapped with exactly the same crop as the picture (`models.scale_frame`), so the hand you see is where the game sees it.

Tuning lives in `elemental_convergence/combat.py` (attack speeds, damage, warning times) and the balance block at the top of `elemental_convergence/session.py` (`ENEMY_BASE_HP`, `BOSS_BASE_HP`, protection time). Reduced flash / reduced shake in Settings tone down the flashes and shake.

## Requirements

- Windows 10/11 is the primary supported platform.
- Python 3.10–3.12.
- A webcam or virtual camera visible to OpenCV.
- Lighting bright enough for MediaPipe to see the full hand.

The game uses `opencv-python`, `cvzone`, `mediapipe`, `numpy`, and `pygame`. Development and packaging additionally use `pytest` and `pyinstaller`.

## Developer setup

From PowerShell:

```powershell
git clone https://github.com/somarjez/hand-battle.git
cd hand-battle
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
python handTrack.py --windowed
```

Use a specific camera index when automatic index `0` is not the intended device:

```powershell
python handTrack.py --camera 1 --windowed
```

The installed console entrypoint is equivalent:

```powershell
elemental-convergence --camera 1
```

### Controls

| Input | Context | Action |
| --- | --- | --- |
| Arrow keys / `W` `A` `S` `D` | Menus | Move the highlight; Left / Right change sliders, toggles and choices |
| Mouse | Menus | Hover to highlight, click to select, click or drag sliders |
| `Enter` / `Space` | Menus and story | Confirm, or skip the text reveal and then advance |
| Left / Right | Level select, Codex, How to Play | Choose a seal, switch tab, turn page |
| `Esc` | Gameplay | Pause (resume, restart, settings, quit to menu) |
| `Esc` | Any other screen | Go back (the main menu quits) |
| `F11` | Anywhere | Toggle fullscreen |
| `C` / `Space` | Calibration | Try the next camera / continue with default thresholds |

Combat casts automatically while a recognized pose is held and the relevant mana/cooldown permits it. Keep at least one hand visible: after the difficulty-specific grace period, missing hands drain health.

### Menus and settings

The **Settings** screen changes everything live and saves as you go: master, music and effects volume (sliders), difficulty, fullscreen, reduced flash, reduced shake, gesture labels, which camera to use, recalibration, and a confirmed *Reset progress*. The same screen opens from the pause menu and returns to it.

### Look, and replacing the art

There is no bitmap art. Each place is a layered paper-cut scene drawn in `presentation/art.py`, with a printed-grain texture and one animated detail: fireflies on Makiling, ripples in the gorge, the sweeping lamp at Basco, embers from Taal's crater, ash falling past the eclipsed moon. The interface uses a warm ink-and-gold palette, chamfered panels edged with a woven diamond band, and an eight-ray sun for selections and ratings. Text is set in the bundled Alegreya. To use your own picture for any place, save `assets/images/override/<stage>.png`.

### Audio

All sound effects (37) and music tracks (9) are synthesised in code at startup on a background thread, so there are no audio files to ship. The music uses five-note scales with gong, bamboo-flute and hand-drum voices in place of generic synth pads; each place has its own theme, the guardian fight has a boss theme, and results play a victory or defeat stinger. Every spell, reaction, hit and pick-up has its own sound, and Kalampag adds a crowd of pots and pans. Music crossfades between screens and quietens while paused, and a heartbeat quickens as health drops. Run `python tools/export_audio.py` to write everything out as WAV files, and drop an `.ogg` named after a sound into `elemental_convergence/assets/audio/` to replace it.

### Gesture Sandbox, How to Play and the Codex

The **Gesture Sandbox** is a guided lesson: it asks for your hand, then each of the five hand-signs and the two-palm Kalampag, shows a
drawn hand-sign and a ring that fills while you hold it, and tells you what it sees ("I see Air. Spread your fingers wider") if it is
not quite right. After the lesson it stays open for free practice. Enter or Right skips ahead, Left goes back, R restarts. **How to Play**
is an illustrated, animated lesson read aloud by Lola Auring. The **Codex** shows each creature as a portrait with what it fears and
resists; creatures you have not met yet are dark silhouettes.

### Narrator

The prologue, each place's introduction, the end-of-level story and the epilogue are read aloud by a storyteller using your
system's own text-to-speech voice (Windows uses its built-in SAPI voices, so there is nothing to download). Each line of text
appears as it is spoken, Enter skips ahead, and the music lowers while the narrator talks. Turn it off under Settings > Narrator.
To choose a voice, set `SINAG_VOICE` to part of its name (for example `zira`); `SINAG_NARRATOR=off` disables it entirely. If
no voice is installed the story scenes simply use their normal timed text. The narrator uses `pyttsx3` when it is installed and
otherwise Windows' own speech engine (PowerShell), so it works without any extra install. If you hear nothing, run
`python -m elemental_convergence.narrator`: it speaks a test sentence, or tells you exactly why it could not. Problems are also
printed in the terminal as `[narrator] disabled: ...`.

### Graphics setting

*Graphics: Auto* watches frame times during fights and switches to a lighter path (softer glow, fewer particles, faster scaling) only after a sustained run of slow frames, and back only after a long calm one, so it cannot flicker. *High* and *Fast* force a mode. Menus never trigger it.

### No camera or a black preview

1. Close applications already using the webcam.
2. Enable Windows **Privacy & security → Camera → Let desktop apps access your camera**.
3. Try `python handTrack.py --camera 1 --windowed`, then indices `2` through `5`.
4. For a phone/virtual camera, start its desktop and phone components before launching the game.

### Gestures flicker or classify incorrectly

- Keep the full wrist and fingertips inside the frame.
- Use even front lighting and avoid a bright window behind the hand.
- Move farther from the camera if fingertips leave the frame.
- Revisit Calibration and hold each pose steadily; Water requires visibly spread fingers while Air keeps them together.

### Low frame rate

- Close other camera and GPU-heavy applications.
- Use windowed mode while diagnosing.
- Avoid very high-resolution virtual-camera output; the game targets a 1280×720 logical arena.
- Confirm the same Python environment contains compatible NumPy, OpenCV, MediaPipe, and Pygame versions.

### No sound

Audio is best-effort. Confirm a Windows output device is enabled and check the three volume settings. Missing optional `.ogg` files do not prevent gameplay.

## Contributing

Keep changes inside the subsystem that owns the behavior. Write a failing test before changing production code, run the full suite afterward, and keep camera/audio dependencies out of domain tests. New art or audio must be original or redistributable and documented in `elemental_convergence/assets/ATTRIBUTION.md`.

Pull requests should explain why the change is needed, list the affected player/developer behavior, and mention any manual camera validation that reviewers must perform locally.

## Credits

- Computer vision: OpenCV, MediaPipe, and cvzone.
- Windowing, rendering, and audio: Pygame.
- Art, audio and the interface are all generated in code. The font is Alegreya under the SIL Open Font License; see the asset attribution file.
