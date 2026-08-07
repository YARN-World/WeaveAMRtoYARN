"""Manifests and metadata stamping. No backend needed."""

from __future__ import annotations

import json
import re

from weave_amr2yarn.manifest import RunManifest, ruleSetDigest, timestamp
from weave_amr2yarn.resources import bundledGrs


def test_timestampIsIsoUtcToTheMillisecond():
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z", timestamp())


def test_digestCoversTheWholeRuleDirectory(tmp_path):
    """main.grs imports 43 siblings, so hashing the entry alone would call two
    different rule sets identical."""
    first = tmp_path / "a"
    first.mkdir()
    (first / "main.grs").write_text("strat s { Onf(x) }", encoding="utf-8")
    (first / "other.grs").write_text("rule r { }", encoding="utf-8")

    before = ruleSetDigest(first / "main.grs")
    (first / "other.grs").write_text("rule r { changed }", encoding="utf-8")
    assert ruleSetDigest(first / "main.grs") != before


def test_digestIncludesLexicons(tmp_path):
    directory = tmp_path / "rules"
    directory.mkdir()
    (directory / "main.grs").write_text("strat s { }", encoding="utf-8")
    (directory / "words.lex").write_text("a\n", encoding="utf-8")

    before = ruleSetDigest(directory / "main.grs")
    (directory / "words.lex").write_text("b\n", encoding="utf-8")
    assert ruleSetDigest(directory / "main.grs") != before


def test_digestIsStableForTheBundledRules():
    assert ruleSetDigest(bundledGrs()) == ruleSetDigest(bundledGrs())


def test_manifestRoundTripsThroughJson(tmp_path):
    manifest = RunManifest(
        weaveVersion="0.1.0",
        startedAt=timestamp(),
        counts={"sentences": 3, "converted": 2, "failed": 1},
        failures=[{"id": "s3", "error": "boom"}],
    )
    path = manifest.write(tmp_path)
    written = json.loads(path.read_text(encoding="utf-8"))

    assert path.name == "manifest.json"
    assert written["counts"]["converted"] == 2
    assert written["failures"][0]["id"] == "s3"


def test_manifestCreatesItsDirectory(tmp_path):
    target = tmp_path / "deep" / "nested"
    RunManifest(weaveVersion="0.1.0", startedAt=timestamp()).write(target)
    assert (target / "manifest.json").is_file()