"""Pannello squadra: header (gen picker, toggle, chiudi) + sei slot.

Il widget è puramente presentazionale sopra `AppState`: legge lo stato
corrente dall'esterno, mostra i sei slot con nome/tipi/livello e apre
`AddPokemonDialog` per assegnare o modificare uno slot.

Segnali emessi verso l'app layer, che li usa per aggiornare `AppState` e
persistere:

- `generationChanged(int)`
- `slotChanged(int, TeamSlot | None)` — index in [0, 5], None per rimozione
- `clickThroughToggled(bool)`
- `closeRequested()`
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from pokemon_helper.data import PokemonRepository
from pokemon_helper.ui.add_pokemon_dialog import AddPokemonDialog
from pokemon_helper.ui.opponent_panel import OpponentPanel
from pokemon_helper.ui.state import (
    MAX_GENERATION,
    MIN_GENERATION,
    TEAM_SIZE,
    AppState,
    TeamSlot,
)
from pokemon_helper.ui.types_meta import color_for, label_it


class TeamPanel(QWidget):
    """Widget principale con header + squadra + apertura dialoghi."""

    generationChanged = Signal(int)
    slotChanged = Signal(int, object)  # (index, TeamSlot | None)
    clickThroughToggled = Signal(bool)
    closeRequested = Signal()

    def __init__(
        self, repository: PokemonRepository, state: AppState, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._repository = repository
        self._state = state
        self._slots: list[TeamSlotWidget] = []
        self._opponent_panel: OpponentPanel | None = None

        self._build_ui()
        self._refresh_slots()

    # ------------------------------------------------------- costruzione UI

    def _build_ui(self) -> None:
        self.setObjectName("teamPanel")
        # Sfondo scuro semi-trasparente + bordi arrotondati.
        self.setStyleSheet(
            """
            #teamPanel {
                background-color: rgba(20, 20, 30, 220);
                border-radius: 12px;
            }
            QLabel { color: #EAEAEA; }
            QPushButton {
                background-color: #303044;
                color: #EAEAEA;
                border: 1px solid #4a4a5f;
                border-radius: 4px;
                padding: 3px 8px;
            }
            QPushButton:hover { background-color: #40405a; }
            QComboBox, QCheckBox { color: #EAEAEA; }
            """
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 8, 10, 10)
        outer.setSpacing(6)

        outer.addLayout(self._build_header())

        for index in range(TEAM_SIZE):
            slot = TeamSlotWidget(index, self._repository, self._state.generation)
            slot.assignRequested.connect(self._open_dialog_for_slot)
            slot.removeRequested.connect(self._clear_slot)
            self._slots.append(slot)
            outer.addWidget(slot)

        # Sezione avversario: placeholder finché F4 non imposta un ID.
        self._opponent_panel = OpponentPanel(self._repository, self._state)
        outer.addWidget(self._opponent_panel)

    def _build_header(self) -> QHBoxLayout:
        header = QHBoxLayout()

        header.addWidget(QLabel("Gen"))
        self._gen_combo = QComboBox(self)
        for gen in range(MIN_GENERATION, MAX_GENERATION + 1):
            self._gen_combo.addItem(f"Gen {gen}", gen)
        self._gen_combo.setCurrentIndex(self._state.generation - MIN_GENERATION)
        self._gen_combo.currentIndexChanged.connect(self._on_generation_changed)
        header.addWidget(self._gen_combo)

        header.addStretch(1)

        self._click_through_check = QCheckBox("Click-through", self)
        self._click_through_check.setChecked(self._state.click_through)
        self._click_through_check.toggled.connect(self.clickThroughToggled.emit)
        header.addWidget(self._click_through_check)

        close_btn = QPushButton("×", self)
        close_btn.setFixedWidth(28)
        close_btn.setToolTip("Chiudi")
        close_btn.clicked.connect(self.closeRequested.emit)
        header.addWidget(close_btn)

        return header

    # -------------------------------------------------------- aggiornamento

    def apply_state(self, state: AppState) -> None:
        """Sincronizza il pannello con uno stato aggiornato dall'esterno."""
        self._state = state
        self._gen_combo.blockSignals(True)
        self._gen_combo.setCurrentIndex(state.generation - MIN_GENERATION)
        self._gen_combo.blockSignals(False)
        self._click_through_check.blockSignals(True)
        self._click_through_check.setChecked(state.click_through)
        self._click_through_check.blockSignals(False)
        self._refresh_slots()

    def _refresh_slots(self) -> None:
        for index, slot_widget in enumerate(self._slots):
            slot_widget.set_generation(self._state.generation)
            slot_widget.set_slot(self._state.team[index])
        if self._opponent_panel is not None:
            self._opponent_panel.apply_state(self._state)

    def set_opponent(self, pokemon_id: int | None) -> None:
        """API pubblica per impostare l'avversario (chiamata da F4 in futuro)."""
        if self._opponent_panel is not None:
            self._opponent_panel.set_opponent(pokemon_id)

    # ------------------------------------------------------------- handler

    def _on_generation_changed(self, index: int) -> None:
        generation = self._gen_combo.itemData(index)
        self._state.generation = generation
        self._refresh_slots()
        self.generationChanged.emit(generation)

    def _open_dialog_for_slot(self, slot_index: int) -> None:
        current = self._state.team[slot_index]
        dialog = AddPokemonDialog(self._repository, self._state.generation, self, initial=current)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        new_slot = dialog.selected_slot()
        if new_slot is None:
            return
        self._state.team[slot_index] = new_slot
        self._slots[slot_index].set_slot(new_slot)
        self.slotChanged.emit(slot_index, new_slot)

    def _clear_slot(self, slot_index: int) -> None:
        self._state.team[slot_index] = None
        self._slots[slot_index].set_slot(None)
        self.slotChanged.emit(slot_index, None)


class TeamSlotWidget(QFrame):
    """Singola riga della squadra: nome + tipi + livello + azioni."""

    assignRequested = Signal(int)
    removeRequested = Signal(int)

    def __init__(self, index: int, repository: PokemonRepository, generation: int) -> None:
        super().__init__()
        self._index = index
        self._repository = repository
        self._generation = generation

        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet("QFrame { background: transparent; }")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(6)

        self._name_label = QLabel("(vuoto)", self)
        name_font = QFont()
        name_font.setBold(True)
        self._name_label.setFont(name_font)
        self._name_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(self._name_label, stretch=2)

        self._types_label = QLabel("", self)
        self._types_label.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(self._types_label, stretch=3)

        self._level_label = QLabel("", self)
        self._level_label.setFixedWidth(48)
        self._level_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._level_label)

        self._edit_btn = QPushButton("…", self)
        self._edit_btn.setFixedWidth(26)
        self._edit_btn.setToolTip("Modifica / assegna")
        self._edit_btn.clicked.connect(lambda: self.assignRequested.emit(self._index))
        layout.addWidget(self._edit_btn)

        self._remove_btn = QPushButton("×", self)
        self._remove_btn.setFixedWidth(26)
        self._remove_btn.setToolTip("Svuota slot")
        self._remove_btn.clicked.connect(lambda: self.removeRequested.emit(self._index))
        layout.addWidget(self._remove_btn)

    def set_generation(self, generation: int) -> None:
        """Aggiorna la generazione senza cambiare lo slot corrente."""
        self._generation = generation

    def set_slot(self, slot: TeamSlot | None) -> None:
        """Renderizza lo slot corrente (o lo stato 'vuoto')."""
        if slot is None:
            self._name_label.setText("(vuoto)")
            self._types_label.setText("")
            self._level_label.setText("")
            self._remove_btn.setEnabled(False)
            return

        pokemon = self._repository.get_by_id(slot.pokemon_id)
        if pokemon is None:
            self._name_label.setText(f"#{slot.pokemon_id}?")
            self._types_label.setText("")
        else:
            self._name_label.setText(pokemon.name_it or pokemon.name_en)
            types = self._repository.get_types(slot.pokemon_id, self._generation)
            self._types_label.setText(self._render_types(types))

        self._level_label.setText(f"Lv. {slot.level}")
        self._remove_btn.setEnabled(True)

    @staticmethod
    def _render_types(types: tuple[str, ...]) -> str:
        """Rende i tipi come badge colorati in HTML."""
        if not types:
            return "<i style='color:#aaa'>—</i>"
        badges: list[str] = []
        for type_name in types:
            color = color_for(type_name)
            label = label_it(type_name)
            badges.append(
                f"<span style='background:{color}; color:white; "
                f"padding:1px 6px; border-radius:6px; margin-right:2px; "
                f"font-size:11px;'>{label}</span>"
            )
        return "".join(badges)
