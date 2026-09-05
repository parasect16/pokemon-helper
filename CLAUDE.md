# CLAUDE.md — istruzioni per Claude su questo repo

Questo file descrive le convenzioni operative del progetto `pokemon-helper`.
Vale insieme a [`PLAN.md`](PLAN.md), che invece definisce obiettivi e roadmap.

## Linguaggio

- **Python 3.14** (pin in `.python-version`, `requires-python = ">=3.14"`).
- **Codice, identificatori, messaggi di log**: inglese.
- **Commenti e docstring**: italiano.
- **Documentazione (`PLAN.md`, `README.md`, questo file)**: italiano.
- **Interazione in chat**: italiano.

## Layout del pacchetto

Layout a sottopacchetti sotto `src/pokemon_helper/`:

```
src/pokemon_helper/
  engine/     motore di efficacia, calcoli sui tipi, logica di combattimento
  data/       accesso al dataset SQLite, modelli dominio (Pokemon, Type, Sprite)
  vision/     cattura schermo, OCR, perceptual hash
  ui/         overlay PySide6, hotkey globali, gestione DPI
  __main__.py entry-point CLI
```

Ogni sottopacchetto ha il proprio `__init__.py` e i propri test in `tests/<subpackage>/`.

## Commit

**Conventional Commits** con scope tra parentesi. Formato:

```
<type>(<scope>): <subject>
```

- `type`: `feat`, `fix`, `chore`, `docs`, `test`, `refactor`, `perf`, `build`, `ci`.
- `scope`: `f0`, `f1`, `f2`, `f3`, `f4`, `engine`, `data`, `vision`, `ui`, `deps`, `repo`.
- `subject`: imperativo, inglese, ≤ 72 caratteri.
- Body opzionale, spiega il **perché** quando non ovvio.

Esempi:
- `feat(f1): add gen1 type chart with historical bug edge cases`
- `test(engine): cover magnemite type change gen1→gen2`
- `chore(deps): bump ruff to 0.16`

Commit frequenti, uno per unità logica. Nessun `--no-verify` senza motivazione esplicita.

## Test

- Framework: **pytest**.
- Test obbligatori per ogni modulo di logica pura (`engine/`, `data/`).
- Test facoltativi per UI/overlay (`ui/`) e vision (`vision/`) — coprire almeno le funzioni pure (parsing, coordinate scaling, hash matching), non le chiamate a Win32/Qt.
- Casi limite obbligatori per `engine/`: eccezioni Gen 1 e tipi variabili per generazione (vedi `PLAN.md` §5).

### Coverage

Soglia minima **90%** sui pacchetti di logica pura:

- `src/pokemon_helper/engine/`
- `src/pokemon_helper/data/`

Configurata in `pyproject.toml` sotto `[tool.coverage.*]`. Sotto soglia la CI fallisce.

## Lint e formattazione

- **ruff** per lint e format (config in `pyproject.toml`).
- Regole selezionate: `E`, `F`, `I`, `UP`, `B`, `SIM`.
- Applicato automaticamente da **pre-commit** (`.pre-commit-config.yaml`).

Installazione hook una tantum:

```powershell
pre-commit install
```

Esecuzione manuale su tutto il repo:

```powershell
pre-commit run --all-files
```

## Comandi di sviluppo

Attivazione venv:

```powershell
.\.venv\Scripts\activate
```

Comandi principali:

```powershell
pytest                              # esecuzione test
pytest --cov=pokemon_helper         # test con coverage
ruff check .                        # lint
ruff format .                       # format
python -m pokemon_helper            # smoke test entry-point
```

## Dati e asset

- Il dataset generato (`data/*.sqlite`) e le directory di vendoring (`data/vendor/`, `data/sprites/`) sono **gitignored**. Anche le PNG diagnostiche prodotte dagli script sotto `data/` sono ignorate (`data/*.png`).
- Gli script che generano il dataset stanno in `scripts/` e devono essere idempotenti (`build_dataset.py`, `build_sprite_index.py`).
- Riferimento dati esterni:
  - `veekun/pokedex` (shallow clone, ~15 MB) per i dati tabulari — vedi `scripts/build_dataset.py`.
  - `PokeAPI/sprites` (sparse clone dei soli `generation-{i..v}`, ~500 MB con animazioni Gen 5) per sprite battaglia + icone menu — vedi `scripts/build_sprite_index.py`.
- Il DB SQLite finale è `data/pokemon.sqlite` con tabelle `pokemon`, `pokemon_types_by_gen`, `sprite_hashes` (front/back/icon).

## Line endings

- `.gitattributes` forza `* text=auto eol=lf` per silenziare i warning CRLF/LF su Windows. Non toccare `core.autocrlf`.

## Ambiente di esecuzione

- **F0, F1**: pura logica Python, eseguibile ovunque (anche WSL).
- **F2, F3, F4**: Windows nativo obbligatorio (overlay, capture, hotkey). Vedi `PLAN.md` §3.

Extras opzionali:

- `[dev]` (dev+CI): `pytest`, `pytest-cov`, `ruff`, `pre-commit`.
- `[app]` (overlay Windows F2): `PySide6>=6.7`, `pynput>=1.7`.
- `[vision]` (F0.2 sprite indexing + F3 runtime): `Pillow>=10`, `imagehash>=4.3`, `windows-capture>=1.4` (Windows-only), `rapidocr>=3.9`, `onnxruntime>=1.19`. Il pacchetto `rapidocr-onnxruntime` legacy non ha wheel per Python 3.14.

Installazione tipica sviluppo Windows: `pip install -e ".[dev,app,vision]"`.

## Note per Claude

- In caso di dubbio su convenzioni, scope, scelte architetturali: **fermati e chiedi**.
- Non introdurre dipendenze runtime senza discuterle prima.
- Non aggiungere file `.md` di planning/analisi intermedi: usa il contesto della chat. Eccezioni permanenti: `HANDOFF.md` (stato del progetto per una nuova sessione) e `TODO.md` (memoria intermedia di attività in corso o da fare, aggiornata a fine sessione).
- Commit conventional puntuali durante il lavoro, non un unico commit gigante a fine sessione.
