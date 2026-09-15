"""Persistenza su JSON delle ROI calibrate dall'utente.

Le ROI di `roi.py` sono i valori di fabbrica: misurati su una macchina, per
un gioco, a una scala. Funzionano finché l'emulatore è quello e il gioco è
quello. Questo modulo aggiunge il secondo strato — una calibrazione locale
che vince sui default — così che il calibratore visuale possa salvare senza
toccare il codice, e un gioco non ancora supportato dal repo possa essere
usato da chi se lo calibra.

Il file vive in `%APPDATA%\\pokemon-helper\\rois\\<gioco>.json`, uno per
gioco, e contiene le coordinate normalizzate esattamente come le dichiara
`roi.py`. Sono normalizzate, quindi restano valide a qualunque dimensione
della finestra: si ricalibra quando cambia il *gioco*, non quando si
ridimensiona mGBA.

Politica di lettura, deliberatamente tutto-o-niente: un file illeggibile,
malformato o con un solo rettangolo fuori range viene scartato **intero** e
si torna ai default, con un avviso in console. Applicarne metà produrrebbe
un insieme di ROI che non è né la calibrazione dell'utente né quella del
repo, e l'unico sintomo sarebbe un riconoscimento che sbaglia senza motivo
apparente. Le chiavi sconosciute invece vengono ignorate in silenzio, come
fa `ui.state`: sono file che sopravvivono agli aggiornamenti.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from pokemon_helper.vision.roi import (
    GAME_ROIS,
    GameLayout,
    GameRois,
    Roi,
    TeamMenuRois,
)

# Versione dello schema del file. Serve a distinguere un formato futuro da
# uno attuale senza indovinare dalla forma del payload.
ROI_STORE_VERSION = 1

# Campi di `GameRois` che sono un singolo rettangolo. `team_menu` è a parte
# perché è una struttura annidata di liste.
_SINGLE_ROI_FIELDS = (
    "opponent_name",
    "opponent_hp_bar",
    "player_name",
    "party_menu_sentinel",
)

# Campi di `TeamMenuRois`, ciascuno una lista di sei rettangoli.
_TEAM_MENU_FIELDS = ("slot_areas", "slot_levels")


def default_roi_dir() -> Path:
    """Directory predefinita delle ROI utente.

    Stessa logica di `ui.state.default_state_path`: `%APPDATA%` su Windows
    nativo, `~/.pokemon-helper` dove non è definito (WSL, macOS in sviluppo).
    """
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "pokemon-helper" / "rois"
    return Path.home() / ".pokemon-helper" / "rois"


def serialize_rois(rois: GameRois, game_key: str) -> dict:
    """Trasforma un `GameRois` in un dict JSON-friendly."""
    return {
        "version": ROI_STORE_VERSION,
        "game": game_key,
        "rois": {
            **{name: _roi_to_payload(getattr(rois, name)) for name in _SINGLE_ROI_FIELDS},
            "team_menu": {
                name: [_roi_to_payload(roi) for roi in getattr(rois.team_menu, name)]
                for name in _TEAM_MENU_FIELDS
            },
        },
    }


def deserialize_rois(payload: dict, base: GameRois) -> GameRois:
    """Rigenera un `GameRois` dal payload, con `base` a coprire i buchi.

    Alza `KeyError`, `TypeError` o `ValueError` su un payload non conforme —
    è `RoiStore.load` a decidere cosa farne. I rettangoli fuori da [0, 1]
    vengono respinti da `Roi.__post_init__`, quindi la validazione delle
    coordinate non è duplicata qui.
    """
    raw = payload.get("rois")
    if raw is None:
        raise KeyError("rois")
    if not isinstance(raw, dict):
        raise TypeError("rois must be a dict")

    singles = {
        name: _roi_from_payload(raw[name]) if name in raw else getattr(base, name)
        for name in _SINGLE_ROI_FIELDS
    }
    return GameRois(
        team_menu=_team_menu_from_payload(raw.get("team_menu"), base.team_menu),
        **singles,
    )


class RoiStore:
    """Legge e scrive le ROI utente, un file per gioco."""

    def __init__(self, directory: Path | None = None) -> None:
        self._dir = directory if directory is not None else default_roi_dir()

    @property
    def directory(self) -> Path:
        return self._dir

    def path_for(self, game_key: str) -> Path:
        """Path del file di calibrazione per un gioco (esista o no)."""
        return self._dir / f"{game_key}.json"

    def load(self, game_key: str, base: GameRois) -> GameRois:
        """Ritorna le ROI dell'utente, o `base` se non ce ne sono di valide."""
        path = self.path_for(game_key)
        if not path.exists():
            return base
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"[roi-store] {path} illeggibile ({exc}): uso le ROI di default")
            return base
        if not isinstance(payload, dict):
            print(f"[roi-store] {path} non contiene un oggetto JSON: uso le ROI di default")
            return base
        try:
            return deserialize_rois(payload, base)
        except (KeyError, TypeError, ValueError) as exc:
            print(f"[roi-store] {path} non conforme ({exc}): uso le ROI di default")
            return base

    def save(self, game_key: str, rois: GameRois) -> Path:
        """Scrive la calibrazione su disco e ritorna il path scritto.

        Salva l'insieme completo, non il solo scarto dai default: il file
        descrive per intero come è fatto quel gioco su questa macchina, e
        resta leggibile da solo.
        """
        path = self.path_for(game_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(serialize_rois(rois, game_key), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return path

    def clear(self, game_key: str) -> bool:
        """Cancella la calibrazione utente. Ritorna se c'era qualcosa da togliere."""
        path = self.path_for(game_key)
        if not path.exists():
            return False
        path.unlink()
        return True


def resolve_rois(game_key: str, store: RoiStore | None = None) -> tuple[GameLayout, GameRois]:
    """Layout e ROI effettive per un gioco: default del repo + override utente.

    È il punto da cui devono passare tutti i chiamanti, al posto di leggere
    `GAME_ROIS` direttamente: è ciò che rende una calibrazione valida ovunque
    invece che solo dove qualcuno si è ricordato di cercarla.
    """
    layout, base = GAME_ROIS[game_key]
    resolved = (store if store is not None else RoiStore()).load(game_key, base)
    return layout, resolved


def _roi_to_payload(roi: Roi) -> dict[str, float]:
    return {"x": roi.x, "y": roi.y, "w": roi.w, "h": roi.h}


def _roi_from_payload(raw: object) -> Roi:
    if not isinstance(raw, dict):
        raise TypeError(f"roi must be an object, got {type(raw).__name__}")
    return Roi(x=float(raw["x"]), y=float(raw["y"]), w=float(raw["w"]), h=float(raw["h"]))


def _team_menu_from_payload(raw: object, base: TeamMenuRois) -> TeamMenuRois:
    """Ricostruisce le ROI del menu squadra, con `base` a coprire i buchi."""
    if raw is None:
        return base
    if not isinstance(raw, dict):
        raise TypeError("team_menu must be a dict")
    slots = {}
    for name in _TEAM_MENU_FIELDS:
        if name not in raw:
            slots[name] = getattr(base, name)
            continue
        entries = raw[name]
        if not isinstance(entries, list):
            raise TypeError(f"team_menu.{name} must be a list")
        # La lunghezza sbagliata la respinge `TeamMenuRois.__post_init__`, che
        # è già l'unico posto dove vive il vincolo dei sei slot.
        slots[name] = tuple(_roi_from_payload(entry) for entry in entries)
    return TeamMenuRois(**slots)
