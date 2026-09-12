"""Test di `ui.opponent_panel`.

Coprono la decisione "quale abilità applicare e cosa resta incerto" — logica
di dominio anche se vive accanto ai widget — e il pannello vero, che a
seconda di cosa sa mostra un placeholder o le due card affiancate.

La fixture `qapp` arriva da pytest-qt; la piattaforma offscreen la imposta
`conftest.py`.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QLabel

from pokemon_helper.data.models import Ability
from pokemon_helper.ui.opponent_panel import (
    OpponentPanel,
    _sync_combo_tooltip,
    resolve_ability,
    uncertain_abilities,
)


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


# --- pannello ---


def _labels(panel: OpponentPanel) -> list[str]:
    """Testo delle QLabel del contenuto corrente.

    Si guarda `_content` e non l'intero pannello perché il contenuto
    precedente viene rimosso con `deleteLater()`: resta figlio finché
    l'event loop non lo smaltisce, e `findChildren` lo troverebbe ancora.
    """
    return [label.text() for label in panel._content.findChildren(QLabel)]


def _combos(panel: OpponentPanel) -> list[QComboBox]:
    """Menu a tendina del contenuto corrente (stesso motivo di `_labels`)."""
    return panel._content.findChildren(QComboBox)


@pytest.fixture
def opponent_panel(qtbot, repository, state) -> OpponentPanel:
    panel = OpponentPanel(repository, state)
    qtbot.addWidget(panel)
    return panel


def test_without_a_battle_the_panel_shows_a_placeholder(opponent_panel) -> None:
    assert any("Combattimento non in corso" in text for text in _labels(opponent_panel))


def test_an_opponent_without_a_known_player_asks_for_a_recognize(opponent_panel) -> None:
    """Senza sapere chi è in campo la tabella matchup non si può calcolare."""
    opponent_panel.set_opponent(4)
    assert any("Player in campo sconosciuto" in text for text in _labels(opponent_panel))


def test_both_sides_known_renders_the_two_cards(opponent_panel) -> None:
    opponent_panel.set_opponent(4)  # Charmander
    opponent_panel.set_active_player(1)  # Bulbasaur

    texts = _labels(opponent_panel)
    assert "Charmander" in texts
    assert "Bulbasaur" in texts
    assert not any("Combattimento non in corso" in text for text in texts)


def test_a_pokemon_missing_from_the_dataset_falls_back_to_a_placeholder(opponent_panel) -> None:
    opponent_panel.set_opponent(9999)
    opponent_panel.set_active_player(1)
    assert any("Dati incompleti" in text for text in _labels(opponent_panel))


def test_a_pokemon_without_types_in_that_generation_is_incomplete(opponent_panel) -> None:
    """Chikorita in Gen 1: esiste come riga, ma non ha tipi da confrontare."""
    opponent_panel.set_opponent(152)
    opponent_panel.set_active_player(1)
    assert any("Dati incompleti" in text for text in _labels(opponent_panel))


def test_clearing_the_opponent_goes_back_to_the_placeholder(opponent_panel) -> None:
    opponent_panel.set_opponent(4)
    opponent_panel.set_active_player(1)
    opponent_panel.set_opponent(None)
    assert any("Combattimento non in corso" in text for text in _labels(opponent_panel))


def test_a_single_ability_is_shown_as_plain_text(opponent_panel, state) -> None:
    """Gastly ha solo Levitazione: niente da scegliere, quindi niente menu."""
    state.generation = 3
    opponent_panel.apply_state(state)
    opponent_panel.set_opponent(92)
    opponent_panel.set_active_player(1)

    assert any("Levitazione" in text for text in _labels(opponent_panel))
    assert _combos(opponent_panel) == []


def test_an_ambiguous_ability_becomes_a_combo_that_pins_the_choice(
    opponent_panel, state, qtbot
) -> None:
    """Magnemite in Gen 4 ne ammette due: l'utente fissa quella vista in battaglia."""
    state.generation = 4
    opponent_panel.apply_state(state)
    opponent_panel.set_opponent(81)
    opponent_panel.set_active_player(92)

    combos = _combos(opponent_panel)
    assert len(combos) == 1
    box = combos[0]

    with qtbot.waitSignal(opponent_panel.abilityPinned) as blocker:
        box.setCurrentIndex(1)
    assert blocker.args[0] == 81
    assert blocker.args[1] == box.itemData(1)


def test_a_pinned_ability_comes_back_selected(opponent_panel, state) -> None:
    state.generation = 4
    state.abilities[81] = "motor-drive"
    opponent_panel.apply_state(state)
    opponent_panel.set_opponent(81)
    opponent_panel.set_active_player(92)

    box = _combos(opponent_panel)[0]
    assert box.currentData() == "motor-drive"
