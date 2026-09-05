# CLAUDE.md — istruzioni per Claude su questo repo

File descrive convenzioni operative progetto `pokemon-helper`.
Vale con [`PLAN.md`](PLAN.md), che definisce obiettivi e roadmap.

## Linguaggio

- **Python 3.14** (pin in `.python-version`, `requires-python = ">=3.14"`).
- **Codice, identificatori, log**: inglese.
- **Commenti e docstring**: italiano.
- **Documentazione (`PLAN.md`, `README.md`, questo file)**: italiano.
- **Chat**: italiano.

## Layout del pacchetto

Sottopacchetti sotto `src/pokemon_helper/`:

```
src/pokemon_helper/
  engine/     motore di efficacia, calcoli sui tipi, logica di combattimento
  data/       accesso al dataset SQLite, modelli dominio (Pokemon, Type, Sprite)
  vision/     cattura schermo, OCR, perceptual hash
  ui/         overlay PySide6, hotkey globali, gestione DPI
  __main__.py entry-point CLI
```

Ogni sottopacchetto ha proprio `__init__.py` e test in `tests/<subpackage>/`.

## Commit

**Conventional Commits** con scope tra parentesi. Formato:

```
<type>(<scope>): <subject>
```

- `type`: `feat`, `fix`, `chore`, `docs`, `test`, `refactor`, `perf`, `build`, `ci`.
- `scope`: `f0`, `f1`, `f2`, `f3`, `f4`, `engine`, `data`, `vision`, `ui`, `deps`, `repo`.
- `subject`: imperativo, inglese, ≤ 72 caratteri.
- Body opzionale, spiega **perché** quando non ovvio.

Esempi:
- `feat(f1): add gen1 type chart with historical bug edge cases`
- `test(engine): cover magnemite type change gen1→gen2`
- `chore(deps): bump ruff to 0.16`

Commit frequenti, uno per unità logica. Nessun `--no-verify` senza motivazione esplicita.

## Test

- Framework: **pytest**.
- Test obbligatori per ogni modulo logica pura (`engine/`, `data/`).
- Test facoltativi per UI/overlay (`ui/`) e vision (`vision/`) — coprire almeno funzioni pure (parsing, coordinate scaling, hash matching), non chiamate Win32/Qt.
- Casi limite obbligatori per `engine/`: eccezioni Gen 1 e tipi variabili per generazione (vedi `PLAN.md` §5).

### Coverage

Soglia minima **90%** su pacchetti logica pura:

- `src/pokemon_helper/engine/`
- `src/pokemon_helper/data/`

Config in `pyproject.toml` sotto `[tool.coverage.*]`. Sotto soglia CI fallisce.

## Lint e formattazione

- **ruff** per lint e format (config in `pyproject.toml`).
- Regole: `E`, `F`, `I`, `UP`, `B`, `SIM`.
- Applicato da **pre-commit** (`.pre-commit-config.yaml`).

Install hook una tantum:

```powershell
pre-commit install
```

Run manuale su tutto repo:

```powershell
pre-commit run --all-files
```

## Comandi di sviluppo

Attiva venv:

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

- Dataset generato (`data/*.sqlite`) e directory vendoring (`data/vendor/`, `data/sprites/`) sono **gitignored**. Anche PNG diagnostiche da script sotto `data/` ignorate (`data/*.png`).
- Script che generano dataset stanno in `scripts/`, devono essere idempotenti (`build_dataset.py`, `build_sprite_index.py`).
- Dati esterni:
  - `veekun/pokedex` (shallow clone, ~15 MB) per dati tabulari — vedi `scripts/build_dataset.py`.
  - `PokeAPI/sprites` (sparse clone dei soli `generation-{i..v}`, ~500 MB con animazioni Gen 5) per sprite battaglia + icone menu — vedi `scripts/build_sprite_index.py`.
- DB SQLite finale: `data/pokemon.sqlite`, tabelle `pokemon`, `pokemon_types_by_gen`, `sprite_hashes` (front/back/icon).

## Line endings

- `.gitattributes` forza `* text=auto eol=lf` per silenziare warning CRLF/LF su Windows. Non toccare `core.autocrlf`.

## Ambiente di esecuzione

- **F0, F1**: pura logica Python, gira ovunque (anche WSL).
- **F2, F3, F4**: Windows nativo obbligatorio (overlay, capture, hotkey). Vedi `PLAN.md` §3.

Extras opzionali:

- `[dev]` (dev+CI): `pytest`, `pytest-cov`, `ruff`, `pre-commit`.
- `[app]` (overlay Windows F2): `PySide6>=6.7`, `pynput>=1.7`.
- `[vision]` (F0.2 sprite indexing + F3 runtime): `Pillow>=10`, `imagehash>=4.3`, `windows-capture>=1.4` (Windows-only), `rapidocr>=3.9`, `onnxruntime>=1.19`. Pacchetto legacy `rapidocr-onnxruntime` non ha wheel per Python 3.14.

Install tipica dev Windows: `pip install -e ".[dev,app,vision]"`.

## Note per Claude

- Dubbio su convenzioni, scope, scelte architetturali: **fermati e chiedi**.
- Niente dipendenze runtime senza discussione prima.
- Niente file `.md` di planning/analisi intermedi: usa contesto chat. Eccezioni permanenti: `HANDOFF.md` (stato progetto per nuova sessione) e `TODO.md` (memoria attività in corso o da fare, aggiornata a fine sessione).
- Commit conventional puntuali durante lavoro, non un unico commit gigante a fine sessione.
