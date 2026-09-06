"""Macchina a stati che traduce una sequenza di frame in eventi di battaglia.

`is_battle_screen` risponde su un frame isolato; qui teniamo la memoria fra
un frame e l'altro per riconoscere le *transizioni*, che sono ciò che
interessa a chi deve aggiornare il pannello:

- si entra in combattimento → riconoscere chi è in campo;
- si esce davvero → svuotare il pannello, senza farsi ingannare dalle
  schermate che coprono la battaglia senza chiuderla;
- cambia un Pokemon a metà lotta, da una parte o dall'altra → riconoscere di
  nuovo.

Il cambio dell'avversario si vedrebbe anche senza firma: durante l'animazione
il suo HUD sparisce, quindi arrivano un LEFT e un ENTERED. Il cambio del
*giocatore* no: la barra HP avversaria resta visibile per tutto il tempo,
nessuna transizione, e il pannello continuerebbe a mostrare il Pokemon
precedente. Per questo la firma copre entrambi i riquadri nome.

Due accortezze rendono il tutto usabile su frame reali:

**Isteresi.** Durante dissolvenze e animazioni la barra HP sparisce per
qualche frame, e un singolo frame anomalo non deve far rimbalzare lo stato.
Serve `confirmations` osservazioni consecutive concordi prima di cambiare
idea. Il default di 2 costa due intervalli di ritardo sull'ingresso in
battaglia — utile comunque, perché dà tempo agli sprite di finire di
comparire prima che parta il riconoscimento.

**Firma testuale, non pittorica.** La prima versione confrontava il pHash dei
riquadri nome e produceva falsi positivi in continuazione: fra una cattura e
l'altra il contenuto del frame trasla di un paio di pixel, e il pHash è
insensibile alla scala ma non alla traslazione, quindi oscillava fra due
valori ogni pochi secondi a gioco fermo. La firma è invece il testo letto
dall'OCR, confrontato per similarità: lo stesso nome letto due volte dà
0.91-0.96 anche quando l'OCR sbaglia un carattere (`FIAMHETTA` contro
`FIAHHETTA`), mentre due Pokemon diversi stanno sotto 0.46. La soglia a 0.75
sta nel mezzo con margine quasi doppio da entrambi i lati.

I lati vengono confrontati separatamente: mettendoli in un'unica stringa, il
lato rimasto uguale diluirebbe la differenza dell'altro.

La classe non conosce né PIL né le ROI: riceve `in_battle` e `signature` già
calcolati e ritorna l'evento. Così è verificabile senza emulatore.
"""

from __future__ import annotations

from collections.abc import Sequence
from difflib import SequenceMatcher
from enum import Enum

# Firma di un lato: il testo del riquadro nome, così come esce dall'OCR.
Signature = Sequence[str]


class BattleEvent(Enum):
    """Transizione osservata fra due poll consecutivi."""

    ENTERED = "entered"
    LEFT = "left"
    COMBATANTS_CHANGED = "combatants_changed"


# Similarità sotto la quale due letture sono considerate Pokemon diversi.
# Misurato su cattura live: rumore OCR 0.91-0.96, Pokemon diversi 0.40-0.46.
DEFAULT_SIGNATURE_SIMILARITY = 0.75
# Osservazioni concordi richieste prima di accettare un cambio di stato.
DEFAULT_CONFIRMATIONS = 2


class BattleWatcher:
    """Traduce osservazioni successive in eventi, con isteresi."""

    def __init__(
        self,
        *,
        confirmations: int = DEFAULT_CONFIRMATIONS,
        min_similarity: float = DEFAULT_SIGNATURE_SIMILARITY,
    ) -> None:
        if confirmations < 1:
            raise ValueError(f"confirmations must be >= 1, got {confirmations}")
        self._confirmations = confirmations
        self._min_similarity = min_similarity
        self._in_battle = False
        self._signature: Signature | None = None
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

    def observe(
        self, in_battle: bool | None, signature: Signature | None = None
    ) -> BattleEvent | None:
        """Registra un'osservazione e ritorna l'eventuale transizione.

        `in_battle=None` significa "non lo so": lo stato resta com'è e non
        viene emesso nulla. Serve per le schermate che non dicono nulla sul
        combattimento — l'elenco Pokemon su tutte, che si apre proprio *per*
        cambiare Pokemon a metà lotta e in cui la barra HP avversaria non è
        visibile. Trattarla come "fuori combattimento" svuoterebbe il
        pannello nel momento in cui serve di più.
        """
        if in_battle is None:
            # Azzera i pending: una transizione va confermata da osservazioni
            # davvero consecutive, non da due spezzoni separati da una pausa.
            self._pending = None
            self._pending_count = 0
            return None
        if in_battle != self._in_battle:
            return self._observe_change(in_battle, signature)

        # Stato confermato: azzera un eventuale cambio in sospeso.
        self._pending = None
        self._pending_count = 0
        if not in_battle:
            return None
        return self._observe_same_battle(signature)

    def _observe_change(self, in_battle: bool, signature: Signature | None) -> BattleEvent | None:
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

    def _observe_same_battle(self, signature: Signature | None) -> BattleEvent | None:
        """In battaglia da prima: cerca un cambio fra i Pokemon in campo."""
        if signature is None:
            return None
        if self._signature is None:
            # Prima firma utile della battaglia corrente: adottala in silenzio.
            self._signature = signature
            return None
        if signatures_differ(self._signature, signature, self._min_similarity):
            self._signature = signature
            return BattleEvent.COMBATANTS_CHANGED
        return None


def signatures_differ(left: Signature, right: Signature, min_similarity: float) -> bool:
    """Vero se almeno un lato è cambiato oltre la tolleranza sul rumore OCR.

    Firme di lunghezza diversa non sono confrontabili: le trattiamo come
    diverse, piuttosto che sollevare un errore in mezzo al polling. Una
    lettura vuota, invece, non prova nulla — l'OCR può aver mancato il
    riquadro per un frame — e non conta come cambio.
    """
    if len(left) != len(right):
        return True
    for before, after in zip(left, right, strict=True):
        if not before or not after:
            continue
        if SequenceMatcher(None, before, after).ratio() < min_similarity:
            return True
    return False
