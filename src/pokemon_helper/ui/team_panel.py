"""Pannello squadra: header (gen picker) + sei slot + sezione avversario.

Il widget è puramente presentazionale sopra `AppState`: legge lo stato
corrente dall'esterno, mostra i sei slot con nome/tipi/livello e apre
`AddPokemonDialog` per assegnare o modificare uno slot. La finestra
contenitrice (`CompanionWindow`) fornisce chrome nativo (drag, minimize,
close) quindi qui non c'è più né title bar custom né pulsante chiudi.

Segnali emessi verso l'app layer, che li usa per aggiornare `AppState` e
persistere:

- `generationChanged(int)`
- `slotChanged(int, TeamSlot | None)` — index in [0, 5], None per rimozione
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
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
from pokemon_helper.ui.types_meta import render_type_badges


class TeamPanel(QWidget):
    """Widget principale con header + squadra + apertura dialoghi."""

    generationChanged = Signal(int)
    slotChanged = Signal(int, object)  # (index, TeamSlot | None)
    teamReplaced = Signal(object)  # nuovo team completo (list[TeamSlot | None])
    reloadTeamRequested = Signal()  # utente ha cliccato "Ricarica squadra"
    reloadOpponentRequested = Signal()  # utente ha cliccato "Ricarica avversario"
    nicknamesRequested = Signal()  # utente ha cliccato "Nickname"
    autoDetectToggled = Signal(bool)  # utente ha cambiato l'interruttore auto-detect

    def __init__(
        self,
        repository: PokemonRepository,
        state: AppState,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._repository = repository
        self._state = state
        self._slots: list[TeamSlotWidget] = []
        self._opponent_panel: OpponentPanel | None = None
        self._active_player_id: int | None = None

        self._build_ui()
        self._refresh_slots()

    # ------------------------------------------------------- costruzione UI

    def _build_ui(self) -> None:
        self.setObjectName("teamPanel")
        # `WA_StyledBackground` è necessario affinché una QWidget "normale"
        # dipinga effettivamente il background-color dichiarato in QSS
        # (altrimenti Qt mostra la palette di sistema, chiara).
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        # Sfondo scuro opaco per il pannello. La finestra ospitante fornisce
        # bordi e chrome nativi Windows.
        self.setStyleSheet(
            """
            #teamPanel { background-color: rgb(24, 24, 34); }
            QLabel { color: #EAEAEA; }
            QPushButton {
                background-color: #303044;
                color: #EAEAEA;
                border: 1px solid #4a4a5f;
                border-radius: 4px;
                padding: 3px 8px;
            }
            QPushButton:hover { background-color: #40405a; }
            QComboBox {
                background-color: #303044;
                color: #EAEAEA;
                border: 1px solid #4a4a5f;
                border-radius: 4px;
                padding: 2px 6px;
                selection-background-color: #40405a;
                selection-color: #EAEAEA;
            }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView {
                background-color: #202030;
                color: #EAEAEA;
                selection-background-color: #40405a;
                border: 1px solid #4a4a5f;
            }
            """
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 8, 10, 10)
        outer.setSpacing(6)

        outer.addLayout(self._build_reload_buttons())
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

    _RELOAD_TEAM_LABEL = "⟳ Squadra"
    _RELOAD_OPP_LABEL = "⚔ Avversario"
    _SUCCESS_STYLE = (
        "QPushButton { background-color: #2c5c2c; border: 1px solid #5cd05c; color: #d0ffd0; }"
    )
    _WARNING_STYLE = (
        "QPushButton { background-color: #6b5a1c; border: 1px solid #e0c060; color: #ffe9a8; }"
    )
    _SUCCESS_HOLD_MS = 10_000
    _WARNING_HOLD_MS = 10_000

    def _build_reload_buttons(self) -> QHBoxLayout:
        """Riga di pulsanti di ricarica (equivalenti alle hotkey `Ctrl+Alt+T/R`)."""
        row = QHBoxLayout()
        row.setSpacing(4)

        # Uso simboli Unicode (⟳ = clockwise arrow, ⚔ = swords) per non
        # dipendere da asset icona esterni. Il tooltip cita la hotkey associata.
        self._reload_team_btn = QPushButton(self._RELOAD_TEAM_LABEL, self)
        self._reload_team_btn.setToolTip("Ricarica squadra dal menu Pokemon (Ctrl+Alt+T)")
        self._reload_team_btn.clicked.connect(lambda: self.reloadTeamRequested.emit())
        row.addWidget(self._reload_team_btn)

        self._reload_opp_btn = QPushButton(self._RELOAD_OPP_LABEL, self)
        self._reload_opp_btn.setToolTip(
            "Ricarica avversario dalla schermata di combattimento (Ctrl+Alt+R)"
        )
        self._reload_opp_btn.clicked.connect(lambda: self.reloadOpponentRequested.emit())
        row.addWidget(self._reload_opp_btn)

        self._nicknames_btn = QPushButton("🏷", self)
        self._nicknames_btn.setToolTip("Gestisci nickname personalizzati (nick → specie)")
        self._nicknames_btn.setFixedWidth(30)
        self._nicknames_btn.clicked.connect(lambda: self.nicknamesRequested.emit())
        row.addWidget(self._nicknames_btn)

        # Interruttore F4. Spento di default: mentre è attivo l'app cattura la
        # finestra dell'emulatore due volte al secondo, quindi deve essere una
        # scelta esplicita dell'utente e non un comportamento implicito.
        self._auto_detect_box = QCheckBox("Auto", self)
        self._auto_detect_box.setToolTip(
            "Rileva da solo l'inizio del combattimento e il cambio di avversario"
        )
        self._auto_detect_box.toggled.connect(lambda on: self.autoDetectToggled.emit(on))
        row.addWidget(self._auto_detect_box)

        row.addStretch(1)
        return row

    def set_auto_detect(self, enabled: bool) -> None:
        """Allinea l'interruttore allo stato persistito, senza emettere segnali."""
        was_blocked = self._auto_detect_box.blockSignals(True)
        self._auto_detect_box.setChecked(enabled)
        self._auto_detect_box.blockSignals(was_blocked)

    def set_reload_buttons_enabled(self, enabled: bool) -> None:
        """Abilita/disabilita entrambi i pulsanti di ricarica.

        Usato dall'app layer per dare feedback visivo mentre una cattura +
        riconoscimento è in corso (~200-400 ms su thread di background).
        """
        self._reload_team_btn.setEnabled(enabled)
        self._reload_opp_btn.setEnabled(enabled)

    def flash_team_reload_success(self) -> None:
        """Segnala successo sul pulsante squadra: check verde per 10 s."""
        self._flash(
            self._reload_team_btn,
            self._RELOAD_TEAM_LABEL,
            suffix="✓",
            style=self._SUCCESS_STYLE,
            tooltip=None,
        )

    def flash_opponent_reload_success(self) -> None:
        """Segnala successo sul pulsante avversario: check verde per 10 s."""
        self._flash(
            self._reload_opp_btn,
            self._RELOAD_OPP_LABEL,
            suffix="✓",
            style=self._SUCCESS_STYLE,
            tooltip=None,
        )

    def flash_team_reload_warning(self, message: str = "") -> None:
        """Segnala warning sul pulsante squadra: `⚠` giallo per 10 s.

        Il `message` opzionale viene messo come tooltip così l'utente può
        leggere il motivo (es. "schermata Pokemon non rilevata").
        """
        self._flash(
            self._reload_team_btn,
            self._RELOAD_TEAM_LABEL,
            suffix="⚠",
            style=self._WARNING_STYLE,
            tooltip=message or None,
        )

    def flash_opponent_reload_warning(self, message: str = "") -> None:
        """Segnala warning sul pulsante avversario: `⚠` giallo per 10 s."""
        self._flash(
            self._reload_opp_btn,
            self._RELOAD_OPP_LABEL,
            suffix="⚠",
            style=self._WARNING_STYLE,
            tooltip=message or None,
        )

    def _flash(
        self,
        button: QPushButton,
        base_label: str,
        *,
        suffix: str,
        style: str,
        tooltip: str | None,
    ) -> None:
        """Applica suffisso + stile temporaneo al pulsante, ripristina dopo 10 s."""
        original_tooltip = button.toolTip()
        button.setText(f"{base_label} {suffix}")
        button.setStyleSheet(style)
        if tooltip is not None:
            button.setToolTip(tooltip)

        def _reset() -> None:
            # No-op se nel frattempo un'altra azione ha cambiato lo stato:
            # timer stale non deve sovrascrivere feedback più recente.
            if button.text() == f"{base_label} {suffix}":
                button.setText(base_label)
                button.setStyleSheet("")
                if tooltip is not None:
                    button.setToolTip(original_tooltip)

        QTimer.singleShot(self._WARNING_HOLD_MS, _reset)

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
        return header

    # -------------------------------------------------------- aggiornamento

    def apply_state(self, state: AppState) -> None:
        """Sincronizza il pannello con uno stato aggiornato dall'esterno."""
        self._state = state
        self._gen_combo.blockSignals(True)
        self._gen_combo.setCurrentIndex(state.generation - MIN_GENERATION)
        self._gen_combo.blockSignals(False)
        self._refresh_slots()

    def _refresh_slots(self) -> None:
        for index, slot_widget in enumerate(self._slots):
            slot_widget.set_generation(self._state.generation)
            slot_widget.set_slot(self._state.team[index])
        if self._opponent_panel is not None:
            self._opponent_panel.apply_state(self._state)
        # Riapplica l'evidenziazione (potrebbe essere cambiata la squadra).
        if self._active_player_id is not None:
            self.set_active_player(self._active_player_id)

    def set_opponent(self, pokemon_id: int | None) -> None:
        """API pubblica per impostare l'avversario (chiamata da F4 in futuro)."""
        if self._opponent_panel is not None:
            self._opponent_panel.set_opponent(pokemon_id)

    def replace_team(self, new_team: list[TeamSlot | None]) -> None:
        """Rimpiazza il team con la lista fornita (esattamente `TEAM_SIZE` slot).

        Aggiorna `state.team`, ridisegna gli slot, riapplica l'evidenziazione
        del Pokemon attivo (se ancora presente nel nuovo team) e propaga
        `teamReplaced` per far persistere lo stato al layer app.
        """
        if len(new_team) != TEAM_SIZE:
            raise ValueError(f"replace_team richiede {TEAM_SIZE} slot, ricevuti {len(new_team)}")
        self._state.team = list(new_team)
        self._refresh_slots()
        self.teamReplaced.emit(self._state.team)

    def set_active_player(self, pokemon_id: int | None) -> None:
        """Marca lo slot squadra corrispondente come "attivo" in combattimento.

        Se `pokemon_id` non compare fra gli slot popolati (Pokemon non in
        squadra), nessuno slot risulta evidenziato — è un no-op silenzioso.
        Passando `None` si rimuove l'evidenziazione.

        Propaga anche a `OpponentPanel` così la tabella matchup si aggiorna
        per mostrare solo la coppia (avversario, player attivo).
        """
        self._active_player_id = pokemon_id
        for index, slot_widget in enumerate(self._slots):
            slot = self._state.team[index]
            slot_widget.set_active(
                slot is not None and pokemon_id is not None and slot.pokemon_id == pokemon_id
            )
        if self._opponent_panel is not None:
            self._opponent_panel.set_active_player(pokemon_id)

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

    _STYLE_INACTIVE = "QFrame#teamSlot { background: transparent; border-radius: 4px; }"
    _STYLE_ACTIVE = (
        "QFrame#teamSlot { background: rgba(104, 144, 240, 60); "
        "border: 1px solid #6890F0; border-radius: 4px; }"
    )

    def __init__(self, index: int, repository: PokemonRepository, generation: int) -> None:
        super().__init__()
        self._index = index
        self._repository = repository
        self._generation = generation

        self.setObjectName("teamSlot")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet(self._STYLE_INACTIVE)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(6)

        self._name_label = QLabel("(vuoto)", self)
        name_font = QFont()
        name_font.setBold(True)
        name_font.setPointSize(11)
        self._name_label.setFont(name_font)
        self._name_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(self._name_label, stretch=2)

        self._types_label = QLabel("", self)
        self._types_label.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(self._types_label, stretch=3)

        self._level_label = QLabel("", self)
        self._level_label.setFixedWidth(54)
        self._level_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        level_font = QFont()
        level_font.setBold(True)
        level_font.setPointSize(10)
        self._level_label.setFont(level_font)
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

    def set_active(self, active: bool) -> None:
        """Evidenzia lo slot se `active=True` (Pokemon in campo in battaglia)."""
        self.setStyleSheet(self._STYLE_ACTIVE if active else self._STYLE_INACTIVE)

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
        """Rende i tipi come badge colorati in HTML con contrasto auto."""
        if not types:
            return "<i style='color:#aaa'>—</i>"
        return render_type_badges(types, font_size_px=11)
