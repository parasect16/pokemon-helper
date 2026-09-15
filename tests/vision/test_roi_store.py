"""Test di `vision.roi_store`: round-trip, override e file malformati.

Tutto gira su `tmp_path`: nessun accesso a `%APPDATA%` reale, nessuna
dipendenza dagli extra `[vision]` — il modulo tocca solo JSON e `roi.py`.
"""

from __future__ import annotations

import json

import pytest

from pokemon_helper.vision.roi import GAME_ROIS, ROIS_FIRERED, Roi, TeamMenuRois
from pokemon_helper.vision.roi_store import (
    ROI_STORE_VERSION,
    RoiStore,
    default_roi_dir,
    deserialize_rois,
    resolve_rois,
    serialize_rois,
)

BASE = ROIS_FIRERED


@pytest.fixture
def store(tmp_path) -> RoiStore:
    return RoiStore(tmp_path / "rois")


def _payload(**rois) -> dict:
    """Payload minimo valido, con i soli campi passati."""
    return {"version": ROI_STORE_VERSION, "game": "firered", "rois": rois}


def _roi_dict(roi: Roi) -> dict[str, float]:
    return {"x": roi.x, "y": roi.y, "w": roi.w, "h": roi.h}


# ---------------------------------------------------------------- round-trip


def test_save_then_load_returns_the_same_rois(store: RoiStore) -> None:
    custom = _with_opponent_name(Roi(x=0.1, y=0.2, w=0.3, h=0.4))

    store.save("firered", custom)

    assert store.load("firered", BASE) == custom


def test_saving_creates_the_directory(tmp_path) -> None:
    """Il calibratore salva al primo uso: la cartella non esiste ancora."""
    store = RoiStore(tmp_path / "mai" / "creata")

    path = store.save("firered", BASE)

    assert path.exists()
    assert path.parent.is_dir()


def test_the_saved_file_is_readable_json_with_a_version(store: RoiStore) -> None:
    path = store.save("firered", BASE)

    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["version"] == ROI_STORE_VERSION
    assert payload["game"] == "firered"
    assert payload["rois"]["opponent_name"] == _roi_dict(BASE.opponent_name)
    assert len(payload["rois"]["team_menu"]["slot_levels"]) == 6


def test_each_game_has_its_own_file(store: RoiStore) -> None:
    store.save("firered", _with_opponent_name(Roi(x=0.1, y=0.1, w=0.1, h=0.1)))
    store.save("crystal", _with_opponent_name(Roi(x=0.2, y=0.2, w=0.2, h=0.2)))

    assert store.load("firered", BASE).opponent_name.x == pytest.approx(0.1)
    assert store.load("crystal", BASE).opponent_name.x == pytest.approx(0.2)


# ------------------------------------------------------------------- default


def test_no_file_means_the_built_in_rois(store: RoiStore) -> None:
    assert store.load("firered", BASE) == BASE


def test_clear_removes_the_calibration(store: RoiStore) -> None:
    store.save("firered", _with_opponent_name(Roi(x=0.1, y=0.2, w=0.3, h=0.4)))

    assert store.clear("firered") is True
    assert store.load("firered", BASE) == BASE


def test_clearing_nothing_says_so(store: RoiStore) -> None:
    assert store.clear("firered") is False


def test_the_default_directory_sits_next_to_the_state_file(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))

    assert default_roi_dir() == tmp_path / "pokemon-helper" / "rois"


def test_without_appdata_it_falls_back_to_the_home_directory(monkeypatch) -> None:
    """WSL e macOS in sviluppo non hanno `%APPDATA%`."""
    monkeypatch.delenv("APPDATA", raising=False)

    assert default_roi_dir().name == "rois"
    assert ".pokemon-helper" in default_roi_dir().parts


# ------------------------------------------------------------------ override


def test_a_partial_file_leaves_the_other_rois_at_their_default() -> None:
    """Il file può descrivere un rettangolo solo: il resto viene dai default."""
    custom = Roi(x=0.5, y=0.5, w=0.1, h=0.1)

    rois = deserialize_rois(_payload(opponent_name=_roi_dict(custom)), BASE)

    assert rois.opponent_name == custom
    assert rois.player_name == BASE.player_name
    assert rois.team_menu == BASE.team_menu


def test_a_partial_team_menu_keeps_the_other_group() -> None:
    levels = [_roi_dict(Roi(x=0.1 * i, y=0.1, w=0.05, h=0.05)) for i in range(6)]

    rois = deserialize_rois(_payload(team_menu={"slot_levels": levels}), BASE)

    assert rois.team_menu.slot_levels[3].x == pytest.approx(0.3)
    assert rois.team_menu.slot_areas == BASE.team_menu.slot_areas


def test_unknown_keys_are_ignored() -> None:
    """I file devono sopravvivere alla rimozione di una ROI dal codice."""
    payload = _payload(opponent_sprite={"x": 0.1, "y": 0.1, "w": 0.1, "h": 0.1})

    assert deserialize_rois(payload, BASE) == BASE


# --------------------------------------------------------------- file rotti


@pytest.mark.parametrize(
    ("content", "expected_note"),
    [
        ("{non json", "illeggibile"),
        ("[1, 2, 3]", "non contiene un oggetto JSON"),
        ('{"version": 1}', "non conforme"),
        ('{"rois": "nope"}', "non conforme"),
    ],
)
def test_a_broken_file_falls_back_to_default_with_a_warning(
    store: RoiStore, capsys, content: str, expected_note: str
) -> None:
    path = store.path_for("firered")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

    assert store.load("firered", BASE) == BASE
    assert expected_note in capsys.readouterr().out


def test_one_bad_rectangle_discards_the_whole_file(store: RoiStore, capsys) -> None:
    """Tutto o niente: mezza calibrazione sbaglierebbe senza dare spiegazioni.

    `y=1.4` esce da [0, 1] e `Roi` lo rifiuta; il resto del file è valido e
    verrebbe applicato, lasciando un insieme che non è né la calibrazione
    dell'utente né quella del repo.
    """
    good = _roi_dict(Roi(x=0.1, y=0.1, w=0.1, h=0.1))
    payload = _payload(opponent_name=good, player_name={"x": 0.1, "y": 1.4, "w": 0.1, "h": 0.1})
    path = store.path_for("firered")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert store.load("firered", BASE) == BASE
    assert "non conforme" in capsys.readouterr().out


def test_a_team_menu_with_the_wrong_slot_count_is_rejected() -> None:
    """Il vincolo dei sei slot vive in `TeamMenuRois`, non duplicato qui."""
    payload = _payload(team_menu={"slot_areas": [_roi_dict(Roi(x=0.1, y=0.1, w=0.1, h=0.1))]})

    with pytest.raises(ValueError, match="slot_areas"):
        deserialize_rois(payload, BASE)


def test_a_team_menu_group_that_is_not_a_list_is_rejected() -> None:
    with pytest.raises(TypeError, match="slot_areas"):
        deserialize_rois(_payload(team_menu={"slot_areas": {"x": 0.1}}), BASE)


def test_a_roi_that_is_not_an_object_is_rejected() -> None:
    with pytest.raises(TypeError, match="roi must be an object"):
        deserialize_rois(_payload(opponent_name=[0.1, 0.2, 0.3, 0.4]), BASE)


def test_a_payload_without_rois_is_rejected() -> None:
    with pytest.raises(KeyError):
        deserialize_rois({"version": ROI_STORE_VERSION}, BASE)


# ----------------------------------------------------------------- resolver


def test_resolve_returns_the_built_in_rois_without_a_calibration(store: RoiStore) -> None:
    layout, rois = resolve_rois("firered", store)

    assert layout is GAME_ROIS["firered"][0]
    assert rois == BASE


def test_resolve_prefers_the_user_calibration(store: RoiStore) -> None:
    custom = _with_opponent_name(Roi(x=0.42, y=0.42, w=0.1, h=0.1))
    store.save("firered", custom)

    _, rois = resolve_rois("firered", store)

    assert rois.opponent_name == custom.opponent_name


def test_resolving_an_unknown_game_still_fails_loudly(store: RoiStore) -> None:
    """Una calibrazione non inventa un gioco: serve comunque il layout."""
    with pytest.raises(KeyError):
        resolve_rois("pokemon-fantasia", store)


def test_serialize_round_trips_through_deserialize() -> None:
    payload = serialize_rois(BASE, "firered")

    assert deserialize_rois(payload, _with_opponent_name(Roi(x=0.9, y=0.9, w=0.01, h=0.01))) == BASE


def _with_opponent_name(roi: Roi):
    """Copia delle ROI FireRed con un solo rettangolo cambiato."""
    return type(BASE)(
        opponent_name=roi,
        opponent_hp_bar=BASE.opponent_hp_bar,
        player_name=BASE.player_name,
        party_menu_sentinel=BASE.party_menu_sentinel,
        team_menu=TeamMenuRois(
            slot_areas=BASE.team_menu.slot_areas,
            slot_levels=BASE.team_menu.slot_levels,
        ),
    )
