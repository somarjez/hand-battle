"""Words of the game: prologue, epilogue, codex entries and the how-to-play pages.

Kept apart from the level data so the narrative can be edited without touching game rules.
"""

from __future__ import annotations

TITLE = "ELEMENTAL CONVERGENCE"
TAGLINE = "Five seals. Two hands. One dawn."

PROLOGUE: tuple[str, ...] = (
    "The sun did not rise on the day the Rift opened.",
    "Five Seals held the Loom of Dawn together: Stone, Tide, Gale, Ember and Storm.",
    "Someone cut the threads. The Keepers fell silent, and the shadows learned to hunt.",
    "You are the last Warden. Your hands remember how to speak to the elements.",
    "Go. Restore the seals. Bring back the dawn.",
)

EPILOGUE: tuple[str, ...] = (
    "The Loom turns. The seals hold. Light spills over every ruin you crossed.",
    "Orrin lays a stone. Sael rings the bell. Ysa reads a clear sky. Kael lights the forge.",
    "Veyra stands at the Citadel's door, human again, and does not speak for a long while.",
    "Then she lifts both hands and asks you to teach her the Convergence.",
)

ENEMY_LORE: dict[str, tuple[str, str]] = {
    "shooter": ("Shooter", "A shadow that learned to throw. Fires aimed orbs and short fans. Shoot the orbs down or step aside."),
    "charger": ("Charger", "Trembles, then lunges along a red lane. A hit while it winds up breaks the charge."),
    "sniper": ("Sniper", "Paints you with a thin red line that tightens before it fires. Interrupt it, or leave the line."),
    "gunner": ("Gunner", "Armoured and patient. Fires bursts and walls of orbs with a single gap to slip through."),
    "bomber": ("Bomber", "Marks the ground with red circles that fill and burst. Defuse a circle with a blast, or leave it."),
    "caster": ("Caster", "Throws rings of orbs and slow orange homing orbs. Blasts destroy homing orbs."),
    "spinner": ("Spinner", "Its blades spin faster as it fires a spiral of orbs. Strike it before the spiral starts."),
    "sweeper": ("Sweeper", "Swings a thick beam across the arena or crosses two through your hand. Its eye widens first."),
    "blinker": ("Blinker", "Vanishes in smoke and reappears beside you, firing a fan. Keep moving."),
    "stone_guardian": ("Stone Guardian", "Orrin's guardian, twisted by the Rift. Crushing waves, summoned shooters and falling stone."),
    "tide_guardian": ("Tide Guardian", "A vast thing beneath the Drowned Bell. Beams, bombs and homing water."),
    "gale_guardian": ("Gale Guardian", "The silence before the storm. Walls of orbs and sudden bursts."),
    "ember_guardian": ("Ember Guardian", "The forge-heart given a body. Spirals, sweeping fire and teleporting strikes."),
    "rift_sovereign": ("Rift Sovereign", "Veyra, consumed. Every attack in the Rift is hers, and she is faster when wounded."),
}

HAZARD_LORE: dict[str, str] = {
    "rockfall": "Falling rocks mark the ground with red circles. Leave them before they land.",
    "tide": "A tidal surge sweeps a wall of orbs across the arena with one gap.",
    "storm": "Lightning storms drop beams in straight lines through the arena.",
    "forge": "Forge flares ignite a cluster of bombs around you.",
    "eclipse": "The Eclipse borrows every hazard of the other stages.",
}

HOW_TO_PLAY: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Gestures", (
        "Fist: Earth        Spread palm: Water        Closed palm: Air",
        "Two fingers: Fire        Point: Lightning",
        "Your hands are your shield. Keep at least one in view.",
        "Elements unlock stage by stage: Stonewake gives you Earth.",
    )),
    ("Fighting back", (
        "Your blasts shoot enemy orbs down, defuse bombs and interrupt charging enemies.",
        "A beam that is already firing cannot be stopped, so dodge it.",
        "Combo: chain kills within three seconds to raise your score multiplier up to x5.",
        "Elite enemies are tougher and always drop loot.",
    )),
    ("Loot", (
        "Touch pick-ups with your hand before they fade.",
        "Heart: +25 HP        Regen: health over time        Shield: blocks every hit",
        "Boost: stronger, faster blasts        Mana: refills one element",
    )),
    ("Convergence", (
        "Defeat 10 enemies to fill the Convergence meter (a guardian counts as 5).",
        "Press both palms together and hold for half a second.",
        "For two seconds every enemy on the field is struck down.",
    )),
    ("Hazards and stars", (
        "Each stage has its own hazard: rockfall, surges, storms, forge flares.",
        "Waves: defeat everyone, hunt a quota, or survive the clock. Then the guardian.",
        "Stars: clear the stage (1), lose no life (2), take five hits or fewer (3).",
    )),
)

CREDITS: tuple[str, ...] = (
    "Design and development: project contributors",
    "Hand tracking: OpenCV, MediaPipe, cvzone",
    "Interface and audio engine: Pygame, NumPy",
    "All music and sound effects are synthesised in code",
    "Thank you for restoring the seals.",
)
