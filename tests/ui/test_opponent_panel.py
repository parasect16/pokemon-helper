"""Test delle funzioni pure di `ui.opponent_panel`.

Coprono la decisione "quale abilità applicare e cosa resta incerto", che è
logica di dominio anche se vive accanto ai widget. Nessun Qt viene istanziato.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QComboBox

from pokemon_helper.data.models import Ability
from pokemon_helper.ui.opponent_panel import (
    _sync_combo_tooltip,
    resolve_ability,
    uncertain_abilities,
)


@pytest.fixture(scope="module")
def qapp():
    """QApplication condivisa: i widget Qt non si costruiscono senza."""
    app = QApplication.instance() or QApplication([])
    yield app


def _ability(identifier: str, slot: int = 1) -> Ability:
    return Ability(
        id=slot,
        identifier=identifier,
        name_en=identifier.replace("-", " ").title(),
        name_it=None,
        description=None,
        slot=slot,
        is_hidden=False,
    )


LEVITATE = _ability("levitate")
STURDY = _ability("sturdy", slot=2)
VOLT_ABSORB = _ability("volt-absorb", slot=2)


def test_a_single_candidate_is_applied_without_asking() -> None:
    """Gengar in Gen 3 ha solo Levitazione: nessuna ambiguità da risolvere."""
    applied, candidates = resolve_ability([LEVITATE], None)
    assert applied == "levitate"
    assert candidates == [LEVITATE]


def test_several_candidates_apply_nothing_by_default() -> None:
    applied, candidates = resolve_ability([LEVITATE, STURDY], None)
    assert applied is None
    assert candidates == [LEVITATE, STURDY]


def test_a_pinned_choice_wins_over_the_ambiguity() -> None:
    applied, _ = resolve_ability([LEVITATE, STURDY], "sturdy")
    assert applied == "sturdy"


def test_a_pinned_choice_that_is_no_longer_possible_is_ignored() -> None:
    """Cambiando generazione l'abilità fissata può non essere più disponibile."""
    applied, _ = resolve_ability([STURDY], "levitate")
    assert applied == "sturdy"


def test_a_pinned_choice_is_ignored_when_ambiguous_and_unavailable() -> None:
    applied, _ = resolve_ability([LEVITATE, STURDY], "volt-absorb")
    assert applied is None


def test_no_candidates_means_nothing_to_apply() -> None:
    assert resolve_ability([], "levitate") == (None, [])


def test_an_ambiguity_that_cannot_change_the_verdict_is_not_flagged() -> None:
    """Magnemite: due abilità, nessuna delle quali tocca l'efficacia.

    Segnalarla sarebbe rumore: non è "non lo so", è "so che non conta".
    """
    assert uncertain_abilities(None, [_ability("magnet-pull"), STURDY], 3) == []


def test_an_ambiguity_that_can_change_the_verdict_is_flagged() -> None:
    """Lanturn: Assorbivolt cambierebbe Elettro, quindi il profilo è dubbio."""
    flagged = uncertain_abilities(None, [VOLT_ABSORB, _ability("illuminate")], 4)
    assert [a.identifier for a in flagged] == ["volt-absorb"]


def test_nothing_is_flagged_once_an_ability_has_been_applied() -> None:
    assert uncertain_abilities("volt-absorb", [VOLT_ABSORB, LEVITATE], 5) == []


def test_flagging_respects_the_generation_of_the_effect() -> None:
    """Parafulmine dà immunità solo dalla Gen 5: prima non c'è nulla da segnalare."""
    candidates = [_ability("lightning-rod"), STURDY]
    assert uncertain_abilities(None, candidates, 4) == []
    assert [a.identifier for a in uncertain_abilities(None, candidates, 5)] == ["lightning-rod"]


# --- tooltip del menu a tendina ---


def _combo_with(descriptions: list[str | None]) -> QComboBox:
    """QComboBox con una voce "?" iniziale e una voce per descrizione."""
    box = QComboBox()
    box.addItem("Abilità: ?", None)
    for index, description in enumerate(descriptions, start=1):
        box.addItem(f"voce {index}", f"id{index}")
        if description is not None:
            box.setItemData(index, description, Qt.ItemDataRole.ToolTipRole)
    return box


def test_the_closed_combo_shows_the_tooltip_of_the_selected_item(qapp) -> None:
    """Qt mostra i tooltip per voce solo a menu aperto, ed è il caso sbagliato."""
    box = _combo_with(["Immune agli attacchi di tipo Terra.", "Non cade in trappola."])
    box.setCurrentIndex(1)
    _sync_combo_tooltip(box)
    assert box.toolTip() == "Immune agli attacchi di tipo Terra."


def test_the_tooltip_follows_the_selection(qapp) -> None:
    box = _combo_with(["prima", "seconda"])
    box.setCurrentIndex(2)
    _sync_combo_tooltip(box)
    assert box.toolTip() == "seconda"


def test_an_item_without_description_clears_the_tooltip(qapp) -> None:
    box = _combo_with(["prima", None])
    box.setCurrentIndex(1)
    _sync_combo_tooltip(box)
    box.setCurrentIndex(2)
    _sync_combo_tooltip(box)
    assert box.toolTip() == ""
