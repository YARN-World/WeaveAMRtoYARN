"""Argument handling and the environment report."""

from __future__ import annotations

import pytest

from weave_amr2yarn.cli import buildParser
from weave_amr2yarn.doctor import Check, _isOlder


def test_convertRequiresAmrAndOut():
    with pytest.raises(SystemExit):
        buildParser().parse_args(["convert"])


def test_convertDefaults():
    args = buildParser().parse_args(["convert", "--amr", "a.txt", "--out", "o"])
    assert args.strat == "eval"
    assert args.key_snt == "snt"
    assert args.layout == "flat"
    assert args.timeout == 30
    assert args.penman_dereify is False
    assert args.ud is None and args.anchors is None


def test_layoutIsConstrained():
    with pytest.raises(SystemExit):
        buildParser().parse_args(
            ["convert", "--amr", "a", "--out", "o", "--layout", "nested"]
        )


def test_missingInputIsReportedBeforeAnythingLoads(tmp_path, capsys):
    from weave_amr2yarn.cli import runConvert

    args = buildParser().parse_args(
        ["convert", "--amr", str(tmp_path / "nope.txt"), "--out", str(tmp_path)]
    )
    with pytest.raises(SystemExit, match="no such AMR corpus"):
        runConvert(args)


def test_subcommandIsRequired():
    with pytest.raises(SystemExit):
        buildParser().parse_args([])


def test_versionComparison():
    assert _isOlder("0.5.9", "0.6.0")
    assert not _isOlder("0.6.0", "0.6.0")
    assert not _isOlder("0.6.1", "0.6.0")
    assert not _isOlder("1.0", "0.6.0")


def test_failedCheckShowsItsHint():
    line = Check("thing", False, "not found", "install it").line()
    assert "MISS" in line and "install it" in line


def test_optionalFailureIsNotMarkedMissing():
    assert "MISS" not in Check("thing", False, "-", required=False).line()