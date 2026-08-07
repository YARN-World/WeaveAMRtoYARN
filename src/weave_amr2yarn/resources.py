"""Locating the rule set that ships inside the package.

The GRS is package data, not a path the caller has to know. This is what lets
the library run from any working directory: the original code defaulted to the
string ``"grs/main.grs"``, which only resolves when the process happens to be
sitting in the repository root.

``main.grs`` pulls in 43 sibling files, and several rules load ``.lex``
lexicons. Both resolve relative to the file naming them, so the directory has to
travel together — but an absolute path to the entry file is fine.
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path

from .errors import GrsError

_GRS_DIR = "grs"
DEFAULT_ENTRY = "main.grs"


def bundledGrsDir() -> Path:
    """Return the directory holding the bundled rule set."""
    directory = Path(str(resources.files(__package__).joinpath(_GRS_DIR)))
    if not directory.is_dir():
        raise GrsError(
            f"the bundled rule set is missing (looked in {directory}). "
            "It has to be readable as real files — reinstall with `pip install`."
        )
    return directory


def bundledGrs(entry: str = DEFAULT_ENTRY) -> Path:
    """Return the path to a bundled GRS entry file, by default ``main.grs``."""
    path = bundledGrsDir() / entry
    if not path.is_file():
        available = sorted(p.name for p in bundledGrsDir().glob("*.grs"))
        raise GrsError(
            f"no bundled rule set named {entry!r}. Available: {', '.join(available)}"
        )
    return path