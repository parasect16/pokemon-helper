"""Stato dell'applicazione e persistenza su JSON.

Definisce il modello di stato (squadra, generazione selezionata, posizione
finestra) e uno `StateStore` che lo serializza in un file JSON sotto
`%APPDATA%\\pokemon-helper\\state.json`.

Le funzioni sono pure: non fanno side effect verso Qt né usano thread. Il
salvataggio è invocato esplicitamente dai chiamanti (ad esempio all'uscita
o dopo ogni modifica significativa dello stato).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

TEAM_SIZE: int = 6
MIN_LEVEL: int = 1
MAX_LEVEL: int = 100
MIN_GENERATION: int = 1
MAX_GENERATION: int = 5
DEFAULT_GENERATION: int = 5


@dataclass(frozen=True, slots=True)
class TeamSlot:
    """Slot della squadra: id del Pokemon e livello (1-100)."""

    pokemon_id: int
    level: int

    def __post_init__(self) -> None:
        if not MIN_LEVEL <= self.level <= MAX_LEVEL:
            raise ValueError(f"level must be in [{MIN_LEVEL}, {MAX_LEVEL}], got {self.level}")


@dataclass
class AppState:
    """Stato completo dell'applicazione, serializzabile su JSON.

    `team` è sempre una lista di lunghezza `TEAM_SIZE`; ogni elemento è uno
    `TeamSlot` oppure `None` per indicare uno slot vuoto.

    `nicknames` mappa testo OCR (normalizzato uppercase) a `pokemon_id`, usato
    da `Recognizer.recognize_team` come override sul fuzzy match: quando il
    gioco mostra un nickname custom (es. "FIAMMETTA" per Charizard), fuzzy
    fallisce ma il mapping utente risolve.

    `auto_detect` abilita il polling periodico della finestra dell'emulatore
    (F4). È spento di default: mentre è attivo l'app cattura lo schermo di
    continuo, e quella è una scelta che deve restare dell'utente.
    """

    generation: int = DEFAULT_GENERATION
    team: list[TeamSlot | None] = field(default_factory=lambda: [None] * TEAM_SIZE)
    overlay_x: int | None = None
    overlay_y: int | None = None
    nicknames: dict[str, int] = field(default_factory=dict)
    auto_detect: bool = False

    def __post_init__(self) -> None:
        if not MIN_GENERATION <= self.generation <= MAX_GENERATION:
            raise ValueError(
                f"generation must be in [{MIN_GENERATION}, {MAX_GENERATION}], got {self.generation}"
            )
        if len(self.team) != TEAM_SIZE:
            raise ValueError(f"team must have exactly {TEAM_SIZE} slots, got {len(self.team)}")


def default_state_path() -> Path:
    """Path predefinito del file di stato.

    Su Windows nativo usa `%APPDATA%\\pokemon-helper\\state.json`. Su ambienti
    dove `%APPDATA%` non è definito (ad esempio WSL o macOS in sviluppo),
    ripiega su `~/.pokemon-helper/state.json`.
    """
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "pokemon-helper" / "state.json"
    return Path.home() / ".pokemon-helper" / "state.json"


class StateStore:
    """Serializzatore JSON per `AppState`.

    Il metodo `load` è tollerante: file mancante o JSON corrotto restituiscono
    uno stato di default invece di sollevare. `save` invece propaga eventuali
    errori di scrittura (permessi, disco pieno) al chiamante.
    """

    def __init__(self, path: Path) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> AppState:
        """Carica lo stato dal file. Ritorna default se manca o è invalido."""
        if not self._path.exists():
            return AppState()
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except OSError, json.JSONDecodeError:
            return AppState()
        try:
            return _deserialize(payload)
        except KeyError, TypeError, ValueError:
            # Payload non conforme allo schema atteso: torna al default.
            # I chiamanti che vogliono differenziare possono controllare
            # la mtime del file prima di chiamare load.
            return AppState()

    def save(self, state: AppState) -> None:
        """Scrive lo stato su disco. Crea la directory padre se serve."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = _serialize(state)
        self._path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


def _serialize(state: AppState) -> dict:
    """Trasforma `AppState` in un dict JSON-friendly."""
    return {
        "generation": state.generation,
        "team": [
            None if slot is None else {"pokemon_id": slot.pokemon_id, "level": slot.level}
            for slot in state.team
        ],
        "overlay_x": state.overlay_x,
        "overlay_y": state.overlay_y,
        "nicknames": dict(state.nicknames),
        "auto_detect": state.auto_detect,
    }


def _deserialize(payload: dict) -> AppState:
    """Rigenera `AppState` da un dict letto dal JSON.

    Chiavi non riconosciute (es. `click_through` di versioni precedenti)
    vengono ignorate silenziosamente per non rompere i file di stato esistenti.
    """
    raw_team = payload["team"]
    if not isinstance(raw_team, list):
        raise TypeError("team must be a list")
    team: list[TeamSlot | None] = []
    for entry in raw_team:
        if entry is None:
            team.append(None)
        else:
            team.append(TeamSlot(pokemon_id=int(entry["pokemon_id"]), level=int(entry["level"])))
    raw_nicknames = payload.get("nicknames") or {}
    if not isinstance(raw_nicknames, dict):
        raise TypeError("nicknames must be a dict")
    nicknames = {str(k).upper(): int(v) for k, v in raw_nicknames.items()}
    return AppState(
        generation=int(payload["generation"]),
        team=team,
        overlay_x=_optional_int(payload.get("overlay_x")),
        overlay_y=_optional_int(payload.get("overlay_y")),
        nicknames=nicknames,
        auto_detect=bool(payload.get("auto_detect", False)),
    )


def _optional_int(value: object) -> int | None:
    """Converte `value` in int se non è None."""
    return None if value is None else int(value)  # type: ignore[arg-type]
