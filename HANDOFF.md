# HANDOFF — pokemon-helper

Passaggio per nuova sessione o nuovo collaboratore. Stato al **2026-09-15**.

Vedi [`PLAN.md`](PLAN.md) per roadmap, [`CLAUDE.md`](CLAUDE.md) per convenzioni.

## 1. Cosa fa oggi

Tool desktop Windows. Affianca emulatore Pokemon Gen 1-5 con pannello sempre in primo piano. Funzionalità:

- **Squadra manuale**: 6 slot nome + livello, generazione selezionabile. Persistenza in `%APPDATA%\pokemon-helper\state.json`.
- **Riconoscimento battaglia** (`Ctrl+Alt+R` o pulsante `⚔ Avversario`) su mGBA + Rosso Fuoco: cattura finestra, riconosce avversario via OCR del nome — unico canale, il pHash degli sprite è stato tolto (vedi §6) — e in parallelo Pokemon giocatore in campo (vincolato ai 6 membri squadra per precisione). Guardia `classify_screen` blocca l'update se la schermata non è quella di combattimento — la ROI HP avversario senza pixel colore-HP (warning ⚠, motivo in tooltip).
- **Riconoscimento squadra** (`Ctrl+Alt+T` o pulsante `⟳ Squadra`) da schermata elenco Pokemon: OCR nome per ciascuno dei 6 slot con fuzzy match, livello letto cifra per cifra da `vision/level_reader.py`, sovrascrive `state.team`. Guard doppia: prima `classify_screen` deve leggere il pulsante `ESCI` in basso a destra (schermata sbagliata → nessuna delle 12 OCR sugli slot parte), poi la lettura deve essere coerente — <3/6 slot leggibili o stesso pokemon_id in ≥2 slot → aggiornamento bloccato.
- **Mappa nickname** (pulsante `🏷`): dialog per associare nickname custom (es. "FIAMMETTA") a un pokemon_id, usata sia dal riconoscimento squadra sia da quello del player in battaglia. Il nickname si scrive come appare nel gioco: il confronto è fuzzy e assorbe gli errori OCR. Persistita in `state.json`.
- **Calibratore ROI** (pulsante `▣`): mostra la finestra dell'emulatore e i 16 rettangoli da cui l'app legge. Si disegnano col mouse, con snap alla griglia nativa 240x160, frecce per spostare di un pixel nativo e Shift+frecce per ridimensionare. Sotto l'elenco compaiono il ritaglio ingrandito e **cosa ci si legge dentro** (OCR per i box di testo, livello cifra per cifra per i `L.XX`, conteggio dei pixel colore-PS per la barra). Una riga di stato dice quale schermata è a video e avvisa se il rettangolo selezionato si misura sull'altra. Salvataggio in `%APPDATA%\\pokemon-helper\\rois\\<gioco>.json`, che vince sui default del repo; "Copia snippet per roi.py" esporta il literal Python per promuovere una calibrazione a default.
- **OpponentPanel**: due card affiancate (player | avversario) con sprite Pokedex, nome, tipi, abilità e tabella efficacia difensiva colorata (Debolezze / Resistenze / Immune, neutri esclusi).
- **Abilità**: l'efficacia tiene conto delle abilità che la modificano — contro un Gengar con Levitazione, Terra risulta `0×` e non `2×`. Quando il dataset ammette una sola abilità per quella generazione viene applicata da sola; con più candidati un menu a tendina permette di fissare quella vista in battaglia, e la scelta è persistita per specie. Il menu è evidenziato solo se l'ambiguità può davvero cambiare il verdetto. Tooltip con la descrizione dell'abilità in italiano.
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

# ATTENZIONE all'ordine: `build_dataset.py` ricrea il file da zero, quindi
# cancella anche `sprite_hashes`. Se lo rilanci, rilancia anche l'indice.

# Avvio applicazione.
python -m pokemon_helper
```

Requisiti: Python 3.14 (pin in `.python-version`), Windows 10/11, mGBA per riconoscimento (Rosso Fuoco / FRLG Italiano unico gioco tarato).

## 3. Layout progetto

```
src/pokemon_helper/
  engine/           # F1: type chart, EffectivenessEngine, matchup helpers.
  data/             # F0.1: SQLite schema, models, PokemonRepository.
  vision/           # F0.2 + F3: capture, chrome, ROI, OCR, sprite hash, recognizer,
                    #            screen_mode (battaglia / elenco Pokemon / altro),
                    #            roi_store (calibrazione utente), roi_targets (i 16
                    #            rettangoli), roi_probe (cosa si legge in un crop).
  ui/               # F2: overlay Qt, TeamPanel, OpponentPanel, hotkey, state,
                    #     roi_calibrator (dialogo di calibrazione).
  __main__.py       # CLI entry-point → ui.app.run

scripts/
  build_dataset.py           # veekun/pokedex clone + parse → data/pokemon.sqlite
                             # (ricrea il DB: poi va rilanciato build_sprite_index)
  build_sprite_index.py      # PokeAPI/sprites sparse clone + pHash → sprite_hashes
  capture_test.py            # cattura mGBA → data/capture-test.png
  roi_debug.py               # overlay ROI battaglia (mGBA + FRLG)
  team_menu_debug.py         # overlay ROI menu squadra
  level_debug.py             # OCR debug su ROI level dedicate
  ocr_debug_team.py          # OCR debug su ROI slot squadra
  recognize_test.py          # end-to-end recognize opponent
  recognize_team_test.py     # end-to-end recognize squadra
  battle_watch_debug.py      # eventi F4 (ENTERED/LEFT/CHANGED) senza GUI
  player_debug.py            # end-to-end recognize player (con crop + overlay)
  extract_roi_from_annotated.py  # bbox per colore da PNG annotato → coord Roi

tests/
  engine/ data/ ui/ vision/  # pytest, 395 test. engine+data al 100%, ui/ al 76%.

data/                        # gitignored (eccetto la struttura)
  vendor/pokedex/            # shallow clone veekun (CSV Pokedex)
  vendor/sprites/            # sparse clone PokeAPI/sprites (PNG)
  pokemon.sqlite             # DB generato
```

## 4. Comandi utili

```powershell
pytest -q                            # 395 test, tutti verdi
pytest --cov                         # coverage con floor 90% su engine+data (oggi 100%)
ruff check .                         # lint
ruff format .                        # format
pre-commit run --all-files           # tutti gli hook (ruff + eol + pytest --cov)
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
| F5   | ✅ done | Abilità che modificano l'efficacia (fuori dal piano originale). Vedi `PLAN.md` §6. |

## 6. Limitazioni note (da PLAN §7)

- **Livello non mostrato con alterazione di stato**: se il Pokemon è avvelenato/paralizzato/ecc. il gioco disegna il badge di stato al posto di `L.XX`. `read_level` ritorna `None` e lo slot conserva il livello precedente, editabile via `…`. (La lettura del livello in sé è risolta: vedi `vision/level_reader.py`.)
- **Match icona menu Pokemon**: rimosso. La confidenza era `1 - distanza/18` e le distanze reali stavano fra 16 e 24 anche sul match giusto — sempre sotto la soglia di 0.60 con cui la squadra viene scritta, quindi il canale non poteva cambiare nulla. Le righe `side='icon'` restano nel DB, non le legge più nessuno.
- **Chrome mGBA**: non è più un numero fisso. `vision/chrome.py` misura la fascia sul frame catturato (titolo e menu bar sono righe grigie e chiare, le schermate di gioco sono sature) e i 52 px del layout restano il fallback. Con un tema scuro la misura non passa e si ripiega sul fallback: il nero è escluso di proposito, perché è anche il colore delle bande di letterbox.
- **ROI di fabbrica**: quelle nel repo coprono solo FRLG a scala mGBA. Quelle di combattimento sono state verificate su cattura live (le due del lato giocatore ricalibrate misurando i pixel). Per il resto c'è il calibratore (pulsante `▣`): si ridisegnano i 16 rettangoli sulla propria finestra e si salvano, senza toccare il codice. Resta anche `extract_roi_from_annotated.py` (offline, da PNG annotato).
- **pHash sprite in combattimento**: rimosso. La cattura ha campo e cielo dietro il Pokemon, le reference indicizzate stanno su bianco: la specie corretta non entrava nei primi tre a nessun offset di ROI (Weezing a distanza 20-24 mentre specie sbagliate stanno a 14-16). Lato avversario non superava mai la soglia; lato giocatore poteva perfino decidere da solo a OCR muta, con confidenza 0.70 sulla distanza minima, cioè quasi sempre la specie sbagliata. Il verdetto regge interamente sul nome. `PokemonRepository.find_pokemon_by_sprite_hash` resta, senza chiamanti: è la query che servirebbe se un giorno si segmentasse il soggetto dallo sfondo.
- **Abilità ambigue**: molte specie ne ammettono più d'una e dallo sprite non si distinguono. Il filtro per generazione ne risolve circa metà in Gen 3, meno in Gen 5. Per il resto il pannello non applica nulla e segnala il dubbio, e l'abilità si fissa a mano dal menu sulla card.
- **Abilità storiche**: veekun pubblica solo l'assegnazione corrente. `ABILITY_HISTORY_OVERRIDES` copre Gengar (che ha perso Levitazione in Gen 7); altri casi eventuali vanno aggiunti lì a mano.
- **Ambiente**: F2/F3/F4 richiedono Windows nativo (COM + Windows Graphics Capture + hotkey Win32). Logica pura (`engine/`, `data/`) ovunque, anche WSL/Linux.
- **Nickname Pokemon**: il fuzzy sui nomi di specie non li riconosce. Fix via mappa utente `state.nicknames` (dialog 🏷), consultata sia da `recognize_team` sia da `recognize_player` (l'HUD di combattimento mostra il nickname, non la specie). Il confronto è fuzzy, quindi assorbe i tipici errori OCR: il nickname va scritto **come appare nel gioco**.

## 7. Prossimi step suggeriti

Ordinati per valore/costo. Tutte le fasi del piano (F0-F4) sono chiuse: da qui
in poi sono estensioni, non completamento.

1. **Secondo gioco**: Cristallo (Gen 2 mGBA) o HeartGold (Gen 4
   melonDS/DeSmuME). Serve layout GB/GBC (160×144, aspect 10:9) o doppio
   schermo DS, ROI dedicate, `preferred_game`. Nota: in Gen 1-2 non esistono
   abilità, quindi quel layer semplicemente non si attiva.
2. **Packaging Windows**: PyInstaller o installer, per non dipendere dal venv.
3. **Segmentare lo sprite dallo sfondo**: il pHash in battaglia è stato
   rimosso perché la cattura ha campo e cielo mentre le reference stanno su
   bianco. I fondali di battaglia sono a bande piatte, quindi un flood-fill
   dai bordi è plausibile. Rimetterebbe in piedi il secondo segnale, oggi
   portato interamente dal nome — ma va rifatto insieme alle ROI sprite,
   tolte anch'esse.

## 8. Convenzioni rapide

- Commit: Conventional Commits, scope in parentesi (es. `feat(f3):`). Body opzionale ma preferito per "il perché".
- Codice/log/identificatori in inglese; docstring e commenti in italiano.
- Coverage minima 90% su `engine/` e `data/`. Non c'è CI: il floor è applicato dall'hook pre-commit `pytest --cov`, che blocca il commit se scende.
- `.gitattributes` forza LF ovunque; non toccare `core.autocrlf`.

## 9. File di stato utente

`%APPDATA%\pokemon-helper
ois\<gioco>.json`: le ROI calibrate dall'utente, che vincono sui default di `roi.py`. Un file rotto o con un rettangolo fuori range viene scartato **intero**, con un avviso in console: mezza calibrazione sbaglierebbe senza spiegazioni.

`%APPDATA%\pokemon-helper\state.json`: JSON con `generation`, `team[6]` (id + livello), `overlay_x`, `overlay_y`, `nicknames` (dict UPPERCASE → pokemon_id), `auto_detect` (bool), `abilities` (dict pokemon_id → identifier abilità fissata). Rigenerato al primo salvataggio se assente. Chiavi non riconosciute ignorate silenziosamente (es. vecchia `click_through`); chiavi mancanti prendono il default, quindi i file scritti da versioni precedenti restano leggibili.

## 10. Dove chiedere

Tool non riconosce avversario: prima riprova ben posizionato su schermata battaglia. Se non basta, gira script diagnostico `scripts/recognize_test.py` (opponent) o `scripts/player_debug.py` (player) e guarda overlay `data/roi-firered-overlay.png` — spesso ROI leggermente disallineate rispetto a dimensione finestra mGBA.
