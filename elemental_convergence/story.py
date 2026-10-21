"""Words of the game: prologue, epilogue, codex entries and the how-to-play pages.

Kept apart from the level data so the writing can be edited without touching game rules.
The setting is Philippine folklore: the Bakunawa, a sea dragon that swallows the moon, and the old
remedy of banging pots and pans until it gives the moon back (kalampag).
"""

from __future__ import annotations

TITLE = "SINAG"
TAGLINE = "When the Bakunawa eats the moon, make some noise."

PROLOGUE: tuple[str, ...] = (
    "In the old stories, the Bakunawa is a sea dragon that eats the moon.",
    "When it does, the elders bang pots and pans until it spits the moon back out. Kalampag.",
    "This time it swallowed the sun as well, and nobody's pots were loud enough. Three days now, and no dawn.",
    "The light broke into five sinag, five rays, and each one is hiding in a place that needs it most.",
    "Lola Auring taught you the hand-signs when you were small. She said they would be useful someday. You thought she meant for the harvest.",
    "Pack your baon. Find the five rays. Be loud.",
)

EPILOGUE: tuple[str, ...] = (
    "Back in the barangay, Lola Auring is still hitting a kaldero with a wooden spoon. She has not stopped since Tuesday. She stops when you walk in.",
    "'Kumain ka na ba?' she asks. Have you eaten yet. It is how she asks everything else.",
    "Five rays hang over Laguna, Batanes, Batangas. Fainter than the sun, but enough.",
    "The Bakunawa sleeps. The stories say it will be hungry again one day. You have your hands, and a lot of neighbours with pots.",
)

ENEMY_LORE: dict[str, tuple[str, str]] = {
    "shooter": ("Manananggal (Shooter)", "The torso that leaves its legs behind to hunt at night, and hurls glowing orbs from the dark. Aimed orbs and short fans. Shoot the orbs down or step aside."),
    "charger": ("Tikbalang (Charger)", "The horse-headed trickster of the mountain trails. Shakes, then charges down a red lane. Hit it while it shakes and the charge falls apart."),
    "sniper": ("Bungisngis (Sniper)", "The one-eyed giant who never stops giggling. Paints a thin red line on you that tightens before it fires. Hit it first, or get off the line."),
    "gunner": ("Mandirigma (Gunner)", "A shield-and-lantaka warrior, armoured and patient. Fires bursts, and walls of orbs with exactly one gap in them."),
    "bomber": ("Duwende (Bomber)", "The little trickster from the punso, the anthill. Marks the ground with red circles that fill up and burst. A blast through the circle defuses it."),
    "caster": ("Diwata (Caster)", "A forest spirit crowned in sampaguita. Throws rings of orbs, and slow orange ones that follow you. Blasts pop the orange ones."),
    "spinner": ("Sigbin (Spinner)", "The hound with ears that clap like hands. Spins faster as it fires a spiral of orbs. Hit it before the spiral starts."),
    "sweeper": ("Santelmo (Sweeper)", "Ghost-fire that drifts over graves and masts. Swings a wide beam across the arena, or crosses two through your hand. Its eye widens just before."),
    "blinker": ("Babaeng Puti (Blinker)", "The White Lady. Vanishes in smoke, turns up next to you and fires a fan. Keep moving."),
    "stone_guardian": ("Kapre of the Balete", "A tree giant with a giant cigar, shadow-struck and furious. Falling stone, summoned shooters and heavy rushes."),
    "tide_guardian": ("Siyokoy King", "Lord of the pool below the falls. Beams, bombs and homing water, and a sudden dive."),
    "gale_guardian": ("The Typhoon", "The storm that sat on Batanes. Walls of orbs and sudden bursts, and it gets worse when the eye closes."),
    "ember_guardian": ("Blaze of Taal", "The crater given a face. Spirals, sweeping fire and teleporting strikes. Water is the answer."),
    "rift_sovereign": ("Bakunawa", "The moon-eater itself. Every attack in the game is in its mouth, and it is faster when hurt. No weakness: use everything."),
}

HAZARD_LORE: dict[str, str] = {
    "rockfall": "Red circles mark where rocks will land. Leave them before they do.",
    "tide": "A wall of water-orbs sweeps across the arena with one gap.",
    "storm": "Lightning strikes in straight lines through the arena.",
    "forge": "A cluster of bombs goes off around you.",
    "eclipse": "The dragon borrows every hazard of the other four places.",
}

HOW_TO_PLAY: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Hand-signs", (
        "Fist: Earth (lupa). Spread palm: Water (tubig). Closed palm: Air (hangin).",
        "Two fingers: Fire (apoy). Point: Lightning (kidlat).",
        "Your hands are your shield. Keep at least one in view.",
        "You learn the signs one place at a time. Mount Makiling teaches Earth. Practise any time in the Gesture Sandbox.",
    )),
    ("Elements combine", (
        "Every enemy is weak to one element and resists another. The coloured dot by its name shows its weakness.",
        "Water soaks an enemy. Lightning on a soaked enemy SHOCKS it: extra damage and a stun.",
        "Fire on a soaked enemy makes STEAM, a burst that hurts everything near it. Fire on a dry enemy sets it burning.",
        "Air on a burning enemy starts a FIRESTORM that spreads the flames. Earth slows whatever it hits.",
    )),
    ("Fighting back", (
        "Your blasts shoot enemy orbs down, defuse bombs and interrupt anything that is still charging up.",
        "A beam that is already firing cannot be stopped, so move out of it.",
        "Chain kills within three seconds to raise your score multiplier, up to x5.",
        "Elite enemies are tougher and always drop something useful.",
    )),
    ("Pick-ups", (
        "Touch pick-ups with your hand before they fade.",
        "Heart: +25 HP        Regen: health over time        Shield: blocks every hit",
        "Boost: stronger, faster blasts        Mana: refills one element",
    )),
    ("Kalampag", (
        "Defeat 10 enemies to fill the Kalampag meter. A guardian counts as 5.",
        "It is what the elders do to the Bakunawa: make a racket. Press both palms together and hold for half a second.",
        "For two seconds every enemy on the field is struck down.",
    )),
    ("Places and stars", (
        "Each place has its own hazard: landslide, rapids, lightning, eruption.",
        "A place has four parts: defeat everyone, hunt a quota, survive the clock, then the guardian.",
        "Stars: clear it (1), lose no life (2), take five hits or fewer (3).",
    )),
)

# Lola Auring's lesson for each How to Play page. She says it first, then the page's rules are read out.
HOW_TO_LOLA: tuple[str, ...] = (
    "Anak, listen. Your hands are the whole spell. Show them to me, and the elements will answer.",
    "Nothing in this world stands alone, apo. Water meets lightning, fire meets water, and they argue loudly.",
    "A good warden does not only strike. A good warden also watches, and knows when to move.",
    "Take what the land leaves for you, but do not dawdle. Nothing stays long on the ground.",
    "Our elders made a racket when the Bakunawa came for the moon. You will make the same racket.",
    "Every place has its own temper. Learn it, and then it is only a very loud neighbour.",
)

CREDITS: tuple[str, ...] = (
    "Main Creator: Jezreel Ramos",
    "Support: Judeelyn Capili, Shaila Patrice Avellaneda",
    "Story inspired by Philippine folklore: the Bakunawa, Maria Makiling, the kapre and the siyokoy.",
    "Hand tracking: OpenCV, MediaPipe and cvzone. Interface and audio: Pygame and NumPy.",
    "Typeface: Alegreya, by Juan Pablo del Peral, under the SIL Open Font License.",
    "Every sound and every piece of music is generated in code.",
    "Salamat sa paglalaro. Thank you for playing.",
)
