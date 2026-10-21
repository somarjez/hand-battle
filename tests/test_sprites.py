import numpy as np

from elemental_convergence.combat import BOSS_KINDS, ENEMY_KINDS
from elemental_convergence.presentation import sprites


def test_every_enemy_and_boss_has_a_sprite():
    for kind in list(ENEMY_KINDS) + list(BOSS_KINDS):
        assert kind in sprites.DRAWERS, kind
        assert kind in sprites.AURA, kind


def test_sprites_are_cached_opaque_in_the_middle_and_clear_at_the_corners():
    book = sprites.SpriteBook()
    for kind, r in (("shooter", 40), ("rift_sovereign", 100)):
        col, al = book.get(kind, r)
        assert book.get(kind, r)[1] is al                      # cached
        h, w = al.shape
        assert al[h // 2, w // 2] > 200
        assert al[0, 0] == 0 and al[-1, -1] == 0
        assert col.shape == (h, w, 3)


def test_flash_variant_is_a_white_silhouette():
    book = sprites.SpriteBook()
    col, al = book.get("charger", 44, flash=True)
    assert np.array_equal(col[..., 0], al)


def test_blit_clips_at_the_screen_edge_and_blends():
    book = sprites.SpriteBook()
    col, al = book.get("bomber", 40)
    img = np.zeros((200, 200, 3), np.uint8)
    sprites.blit(img, col, al, -5, 100)                         # half off-screen must not raise
    sprites.blit(img, col, al, 500, 500)                        # fully off-screen is a no-op
    sprites.blit(img, col, al, 100, 100)
    assert img[100, 100].any()
