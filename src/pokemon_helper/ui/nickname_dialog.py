"""Dialog per gestire la mappa `nickname → pokemon_id`.

Uso: da `TeamPanel` con un pulsante toolbar. Il dialog espone:

- tabella `nickname | species` con le entry correnti;
- pulsante "Aggiungi" che apre `AddPokemonDialog` per scegliere la specie e
  chiede il nickname come appare nel gioco (normalizzato uppercase);
- pulsante "Rimuovi" per la riga selezionata.

Il nickname va digitato come lo mostra il gioco, non come lo legge l'OCR: il
confronto lato `Recognizer` è fuzzy (`_match_nickname`), quindi assorbe gli
errori tipici sui font pixel (es. "FIAMMETTA" letto "FIAHHETTA").

Alla chiusura ritorna il dict aggiornato via `nicknames()`. Il chiamante
si occupa di sostituire `state.nicknames` e persistere.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QInputDialog,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from pokemon_helper.data import PokemonRepository
from pokemon_helper.ui.add_pokemon_dialog import AddPokemonDialog


class NicknameDialog(QDialog):
    """Editor delle voci nickname → species."""

    def __init__(
        self,
        repository: PokemonRepository,
        generation: int,
        nicknames: dict[str, int],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._repo = repository
        self._generation = generation
        # Copia difensiva: il chiamante deve leggere `nicknames()` a fine dialog.
        self._entries: dict[str, int] = dict(nicknames)

        self.setWindowTitle("Nickname personalizzati")
        self.setMinimumWidth(360)

        outer = QVBoxLayout(self)

        self._table = QTableWidget(0, 2, self)
        self._table.setHorizontalHeaderLabels(["Nickname (OCR)", "Pokemon"])
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.horizontalHeader().setStretchLastSection(True)
        outer.addWidget(self._table)

        actions = QHBoxLayout()
        add_btn = QPushButton("Aggiungi", self)
        add_btn.clicked.connect(self._on_add)
        actions.addWidget(add_btn)
        remove_btn = QPushButton("Rimuovi selezionato", self)
        remove_btn.clicked.connect(self._on_remove)
        actions.addWidget(remove_btn)
        actions.addStretch(1)
        outer.addLayout(actions)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

        self._refresh_table()

    def nicknames(self) -> dict[str, int]:
        """Ritorna la mappa aggiornata (uppercase → pokemon_id)."""
        return dict(self._entries)

    # ------------------------------------------------------------------ handlers

    def _on_add(self) -> None:
        nickname, ok = QInputDialog.getText(
            self,
            "Nickname",
            "Nickname come appare nel gioco (case-insensitive):",
        )
        if not ok:
            return
        nickname = nickname.strip().upper()
        if not nickname:
            return
        dialog = AddPokemonDialog(self._repo, self._generation, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        slot = dialog.selected_slot()
        if slot is None:
            return
        self._entries[nickname] = slot.pokemon_id
        self._refresh_table()

    def _on_remove(self) -> None:
        row = self._table.currentRow()
        if row < 0:
            return
        nickname_item = self._table.item(row, 0)
        if nickname_item is None:
            return
        nickname = nickname_item.text()
        self._entries.pop(nickname, None)
        self._refresh_table()

    # ------------------------------------------------------------------ helpers

    def _refresh_table(self) -> None:
        self._table.setRowCount(0)
        for nickname in sorted(self._entries):
            pokemon_id = self._entries[nickname]
            pokemon = self._repo.get_by_id(pokemon_id)
            species = pokemon.name_it or pokemon.name_en if pokemon else f"#{pokemon_id}"
            row = self._table.rowCount()
            self._table.insertRow(row)
            nk_item = QTableWidgetItem(nickname)
            nk_item.setFlags(nk_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            sp_item = QTableWidgetItem(species)
            sp_item.setFlags(sp_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(row, 0, nk_item)
            self._table.setItem(row, 1, sp_item)
