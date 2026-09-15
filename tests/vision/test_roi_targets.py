"""Test di `vision.roi_targets`: l'elenco dei rettangoli e come si indirizzano."""

from __future__ import annotations

import pytest

from pokemon_helper.vision.roi import ROIS_FIRERED, TEAM_SIZE, GameRois, Roi
from pokemon_helper.vision.roi_targets import (
    SCREEN_BATTLE,
    SCREEN_PARTY_MENU,
    TARGETS,
    TARGETS_BY_KEY,
    get_roi,
    replace_roi,
    targets_for_screen,
)

# Un rettangolo qualunque, riconoscibile a colpo d'occhio negli assert.
MARKER = Roi(x=0.25, y=0.25, w=0.1, h=0.1)


def test_there_is_one_target_per_rectangle_of_the_game() -> None:
    """Sedici: 3 di combattimento, la sentinella, 6 nomi e 6 livelli."""
    assert len(TARGETS) == 16
    assert len(targets_for_screen(SCREEN_BATTLE)) == 3
    assert len(targets_for_screen(SCREEN_PARTY_MENU)) == 13


def test_the_targets_cover_the_whole_game_rois_structure() -> None:
    """Un campo senza bersaglio sarebbe un rettangolo che nessuno può calibrare."""
    singles = {key for key in TARGETS_BY_KEY if not key.startswith("team_menu.")}
    fields = set(GameRois.__dataclass_fields__) - {"team_menu"}

    assert singles == fields
    for group in ("slot_areas", "slot_levels"):
        keys = {key for key in TARGETS_BY_KEY if key.startswith(f"team_menu.{group}.")}
        assert len(keys) == TEAM_SIZE


def test_every_target_has_a_label_and_a_hint() -> None:
    for target in TARGETS:
        assert target.label
        assert target.hint.endswith(".")


def test_the_keys_are_unique() -> None:
    assert len(TARGETS_BY_KEY) == len(TARGETS)


def test_the_slot_labels_are_numbered_from_one() -> None:
    """Gli slot si contano come nel gioco, non come in Python."""
    assert TARGETS_BY_KEY["team_menu.slot_areas.0"].label == "Nome slot 1"
    assert TARGETS_BY_KEY["team_menu.slot_levels.5"].label == "Livello slot 6"


# ------------------------------------------------------------- get / replace


def test_get_reads_a_single_rectangle() -> None:
    assert get_roi(ROIS_FIRERED, "opponent_name") == ROIS_FIRERED.opponent_name


def test_get_reads_a_slot_by_index() -> None:
    assert (
        get_roi(ROIS_FIRERED, "team_menu.slot_levels.4") == (ROIS_FIRERED.team_menu.slot_levels[4])
    )


def test_replace_touches_only_the_addressed_rectangle() -> None:
    updated = replace_roi(ROIS_FIRERED, "player_name", MARKER)

    assert updated.player_name == MARKER
    assert updated.opponent_name == ROIS_FIRERED.opponent_name
    assert updated.team_menu == ROIS_FIRERED.team_menu


def test_replace_on_a_slot_keeps_its_five_neighbours() -> None:
    updated = replace_roi(ROIS_FIRERED, "team_menu.slot_areas.2", MARKER)

    assert updated.team_menu.slot_areas[2] == MARKER
    assert updated.team_menu.slot_areas[1] == ROIS_FIRERED.team_menu.slot_areas[1]
    assert updated.team_menu.slot_areas[3] == ROIS_FIRERED.team_menu.slot_areas[3]
    assert updated.team_menu.slot_levels == ROIS_FIRERED.team_menu.slot_levels


def test_replace_leaves_the_original_untouched() -> None:
    """`GameRois` è immutabile: `replace_roi` ne restituisce una copia."""
    before = ROIS_FIRERED.player_name

    replace_roi(ROIS_FIRERED, "player_name", MARKER)

    assert ROIS_FIRERED.player_name == before


@pytest.mark.parametrize("key", ["opponent_sprite", "team_menu.slot_icons.0", "", "player"])
def test_an_unknown_key_fails_loudly(key: str) -> None:
    """Meglio alzare che scrivere un rettangolo in un campo che non esiste."""
    with pytest.raises(KeyError):
        get_roi(ROIS_FIRERED, key)
    with pytest.raises(KeyError):
        replace_roi(ROIS_FIRERED, key, MARKER)


def test_a_round_trip_through_replace_and_get_is_stable() -> None:
    updated = replace_roi(ROIS_FIRERED, "party_menu_sentinel", MARKER)

    assert get_roi(updated, "party_menu_sentinel") == MARKER
