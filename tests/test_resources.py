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


def test_lexiconsResolveFromTheRulesThatNameThem():
    """A `lex from` path resolves against the file declaring the rule, so it is
    that file's directory the path must be relative to — not the rule set root."""
    import re

    for source in bundledGrsDir().rglob("*.grs"):
        for reference in re.findall(r'(?:s?lex)\s+from\s+"([^"]+)"', source.read_text(encoding="utf-8")):
            assert (source.parent / reference).is_file(), f"{source.name} -> {reference}"


def test_everyIncludedFileIsPresent():
    """`include` is used rather than `import` on purpose: grewlib names an
    imported package after the whole path, so `import "amr/quant.grs"` yields a
    package called `amr/quant` that no strategy can name. It loads cleanly and
    fails on the first rewrite, so this checks the paths resolve."""
    import re

    text = bundledGrs().read_text(encoding="utf-8")
    included = set(re.findall(r'include\s+"([^"]+)"', text))
    assert included, "main.grs includes nothing — the rule set is probably empty"
    missing = {name for name in included if not (bundledGrsDir() / name).is_file()}
    assert not missing, f"main.grs includes files that are absent: {sorted(missing)}"


def test_everyIncludedFileDeclaresItsPackage():
    """A file spliced in by `include` carries no package of its own, so each
    must declare one — that is what keeps `Onf(name)` resolving."""
    import re

    text = bundledGrs().read_text(encoding="utf-8")
    for name in re.findall(r'include\s+"([^"]+)"', text):
        source = bundledGrsDir() / name
        expected = source.stem
        assert re.search(rf"^package\s+{re.escape(expected)}\s*{{", 
                         source.read_text(encoding="utf-8"), re.M), \
            f"{name} does not declare `package {expected}`"


def test_unknownEntryNamesAreReported():
    with pytest.raises(GrsError, match="no bundled rule set"):
        bundledGrs("nope.grs")