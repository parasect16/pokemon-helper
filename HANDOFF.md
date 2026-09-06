# HANDOFF — pokemon-helper

Passaggio per nuova sessione o nuovo collaboratore. Stato al **2026-09-06**.

Vedi [`PLAN.md`](PLAN.md) per roadmap, [`CLAUDE.md`](CLAUDE.md) per convenzioni.

## 1. Cosa fa oggi

Tool desktop Windows. Affianca emulatore Pokemon Gen 1-5 con pannello sempre in primo piano. Funzionalità:

- **Squadra manuale**: 6 slot nome + livello, generazione selezionabile. Persistenza in `%APPDATA%\pokemon-helper\state.json`.
- **Riconoscimento battaglia** (`Ctrl+Alt+R` o pulsante `⚔ Avversario`) su mGBA + Rosso Fuoco: cattura finestra, riconosce avversario via OCR nome + pHash sprite, in parallelo Pokemon giocatore in campo (vincolato ai 6 membri squadra per precisione). Guardia `is_battle_screen` blocca l'update se la ROI HP avversario non ha pixel colore-HP (schermata non-battaglia → warning ⚠).
- **Riconoscimento squadra** (`Ctrl+Alt+T` o pulsante `⟳ Squadra`) da schermata elenco Pokemon: OCR nome per ciascuno dei 6 slot con fuzzy match, livello letto cifra per cifra da `vision/level_reader.py`, sovrascrive `state.team`. Guard doppia: <3/6 slot leggibili o stesso pokemon_id in ≥2 slot → aggiornamento bloccato.
- **Mappa nickname** (pulsante `🏷`): dialog per associare nickname custom (es. "FIAMMETTA") a un pokemon_id, usata sia dal riconoscimento squadra sia da quello del player in battaglia. Il nickname si scrive come appare nel gioco: il confronto è fuzzy e assorbe gli errori OCR. Persistita in `state.json`.
- **OpponentPanel**: due card affiancate (player | avversario) con sprite Pokedex, nome, tipi, tabella efficacia difensiva colorata (Debolezze / Resistenze / Immune, neutri esclusi).
- **Auto-detect** (checkbox `Auto`, spento di default, persistito): polla la finestra dell'emulatore ogni 750 ms e aggiorna il pannello da solo all'inizio del combattimento, alla fine e a ogni cambio di Pokemon in campo (entrambi i lati). L'elenco Pokemon aperto a metà lotta non conta come "combattimento finito".
- **Hotkey globale** (`Ctrl+Alt+P`): mostra / minimizza finestra.
- **Feedback pulsanti**: ✓ verde su successo 10 s, ⚠ giallo su fallimento (motivo in tooltip).

## 2. Come avviare

```powershell
cd C:\Sviluppo\Progetti\pokemon-helper
py -3.14 -m venv .venv
.\.venv\Scripts\activate
pip install -e ".[dev,app,vision]"

# Popola i dati la prima volta (idempotenti — si possono rilanciare).
python scripts/build_dataset.py       # -> data/pokemon.sqlite (~2 MB)
python scripts/build_sprite_index.py  # -> ~10k righe sprite_hashes

# Avvio applicazione.
python -m pokemon_helper
```

Requisiti: Python 3.14 (pin in `.python-version`), Windows 10/11, mGBA per riconoscimento (Rosso Fuoco / FRLG Italiano unico gioco tarato).

## 3. Layout progetto

```
src/pokemon_helper/
  engine/           # F1: type chart, EffectivenessEngine, matchup helpers.
  data/             # F0.1: SQLite schema, models, PokemonRepository.
  vision/           # F0.2 + F3: capture, ROI, OCR, sprite hash, recognizer.
  ui/               # F2: overlay Qt, TeamPanel, OpponentPanel, hotkey, state.
  __main__.py       # CLI entry-point → ui.app.run

scripts/
  build_dataset.py           # veekun/pokedex clone + parse → data/pokemon.sqlite
  build_sprite_index.py      # PokeAPI/sprites sparse clone + pHash → sprite_hashes
  capture_test.py            # cattura mGBA → data/capture-test.png
  roi_debug.py               # overlay ROI battaglia (mGBA + FRLG)
  team_menu_debug.py         # overlay ROI menu squadra
  level_debug.py             # OCR debug su ROI level dedicate
  ocr_debug_team.py          # OCR debug su ROI slot squadra
  icon_compare.py            # confronto pHash icone reference vs capture
  icon_debug.py              # top-K pHash icone per debug
  recognize_test.py          # end-to-end recognize opponent
  recognize_team_test.py     # end-to-end recognize squadra
  battle_watch_debug.py      # eventi F4 (ENTERED/LEFT/CHANGED) senza GUI
  player_debug.py            # end-to-end recognize player (con crop + overlay)
  extract_roi_from_annotated.py  # bbox per colore da PNG annotato → coord Roi

tests/
  engine/ data/ ui/ vision/  # pytest, 213 test.

data/                        # gitignored (eccetto la struttura)
  vendor/pokedex/            # shallow clone veekun (CSV Pokedex)
  vendor/sprites/            # sparse clone PokeAPI/sprites (PNG)
  pokemon.sqlite             # DB generato
```

## 4. Comandi utili

```powershell
pytest -q                            # 213 test, tutti verdi
pytest --cov                         # con coverage report (soglia 90% engine+data)
ruff check .                         # lint
ruff format .                        # format
pre-commit run --all-files           # tutti gli hook (ruff + eol + ecc.)
POKEMON_HELPER_SMOKE=1 python -m pokemon_helper   # avvia + auto-quit dopo 2 s
```

Ogni `scripts/*_debug.py` presume mGBA aperto. Produce PNG diagnostici sotto `data/` (gitignored). Utile per aggiustare ROI.

## 5. Stato per fase

| Fase | Stato | Note principali |
|------|-------|-----------------|
| F0.1 | ✅ done | `data/pokemon.sqlite` da veekun. `TYPE_HISTORY_OVERRIDES` per Magnemite Gen 1. |
| F0.2 | ✅ done | Sprite front/back/icon indicizzati da PokeAPI/sprites (~10k righe). |
| F1   | ✅ done | `EffectivenessEngine`, `compute_matchup`, 100% test. |
| F2   | ✅ done | Companion window nativa con chrome Windows, hotkey, persistenza. |
| F3   | ✅ usable | mGBA + Rosso Fuoco. 19 sotto-step in `PLAN.md` §6. Su cattura live: 6/6 nomi e 6/6 livelli dal menu squadra, avversario e player riconosciuti in battaglia. |
| F4   | ✅ done | Auto-detect via `BattleWatcher` + poll 750 ms. Interruttore "Auto", spento di default. Segue ingresso, uscita e cambi di Pokemon su entrambi i lati. |

## 6. Limitazioni note (da PLAN §7)

- **Livello non mostrato con alterazione di stato**: se il Pokemon è avvelenato/paralizzato/ecc. il gioco disegna il badge di stato al posto di `L.XX`. `read_level` ritorna `None` e lo slot conserva il livello precedente, editabile via `…`. (La lettura del livello in sé è risolta: vedi `vision/level_reader.py`.)
- **Match icona menu Pokemon**: pHash/dhash rumorosi anche col color-key HSV. Oggi conta poco: l'OCR nome rec-only riconosce tutti gli slot, quindi il fallback icona non viene quasi mai raggiunto.
- **Chrome mGBA hardcoded 52 px**: title bar + menu bar misurati sulla macchina utente (Win10 Pro DPI 100%). Su Win11 o DPI diverse serve auto-detect (scan prima riga teal del frame).
- **ROI hardcoded**: solo FRLG a scala mGBA. Calibratore visuale drag-a-rettangolo sbloccherebbe altri giochi. Parzialmente coperto da `extract_roi_from_annotated.py` (offline).
- **Ambiente**: F2/F3/F4 richiedono Windows nativo (COM + Windows Graphics Capture + hotkey Win32). Logica pura (`engine/`, `data/`) ovunque, anche WSL/Linux.
- **Nickname Pokemon**: il fuzzy sui nomi di specie non li riconosce. Fix via mappa utente `state.nicknames` (dialog 🏷), consultata sia da `recognize_team` sia da `recognize_player` (l'HUD di combattimento mostra il nickname, non la specie). Il confronto è fuzzy, quindi assorbe i tipici errori OCR: il nickname va scritto **come appare nel gioco**.

## 7. Prossimi step suggeriti

Ordinati per valore/costo:

1. **Coverage gate rosso**: `pytest --cov` fallisce a 84.79% contro il floor 90% in `pyproject.toml`. Non è una regressione recente — è così da `af5930f`, che ha aggiunto tre metodi di `PokemonRepository` mai testati (`find_by_fuzzy_name`, `get_sprite_source_path`, filtro `sides` di `find_pokemon_by_sprite_hash`). Da chiudere insieme alla CI, altrimenti il floor non lo applica nessuno. ~1-2h per entrambi.
2. **Sessione di cattura persistente**: ogni poll apre e chiude una sessione Windows Graphics Capture, e il bordo che il sistema disegna attorno alla finestra lampeggia a ogni giro. Una sessione long-lived con callback lo renderebbe fisso e porterebbe la cattura da ~90 ms a ~0. ~2-3h.
3. **Abilità che modificano l'efficacia** (Levitazione, Assorbivolt, Parafulmine): oggi il calcolo guarda solo i tipi, quindi su un Gengar con Levitazione il consiglio è sbagliato. È l'unico punto in cui il tool può dare una risposta *errata* anziché incompleta. Estende `EffectivenessEngine` con un secondo layer.
4. **Calibratore ROI visuale**: dialog con canvas su screenshot, disegni rettangoli per (nome opp, sprite opp, HUD player, ecc.). Sblocca altri giochi/scaling senza toccare codice. ~4-6h.
5. **Altro emulatore / gioco**: aggiungere Cristallo (Gen 2 mGBA) o HeartGold (Gen 4 melonDS/DeSmuME). Serve ROI dedicate + preferred_game in `_preferred_game()`.
6. **Test UI**: coverage componenti Qt a 0, ed è cresciuto parecchio con F4 (`_BattlePoller`, wiring del watcher, `fit_height`). `pytest-qt` per state binding di `TeamPanel` / `OpponentPanel`.
7. **ROI `player_sprite` / `player_hp_bar`**: ancora mal centrate anche dopo la riproiezione di `1f85b1e`, perché la loro calibrazione originale era sbagliata a prescindere dal chrome. Impatto basso (il pHash in battaglia è comunque inservibile), ~1h con una cattura di riferimento.

## 8. Convenzioni rapide

- Commit: Conventional Commits, scope in parentesi (es. `feat(f3):`). Body opzionale ma preferito per "il perché".
- Codice/log/identificatori in inglese; docstring e commenti in italiano.
- Coverage minima 90% su `engine/` e `data/` (fail CI sotto soglia).
- `.gitattributes` forza LF ovunque; non toccare `core.autocrlf`.

## 9. File di stato utente

`%APPDATA%\pokemon-helper\state.json`: JSON con `generation`, `team[6]` (id + livello), `overlay_x`, `overlay_y`, `nicknames` (dict UPPERCASE → pokemon_id). Rigenerato al primo salvataggio se assente. Chiavi non riconosciute ignorate silenziosamente (es. vecchia `click_through`); `nicknames` mancante = dict vuoto (compat pre-F3.16).

## 10. Dove chiedere

Tool non riconosce avversario: prima riprova ben posizionato su schermata battaglia. Se non basta, gira script diagnostico `scripts/recognize_test.py` (opponent) o `scripts/player_debug.py` (player) e guarda overlay `data/roi-firered-overlay.png` — spesso ROI leggermente disallineate rispetto a dimensione finestra mGBA.
