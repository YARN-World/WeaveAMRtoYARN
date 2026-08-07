"""UD and anchor providers. Nothing here needs Stanza or grewpy."""

from __future__ import annotations

from weave_amr2yarn.formats import AmrCorpus, AnchorDictionary
from weave_amr2yarn.graph import normalizeGraph, penmanToGrew
from weave_amr2yarn.providers import (
    ChainedAnchorer,
    ChainedUd,
    ConlluUd,
    LevenshteinAnchorer,
    PrecomputedAnchorer,
)

UD = {
    "nodes": {
        "0": {"id": "0", "form": "_0_"},
        "1": {"id": "1", "form": "John", "lemma": "John", "upos": "PROPN"},
        "2": {"id": "2", "form": "ran", "lemma": "run", "upos": "VERB"},
    },
    "edges": [{"src": "0", "label": "root", "tar": "2"}],
}


def _sentence(text="(r / run-01)", identifier="s1"):
    return AmrCorpus.fromText(f"# ::id {identifier}\n{text}")[0]


def _amr(text):
    return normalizeGraph(penmanToGrew(text))


def test_conlluProviderMatchesBySentenceId(tmp_path):
    path = tmp_path / "c.conllu"
    path.write_text("# sent_id = s1\n1\ta\ta\tX\t_\t_\t0\troot\t_\t_\n", encoding="utf-8")
    provider = ConlluUd.fromFile(path)
    assert provider.graphFor(_sentence(identifier="s1")) is not None
    assert provider.graphFor(_sentence(identifier="other")) is None


def test_chainedUdFallsThroughToTheSecondProvider():
    empty = ConlluUd({})
    populated = ConlluUd({"s1": UD})
    assert ChainedUd(empty, populated).graphFor(_sentence()) is UD


def test_precomputedAnchorsComeFromTheDictionary():
    provider = PrecomputedAnchorer(AnchorDictionary({"s1": {"r": "2"}}))
    assert provider.anchorsFor(_sentence(), _amr("(r / run-01)"), UD) == {"r": "2"}


def test_precomputedReturnsNoneForAnAbsentSentence():
    """None means fall through to the next provider; {} would not."""
    provider = PrecomputedAnchorer(AnchorDictionary({"other": {"r": "2"}}))
    assert provider.anchorsFor(_sentence(), _amr("(r / run-01)"), UD) is None


def test_chainedAnchorerPrefersTheDictionaryThenComputes():
    chained = ChainedAnchorer(
        PrecomputedAnchorer(AnchorDictionary({"s1": {"r": "1"}})),
        LevenshteinAnchorer(),
    )
    assert chained.anchorsFor(_sentence(), _amr("(r / run-01)"), UD) == {"r": "1"}

    missing = ChainedAnchorer(
        PrecomputedAnchorer(AnchorDictionary({})), LevenshteinAnchorer()
    )
    assert missing.anchorsFor(_sentence(), _amr("(r / run-01)"), UD) == {"r": "2"}


def test_senseNumberStripsButHyphensSurvive():
    """have-mod-91 must reduce to have-mod, not havemod."""
    specs = LevenshteinAnchorer()._matchSpecs({"pred": "have-mod-91"}, None)
    assert specs[0][0] == "have-mod"


def test_namedEntityAnchorsThroughItsLiteral():
    """person -name-> name -[]-> "John" should anchor person to the token
    "John", not try to match the generic concept "person"."""
    amr = _amr('(p / person :name (n / name :op1 "John"))')
    anchors = LevenshteinAnchorer().anchorsFor(_sentence(), amr, UD)
    assert anchors.get("p") == "1"


def test_structuralConceptsAreNeverAnchored():
    amr = _amr('(a / and :op1 (r / run-01))')
    anchors = LevenshteinAnchorer().anchorsFor(_sentence(), amr, UD)
    assert "a" not in anchors


def test_strongerMatchWinsTheToken():
    """Assignment is highest-score-first, so node order cannot steal a token."""
    ud = {
        "nodes": {
            "1": {"id": "1", "lemma": "run"},
        },
        "edges": [],
    }
    # "runner" scores lower against "run" than "run-01" does.
    amr = _amr("(x / runner :ARG0-of (r / run-01))")
    anchors = LevenshteinAnchorer().anchorsFor(_sentence(), amr, ud)
    assert anchors.get("r") == "1"
    assert "x" not in anchors