"""Macchina a stati che traduce una sequenza di frame in eventi di battaglia.

`is_battle_screen` risponde su un frame isolato; qui teniamo la memoria fra
un frame e l'altro per riconoscere le *transizioni*, che sono ciò che
interessa a chi deve aggiornare il pannello:

- si entra in combattimento → riconoscere l'avversario;
- si esce → svuotare il pannello;
- l'avversario cambia a metà lotta (l'allenatore ne manda in campo un altro)
  → riconoscere di nuovo.

Due accortezze rendono il tutto usabile su frame reali:

**Isteresi.** Durante dissolvenze e animazioni la barra HP sparisce per
qualche frame, e un singolo frame anomalo non deve far rimbalzare lo stato.
Serve `confirmations` osservazioni consecutive concordi prima di cambiare
idea. A 500 ms di intervallo, il default di 2 costa un secondo di ritardo
sull'ingresso in battaglia — utile comunque, perché dà tempo agli sprite di
finire di comparire prima che parta il riconoscimento.

**Firma tollerante.** Il cambio di avversario si rileva confrontando una
firma (il pHash della ROI del nome) fra un poll e l'altro. Il confronto è a
distanza di Hamming e non per uguaglianza: sullo stesso Pokemon la firma
oscilla di qualche bit per via dell'anti-aliasing della scala non intera.

La classe non conosce né PIL né le ROI: riceve `in_battle` e `signature`
già calcolati e ritorna l'evento. Così è verificabile senza emulatore.
"""

from __future__ import annotations

from enum import Enum


class BattleEvent(Enum):
    """Transizione osservata fra due poll consecutivi."""

    ENTERED = "entered"
    LEFT = "left"
    OPPONENT_CHANGED = "opponent_changed"


# Bit di differenza oltre i quali due firme sono considerate Pokemon diversi.
# Sotto questa soglia le differenze sono rumore di scaling sullo stesso nome.
DEFAULT_SIGNATURE_DISTANCE = 12
# Osservazioni concordi richieste prima di accettare un cambio di stato.
DEFAULT_CONFIRMATIONS = 2


class BattleWatcher:
    """Traduce osservazioni successive in eventi, con isteresi."""

    def __init__(
        self,
        *,
        confirmations: int = DEFAULT_CONFIRMATIONS,
        signature_distance: int = DEFAULT_SIGNATURE_DISTANCE,
    ) -> None:
        if confirmations < 1:
            raise ValueError(f"confirmations must be >= 1, got {confirmations}")
        self._confirmations = confirmations
        self._signature_distance = signature_distance
        self._in_battle = False
        self._signature: str | None = None
        self._pending: bool | None = None
        self._pending_count = 0

    @property
    def in_battle(self) -> bool:
        """Stato attualmente accettato (dopo isteresi)."""
        return self._in_battle

    def reset(self) -> None:
        """Dimentica tutto: da usare quando il polling viene disattivato.

        Senza questo, riattivando l'auto-detect a combattimento già in corso
        lo stato risulterebbe "in battaglia" fin dal primo poll e nessun
        evento `ENTERED` verrebbe emesso, lasciando il pannello vuoto.
        """
        self._in_battle = False
        self._signature = None
        self._pending = None
        self._pending_count = 0

    def observe(self, in_battle: bool, signature: str | None = None) -> BattleEvent | None:
        """Registra un'osservazione e ritorna l'eventuale transizione."""
        if in_battle != self._in_battle:
            return self._observe_change(in_battle, signature)

        # Stato confermato: azzera un eventuale cambio in sospeso.
        self._pending = None
        self._pending_count = 0
        if not in_battle:
            return None
        return self._observe_same_battle(signature)

    def _observe_change(self, in_battle: bool, signature: str | None) -> BattleEvent | None:
        """Accumula osservazioni discordi finché non raggiungono l'isteresi."""
        if self._pending == in_battle:
            self._pending_count += 1
        else:
            self._pending = in_battle
            self._pending_count = 1
        if self._pending_count < self._confirmations:
            return None

        self._in_battle = in_battle
        self._pending = None
        self._pending_count = 0
        if in_battle:
            self._signature = signature
            return BattleEvent.ENTERED
        self._signature = None
        return BattleEvent.LEFT

    def _observe_same_battle(self, signature: str | None) -> BattleEvent | None:
        """In battaglia da prima: cerca un cambio di avversario."""
        if signature is None:
            return None
        if self._signature is None:
            # Prima firma utile della battaglia corrente: adottala in silenzio.
            self._signature = signature
            return None
        if signature_differs(self._signature, signature, self._signature_distance):
            self._signature = signature
            return BattleEvent.OPPONENT_CHANGED
        return None


def signature_differs(left: str, right: str, max_distance: int) -> bool:
    """Vero se due firme esadecimali distano più di `max_distance` bit.

    Firme di lunghezza diversa non sono confrontabili: le trattiamo come
    diverse, piuttosto che sollevare un errore in mezzo al polling.
    """
    if len(left) != len(right):
        return True
    return bin(int(left, 16) ^ int(right, 16)).count("1") > max_distance
