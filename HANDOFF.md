# HANDOFF — pokemon-helper

Passaggio per nuova sessione o nuovo collaboratore. Stato al **2026-09-06**.

Vedi [`PLAN.md`](PLAN.md) per roadmap, [`CLAUDE.md`](CLAUDE.md) per convenzioni.

## 1. Cosa fa oggi

Tool desktop Windows. Affianca emulatore Pokemon Gen 1-5 con pannello sempre in primo piano. Funzionalità:

- **Squadra manuale**: 6 slot nome + livello, generazione selezionabile. Persistenza in `%APPDATA%\pokemon-helper\state.json`.
- **Riconoscimento battaglia** (`Ctrl+Alt+R` o pulsante `⚔ Avversario`) su mGBA + Rosso Fuoco: cattura finestra, riconosce avversario via OCR nome + pHash sprite, in parallelo Pokemon giocatore in campo (vincolato ai 6 membri squadra per precisione). Guardia `is_battle_screen` blocca l'update se la ROI HP avversario non ha pixel colore-HP (schermata non-battaglia → warning ⚠).
- **Riconoscimento squadra** (`Ctrl+Alt+T` o pulsante `⟳ Squadra`) da schermata elenco Pokemon: OCR per ciascuno dei 6 slot, fuzzy match nome, sovrascrive `state.team`. Guard doppia: <3/6 slot leggibili o stesso pokemon_id in ≥2 slot → aggiornamento bloccato.
- **Mappa nickname** (pulsante `🏷`): dialog per associare nickname custom (es. "FIAMMETTA") a un pokemon_id. Recognizer consulta la mappa prima del fuzzy match. Persistita in `state.json`.
- **OpponentPanel**: due card affiancate (player | avversario) con sprite Pokedex, nome, tipi, tabella efficacia difensiva colorata (Debolezze / Resistenze / Immune, neutri esclusi).
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
  player_debug.py            # end-to-end recognize player (con crop + overlay)
  extract_roi_from_annotated.py  # bbox per colore da PNG annotato → coord Roi

tests/
  engine/ data/ ui/ vision/  # pytest, 114 test, 100% branch coverage engine+data.

data/                        # gitignored (eccetto la struttura)
  vendor/pokedex/            # shallow clone veekun (CSV Pokedex)
  vendor/sprites/            # sparse clone PokeAPI/sprites (PNG)
  pokemon.sqlite             # DB generato
```

## 4. Comandi utili

```powershell
pytest -q                            # 114 test, tutti verdi
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
| F3   | ✅ usable | mGBA + Rosso Fuoco. 16 sotto-step in `PLAN.md` §6. Team 5/6 con nome default OK, nickname custom via mappa utente. |
| F4   | ⏳ da fare | Auto-detect combattimento via HP-bar template match. Metà del lavoro già fatta in `battle_detector.is_battle_screen`. |

## 6. Limitazioni note (da PLAN §7)

- **OCR livello (`L.XX`) su font pixel**: RapidOCR poco affidabile, solo alcuni slot danno numero. Fallback: livello preservato, editabile via `…`.
- **Match icona menu Pokemon**: pHash/dhash rumorosi anche col color-key HSV. Valutare template matching per game se conta.
- **Chrome mGBA hardcoded 52 px**: title bar + menu bar misurati sulla macchina utente (Win10 Pro DPI 100%). Su Win11 o DPI diverse serve auto-detect (scan prima riga teal del frame).
- **ROI hardcoded**: solo FRLG a scala mGBA. Calibratore visuale drag-a-rettangolo sbloccherebbe altri giochi. Parzialmente coperto da `extract_roi_from_annotated.py` (offline).
- **Ambiente**: F2/F3/F4 richiedono Windows nativo (COM + Windows Graphics Capture + hotkey Win32). Logica pura (`engine/`, `data/`) ovunque, anche WSL/Linux.
- **Nickname Pokemon**: fuzzy match non li riconosce. Fix via mappa utente `state.nicknames` (dialog 🏷). Fallback: `_apply_team_recognition` preserva slot corrispondente.

## 7. Prossimi step suggeriti

Ordinati per valore/costo:

1. **F4 auto-detect combattimento**: template match su pattern distintivo schermata battaglia (barra HP, ombra sprite). Se detected, invoca `recognize_opponent` senza input utente. ~4h.
2. **Calibratore ROI visuale**: dialog con canvas su screenshot, disegni rettangoli per (nome opp, sprite opp, HUD player, ecc.). Sblocca altri giochi/scaling senza toccare codice. ~4-6h.
3. **Detection livello via template matching per digit**: 10 template per game (0-9 font pixel), match a scorrimento su ROI. Sostituisce fallimento OCR con qualcosa che funziona. ~2-3h per game.
4. **Altro emulatore / gioco**: aggiungere Cristallo (Gen 2 mGBA) o HeartGold (Gen 4 melonDS/DeSmuME). Serve ROI dedicate + preferred_game in `_preferred_game()`.
5. **Test UI**: coverage componenti Qt a 0. Aggiungere test con `pytest-qt` per state binding di `TeamPanel` / `OpponentPanel`.

## 8. Convenzioni rapide

- Commit: Conventional Commits, scope in parentesi (es. `feat(f3):`). Body opzionale ma preferito per "il perché".
- Codice/log/identificatori in inglese; docstring e commenti in italiano.
- Coverage minima 90% su `engine/` e `data/` (fail CI sotto soglia).
- `.gitattributes` forza LF ovunque; non toccare `core.autocrlf`.

## 9. File di stato utente

`%APPDATA%\pokemon-helper\state.json`: JSON con `generation`, `team[6]` (id + livello), `overlay_x`, `overlay_y`, `nicknames` (dict UPPERCASE → pokemon_id). Rigenerato al primo salvataggio se assente. Chiavi non riconosciute ignorate silenziosamente (es. vecchia `click_through`); `nicknames` mancante = dict vuoto (compat pre-F3.16).

## 10. Dove chiedere

Tool non riconosce avversario: prima riprova ben posizionato su schermata battaglia. Se non basta, gira script diagnostico `scripts/recognize_test.py` (opponent) o `scripts/player_debug.py` (player) e guarda overlay `data/roi-firered-overlay.png` — spesso ROI leggermente disallineate rispetto a dimensione finestra mGBA.
