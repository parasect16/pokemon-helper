"""Dialog per selezionare un Pokemon e assegnarne il livello.

Comportamento del filtro:

- Senza testo di ricerca: mostra solo i Pokemon **introdotti nella
  generazione selezionata** (strict, `generation_introduced == gen`).
- Con testo di ricerca: estende la lista a **tutti i Pokemon fino a quella
  generazione** (`generation_introduced <= gen`) per permettere di aggiungere
  Pokemon ottenuti tramite scambio da generazioni precedenti.

Restituisce un `TeamSlot` con id e livello scelti, o `None` se annullato.
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
        # Cache: due sottoinsiemi tenuti in memoria (≤649 righe totali).
        # `_all_pokemon`: tutti i Pokemon disponibili fino alla gen (per la
        # ricerca cross-gen). `_strict_pokemon`: solo quelli introdotti in
        # questa specifica generazione (default a tendina).
        self._all_pokemon = repository.list_by_generation(generation)
        self._strict_pokemon = [
            p for p in self._all_pokemon if p.generation_introduced == generation
        ]

        self._build_ui(initial)
        self._populate_list(filter_text="")

    # --------------------------------------------------------------- build

    def _build_ui(self, initial: TeamSlot | None) -> None:
        layout = QVBoxLayout(self)

        # Info: descrive il filtro corrente, aggiornata da `_populate_list`.
        self._info_label = QLabel("", self)
        self._info_label.setStyleSheet("color: #666; font-size: 11px;")
        layout.addWidget(self._info_label)

        # Ricerca. Il placeholder chiarisce che scrivere allarga la lista
        # ai Pokemon di generazioni precedenti (utile per gli scambi).
        self._search = QLineEdit(self)
        self._search.setPlaceholderText("Cerca per nome (mostra anche Pokemon di gen precedenti)")
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
        """Filtra e ripopola la lista dei Pokemon.

        Strategia in due modalità:
        - Ricerca vuota: usa solo `_strict_pokemon` (Pokemon della gen).
        - Ricerca non vuota: usa `_all_pokemon` (fino alla gen) per coprire
          il caso "ho ottenuto uno Snorlax via scambio in un gioco Gen 3".
        """
        needle = filter_text.strip().lower()
        if needle:
            source = self._all_pokemon
            self._info_label.setText(
                f"Ricerca fra tutti i Pokemon fino a Gen {self._generation} "
                f"({len(self._all_pokemon)} totali)"
            )
        else:
            source = self._strict_pokemon
            self._info_label.setText(
                f"{len(self._strict_pokemon)} Pokemon di Gen {self._generation} "
                "(scrivi per cercare anche in gen precedenti)"
            )

        self._list.clear()
        for pokemon in source:
            name_it = (pokemon.name_it or "").lower()
            name_en = pokemon.name_en.lower()
            if needle and needle not in name_it and needle not in name_en:
                continue
            types = self._repository.get_types(pokemon.id, self._generation)
            display = self._format_pokemon_row(
                pokemon.name_it or pokemon.name_en,
                types,
                pokemon.generation_introduced,
            )
            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, pokemon.id)
            self._list.addItem(item)

        # Seleziona automaticamente il primo risultato per accettazione veloce.
        if self._list.count() > 0:
            self._list.setCurrentRow(0)

    @staticmethod
    def _format_pokemon_row(name: str, types: tuple[str, ...], introduced_gen: int) -> str:
        """Riga display: nome + gen debutto + tipi (es. 'Charizard [G1] — Fuoco/Volante')."""
        gen_tag = f"[G{introduced_gen}]"
        if not types:
            return f"{name} {gen_tag}"
        types_it = "/".join(label_it(t) for t in types)
        return f"{name} {gen_tag} — {types_it}"

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
