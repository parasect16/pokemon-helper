"""Test del modello di stato e della persistenza JSON."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pokemon_helper.ui.state import (
    DEFAULT_GENERATION,
    TEAM_SIZE,
    AppState,
    StateStore,
    TeamSlot,
    default_state_path,
)

# ---------------------------------------------------------------------------
# TeamSlot / AppState validation
# ---------------------------------------------------------------------------


def test_team_slot_accepts_valid_level() -> None:
    """Livelli fra 1 e 100 sono accettati."""
    slot = TeamSlot(pokemon_id=25, level=50)
    assert slot.pokemon_id == 25
    assert slot.level == 50


@pytest.mark.parametrize("level", [0, -1, 101, 999])
def test_team_slot_rejects_out_of_range_level(level: int) -> None:
    """Livelli fuori intervallo alzano ValueError."""
    with pytest.raises(ValueError, match="level must be in"):
        TeamSlot(pokemon_id=1, level=level)


def test_app_state_default_has_six_empty_slots() -> None:
    """Lo stato di default ha 6 slot vuoti e generazione predefinita."""
    state = AppState()
    assert len(state.team) == TEAM_SIZE
    assert all(slot is None for slot in state.team)
    assert state.generation == DEFAULT_GENERATION
    assert state.overlay_x is None
    assert state.overlay_y is None


def test_app_state_rejects_out_of_range_generation() -> None:
    """Generazione fuori 1-5 alza ValueError."""
    with pytest.raises(ValueError, match="generation must be in"):
        AppState(generation=6)


def test_app_state_rejects_wrong_team_size() -> None:
    """Squadra con dimensione != 6 alza ValueError."""
    with pytest.raises(ValueError, match="exactly 6 slots"):
        AppState(team=[None, None])


# ---------------------------------------------------------------------------
# default_state_path
# ---------------------------------------------------------------------------


def test_default_state_path_uses_appdata_when_present(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Se APPDATA è definito, il path usa quella directory."""
    fake_appdata = tmp_path / "AppData" / "Roaming"
    monkeypatch.setenv("APPDATA", str(fake_appdata))
    path = default_state_path()
    assert path == fake_appdata / "pokemon-helper" / "state.json"


def test_default_state_path_falls_back_to_home_without_appdata(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Senza APPDATA, il path ripiega su ~/.pokemon-helper/state.json."""
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    path = default_state_path()
    assert path == tmp_path / ".pokemon-helper" / "state.json"


# ---------------------------------------------------------------------------
# StateStore
# ---------------------------------------------------------------------------


def test_state_store_load_returns_default_when_file_missing(tmp_path: Path) -> None:
    """Se il file non esiste, load ritorna lo stato di default."""
    store = StateStore(tmp_path / "nonexistent.json")
    state = store.load()
    assert state == AppState()


def test_state_store_save_creates_parent_directories(tmp_path: Path) -> None:
    """Save crea automaticamente le directory intermedie."""
    path = tmp_path / "nested" / "deep" / "state.json"
    store = StateStore(path)
    store.save(AppState())
    assert path.exists()


def test_state_store_roundtrip_preserves_full_state(tmp_path: Path) -> None:
    """Salvataggio e caricamento devono preservare lo stato completo."""
    original = AppState(
        generation=3,
        team=[
            TeamSlot(pokemon_id=25, level=42),
            None,
            TeamSlot(pokemon_id=6, level=100),
            None,
            None,
            TeamSlot(pokemon_id=150, level=70),
        ],
        overlay_x=100,
        overlay_y=200,
        nicknames={"FIAMMETTA": 6, "SPARKY": 25},
    )
    store = StateStore(tmp_path / "state.json")
    store.save(original)
    restored = store.load()
    assert restored == original
    assert restored.nicknames == {"FIAMMETTA": 6, "SPARKY": 25}


def test_state_store_normalizes_nicknames_to_uppercase(tmp_path: Path) -> None:
    """Nickname deserializzati vengono uppercased per matching case-insensitive."""
    path = tmp_path / "state.json"
    path.write_text(
        json.dumps(
            {
                "generation": 3,
                "team": [None] * TEAM_SIZE,
                "overlay_x": None,
                "overlay_y": None,
                "nicknames": {"fiammetta": 6, "Sparky": "25"},
            }
        )
    )
    state = StateStore(path).load()
    assert state.nicknames == {"FIAMMETTA": 6, "SPARKY": 25}


def test_state_store_load_without_nicknames_key_defaults_to_empty(tmp_path: Path) -> None:
    """File state.json pre-nicknames deve caricare con dict vuoto (no crash)."""
    path = tmp_path / "state.json"
    path.write_text(
        json.dumps(
            {
                "generation": 3,
                "team": [None] * TEAM_SIZE,
                "overlay_x": None,
                "overlay_y": None,
            }
        )
    )
    state = StateStore(path).load()
    assert state.nicknames == {}


def test_state_store_ignores_unknown_keys(tmp_path: Path) -> None:
    """Vecchie chiavi (es. click_through) vengono ignorate senza errori."""
    path = tmp_path / "state.json"
    path.write_text(
        json.dumps(
            {
                "generation": 3,
                "team": [None] * TEAM_SIZE,
                "overlay_x": 10,
                "overlay_y": 20,
                "click_through": True,  # chiave morta, deve essere ignorata
                "future_key": "whatever",
            }
        ),
        encoding="utf-8",
    )
    store = StateStore(path)
    state = store.load()
    assert state.generation == 3
    assert state.overlay_x == 10
    assert state.overlay_y == 20


def test_state_store_load_returns_default_on_corrupt_json(tmp_path: Path) -> None:
    """JSON non parsabile deve ricadere sul default, non alzare."""
    path = tmp_path / "state.json"
    path.write_text("{ not json", encoding="utf-8")
    store = StateStore(path)
    assert store.load() == AppState()


def test_state_store_load_returns_default_on_schema_mismatch(tmp_path: Path) -> None:
    """JSON valido ma con schema sbagliato torna al default."""
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"unexpected": "shape"}), encoding="utf-8")
    store = StateStore(path)
    assert store.load() == AppState()


def test_state_store_load_returns_default_on_invalid_values(tmp_path: Path) -> None:
    """Valori fuori range (generazione 99) devono cadere sul default."""
    path = tmp_path / "state.json"
    path.write_text(
        json.dumps(
            {
                "generation": 99,
                "team": [None] * TEAM_SIZE,
                "overlay_x": None,
                "overlay_y": None,
            }
        ),
        encoding="utf-8",
    )
    store = StateStore(path)
    assert store.load() == AppState()


def test_state_store_save_writes_readable_utf8(tmp_path: Path) -> None:
    """Il file scritto deve essere UTF-8 e contenere i campi attesi."""
    store = StateStore(tmp_path / "state.json")
    store.save(AppState(generation=2))
    content = (tmp_path / "state.json").read_text(encoding="utf-8")
    payload = json.loads(content)
    assert payload["generation"] == 2
    assert payload["team"] == [None] * TEAM_SIZE


def test_state_store_deserializes_team_slots(tmp_path: Path) -> None:
    """Slot serializzati come dict tornano TeamSlot dopo il load."""
    path = tmp_path / "state.json"
    path.write_text(
        json.dumps(
            {
                "generation": 5,
                "team": [
                    {"pokemon_id": 1, "level": 10},
                    None,
                    None,
                    None,
                    None,
                    None,
                ],
                "overlay_x": None,
                "overlay_y": None,
            }
        ),
        encoding="utf-8",
    )
    store = StateStore(path)
    state = store.load()
    assert state.team[0] == TeamSlot(pokemon_id=1, level=10)
    assert state.team[1] is None
