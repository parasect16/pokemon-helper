# HANDOFF — pokemon-helper

Documento di passaggio per una nuova sessione di sviluppo o un nuovo
collaboratore. Fotografia dello stato al **2026-09-05**.

Vedi anche [`PLAN.md`](PLAN.md) per obiettivi e roadmap, e
[`CLAUDE.md`](CLAUDE.md) per le convenzioni operative.

## 1. Cosa fa oggi

Tool desktop Windows che affianca un emulatore Pokemon Gen 1-5 con un
pannello sempre in primo piano. Funzionalità operative:

- **Squadra manuale**: 6 slot con nome + livello, generazione selezionabile.
  Persistenza in `%APPDATA%\pokemon-helper\state.json`.
- **Riconoscimento battaglia** (`Ctrl+Alt+R` o pulsante `⚔ Avversario`) su
  mGBA + Rosso Fuoco: cattura la finestra, riconosce l'avversario via OCR
  nome + pHash sprite, e in parallelo il Pokemon del giocatore in campo
  (vincolato ai 6 membri della squadra per aumentare la precisione).
- **Riconoscimento squadra** (`Ctrl+Alt+T` o pulsante `⟳ Squadra`) dalla
  schermata elenco Pokemon: OCR per ciascuno dei 6 slot, fuzzy match sul
  nome, sovrascrittura di `state.team`. Se la schermata non è quella del
  menu Pokemon la squadra non viene aggiornata (heuristic sul numero di
  slot leggibili).
- **OpponentPanel**: due card affiancate (player | avversario) con sprite
  Pokedex, nome, tipi, e tabella efficacia difensiva colorata
  (Debolezze / Resistenze / Immune, tipi neutri esclusi).
- **Hotkey globale** (`Ctrl+Alt+P`) per mostrare / minimizzare la finestra.
- **Feedback pulsanti**: ✓ verde su successo per 10 s, ⚠ giallo su
  fallimento (con motivo in tooltip).

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

Requisiti: Python 3.14 (pin in `.python-version`), Windows 10/11, mGBA
per il riconoscimento (Rosso Fuoco / FRLG in Italiano è l'unico gioco
tarato).

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

Ogni script `scripts/*_debug.py` presume mGBA aperto e produce PNG
diagnostici sotto `data/` (gitignored). Utile per aggiustare le ROI.

## 5. Stato per fase

| Fase | Stato | Note principali |
|------|-------|-----------------|
| F0.1 | ✅ done | `data/pokemon.sqlite` da veekun. `TYPE_HISTORY_OVERRIDES` per Magnemite Gen 1. |
| F0.2 | ✅ done | Sprite front/back/icon indicizzati da PokeAPI/sprites (~10k righe). |
| F1   | ✅ done | `EffectivenessEngine`, `compute_matchup`, 100% test. |
| F2   | ✅ done | Companion window nativa con chrome Windows, hotkey, persistenza. |
| F3   | 🟡 usable | mGBA + Rosso Fuoco. Detail dei sotto-step in `PLAN.md` §6. |
| F4   | ⏳ da fare | Auto-detect combattimento via HP-bar template match. |

## 6. Limitazioni note (da PLAN §7)

- **OCR livello (`L.XX`) sui font pixel**: RapidOCR è poco affidabile,
  solo alcuni slot restituiscono il numero. Fallback: livello preservato,
  editabile via `…`.
- **Match icona menu Pokemon**: pHash/dhash restano rumorosi anche col
  color-key HSV. Da valutare template matching per game se conta.
- **ROI hardcoded**: solo per FRLG a scala mGBA con menu bar visibile.
  Un calibratore visuale drag-a-rettangolo sbloccherebbe altri giochi.
- **Ambiente**: F2/F3/F4 richiedono Windows nativo (COM + Windows
  Graphics Capture + hotkey Win32). Sviluppo di logica pura (`engine/`,
  `data/`) possibile ovunque, anche WSL/Linux.
- **Nickname Pokemon**: il fuzzy match non li riconosce. Il team recognize
  preserva lo slot corrispondente se l'OCR legge qualcosa ma non trova
  match — vedi `_apply_team_recognition`.

## 7. Prossimi step suggeriti

Ordinati per rapporto valore/costo:

1. **F4 auto-detect combattimento**: template match su un pattern
   distintivo della schermata di battaglia (barra HP, ombra sprite).
   Quando detected, invoca `recognize_opponent` senza input utente.
   ~4h.
2. **Calibratore ROI visuale**: dialog con canvas su screenshot, disegni
   rettangoli per (nome opp, sprite opp, HUD player, ecc.). Sblocca
   altri giochi/scaling senza toccare il codice. ~4-6h.
3. **Detection livello via template matching per digit**: 10 template
   per game (0-9 in font pixel), match a scorrimento sulla ROI. Sostituisce
   il fallimento OCR con qualcosa che funziona. ~2-3h per game.
4. **Altro emulatore / gioco**: aggiungere Cristallo (Gen 2 mGBA) o
   HeartGold (Gen 4 melonDS/DeSmuME). Serve ROI dedicate + preferred_game
   in `_preferred_game()`.
5. **Test UI**: coverage sui componenti Qt è a 0. Aggiungere test con
   `pytest-qt` per lo state binding di `TeamPanel` / `OpponentPanel`.

## 8. Convenzioni rapide

- Commit: Conventional Commits, scope in parentesi (es. `feat(f3):`).
  Body opzionale ma preferito per "il perché".
- Codice/log/identificatori in inglese; docstring e commenti in italiano.
- Coverage minima 90% su `engine/` e `data/` (fail CI sotto soglia).
- `.gitattributes` forza LF ovunque; non toccare `core.autocrlf`.

## 9. File di stato utente

`%APPDATA%\pokemon-helper\state.json`: JSON con `generation`, `team[6]`
(id + livello), `overlay_x`, `overlay_y`. Rigenerato al primo salvataggio
se assente. Chiavi non riconosciute vengono ignorate silenziosamente
(es. la vecchia `click_through`).

## 10. Dove chiedere

Se il tool non riconosce l'avversario: prima riprova mettendoti bene sulla
schermata di battaglia. Se non basta, gira lo script diagnostico
`scripts/recognize_test.py` (opponent) o `scripts/player_debug.py`
(player) e guarda l'overlay `data/roi-firered-overlay.png` — spesso è una
questione di ROI leggermente disallineate rispetto alla dimensione della
finestra mGBA.
