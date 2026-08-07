"""Graph transformations, exercised without grewpy."""

from __future__ import annotations

import pytest

from weave_amr2yarn.errors import AmrParseError
from weave_amr2yarn.graph import (
    applyAnchoring,
    canonicalizeIds,
    combineNameLiterals,
    dereify,
    penmanToGrew,
    removeWiki,
    renameSNodes,
    splitEvents,
)


def test_senseNumberedConceptsArePredicates():
    nodes = penmanToGrew("(r / run-01 :ARG0 (d / dog))")["nodes"]
    assert nodes["r"]["pred"] == "run-01"
    assert nodes["d"]["concept"] == "dog"


def test_aspectMakesABareConceptAPredicate():
    """UMR marks eventualities with :aspect rather than a sense number."""
    nodes = penmanToGrew('(d / digital :aspect "state")')["nodes"]
    assert nodes["d"]["pred"] == "digital"


def test_topIsMarkedAsFocus():
    nodes = penmanToGrew("(r / run-01 :ARG0 (d / dog))")["nodes"]
    assert nodes["r"]["focus"] == "yes"
    assert "focus" not in nodes["d"]


def test_attributesBecomeNodes():
    graph = penmanToGrew('(n / name :op1 "Elizabeth")')
    assert graph["nodes"]["n_op1_Elizabeth"]["concept"] == "Elizabeth"
    assert {"src": "n", "label": "op1", "tar": "n_op1_Elizabeth"} in graph["edges"]


def test_malformedPenmanRaisesWithTheSentenceId():
    with pytest.raises(AmrParseError, match=r"\[bad-1\]"):
        penmanToGrew("(((", sentenceId="bad-1")


def test_wikiEdgesAndTheirLiteralsGo():
    graph = penmanToGrew('(c / city :wiki "Paris" :name (n / name))')
    stripped = removeWiki(graph)
    assert not [e for e in stripped["edges"] if e["label"] == "wiki"]
    assert "c_wiki_Paris" not in stripped["nodes"]


def test_nameLiteralsCombineInOpOrder():
    graph = penmanToGrew('(n / name :op1 "Queen" :op2 "Elizabeth" :op3 "II")')
    combined = combineNameLiterals(graph)
    concepts = {node.get("concept") for node in combined["nodes"].values()}
    assert "Queen Elizabeth II" in concepts


def test_combinedNodeHasNoVarKey():
    """remove_labelled_edges requires B[var]; it must not match this edge."""
    graph = penmanToGrew('(n / name :op1 "Ann")')
    combined = combineNameLiterals(graph)
    assert "var" not in combined["nodes"]["n_Ann"]


def test_normalizersDoNotMutateTheirInput():
    graph = penmanToGrew('(c / city :wiki "Paris")')
    before = len(graph["nodes"])
    removeWiki(graph)
    assert len(graph["nodes"]) == before


def _amr():
    return {
        "meta": {},
        "nodes": {"r": {"pred": "run-01", "type": "V", "var": "r"},
                  "n": {"concept": "name", "type": "V", "var": "n"}},
        "edges": [],
    }


def _ud():
    return {"nodes": {"1": {"id": "1", "upos": "VERB"}},
            "edges": [{"src": "0", "label": "root", "tar": "1"}]}


def test_anchorEdgesAreAdded():
    merged = applyAnchoring(_amr(), _ud(), {"r": "1"})
    assert {"src": "r", "label": "anchor", "tar": "1"} in merged["edges"]


def test_nameNodesAreNeverAnchored():
    merged = applyAnchoring(_amr(), _ud(), {"n": "1"})
    assert not [e for e in merged["edges"] if e["label"] == "anchor"]


def test_anchorsForUnknownVariablesAreIgnored():
    merged = applyAnchoring(_amr(), _ud(), {"ghost": "1"})
    assert not [e for e in merged["edges"] if e["label"] == "anchor"]


def _anchored(upos, pred="run-01", incoming=None):
    graph = {
        "nodes": {"r": {"pred": pred, "type": "V", "var": "r"},
                  "1": {"id": "1", "upos": upos}},
        "edges": [{"src": "r", "label": "anchor", "tar": "1"}],
    }
    if incoming:
        graph["edges"].append({"src": "9", "label": incoming, "tar": "1"})
    return graph


def test_situationIsCreatedForAVerbalAnchor():
    graph = splitEvents(_anchored("VERB"))
    assert graph["nodes"]["S1"]["type"] == "S"
    assert graph["nodes"]["S1"]["core"] == "r"


def test_auxCountsAsVerbal():
    """A collapsed multi-word predicate can anchor at the auxiliary."""
    assert "S1" in splitEvents(_anchored("AUX"))["nodes"]


def test_nominalAnchorsGetNoSituation():
    assert "S1" not in splitEvents(_anchored("NOUN"))["nodes"]


def test_attributiveVerbsGetNoSituation():
    assert "S1" not in splitEvents(_anchored("VERB", incoming="amod"))["nodes"]


def test_causeIsAnOperatorNotASituation():
    assert "S1" not in splitEvents(_anchored("VERB", pred="cause-01"))["nodes"]


def test_situationsAreNumberedByCoreNotByEngineId():
    data = {
        "nodes": {"_9_": {"type": "S", "core": "d10"},
                  "_2_": {"type": "S", "core": "d2"}},
        "edges": [],
    }
    renameSNodes(data)
    # d2 sorts before d10 naturally, despite "10" < "2" as text.
    assert data["nodes"]["_2_"]["event"] == "S1"
    assert data["nodes"]["_9_"]["event"] == "S2"


def test_situationsWithoutACoreSortLast():
    data = {
        "nodes": {"_1_": {"type": "S"}, "_2_": {"type": "S", "core": "a"}},
        "edges": [],
    }
    renameSNodes(data)
    assert data["nodes"]["_2_"]["event"] == "S1"
    assert data["nodes"]["_1_"]["event"] == "S2"


def test_engineIdsAreRenamedAndEdgesFollow():
    data = {
        "nodes": {"_7_": {"type": "F", "feat": "num"}, "x": {"type": "V", "var": "x"}},
        "edges": [{"src": "_7_", "label": "l", "tar": "x"}],
    }
    canonicalizeIds(data)
    assert "_1_" in data["nodes"] and "_7_" not in data["nodes"]
    assert data["edges"][0]["src"] == "_1_"


def test_situationIdsBecomeTheirEventName():
    data = {"nodes": {"_4_": {"type": "S", "core": "a", "event": "S1"}}, "edges": []}
    canonicalizeIds(data)
    assert "S1" in data["nodes"]


def test_dereifyCollapsesRoleFrames():
    out = dereify("(h / have-org-role-91 :ARG0 (p / person) :ARG2 (l / lawyer))")
    assert ":role" in out
    assert "have-org-role-91" not in out


def test_dereifyKeepsMetadata():
    out = dereify("# ::id x\n# ::snt A lawyer.\n(h / have-org-role-91 "
                  ":ARG0 (p / person) :ARG2 (l / lawyer))")
    assert "::id x" in out


def test_dereifyRaisesRatherThanReturningAPoisonString():
    """The original returned "(parse error: ...)", which then decoded as a
    one-node graph and was counted as a successful conversion."""
    with pytest.raises(AmrParseError):
        dereify("(((", sentenceId="bad-1")