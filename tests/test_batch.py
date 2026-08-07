"""Config parsing. No conversion happens here, so no backend is needed."""

from __future__ import annotations

from pathlib import Path

import pytest

from weave_amr2yarn.batch import loadPlan
from weave_amr2yarn.errors import WeaveError

CONFIG = """
out_root = "results"

[defaults]
strat = "eval"
key_snt = "text"

[corpus.one]
amr = "a/one.txt"
ud = "a/one.conllu"

[corpus.two]
amr = "a/two.txt"
strat = "main"
layout = "grouped"
"""


def _config(tmp_path, text=CONFIG):
    path = tmp_path / "weave.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_everyCorpusBecomesASpec(tmp_path):
    plan = loadPlan(_config(tmp_path))
    assert [spec.name for spec in plan.specs] == ["one", "two"]


def test_defaultsApplyAndSectionsOverrideThem(tmp_path):
    one, two = loadPlan(_config(tmp_path)).specs
    assert one.strat == "eval"
    assert two.strat == "main"
    assert two.keySnt == "text"  # inherited from defaults


def test_snakeCaseKeysAreAccepted(tmp_path):
    """Configs are written in the shell's idiom, not Python's."""
    assert loadPlan(_config(tmp_path)).specs[0].keySnt == "text"


def test_pathsResolveAgainstTheConfigNotTheCwd(tmp_path):
    """So a config can be moved with its data."""
    spec = loadPlan(_config(tmp_path)).specs[0]
    assert spec.amr == str((tmp_path / "a/one.txt").resolve())
    assert Path(spec.amr).is_absolute()


def test_outRootResolvesAgainstTheConfigToo(tmp_path):
    assert loadPlan(_config(tmp_path)).outRoot == (tmp_path / "results").resolve()


def test_outputDirIsNamedAfterTheCorpus(tmp_path):
    plan = loadPlan(_config(tmp_path))
    assert plan.specs[0].outputDir(plan.outRoot).name == "one"


def test_selectPicksNamedCorpora(tmp_path):
    plan = loadPlan(_config(tmp_path))
    assert [spec.name for spec in plan.select(["two"])] == ["two"]
    assert len(plan.select(None)) == 2


def test_selectingAnUnknownCorpusListsTheRealOnes(tmp_path):
    plan = loadPlan(_config(tmp_path))
    with pytest.raises(WeaveError, match="Available: one, two"):
        plan.select(["three"])


def test_unknownSettingIsRejectedWithSuggestions(tmp_path):
    path = _config(tmp_path, '[corpus.one]\namr = "a.txt"\nstart = "eval"\n')
    with pytest.raises(WeaveError, match="unknown setting 'start'"):
        loadPlan(path)


def test_corpusWithoutAmrIsRejected(tmp_path):
    path = _config(tmp_path, '[corpus.one]\nud = "a.conllu"\n')
    with pytest.raises(WeaveError, match="has no 'amr'"):
        loadPlan(path)


def test_configWithoutCorporaIsRejected(tmp_path):
    with pytest.raises(WeaveError, match="defines no corpora"):
        loadPlan(_config(tmp_path, '[defaults]\nstrat = "eval"\n'))


def test_malformedTomlIsReportedAsSuch(tmp_path):
    with pytest.raises(WeaveError, match="not valid TOML"):
        loadPlan(_config(tmp_path, "[corpus.one\n"))


def test_missingFileIsReported(tmp_path):
    with pytest.raises(WeaveError, match="could not read"):
        loadPlan(tmp_path / "absent.toml")