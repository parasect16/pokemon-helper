"""Fixture per i test dei widget Qt.

I widget vengono costruiti davvero — non sono mock — ma su piattaforma
`offscreen`: senza, ogni test aprirebbe una finestra vera, ruberebbe il focus
alla sessione e non girerebbe su una macchina senza desktop. La variabile va
impostata prima che `pytest-qt` costruisca la `QApplication`, quindi in cima
a questo conftest e non dentro una fixture.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402 — deve venire dopo il setup della piattaforma Qt

from pokemon_helper.ui.state import AppState, TeamSlot  # noqa: E402
from pokemon_helper.ui.team_panel import TeamPanel  # noqa: E402

# Gen 1 perché è l'unica in cui tutti i Pokemon del repository di test hanno
# tipi: Chikorita compare solo da Gen 2 e renderebbe gli assert dipendenti
# dalla generazione scelta.
TEST_GENERATION = 1


@pytest.fixture
def state() -> AppState:
    """Stato con quattro slot pieni e due vuoti, tutti presenti nel repository."""
    return AppState(
        generation=TEST_GENERATION,
        team=[
            TeamSlot(pokemon_id=1, level=10),  # Bulbasaur
            TeamSlot(pokemon_id=4, level=12),  # Charmander
            TeamSlot(pokemon_id=81, level=15),  # Magnemite
            TeamSlot(pokemon_id=92, level=18),  # Gastly
            None,
            None,
        ],
    )


@pytest.fixture
def panel(qtbot, repository, state) -> TeamPanel:
    """`TeamPanel` sul repository in-memory, registrato per la pulizia."""
    widget = TeamPanel(repository, state)
    qtbot.addWidget(widget)
    return widget
