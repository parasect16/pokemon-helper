"""Sezione avversario del pannello overlay.

Tre stati di visualizzazione:

- **Nessun avversario**: placeholder "Combattimento non in corso".
- **Avversario impostato, player attivo sconosciuto**: mostra intestazione
  avversario + suggerimento di attivare il recognize per identificare il
  Pokemon del giocatore in campo.
- **Avversario + player attivo entrambi impostati**: mostra una riga
  singola con nome/tipi del player in campo e i moltiplicatori difesa
  (max STAB nemico in ingresso) e offesa (max STAB proprio in uscita).

I dati coprono solo i due Pokemon **effettivamente in scontro** (avversario
+ player attivo). La logica dei moltiplicatori vive in
`pokemon_helper.engine.matchup`; qui resta solo formattazione e rendering.
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
from pokemon_helper.engine import EffectivenessEngine, compute_matchup
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
        self._active_player_id: int | None = None
        self._content: QWidget | None = None

        # Layout esterno: il contenuto interno è rigenerato ad ogni refresh().
        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(0, 6, 0, 0)
        self._outer.setSpacing(0)

        self._refresh()

    # -------------------------------------------------------- public API

    def set_opponent(self, pokemon_id: int | None) -> None:
        """Imposta l'avversario corrente."""
        if self._opponent_id == pokemon_id:
            return
        self._opponent_id = pokemon_id
        self._refresh()

    def set_active_player(self, pokemon_id: int | None) -> None:
        """Imposta il Pokemon del giocatore attualmente in campo.

        Il matchup viene sempre calcolato per la coppia
        (avversario, player attivo). Se uno dei due manca, il pannello
        mostra un placeholder informativo invece della tabella.
        """
        if self._active_player_id == pokemon_id:
            return
        self._active_player_id = pokemon_id
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
        """Riquadro con lo scontro corrente: solo player attivo vs avversario.

        Ritorna `None` se i dati per costruirlo sono incompleti (avversario
        sconosciuto o senza tipi nella generazione). Se manca il player attivo
        mostra un messaggio informativo al posto della tabella.
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
        layout.addWidget(self._build_matchup_row(widget, opp_types))
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

    def _build_matchup_row(self, parent: QWidget, opp_types: tuple[str, ...]) -> QWidget:
        """Riga singola con difesa/offesa del player attivo vs avversario.

        Se il player attivo non è impostato (nessun recognize battaglia
        eseguito), mostra un messaggio informativo invece della riga.
        """
        container = QWidget(parent)
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 4, 0, 0)
        container_layout.setSpacing(2)

        if self._active_player_id is None:
            hint = QLabel(
                "Player in campo sconosciuto — usa Ctrl+Alt+R o ⚔ Avversario "
                "in combattimento per rilevarlo",
                container,
            )
            hint.setWordWrap(True)
            hint.setStyleSheet("color: #7a7a8a; font-style: italic; padding: 4px;")
            container_layout.addWidget(hint)
            return container

        player_pokemon = self._repo.get_by_id(self._active_player_id)
        if player_pokemon is None:
            hint = QLabel(f"Player id={self._active_player_id} non nel dataset", container)
            hint.setStyleSheet("color: #7a7a8a; font-style: italic; padding: 4px;")
            container_layout.addWidget(hint)
            return container

        player_types = self._repo.get_types(player_pokemon.id, self._state.generation)
        if not player_types:
            hint = QLabel(
                f"{player_pokemon.name_it or player_pokemon.name_en}: nessun tipo "
                f"per Gen {self._state.generation}",
                container,
            )
            hint.setStyleSheet("color: #7a7a8a; font-style: italic; padding: 4px;")
            container_layout.addWidget(hint)
            return container

        engine = EffectivenessEngine(self._state.generation)
        defense, offense = compute_matchup(engine, opp_types, player_types)

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(2)

        header_style = "color: #aaaabb; font-size: 10px;"
        for col, text in enumerate(("In campo", "Dif.", "Off.")):
            lbl = QLabel(text, container)
            lbl.setStyleSheet(header_style)
            grid.addWidget(lbl, 0, col)

        name = player_pokemon.name_it or player_pokemon.name_en
        name_lbl = QLabel(name, container)
        name_lbl.setTextFormat(Qt.TextFormat.RichText)
        name_lbl.setText(f"<b>{name}</b> {_render_type_badges(player_types)}")
        def_lbl = _multiplier_badge(defense, defense_color, container)
        off_lbl = _multiplier_badge(offense, offense_color, container)

        grid.addWidget(name_lbl, 1, 0)
        grid.addWidget(def_lbl, 1, 1)
        grid.addWidget(off_lbl, 1, 2)

        container_layout.addLayout(grid)
        return container


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
