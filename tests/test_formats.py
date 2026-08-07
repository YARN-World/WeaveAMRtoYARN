"""Format readers, exercised without grewpy or a parser installed."""

from __future__ import annotations

from weave_amr2yarn.formats import AmrCorpus, AnchorDictionary, addMainOut, readConllu

CORPUS = """\
# ::id n01027007
# ::snt Who are they?
( t / they :domain (a / amr-unknown))

# ::sent-id fracas-001.premise_0
# ::snt An Italian became a tenor.
(b / become-01)

(x / lonely-01)
"""


def test_readsIdsInEverySpelling():
    corpus = AmrCorpus.fromText(CORPUS)
    assert corpus.ids() == ["n01027007", "fracas-001.premise_0", "snt3"]


def test_blockWithoutAnIdIsNamedByPosition():
    """Third block, so snt3 — the index is 1-based to match the old reader."""
    assert AmrCorpus.fromText(CORPUS)[2].id == "snt3"


def test_metadataIsReadableWithoutDecodingPenman():
    assert AmrCorpus.fromText(CORPUS)[0].metadata()["snt"] == "Who are they?"


def test_duplicateIdsAreReported():
    corpus = AmrCorpus.fromText("# ::id a\n(x / x)\n\n# ::id a\n(y / y)")
    assert corpus.duplicateIds() == ["a"]


CONLLU = """\
# sent_id = s1
# text = Who are they?
1\tWho\twho\tPRON\t_\tPronType=Int\t3\tnsubj\t_\t_
2\tare\tbe\tAUX\t_\tNumber=Plur\t3\tcop\t_\t_
3\tthey\tthey\tPRON\t_\t_\t0\troot\t_\t_

# sent_id = s2
1-2\tdon't\t_\t_\t_\t_\t_\t_\t_\t_
1\tdo\tdo\tAUX\t_\t_\t2\taux\t_\t_
2\tgo\tgo\tVERB\t_\t_\t0\troot\t_\t_
"""


def test_readsSentencesKeyedBySentId(tmp_path):
    path = tmp_path / "c.conllu"
    path.write_text(CONLLU, encoding="utf-8")
    graphs = readConllu(path)
    assert sorted(graphs) == ["s1", "s2"]


def test_rootSentinelAndFeaturesAreOnTheNodes(tmp_path):
    path = tmp_path / "c.conllu"
    path.write_text(CONLLU, encoding="utf-8")
    nodes = readConllu(path)["s1"]["nodes"]
    assert nodes["0"] == {"id": "0", "form": "_0_"}
    assert nodes["1"]["upos"] == "PRON"
    assert nodes["1"]["PronType"] == "Int"
    assert "PronType" not in nodes["3"]  # FEATS was "_"


def test_headZeroBecomesAnEdgeFromTheSentinel(tmp_path):
    path = tmp_path / "c.conllu"
    path.write_text(CONLLU, encoding="utf-8")
    edges = readConllu(path)["s1"]["edges"]
    assert {"src": "0", "label": "root", "tar": "3"} in edges


def test_multiwordRangesAreSkipped(tmp_path):
    """A "1-2" row is not a graph node; only the two real tokens are."""
    path = tmp_path / "c.conllu"
    path.write_text(CONLLU, encoding="utf-8")
    assert sorted(readConllu(path)["s2"]["nodes"]) == ["0", "1", "2"]


def test_finalSentenceSurvivesAMissingTrailingBlankLine(tmp_path):
    path = tmp_path / "c.conllu"
    path.write_text("# sent_id = only\n1\ta\ta\tX\t_\t_\t0\troot\t_\t_", encoding="utf-8")
    assert "only" in readConllu(path)


def test_tokenIdsAreStrings(tmp_path):
    anchors = AnchorDictionary({"s1": {"t": 3}})
    assert anchors.sentence("s1") == {"t": "3"}


def test_absentSentenceIsNoneNotEmpty():
    """None means 'compute anchors'; {} means 'deliberately none'."""
    anchors = AnchorDictionary({"s1": {}})
    assert anchors.sentence("s1") == {}
    assert anchors.sentence("s2") is None


def test_anchorsRoundTripThroughAFile(tmp_path):
    original = AnchorDictionary({"s1": {"t": "3", "d": "1"}})
    path = tmp_path / "a.json"
    original.toFile(path)
    assert AnchorDictionary.fromFile(path).triples() == original.triples()
    assert AnchorDictionary.fromFile(path).anchorCount() == 2


def test_mainOutTagsEdgesLeavingLhecNodes():
    graph = {
        "nodes": {"l": {"type": "L"}, "v": {"type": "V"}},
        "edges": [{"src": "l", "label": {}, "tar": "v"},
                  {"src": "v", "label": "ARG0", "tar": "l"}],
    }
    edges = addMainOut(graph)["edges"]
    assert edges[0]["label"] == {"main_out": "Yes"}
    assert edges[1]["label"] == {}  # leaves a V node, so untagged


def test_degreeSrcStaysUntagged():
    """It records that the source is the L-node, and tagging it would move it
    from edge_mapping_from[H] to edge_mapping_toward[L]."""
    graph = {
        "nodes": {"h": {"type": "H"}, "l": {"type": "L"}},
        "edges": [{"src": "h", "label": "degree_src", "tar": "l"}],
    }
    assert addMainOut(graph)["edges"][0]["label"] == {}


def test_addMainOutDoesNotMutateItsInput():
    graph = {"nodes": {"l": {"type": "L"}}, "edges": [{"src": "l", "label": {}, "tar": "l"}]}
    addMainOut(graph)
    assert graph["edges"][0]["label"] == {}