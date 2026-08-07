"""The align2anchor provider's own logic.

align2anchor is bundled, so these run anywhere. LEAMR is not, so anything
needing the aligner is out of scope here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from weave_amr2yarn.errors import MissingDependency, WeaveError
from weave_amr2yarn.providers.align2anchor import (
    LEAMR_VARIABLE,
    Align2AnchorAnchorer,
    loadAlign2Anchor,
    resolveLeamrDir,
)


def _anchorer(**overrides):
    settings = dict(amrPath="a.txt", udPath="u.conllu")
    settings.update(overrides)
    return Align2AnchorAnchorer(**settings)


def test_unknownSourceIsRejected():
    with pytest.raises(WeaveError, match="unknown anchoring source"):
        _anchorer(source="magic")


def test_rawSourceNeedsAPath():
    with pytest.raises(WeaveError, match="needs rawPath"):
        _anchorer(source="raw")


def test_unknownStageIsRejected():
    with pytest.raises(WeaveError, match="unknown stage"):
        _anchorer(stages=("filter", "polish"))


def test_stagesMayBeEmpty():
    """No stages means the aligner's output is used as it comes."""
    assert _anchorer(stages=()).stages == ()


def test_constructionDoesNotLoadAnything():
    """LEAMR loads three models, so nothing should happen until build()."""
    anchorer = _anchorer()
    assert anchorer._anchors is None
    assert anchorer.audit() is None


def test_writeAuditIsFalseWhenTheFilterDidNotRun(tmp_path):
    assert _anchorer().writeAudit(tmp_path / "audit.tsv") is False


def test_bundledPackageImports():
    """The copy is self-contained: no PYTHONPATH, no research checkout."""
    assert Path(loadAlign2Anchor().__file__).parent.name == "align2anchor"


def test_bundledChainIsReachable():
    """The three stages the provider drives are all present in the copy."""
    from weave_amr2yarn.vendor.align2anchor.context import CorpusContext  # noqa: F401
    from weave_amr2yarn.vendor.align2anchor.filter import ConventionFilter  # noqa: F401
    from weave_amr2yarn.vendor.align2anchor.repair import (  # noqa: F401
        RepairStage,
        TenseMovePolicy,
    )


def test_leamrIsFoundByExplicitPath(tmp_path):
    checkout = tmp_path / "leamr"
    (checkout / "amr_utils").mkdir(parents=True)
    assert resolveLeamrDir(checkout) == checkout


def test_leamrIsFoundByEnvironmentVariable(tmp_path, monkeypatch):
    checkout = tmp_path / "leamr"
    (checkout / "amr_utils").mkdir(parents=True)
    monkeypatch.setenv(LEAMR_VARIABLE, str(checkout))
    assert resolveLeamrDir() == checkout


def test_aDirectoryWithoutAmrUtilsIsNotACheckout(tmp_path, monkeypatch):
    """The marker is amr_utils, which LEAMR vendors inside itself."""
    monkeypatch.setenv(LEAMR_VARIABLE, str(tmp_path))
    monkeypatch.chdir(tmp_path)
    with pytest.raises(MissingDependency, match=LEAMR_VARIABLE):
        resolveLeamrDir()