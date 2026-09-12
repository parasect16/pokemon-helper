"""Test di `ui.team_panel` con widget Qt reali su piattaforma offscreen.

Coprono il collante fra stato e widget: sostituzione della squadra,
evidenziazione dello slot in campo, segnali verso l'app layer e feedback
temporaneo sui pulsanti di ricarica. È la parte che `_apply_team_recognition`
e compagni non toccano: lì si decide *cosa* scrivere, qui *come* finisce a
schermo e quali segnali ne escono.
"""

from __future__ import annotations

import pytest

from pokemon_helper.ui import team_panel as team_panel_module
from pokemon_helper.ui.state import TEAM_SIZE, TeamSlot
from pokemon_helper.ui.team_panel import TeamSlotWidget


class _FakeTimer:
    """Sostituto di `QTimer` che registra i singleShot invece di eseguirli.

    I feedback sui pulsanti durano 10 secondi reali: senza questo, verificarne
    il ripristino richiederebbe di aspettarli davvero.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[int, object]] = []

    def singleShot(self, msec, callback) -> None:  # noqa: N802 — firma di Qt
        self.calls.append((msec, callback))

    def fire_all(self) -> None:
        """Esegue i callback in sospeso, nell'ordine in cui sono stati chiesti."""
        calls, self.calls = self.calls, []
        for _msec, callback in calls:
            callback()

    def fire_first(self) -> None:
        """Esegue solo il callback più vecchio, lasciando gli altri in sospeso."""
        _msec, callback = self.calls.pop(0)
        callback()


@pytest.fixture
def fake_timer(monkeypatch) -> _FakeTimer:
    """Rimpiazza il `QTimer` visto da `team_panel` con il fake."""
    timer = _FakeTimer()
    monkeypatch.setattr(team_panel_module, "QTimer", timer)
    return timer


def _names(panel) -> list[str]:
    """Testo del label nome di ciascuno dei sei slot."""
    return [slot._name_label.text() for slot in panel._slots]


def _active_flags(panel) -> list[bool]:
    """Quali slot risultano evidenziati come "in campo"."""
    return [slot.styleSheet() == TeamSlotWidget._STYLE_ACTIVE for slot in panel._slots]


# ------------------------------------------------------------- replace_team


def test_replace_team_rewrites_state_and_labels(panel, state) -> None:
    new_team = [TeamSlot(pokemon_id=129, level=5)] + [None] * (TEAM_SIZE - 1)
    panel.replace_team(new_team)

    assert state.team == new_team
    # Magikarp non ha nome italiano nel dataset di test: si ripiega sull'inglese.
    assert _names(panel)[0] == "Magikarp"
    assert _names(panel)[1] == "(vuoto)"


def test_replace_team_emits_the_new_team(panel, qtbot) -> None:
    new_team = [TeamSlot(pokemon_id=4, level=7)] + [None] * (TEAM_SIZE - 1)
    with qtbot.waitSignal(panel.teamReplaced) as blocker:
        panel.replace_team(new_team)
    assert blocker.args[0] == new_team


def test_replace_team_rejects_a_wrong_number_of_slots(panel, state) -> None:
    """Meglio sollevare che scrivere un team di lunghezza sbagliata nello stato."""
    original = list(state.team)
    with pytest.raises(ValueError, match="6 slot"):
        panel.replace_team([None, None])
    assert state.team == original


def test_replace_team_keeps_the_highlight_if_the_pokemon_is_still_there(panel) -> None:
    panel.set_active_player(4)
    panel.replace_team(
        [
            TeamSlot(pokemon_id=1, level=10),
            TeamSlot(pokemon_id=4, level=12),
            None,
            None,
            None,
            None,
        ]
    )
    assert _active_flags(panel) == [False, True, False, False, False, False]


def test_replace_team_drops_the_highlight_if_the_pokemon_is_gone(panel) -> None:
    """Cambio di squadra a metà lotta: nessuno slot deve restare evidenziato."""
    panel.set_active_player(4)
    panel.replace_team([TeamSlot(pokemon_id=1, level=10)] + [None] * (TEAM_SIZE - 1))
    assert _active_flags(panel) == [False] * TEAM_SIZE


# -------------------------------------------------------- set_active_player


def test_set_active_player_highlights_only_the_matching_slot(panel) -> None:
    panel.set_active_player(81)
    assert _active_flags(panel) == [False, False, True, False, False, False]


def test_set_active_player_with_an_id_outside_the_team_highlights_nothing(panel) -> None:
    """Pokemon non in squadra (nickname risolto male, o squadra non aggiornata)."""
    panel.set_active_player(152)
    assert _active_flags(panel) == [False] * TEAM_SIZE


def test_set_active_player_none_clears_the_highlight(panel) -> None:
    panel.set_active_player(81)
    panel.set_active_player(None)
    assert _active_flags(panel) == [False] * TEAM_SIZE


# ----------------------------------------------------------------- segnali


def test_generation_combo_updates_state_and_emits(panel, state, qtbot) -> None:
    with qtbot.waitSignal(panel.generationChanged) as blocker:
        panel._gen_combo.setCurrentIndex(2)  # Gen 1 -> Gen 3
    assert blocker.args == [3]
    assert state.generation == 3


def test_apply_state_realigns_the_combo_without_emitting(panel, state, qtbot) -> None:
    """Lo stato cambiato altrove non deve rimbalzare indietro come input utente."""
    state.generation = 5
    with qtbot.assertNotEmitted(panel.generationChanged):
        panel.apply_state(state)
    assert panel._gen_combo.currentData() == 5


def test_reload_buttons_emit_their_requests(panel, qtbot) -> None:
    with qtbot.waitSignal(panel.reloadTeamRequested):
        panel._reload_team_btn.click()
    with qtbot.waitSignal(panel.reloadOpponentRequested):
        panel._reload_opp_btn.click()
    with qtbot.waitSignal(panel.nicknamesRequested):
        panel._nicknames_btn.click()


def test_the_auto_detect_switch_emits_only_when_the_user_moves_it(panel, qtbot) -> None:
    """`set_auto_detect` allinea l'interruttore allo stato persistito.

    Se emettesse, l'avvio con `auto_detect=True` riscriverebbe lo stato e
    farebbe ripartire il poller prima che l'app abbia finito di montarsi.
    """
    with qtbot.assertNotEmitted(panel.autoDetectToggled):
        panel.set_auto_detect(True)
    assert panel._auto_detect_box.isChecked()

    with qtbot.waitSignal(panel.autoDetectToggled) as blocker:
        panel._auto_detect_box.setChecked(False)
    assert blocker.args == [False]


def test_setting_the_opponent_announces_the_resize(panel, qtbot) -> None:
    """Le card avversario cambiano l'ingombro: la finestra deve poter reagire."""
    with qtbot.waitSignal(panel.contentResized):
        panel.set_opponent(4)


def test_reload_buttons_can_be_disabled_together(panel) -> None:
    panel.set_reload_buttons_enabled(False)
    assert not panel._reload_team_btn.isEnabled()
    assert not panel._reload_opp_btn.isEnabled()
    panel.set_reload_buttons_enabled(True)
    assert panel._reload_team_btn.isEnabled()


# ------------------------------------------------------------- feedback ⚠/✓


def test_success_feedback_marks_the_button_and_then_restores_it(panel, fake_timer) -> None:
    panel.flash_team_reload_success()
    assert panel._reload_team_btn.text().endswith("✓")
    assert panel._reload_team_btn.styleSheet() != ""

    fake_timer.fire_all()
    assert panel._reload_team_btn.text() == panel._RELOAD_TEAM_LABEL
    assert panel._reload_team_btn.styleSheet() == ""


def test_warning_feedback_puts_the_reason_in_the_tooltip(panel, fake_timer) -> None:
    original_tooltip = panel._reload_opp_btn.toolTip()
    panel.flash_opponent_reload_warning("schermata combattimento non rilevata")

    assert panel._reload_opp_btn.text().endswith("⚠")
    assert panel._reload_opp_btn.toolTip() == "schermata combattimento non rilevata"

    fake_timer.fire_all()
    assert panel._reload_opp_btn.toolTip() == original_tooltip


def test_an_empty_warning_message_leaves_the_tooltip_alone(panel, fake_timer) -> None:
    original_tooltip = panel._reload_team_btn.toolTip()
    panel.flash_team_reload_warning()
    assert panel._reload_team_btn.toolTip() == original_tooltip


def test_a_stale_timer_does_not_overwrite_newer_feedback(panel, fake_timer) -> None:
    """Successo e poi warning entro i 10 s: il ripristino del primo non deve agire."""
    panel.flash_team_reload_success()
    panel.flash_team_reload_warning("niente menu Pokemon")

    fake_timer.fire_first()  # scade il timer del successo, ormai superato
    assert panel._reload_team_btn.text().endswith("⚠")
    assert panel._reload_team_btn.toolTip() == "niente menu Pokemon"

    fake_timer.fire_all()  # scade anche quello del warning: si torna alla normalità
    assert panel._reload_team_btn.text() == panel._RELOAD_TEAM_LABEL


# ----------------------------------------------------------- TeamSlotWidget


def test_slot_widget_renders_an_empty_slot(panel) -> None:
    widget = panel._slots[5]
    assert widget._name_label.text() == "(vuoto)"
    assert widget._types_label.text() == ""
    assert widget._level_label.text() == ""
    assert not widget._remove_btn.isEnabled()


def test_slot_widget_renders_name_types_and_level(panel) -> None:
    widget = panel._slots[0]
    assert widget._name_label.text() == "Bulbasaur"
    assert "erba" in widget._types_label.text().lower()
    assert widget._level_label.text() == "Lv. 10"
    assert widget._remove_btn.isEnabled()


def test_slot_widget_renders_an_id_missing_from_the_dataset(panel) -> None:
    """Stato scritto da un dataset più ricco: si mostra l'id, non si solleva."""
    widget = panel._slots[0]
    widget.set_slot(TeamSlot(pokemon_id=9999, level=50))
    assert widget._name_label.text() == "#9999?"
    assert widget._types_label.text() == ""


def test_slot_widget_shows_a_dash_when_the_pokemon_has_no_types_in_that_gen(panel) -> None:
    """Chikorita non esiste in Gen 1: nessun badge, ma nemmeno un crash."""
    widget = panel._slots[0]
    widget.set_slot(TeamSlot(pokemon_id=152, level=20))
    assert "—" in widget._types_label.text()


def test_clearing_a_slot_empties_the_state_and_emits(panel, state, qtbot) -> None:
    with qtbot.waitSignal(panel.slotChanged) as blocker:
        panel._slots[1]._remove_btn.click()
    assert blocker.args == [1, None]
    assert state.team[1] is None
    assert _names(panel)[1] == "(vuoto)"
