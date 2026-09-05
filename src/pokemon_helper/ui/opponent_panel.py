"""Sezione avversario del pannello overlay.

Due modalità di visualizzazione, alternate via `set_opponent`:

- **Nessun avversario** (default e caso F2): mostra il placeholder
  "Combattimento non in corso".
- **Avversario impostato** (via `set_opponent(pokemon_id)`, in futuro
  chiamato automaticamente da F4): mostra nome + tipi + tabella con difesa
  (max moltiplicatore in ingresso dagli STAB avversari) e offesa (max
  moltiplicatore in uscita con gli STAB del membro squadra) per ciascun
  Pokemon in squadra. Il match migliore è evidenziato in grassetto.

La logica dei moltiplicatori vive in `pokemon_helper.engine.matchup`; qui
resta solo la formattazione e il rendering.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from pokemon_helper.data import PokemonRepository
from pokemon_helper.engine import EffectivenessEngine, best_matchup_index, compute_matchup
from pokemon_helper.ui.state import AppState
from pokemon_helper.ui.types_meta import color_for, label_it


def format_multiplier(value: float) -> str:
    """Formatta un moltiplicatore in forma compatta per la tabella."""
    if value == 0:
        return "0×"
    if value == 0.25:
        return "¼×"
    if value == 0.5:
        return "½×"
    if value == 1:
        return "1×"
    if value == 2:
        return "2×"
    if value == 4:
        return "4×"
    return f"{value:g}×"


def defense_color(multiplier: float) -> str:
    """Colore per un valore di difesa (alto = pericolo, rosso)."""
    if multiplier == 0:
        return "#3f5f3f"  # immune: verde scuro (ottimo)
    if multiplier >= 4:
        return "#c02020"
    if multiplier >= 2:
        return "#e08040"
    if multiplier <= 0.25:
        return "#20a020"
    if multiplier <= 0.5:
        return "#60c060"
    return "#606078"


def offense_color(multiplier: float) -> str:
    """Colore per un valore di offesa (alto = vantaggio, verde)."""
    if multiplier == 0:
        return "#5a2828"  # immunità nemica: colpo inutile
    if multiplier >= 4:
        return "#20a020"
    if multiplier >= 2:
        return "#60c060"
    if multiplier <= 0.25:
        return "#c02020"
    if multiplier <= 0.5:
        return "#e08040"
    return "#606078"


class OpponentPanel(QWidget):
    """Pannello con placeholder + eventuale tabella debolezze/coperture."""

    def __init__(self, repository: PokemonRepository, state: AppState) -> None:
        super().__init__()
        self._repo = repository
        self._state = state
        self._opponent_id: int | None = None
        self._content: QWidget | None = None

        # Layout esterno: il contenuto interno è rigenerato ad ogni refresh().
        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(0, 6, 0, 0)
        self._outer.setSpacing(0)

        self._refresh()

    # -------------------------------------------------------- public API

    def set_opponent(self, pokemon_id: int | None) -> None:
        """Imposta l'avversario corrente. In F2 nessuno lo chiama (rimane None)."""
        if self._opponent_id == pokemon_id:
            return
        self._opponent_id = pokemon_id
        self._refresh()

    def apply_state(self, state: AppState) -> None:
        """Sincronizza con nuovo stato (squadra o generazione cambiati)."""
        self._state = state
        self._refresh()

    # ----------------------------------------------------------- rendering

    def _refresh(self) -> None:
        """Ricostruisce il contenuto interno da zero."""
        if self._content is not None:
            self._outer.removeWidget(self._content)
            self._content.deleteLater()
            self._content = None

        if self._opponent_id is None:
            self._content = self._build_placeholder()
        else:
            self._content = self._build_battle() or self._build_placeholder()

        self._outer.addWidget(self._content)

    def _build_placeholder(self) -> QWidget:
        """Riquadro con separatore + messaggio 'combattimento non in corso'."""
        widget = QWidget(self)
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        layout.addWidget(_separator(widget))

        label = QLabel("Combattimento non in corso", widget)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("color: #7a7a8a; font-style: italic; padding: 6px;")
        layout.addWidget(label)
        return widget

    def _build_battle(self) -> QWidget | None:
        """Riquadro con avversario + tabella difesa/offesa per la squadra.

        Ritorna `None` se i dati per costruirlo sono incompleti (avversario
        sconosciuto, senza tipi in questa generazione).
        """
        if self._opponent_id is None:
            return None
        opponent = self._repo.get_by_id(self._opponent_id)
        if opponent is None:
            return None
        opp_types = self._repo.get_types(opponent.id, self._state.generation)
        if not opp_types:
            return None

        widget = QWidget(self)
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        layout.addWidget(_separator(widget))
        layout.addLayout(self._build_opponent_header(widget, opponent, opp_types))
        layout.addLayout(self._build_matchup_grid(widget, opp_types))
        return widget

    def _build_opponent_header(self, parent: QWidget, opponent, opp_types) -> QHBoxLayout:
        header = QHBoxLayout()
        name_label = QLabel(f"Avversario: <b>{opponent.name_it or opponent.name_en}</b>", parent)
        name_label.setTextFormat(Qt.TextFormat.RichText)
        header.addWidget(name_label)
        header.addStretch(1)

        types_label = QLabel(_render_type_badges(opp_types), parent)
        types_label.setTextFormat(Qt.TextFormat.RichText)
        header.addWidget(types_label)
        return header

    def _build_matchup_grid(self, parent: QWidget, opp_types: tuple[str, ...]) -> QGridLayout:
        engine = EffectivenessEngine(self._state.generation)

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(2)

        header_style = "color: #aaaabb; font-size: 10px;"
        for col, text in enumerate(("Squadra", "Dif.", "Off.")):
            lbl = QLabel(text, parent)
            lbl.setStyleSheet(header_style)
            grid.addWidget(lbl, 0, col)

        rows = self._compute_rows(engine, opp_types)
        best = best_matchup_index([(defense, offense) for _, defense, offense in rows])

        for row_index, (name, defense, offense) in enumerate(rows):
            grid_row = row_index + 1
            is_best = row_index == best

            name_lbl = QLabel(name, parent)
            def_lbl = _multiplier_badge(defense, defense_color, parent)
            off_lbl = _multiplier_badge(offense, offense_color, parent)

            if is_best:
                for lbl in (name_lbl, def_lbl, off_lbl):
                    font = lbl.font()
                    font.setBold(True)
                    lbl.setFont(font)

            grid.addWidget(name_lbl, grid_row, 0)
            grid.addWidget(def_lbl, grid_row, 1)
            grid.addWidget(off_lbl, grid_row, 2)

        if not rows:
            empty = QLabel("(squadra vuota)", parent)
            empty.setStyleSheet("color: #7a7a8a; font-style: italic;")
            grid.addWidget(empty, 1, 0, 1, 3)

        return grid

    def _compute_rows(
        self,
        engine: EffectivenessEngine,
        opp_types: tuple[str, ...],
    ) -> list[tuple[str, float, float]]:
        """Per ogni slot squadra popolato ritorna `(nome, difesa, offesa)`."""
        rows: list[tuple[str, float, float]] = []
        for slot in self._state.team:
            if slot is None:
                continue
            pokemon = self._repo.get_by_id(slot.pokemon_id)
            if pokemon is None:
                continue
            team_types = self._repo.get_types(slot.pokemon_id, self._state.generation)
            if not team_types:
                continue
            defense, offense = compute_matchup(engine, opp_types, team_types)
            rows.append((pokemon.name_it or pokemon.name_en, defense, offense))
        return rows


# ---------------------------------------------------------------------------
# Helper di rendering
# ---------------------------------------------------------------------------


def _separator(parent: QWidget) -> QFrame:
    """Linea di separazione sottile fra sezioni del pannello."""
    line = QFrame(parent)
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFixedHeight(1)
    line.setStyleSheet("background-color: #4a4a5f;")
    return line


def _multiplier_badge(value: float, color_fn, parent: QWidget) -> QLabel:
    """Label con background colorato in base al valore del moltiplicatore."""
    lbl = QLabel(format_multiplier(value), parent)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl.setStyleSheet(
        f"color: white; background: {color_fn(value)}; "
        "padding: 1px 6px; border-radius: 4px; min-width: 32px;"
    )
    return lbl


def _render_type_badges(types: tuple[str, ...]) -> str:
    """Badge HTML colorati per una tupla di tipi."""
    badges: list[str] = []
    for type_name in types:
        color = color_for(type_name)
        label = label_it(type_name)
        badges.append(
            f"<span style='background:{color}; color:white; padding:1px 6px; "
            f"border-radius:6px; margin-left:2px; font-size:11px;'>{label}</span>"
        )
    return "".join(badges)
