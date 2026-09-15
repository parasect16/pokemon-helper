"""Tool desktop di supporto alle lotte Pokemon sugli emulatori Gen 1-5."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("pokemon-helper")
except PackageNotFoundError:  # pragma: no cover - solo eseguendo dai sorgenti
    # Il pacchetto non è installato (`pip install -e .` non fatto): meglio
    # dirlo che riportare un numero scritto a mano che nessuno aggiorna.
    __version__ = "0.0.0+non-installato"

__all__ = ["__version__"]
