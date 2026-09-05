"""Dialog per selezionare un Pokemon e assegnarne il livello.

Ricerca per prefisso di nome (italiano o inglese) sulla lista dei Pokemon
introdotti fino alla generazione corrente. Restituisce un `TeamSlot` con id
e livello scelti dall'utente, o `None` se l'operazione viene annullata.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from pokemon_helper.data import PokemonRepository
from pokemon_helper.ui.state import MAX_LEVEL, MIN_LEVEL, TeamSlot
from pokemon_helper.ui.types_meta import label_it


class AddPokemonDialog(QDialog):
    """Dialog modale per scegliere un Pokemon e il suo livello."""

    def __init__(
        self,
        repository: PokemonRepository,
        generation: int,
        parent: QWidget | None = None,
        initial: TeamSlot | None = None,
    ) -> None:
        """Costruisce il dialog per la generazione data.

        `initial` pre-popola l'input di ricerca e il livello quando si
        modifica uno slot già assegnato.
        """
        super().__init__(parent)
        self.setWindowTitle(f"Aggiungi Pokemon — Gen {generation}")
        self.setModal(True)
        self.resize(360, 460)

        self._repository = repository
        self._generation = generation
        # Cache: elenco Pokemon disponibili fino alla generazione selezionata
        # (introduced <= generation). Piccolo (≤649 righe): stare in memoria
        # non è un problema.
        self._all_pokemon = repository.list_by_generation(generation)

        self._build_ui(initial)
        self._populate_list(filter_text="")

    # --------------------------------------------------------------- build

    def _build_ui(self, initial: TeamSlot | None) -> None:
        layout = QVBoxLayout(self)

        # Info: contatore Pokemon disponibili in questa generazione.
        info = QLabel(
            f"{len(self._all_pokemon)} Pokemon disponibili fino a Gen {self._generation}",
            self,
        )
        info.setStyleSheet("color: #666; font-size: 11px;")
        layout.addWidget(info)

        # Ricerca
        self._search = QLineEdit(self)
        self._search.setPlaceholderText("Cerca per nome (italiano o inglese)")
        self._search.textChanged.connect(self._populate_list)
        layout.addWidget(self._search)

        # Lista risultati
        self._list = QListWidget(self)
        self._list.itemDoubleClicked.connect(self._accept_from_double_click)
        layout.addWidget(self._list, stretch=1)

        # Riga livello
        level_row = QHBoxLayout()
        level_row.addWidget(QLabel("Livello:"))
        self._level_spin = QSpinBox(self)
        self._level_spin.setRange(MIN_LEVEL, MAX_LEVEL)
        self._level_spin.setValue(50 if initial is None else initial.level)
        level_row.addWidget(self._level_spin)
        level_row.addStretch(1)
        layout.addLayout(level_row)

        # Pulsanti OK / Annulla
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        if initial is not None:
            initial_pokemon = self._repository.get_by_id(initial.pokemon_id)
            if initial_pokemon is not None:
                self._search.setText(initial_pokemon.name_it or initial_pokemon.name_en)

    # --------------------------------------------------------- populate

    def _populate_list(self, filter_text: str = "") -> None:
        """Filtra e ripopola la lista dei Pokemon."""
        needle = filter_text.strip().lower()
        self._list.clear()
        for pokemon in self._all_pokemon:
            name_it = (pokemon.name_it or "").lower()
            name_en = pokemon.name_en.lower()
            if needle and needle not in name_it and needle not in name_en:
                continue
            types = self._repository.get_types(pokemon.id, self._generation)
            display = self._format_pokemon_row(pokemon.name_it or pokemon.name_en, types)
            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, pokemon.id)
            self._list.addItem(item)

        # Seleziona automaticamente il primo risultato per accettazione veloce.
        if self._list.count() > 0:
            self._list.setCurrentRow(0)

    @staticmethod
    def _format_pokemon_row(name: str, types: tuple[str, ...]) -> str:
        """Riga display: nome + tipi in italiano (es. 'Charizard — Fuoco/Volante')."""
        if not types:
            return name
        types_it = "/".join(label_it(t) for t in types)
        return f"{name} — {types_it}"

    # ------------------------------------------------------------ accept

    def _accept_from_double_click(self, _item: QListWidgetItem) -> None:
        """Il doppio click su un risultato equivale a premere OK."""
        self.accept()

    def selected_slot(self) -> TeamSlot | None:
        """Ritorna lo slot scelto dopo `exec()`; `None` se annullato o vuoto."""
        if self.result() != QDialog.DialogCode.Accepted:
            return None
        current = self._list.currentItem()
        if current is None:
            return None
        pokemon_id = int(current.data(Qt.ItemDataRole.UserRole))
        return TeamSlot(pokemon_id=pokemon_id, level=self._level_spin.value())
