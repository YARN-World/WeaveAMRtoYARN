"""Every non-Python file under src/ must be matched by a package-data glob.

Package data fails quietly: the wheel builds, imports work, and the missing
file only shows up when something reaches for it at runtime. That is how the
browser app shipped without its JavaScript — `static/*` does not descend into
`static/js/`, so eleven modules were silently left out of every wheel.
"""

from __future__ import annotations

import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - only on 3.10
    import tomli as tomllib

SOURCE = Path(__file__).resolve().parent.parent / "src"
PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"

#: Not shipped, and not expected to be.
IGNORED = {".pyc", ".pyo"}


def declaredGlobs() -> dict[str, list[str]]:
    config = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    return config["tool"]["setuptools"]["package-data"]


def test_everyDataFileIsCoveredByAGlob():
    globs = declaredGlobs()
    uncovered = []

    for path in SOURCE.rglob("*"):
        if not path.is_file() or path.suffix == ".py" or path.suffix in IGNORED:
            continue
        if path.name == "py.typed":
            continue
        # Build artefacts, not sources: setuptools writes .egg-info beside the
        # packages in a src layout, and __pycache__ follows every import.
        if any(part == "__pycache__" or part.endswith(".egg-info")
               for part in path.parts):
            continue

        relative = path.relative_to(SOURCE)
        covered = False
        for package, patterns in globs.items():
            root = SOURCE / Path(*package.split("."))
            if root not in path.parents:
                continue
            inside = path.relative_to(root)
            if any(inside.full_match(pattern) if hasattr(inside, "full_match")
                   else inside.match(pattern) for pattern in patterns):
                covered = True
                break
        if not covered:
            uncovered.append(str(relative))

    assert not uncovered, (
        "these files are under src/ but no package-data glob ships them: "
        f"{sorted(uncovered)}"
    )


def test_theBrowserAppsEntryPointIsShipped():
    """The page loads one module; the rest are imported from it."""
    import re

    template = SOURCE / "weave_ui/templates/index.html"
    referenced = re.findall(r"filename='([^']+)'", template.read_text(encoding="utf-8"))
    assert referenced, "index.html references no static assets at all"
    for name in referenced:
        assert (SOURCE / "weave_ui/static" / name).is_file(), name
