"""Test dei due dialog: scelta del Pokemon e mappa dei nickname.

Nessuno dei due viene mai eseguito con `exec()` nei test — bloccherebbe su un
event loop modale. Si costruiscono, si pilotano i widget interni e si legge
il risultato, che è esattamente ciò che fa l'app layer dopo l'`exec()`.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog

from pokemon_helper.ui import nickname_dialog as nickname_module
from pokemon_helper.ui.add_pokemon_dialog import GENERATION_COMPATIBILITY, AddPokemonDialog
from pokemon_helper.ui.nickname_dialog import NicknameDialog
from pokemon_helper.ui.state import TeamSlot


def _rows(dialog: AddPokemonDialog) -> list[str]:
    return [dialog._list.item(i).text() for i in range(dialog._list.count())]


def _ids(dialog: AddPokemonDialog) -> list[int]:
    return [
        dialog._list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(dialog._list.count())
    ]


def _dialog(qtbot, repository, generation: int, initial=None) -> AddPokemonDialog:
    dialog = AddPokemonDialog(repository, generation, initial=initial)
    qtbot.addWidget(dialog)
    return dialog


# ------------------------------------------------------- AddPokemonDialog


def test_an_empty_search_lists_only_the_species_of_that_generation(qtbot, repository) -> None:
    """Gen 1 stretta: Chikorita (Gen 2) non deve comparire."""
    dialog = _dialog(qtbot, repository, 1)
    assert 152 not in _ids(dialog)
    assert 1 in _ids(dialog)


def test_gen_three_keeps_gen_one_but_not_gen_two(qtbot, repository) -> None:
    """FireRed è un remake Gen 1: i suoi Pokemon sono catturabili, quelli Gen 2 no."""
    assert GENERATION_COMPATIBILITY[3] == frozenset({1, 3})
    dialog = _dialog(qtbot, repository, 3)
    ids = _ids(dialog)
    assert 1 in ids
    assert 152 not in ids


def test_searching_widens_the_list_to_every_earlier_generation(qtbot, repository) -> None:
    """Uno Chikorita ottenuto per scambio in Gen 3 deve restare trovabile."""
    dialog = _dialog(qtbot, repository, 3)
    dialog._search.setText("chiko")
    assert _ids(dialog) == [152]


def test_the_search_matches_the_italian_name_too(qtbot, repository) -> None:
    dialog = _dialog(qtbot, repository, 5)
    dialog._search.setText("bulba")
    assert _ids(dialog) == [1]


def test_the_search_ignores_case_and_padding(qtbot, repository) -> None:
    dialog = _dialog(qtbot, repository, 5)
    dialog._search.setText("  GASTLY  ")
    assert _ids(dialog) == [92]


def test_a_search_without_matches_empties_the_list(qtbot, repository) -> None:
    dialog = _dialog(qtbot, repository, 5)
    dialog._search.setText("mewtwo")
    assert _ids(dialog) == []
    assert dialog.selected_slot() is None


def test_each_row_shows_debut_generation_and_types(qtbot, repository) -> None:
    dialog = _dialog(qtbot, repository, 1)
    dialog._search.setText("bulbasaur")
    assert _rows(dialog) == ["Bulbasaur [G1] — Erba/Veleno"]


def test_a_species_without_types_in_that_generation_still_shows_a_row(qtbot, repository) -> None:
    """Chikorita cercata da Gen 3: esiste, ma i suoi tipi Gen 3 non sono indicizzati."""
    dialog = _dialog(qtbot, repository, 2)
    dialog._search.setText("chikorita")
    assert _rows(dialog) == ["Chikorita [G2] — Erba"]


def test_the_info_label_says_which_filter_is_active(qtbot, repository) -> None:
    dialog = _dialog(qtbot, repository, 3)
    assert "G1, G3" in dialog._info_label.text()
    dialog._search.setText("chiko")
    assert "fino a Gen 3" in dialog._info_label.text()


def test_the_first_result_is_preselected(qtbot, repository) -> None:
    """Cerca e premi invio: senza preselezione l'OK non produrrebbe nulla."""
    dialog = _dialog(qtbot, repository, 5)
    dialog._search.setText("magne")
    assert dialog._list.currentRow() == 0


def test_accepting_returns_the_selected_species_and_level(qtbot, repository) -> None:
    dialog = _dialog(qtbot, repository, 5)
    dialog._search.setText("gastly")
    dialog._level_spin.setValue(42)
    dialog.accept()
    assert dialog.selected_slot() == TeamSlot(pokemon_id=92, level=42)


def test_rejecting_returns_nothing(qtbot, repository) -> None:
    dialog = _dialog(qtbot, repository, 5)
    dialog._search.setText("gastly")
    dialog.reject()
    assert dialog.selected_slot() is None


def test_a_double_click_accepts_the_dialog(qtbot, repository) -> None:
    dialog = _dialog(qtbot, repository, 5)
    dialog._search.setText("gastly")
    dialog._list.itemDoubleClicked.emit(dialog._list.item(0))
    assert dialog.result() == QDialog.DialogCode.Accepted


def test_editing_a_slot_starts_from_its_current_species_and_level(qtbot, repository) -> None:
    dialog = _dialog(qtbot, repository, 5, initial=TeamSlot(pokemon_id=92, level=31))
    assert dialog._search.text() == "Gastly"
    assert dialog._level_spin.value() == 31
    assert _ids(dialog) == [92]


def test_editing_a_slot_whose_species_is_unknown_leaves_the_search_empty(qtbot, repository) -> None:
    dialog = _dialog(qtbot, repository, 5, initial=TeamSlot(pokemon_id=9999, level=31))
    assert dialog._search.text() == ""
    assert dialog._level_spin.value() == 31


# ---------------------------------------------------------- NicknameDialog


class _FakeInputDialog:
    """Sostituto di `QInputDialog`: risponde con un testo deciso dal test."""

    def __init__(self, text: str, ok: bool = True) -> None:
        self.text = text
        self.ok = ok

    def getText(self, *_args, **_kwargs):  # noqa: N802 — firma di Qt
        return self.text, self.ok


class _FakeAddDialog:
    """Sostituto di `AddPokemonDialog`: accetta o annulla senza event loop."""

    slot: TeamSlot | None = TeamSlot(pokemon_id=4, level=50)
    accepted: bool = True

    def __init__(self, *_args, **_kwargs) -> None:
        pass

    def exec(self):
        return QDialog.DialogCode.Accepted if self.accepted else QDialog.DialogCode.Rejected

    def selected_slot(self):
        return self.slot


@pytest.fixture
def nick_dialog(qtbot, repository) -> NicknameDialog:
    dialog = NicknameDialog(repository, 1, {"FIAMMETTA": 4, "ZAPPY": 81})
    qtbot.addWidget(dialog)
    return dialog


def _table(dialog: NicknameDialog) -> list[tuple[str, str]]:
    return [
        (dialog._table.item(row, 0).text(), dialog._table.item(row, 1).text())
        for row in range(dialog._table.rowCount())
    ]


def test_existing_entries_are_listed_alphabetically_with_their_species(nick_dialog) -> None:
    assert _table(nick_dialog) == [("FIAMMETTA", "Charmander"), ("ZAPPY", "Magnemite")]


def test_an_entry_pointing_at_an_unknown_species_shows_the_raw_id(qtbot, repository) -> None:
    dialog = NicknameDialog(repository, 1, {"BOH": 9999})
    qtbot.addWidget(dialog)
    assert _table(dialog) == [("BOH", "#9999")]


def test_the_dialog_does_not_touch_the_map_it_was_given(nick_dialog) -> None:
    """Il chiamante persiste solo dopo un OK: annullare non deve aver già scritto."""
    original = {"FIAMMETTA": 4, "ZAPPY": 81}
    dialog_map = nick_dialog.nicknames()
    dialog_map["ALTRO"] = 1
    assert nick_dialog.nicknames() == original


def test_adding_normalises_the_nickname_to_uppercase(nick_dialog, monkeypatch) -> None:
    """L'OCR viene confrontato in uppercase: salvarlo com'è digitato non matcherebbe."""
    monkeypatch.setattr(nickname_module, "QInputDialog", _FakeInputDialog("  scintilla "))
    monkeypatch.setattr(nickname_module, "AddPokemonDialog", _FakeAddDialog)

    nick_dialog._on_add()

    assert nick_dialog.nicknames()["SCINTILLA"] == 4
    assert ("SCINTILLA", "Charmander") in _table(nick_dialog)


def test_cancelling_the_name_prompt_adds_nothing(nick_dialog, monkeypatch) -> None:
    monkeypatch.setattr(nickname_module, "QInputDialog", _FakeInputDialog("SCINTILLA", ok=False))
    monkeypatch.setattr(nickname_module, "AddPokemonDialog", _FakeAddDialog)

    nick_dialog._on_add()

    assert "SCINTILLA" not in nick_dialog.nicknames()


def test_an_empty_nickname_adds_nothing(nick_dialog, monkeypatch) -> None:
    monkeypatch.setattr(nickname_module, "QInputDialog", _FakeInputDialog("   "))
    monkeypatch.setattr(nickname_module, "AddPokemonDialog", _FakeAddDialog)

    nick_dialog._on_add()

    assert nick_dialog.nicknames() == {"FIAMMETTA": 4, "ZAPPY": 81}


def test_cancelling_the_species_choice_adds_nothing(nick_dialog, monkeypatch) -> None:
    class _Rejected(_FakeAddDialog):
        accepted = False

    monkeypatch.setattr(nickname_module, "QInputDialog", _FakeInputDialog("SCINTILLA"))
    monkeypatch.setattr(nickname_module, "AddPokemonDialog", _Rejected)

    nick_dialog._on_add()

    assert "SCINTILLA" not in nick_dialog.nicknames()


def test_accepting_without_a_species_adds_nothing(nick_dialog, monkeypatch) -> None:
    """OK con lista vuota: `selected_slot()` ritorna None e non c'è nulla da mappare."""

    class _NoSlot(_FakeAddDialog):
        slot = None

    monkeypatch.setattr(nickname_module, "QInputDialog", _FakeInputDialog("SCINTILLA"))
    monkeypatch.setattr(nickname_module, "AddPokemonDialog", _NoSlot)

    nick_dialog._on_add()

    assert "SCINTILLA" not in nick_dialog.nicknames()


def test_removing_drops_the_selected_row(nick_dialog) -> None:
    nick_dialog._table.setCurrentCell(0, 0)
    nick_dialog._on_remove()
    assert _table(nick_dialog) == [("ZAPPY", "Magnemite")]


def test_removing_without_a_selection_is_a_no_op(nick_dialog) -> None:
    nick_dialog._table.setCurrentCell(-1, -1)
    nick_dialog._on_remove()
    assert len(_table(nick_dialog)) == 2
