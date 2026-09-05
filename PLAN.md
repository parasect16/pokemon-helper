# Pokémon Helper — Piano di progetto

Documento di handoff. Redatto in una sessione WSL, destinato a proseguire in una sessione Claude Code su Windows nativo.

## 1. Obiettivo

Tool desktop per Windows che assiste il giocatore durante una partita Pokémon in esecuzione in un emulatore, tramite un overlay sempre in primo piano.

Funzionalità richieste:

1. Riconoscimento di un Pokémon a partire dal nome o dall'immagine.
2. Squadra del giocatore sempre visibile a schermo.
3. Durante il combattimento, per la generazione specifica in uso, visualizzazione di debolezze e punti di forza della squadra rispetto al Pokémon avversario.

## 2. Decisioni già prese

| Ambito | Decisione |
|---|---|
| Sorgente immagine | Emulatore in esecuzione in una finestra Windows |
| Generazioni supportate al primo rilascio | Gen 1-5 (sprite 2D) |
| Piattaforma di esecuzione | Windows nativo (non WSL) |
| Linguaggio | Python 3.12 |

## 3. Perché Windows nativo e non WSL

Il componente di overlay e cattura schermo deve girare come processo Windows nativo. Le ragioni sono vincolanti, non preferenze:

- WSLg esegue le applicazioni grafiche Linux in una sessione RDP virtuale isolata. Una finestra Linux non può essere posizionata sempre in primo piano sopra le applicazioni Windows.
- Dal lato Linux non è accessibile né Windows Graphics Capture né DXGI Desktop Duplication. Non è quindi possibile catturare la finestra dell'emulatore.
- Non sono disponibili gli stili di finestra Windows necessari (`WS_EX_LAYERED`, `WS_EX_TRANSPARENT` per il click-through) né le hotkey globali né la gestione del DPI per-monitor.

Suddivisione del lavoro:

- **Logica pura** (dataset, tabella dei tipi, calcolo dell'efficacia, test): Python puro, eseguibile ovunque. Può essere sviluppata anche da WSL.
- **Applicazione** (overlay, cattura, OCR, hotkey): processo Windows nativo.

### Collocazione del repository

Spostare il repository su filesystem Windows, ad esempio `C:\dev\pokemon-helper`. Da WSL resta accessibile su `/mnt/c/dev/pokemon-helper`.

Da evitare l'ambiente virtuale Python su percorso `\\wsl$\...`: è lento e i binari Windows compilati non funzionano correttamente da lì.

Comandi di migrazione, da eseguire su Windows (PowerShell):

```powershell
git clone \\wsl$\<distro>\git\pokemon-helper C:\dev\pokemon-helper
cd C:\dev\pokemon-helper
py -3.12 -m venv .venv
.\.venv\Scripts\activate
```

## 4. Stack tecnico

| Componente | Scelta | Motivazione |
|---|---|---|
| Interfaccia overlay | PySide6 (Qt 6), finestra frameless con `WindowStaysOnTopHint` e `WA_TranslucentBackground` | Stesso linguaggio della logica di visione artificiale, gestione DPI matura |
| Cattura schermo | `windows-capture` (binding di Windows Graphics Capture) | Cattura per singola finestra, funziona con finestre accelerate in Direct3D e in fullscreen borderless. `mss` e le API GDI non catturano correttamente le finestre degli emulatori |
| OCR del nome | RapidOCR su ONNX Runtime | Completamente offline, veloce, non richiede l'installazione separata di Tesseract |
| Riconoscimento sprite | Perceptual hash (pHash) confrontato con un database di sprite precalcolato | Gli sprite sono asset fissi e deterministici: il confronto per hash è esatto e richiede circa un millisecondo. Una rete neurale sarebbe sovradimensionata |
| Dati Pokémon | Dump locale di PokeAPI in SQLite | Funziona offline, nessun limite di frequenza sulle richieste |

## 5. Note sui dati

### Tabelle dei tipi

Per le generazioni 1-5 servono **due** tabelle distinte, non una:

- **Gen 1**: i tipi Buio e Acciaio non esistono. Spettro non ha effetto su Psico (bug storico del gioco). Coleottero contro Veleno è superefficace. Veleno contro Coleottero è superefficace. Ghiaccio contro Fuoco è neutro.
- **Gen 2-5**: tabella unica e stabile per tutte e quattro le generazioni. Introdotti Buio e Acciaio. Acciaio resiste a Spettro e a Buio. Ghiaccio contro Fuoco diventa non molto efficace.

Il tipo Folletto arriva in Gen 6 e la resistenza di Acciaio a Spettro e Buio viene rimossa nella stessa generazione. Fuori perimetro per il primo rilascio, ma la struttura dati deve restare estendibile per generazione.

### Tipi dei Pokémon variabili per generazione

I tipi di un Pokémon non sono costanti nel tempo. Esempio: Magnemite e Magneton sono di tipo Elettro in Gen 1 e diventano Elettro/Acciaio dalla Gen 2. La chiave del dataset deve essere la coppia `(pokemon_id, generazione)`, non il solo `pokemon_id`.

### Sprite

- Servono gli sprite **frontali** (Pokémon avversario) e **posteriori** (Pokémon del giocatore).
- Gli sprite variano per generazione e talvolta per versione all'interno della stessa generazione.
- Le varianti cromatiche richiedono hash separati.
- Dalla Gen 4 esistono forme differenziate per genere per alcune specie.
- In Gen 5 gli sprite sono animati: calcolare più hash per Pokémon, uno per fotogramma campionato, e accettare la corrispondenza più vicina.

### Risoluzioni native

Le regioni di interesse vanno definite in coordinate native del gioco e riscalate in base alla dimensione effettiva della finestra dell'emulatore, che l'utente può ridimensionare liberamente.

- Game Boy e Game Boy Color: 160x144
- Game Boy Advance: 240x160
- Nintendo DS: 256x192 per schermo, due schermi

## 6. Fasi di sviluppo

L'ordine è pensato per produrre qualcosa di utilizzabile alla fase F2, senza dipendere dalla visione artificiale.

### F0 — Dataset

Costruire il dump offline: pokedex con identificativi, nomi in italiano e inglese, tipi per generazione, sprite per generazione, tabelle dei tipi per generazione. Nessuna dipendenza da Windows: sviluppabile in WSL.

Suddivisione operativa in due sotto-fasi indipendenti:

- **F0.1 — dati tabulari (fatto)**. Fonte: `veekun/pokedex` clonato in shallow mode. Costruisce `data/pokemon.sqlite` con specie, nomi IT/EN, tipi per generazione. Le eccezioni storiche di tipo che veekun non esporta in CSV (linea Magnemite in Gen 1) vivono in `TYPE_HISTORY_OVERRIDES` dentro `scripts/build_dataset.py`.
- **F0.2 — sprite + perceptual hash (fatto)**. Il repo `veekun/pokedex` **non** ship gli sprite (contiene solo CSV), quindi si è passati direttamente al clone `--filter=blob:none --sparse` di `PokeAPI/sprites` limitato a `sprites/pokemon/versions/generation-{i..v}/`. Il vendoring finale occupa circa 500 MB su disco (~250 MB sono le GIF animate di Gen 5 che al momento non vengono indicizzate). Lo script `scripts/build_sprite_index.py` calcola il pHash a 64 bit di ogni sprite front/back per i giochi principali di ciascuna generazione e popola la tabella `sprite_hashes` in `data/pokemon.sqlite`. Il repository espone `find_pokemon_by_sprite_hash(query, gen, max_distance, limit)` per il match runtime via distanza di Hamming, deduplicando la miglior corrispondenza per Pokemon. Nessuna dipendenza a runtime dai binari Windows: `[vision]` extras (`Pillow`, `imagehash`) sono cross-platform.

### F1 — Motore di efficacia (fatto)

Input: tipi dell'attaccante, tipi del difensore, generazione. Output: moltiplicatore offensivo per ciascun tipo di mossa e vulnerabilità difensive del difensore. Implementato in `pokemon_helper/engine/` con `EffectivenessEngine`, `compute_matchup` (difesa/offesa per squadra vs avversario) e `best_matchup_index`. Coverage 100% con casi limite Gen 1 + tipi variabili per generazione.

### F2 — Overlay Windows con inserimento manuale (fatto, evoluto a "companion window")

Inizialmente pensato come overlay traslucido sempre in primo piano; refactorizzato in una **companion window** con chrome nativo Windows dopo il primo giro d'uso: title bar/min/close di sistema, drag nativo, voce in taskbar, `WindowStaysOnTopHint` mantenuto. Il click-through è stato rimosso (non era utile in pratica).

Ogni slot della squadra conserva l'id del Pokemon e il livello (1-100). La generazione di riferimento è selezionabile via dropdown. Persistenza dello stato in `%APPDATA%\pokemon-helper\state.json`. Hotkey globali gestite con `pynput`:
- `Ctrl+Alt+P`: mostra/nasconde/ripristina la finestra.
- `Ctrl+Alt+R`: cattura schermo mGBA + riconoscimento avversario + Pokemon del giocatore (F3.7).
- `Ctrl+Alt+T`: cattura schermo mGBA + riconoscimento intera squadra dal menu Pokemon (F3.8).

`OpponentPanel` mostra la tabella difesa/offesa per ciascun membro squadra vs avversario (placeholder "Combattimento non in corso" quando nessun avversario è impostato). Lo slot squadra corrispondente al Pokemon in campo viene evidenziato.

### F3 — Riconoscimento (in corso, stato dettagliato)

Cattura della finestra dell'emulatore (mGBA su Rosso Fuoco come primo target), ritaglio delle regioni di interesse, OCR del nome via RapidOCR e pHash dello sprite via `imagehash`, con punteggio di confidenza combinato. Le ROI sono hardcoded per gioco in `pokemon_helper/vision/roi.py` (`GAME_ROIS['firered']`), non ancora calibrabili via UI.

Sotto-fasi:

- **F3.1 (fatto)** — Wrapper `WindowCapture` su `windows-capture` (Windows Graphics Capture API): trasforma l'API event-based in una chiamata sincrona `capture_frame()` che ritorna un `PIL.Image`.
- **F3.2 (fatto)** — Sistema ROI con coordinate normalizzate (0-1) rispetto alla risoluzione nativa del gioco, `compute_game_area` per gestire menu bar mGBA + letterbox aspect-ratio, `roi_to_pixels` per lo scaling. Default per Rosso Fuoco misurati empiricamente.
- **F3.3 (fatto)** — pHash del ritaglio sprite, con `_flatten_alpha` per neutralizzare il canale alpha e allineare capture su sfondo bianco alle reference indicizzate.
- **F3.4 (fatto)** — OCR via `rapidocr>=3.9` + `onnxruntime` (il vecchio `rapidocr-onnxruntime` non ha wheel per Py 3.14). `OcrEngine` fa lazy-init dei modelli e ora accetta `upscale` e `high_contrast` per aiutare i font pixel.
- **F3.5 (fatto)** — `Recognizer` orchestrator: OCR fuzzy match sul nome + pHash sprite; se convergono restituisce sorgente `both` con confidenza alta, altrimenti si affida al segnale più forte.
- **F3.6 (fatto)** — Wiring nell'overlay via hotkey `Ctrl+Alt+R`; il callback pynput apre una connessione SQLite dedicata (thread-safety) e marshalla il risultato al thread GUI di Qt.
- **F3.7 (fatto)** — Riconoscimento anche del Pokemon del giocatore (ROI dedicate per HUD + back sprite), evidenziazione dello slot in `TeamPanel`. Same hotkey della F3.6 riconosce entrambi i lati.
- **F3.8 (fatto)** — Riconoscimento intera squadra dal menu Pokemon con `Ctrl+Alt+T`: OCR per ciascuno dei 6 slot, fuzzy match, `_apply_team_recognition` sovrascrive `state.team` preservando gli slot con nickname sconosciuti. Test live: 5/6 Pokemon con nome default riconosciuti correttamente al primo tentativo.
- **F3.9 (in corso, best-effort)** — Fallback pHash su icona menu quando OCR nome fallisce (utile per Pokemon con nickname personalizzato). Schema `sprite_hashes.side` esteso ad accettare `icon`, indice popolato da `PokeAPI/sprites/versions/generation-{roman}/icons/`. Preprocessing HSV color-key rimuove il pattern teal del menu FRLG prima del hash. Al momento le distanze restano alte (≥18-24 anche per il match corretto): il match icon non è affidabile e va valutato se investire in template matching per game.
- **F3.10 (limitazione nota)** — Detection del livello `L.XX` sui font pixel FRLG resta poco affidabile con RapidOCR. Aggiunte le ROI dedicate `slot_levels` e il preprocessing `high_contrast + upscale` sull'engine OCR, ma solo alcuni slot riescono a produrre il numero. `_apply_team_recognition` preserva il livello precedente per lo slot quando l'OCR fallisce; l'utente può modificarlo manualmente via il pulsante `…`. Alternative future: template matching per singolo digit o cambio del motore OCR.

### F4 — Rilevamento automatico del combattimento (da fare)

Rilevare lo stato di combattimento tramite template matching sulla barra dei punti salute avversaria, estrarre il Pokémon avversario e aggiornare il pannello con il confronto fra i sei Pokémon della squadra e l'avversario corrente. Da implementare dopo il consolidamento della F3.

## 7. Punti aperti

- Emulatori da supportare per primi. Candidati: mGBA per Game Boy, Game Boy Color e Game Boy Advance; melonDS o DeSmuME per Nintendo DS. **Attuale**: solo mGBA con Rosso Fuoco (Gen 3 GBA).
- Lingua del gioco per l'OCR: la lingua dell'interfaccia del gioco determina il dizionario di nomi da usare per il confronto. **Attuale**: fuzzy match su nomi IT + EN a prescindere dalla lingua del gioco.
- Gestione delle abilità che modificano l'efficacia dei tipi, ad esempio Levitazione o Assorbivolt. Da valutare dopo la fase F1.
- **Detection del livello sui font pixel**: RapidOCR è poco affidabile. Da valutare template matching per singolo digit (~2h codice per-game) o un motore OCR alternativo.
- **Match icona menu**: pHash/dhash non raggiungono distanze basse anche con color-key HSV. Alternative: template matching su icone note, o accettare che il fallback icona resti un weak signal.
- **Calibrazione ROI visuale**: le ROI attuali sono hardcoded per FRLG a scala mGBA con menu bar visibile. Un calibratore drag-a-rettangolo permetterebbe di supportare altri giochi/scaling con meno codice.
