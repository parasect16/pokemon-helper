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
- **F0.2 — sprite + perceptual hash (rimandato dopo F2)**. Fonte iniziale: la directory `pokedex/data/media/sprites/pokemon/` del clone veekun già presente, che copre i giochi principali di ogni generazione. Se la coverage si dimostrasse insufficiente (sprite di gioco specifico mancante), migrare a un clone `--filter=blob:none --sparse` di `PokeAPI/sprites` limitato a `sprites/pokemon/versions/generation-{i..v}/` (~50-80 MB invece dei ~400 MB del repo completo). Nessuna dipendenza a runtime dai binari Windows: i pHash sono calcolabili anche da WSL.

### F1 — Motore di efficacia

Input: tipi dell'attaccante, tipi del difensore, generazione. Output: moltiplicatore offensivo per ciascun tipo di mossa e vulnerabilità difensive del difensore.

Copertura di test obbligatoria sui casi limite elencati nella sezione 5: le eccezioni della Gen 1 e i tipi che cambiano fra generazioni.

### F2 — Overlay Windows con inserimento manuale

Pannello con la squadra sempre in primo piano, trascinabile, con posizione persistita fra le sessioni, click-through opzionale e hotkey globale per mostrare e nascondere. La squadra viene inserita manualmente.

Ogni slot della squadra conserva l'id del Pokemon e il livello (1-100). La generazione di riferimento è selezionabile via dropdown in UI. Persistenza dello stato in `%APPDATA%\pokemon-helper\state.json`. Hotkey globale gestita con `pynput`.

Al termine di questa fase il tool è già utilizzabile.

### F3 — Riconoscimento

Cattura della finestra dell'emulatore individuata per titolo, ritaglio delle regioni di interesse, OCR del nome e pHash dello sprite, con punteggio di confidenza combinato fra i due segnali. Le regioni di interesse sono configurabili per gioco, con una calibrazione da eseguire una sola volta.

### F4 — Rilevamento automatico del combattimento

Rilevare lo stato di combattimento tramite template matching sulla barra dei punti salute avversaria, estrarre il Pokémon avversario e aggiornare il pannello con il confronto fra i sei Pokémon della squadra e l'avversario corrente.

## 7. Punti aperti

- Emulatori da supportare per primi. Candidati: mGBA per Game Boy, Game Boy Color e Game Boy Advance; melonDS o DeSmuME per Nintendo DS.
- Lingua del gioco per l'OCR: la lingua dell'interfaccia del gioco determina il dizionario di nomi da usare per il confronto.
- Gestione delle abilità che modificano l'efficacia dei tipi, ad esempio Levitazione o Assorbivolt. Da valutare dopo la fase F1.
