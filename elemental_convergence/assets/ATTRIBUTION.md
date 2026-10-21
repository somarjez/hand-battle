# Asset Attribution

## Backgrounds and interface art

All backgrounds (the title dawn and the five place scenes) and every interface ornament (panels, buttons, the
woven diamond band, the eight-ray sun) are drawn in code in `presentation/art.py`. There are no image files to
attribute. To replace a scene with your own artwork, save a PNG as
`assets/images/override/<stage>.png` (`menu`, `stonewake`, `tidelost`, `skyglass`, `cinderforge` or `eclipse`).

## `images/legacy/menu.png` (retired)

- A title illustration generated for an earlier version with an AI image tool. It is **no longer used** by the game.
- It is kept only so the repository history stays intact. Delete it if you do not want AI-generated material in the project.

## `fonts/`

- Alegreya, Alegreya SC (Juan Pablo del Peral, Huerta Tipografica), used under the SIL Open Font License 1.1.
  The licence text is in `fonts/OFL.txt`. Source: https://github.com/google/fonts (ofl/alegreya, ofl/alegreyasc).

## Audio

Every sound effect and music track is synthesised in code (`presentation/synth.py`). There are no recordings.
Drop an `.ogg` named after any sound or track into `assets/audio/` to override it.

## Story

The setting draws on Philippine folklore: the Bakunawa (a sea dragon that swallows the moon), Maria Makiling,
the kapre and the siyokoy. Place names refer to real locations (Mount Makiling, the Pagsanjan Gorge, the Basco
Lighthouse in Batanes, Taal Volcano). The characters who keep each place are original.
