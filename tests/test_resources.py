"""The bundled rule set must be locatable without grewpy or a parser present."""

from __future__ import annotations

import pytest

from weave_amr2yarn.errors import GrsError
from weave_amr2yarn.resources import bundledGrs, bundledGrsDir


def test_bundledGrsDirExists():
    assert bundledGrsDir().is_dir()


def test_bundledEntryIsMainGrs():
    assert bundledGrs().name == "main.grs"
    assert bundledGrs().is_file()


def test_lexiconsTravelWithTheRules():
    """Rules load lexicons by bare filename, so they must sit alongside."""
    names = {p.name for p in bundledGrsDir().iterdir()}
    assert {"becl_num.lex", "state_verb.lex", "duration_noun.lex"} <= names


def test_importsAreResolvableSiblings():
    """Every `import "x.grs"` in main.grs must have been copied too."""
    import re

    text = bundledGrs().read_text(encoding="utf-8")
    imported = set(re.findall(r'import\s+"([^"]+)"', text))
    assert imported, "main.grs declares no imports — the copy is probably wrong"
    missing = {name for name in imported if not (bundledGrsDir() / name).is_file()}
    assert not missing, f"main.grs imports files that were not bundled: {sorted(missing)}"


def test_unknownEntryNamesAreReported():
    with pytest.raises(GrsError, match="no bundled rule set"):
        bundledGrs("nope.grs")