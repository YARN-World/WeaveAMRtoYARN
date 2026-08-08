"""The UI's own logic: step parsing, diffing, rule introspection, rendering.

Routes that convert need the rule engine and a parser, so they are exercised by
hand rather than here; what these cover is everything around them.
"""

from __future__ import annotations

import pytest

from weave_amr2yarn.errors import GrsError
from weave_amr2yarn.resources import bundledGrs
from weave_amr2yarn.transform.rules import RuleSpec, _requestText, rulesOf
from weave_ui.stepsview import renderSteps
from weave_ui.tracing import TraceStep, difference, loadSteps, stepStrategy


def test_stepsComeFromTheRuleSetNotACopy():
    """A hand-kept list drifts; the previous one had lost four steps."""
    steps = loadSteps(bundledGrs(), "eval")
    assert "canonicalize" in steps
    assert "event_recovery" in steps
    assert "reference" in steps
    assert "aspect_pending" in steps


def test_repeatedStepsArePreserved():
    """The scoping passes genuinely run more than once."""
    steps = loadSteps(bundledGrs(), "eval")
    assert steps.count("localize_core") > 1


def test_unknownStrategyIsReported():
    with pytest.raises(GrsError, match="no `strat nope"):
        loadSteps(bundledGrs(), "nope")


def test_bareNamesAreWrappedButQualifiedOnesAreNot():
    """A qualified step declares its own order; Onf would race its rules."""
    assert stepStrategy("tense") == "Onf(tense)"
    assert stepStrategy("aspect.aspect_sequence") == \
        "aspect.aspect_sequence"


def test_qualifiedStepsSurviveParsing():
    steps = loadSteps(bundledGrs(), "eval")
    assert "aspect.aspect_sequence" in steps
    assert "number.number_sequence" in steps


def _graph(nodes, edges=()):
    return {"nodes": nodes, "edges": list(edges)}


def test_differenceCountsBothDirections():
    before = _graph({"a": {"type": "V"}})
    after = _graph({"a": {"type": "V"}, "b": {"type": "S"}})
    added, removed = difference(before, after)
    assert added == {"nodes": 1}
    assert removed == {}


def test_featureChangeCountsAsBothAddAndRemove():
    """A node whose features changed is a different node to the signature."""
    added, removed = difference(
        _graph({"a": {"type": "V"}}), _graph({"a": {"type": "S"}})
    )
    assert added == {"nodes": 1} and removed == {"nodes": 1}


def test_identicalGraphsShowNoChange():
    graph = _graph({"a": {"type": "V"}}, [{"src": "a", "label": "x", "tar": "a"}])
    assert difference(graph, graph) == ({}, {})


def test_stepSummaryReadsAsCounts():
    step = TraceStep("temp", {}, {"nodes": 2}, {"edges": 1})
    assert step.summary() == "+2 nodes −1 edge"
    assert step.changed


def test_unchangedStepSaysSo():
    assert TraceStep("temp", {}, {}, {}).summary() == "no change"
    assert not TraceStep("temp", {}, {}, {}).changed


def test_withoutClausesStaySeparateBlocks():
    """Merging them would mean "not all together" instead of "none of these"."""
    text = _requestText(
        {
            "request": [
                {"pattern": ["X [type=\"S\"]"]},
                {"without": ["X -> Y"]},
                {"without": ["X -> Z"]},
            ]
        }
    )
    assert text.count("without {") == 2
    assert text.startswith("pattern {")


def test_rulesAreReadOutOfTheDeclarations():
    declarations = {
        "temp": {
            "decls": {
                "a_rule": {"request": [{"pattern": ["X [type=\"S\"]"]}], "commands": []},
                "temp_seq": "Seq(Onf(a_rule))",  # a strategy, not a rule
            }
        }
    }
    rules = rulesOf(declarations, "temp")
    assert [rule.name for rule in rules] == ["a_rule"]
    assert rules[0].qualified == "temp.a_rule"


def test_packagesThatDoNotExistYieldNothing():
    assert rulesOf({}, "temp") == []


def test_navigatorHasOneButtonPerStep():
    steps = [TraceStep("initial", {}, {}, {}), TraceStep("temp", {}, {"nodes": 1}, {})]
    html = renderSteps(steps, "grs")
    assert html.count("snav-btn") >= 2
    assert "SN['grs']" in html


def test_changedStepsAreMarkedInTheNavigator():
    html = renderSteps(
        [TraceStep("a", {}, {}, {}), TraceStep("b", {}, {"nodes": 1}, {})], "grs"
    )
    assert "snav-btn changed" in html


def test_ruleNamesAreEscaped():
    """Rule names come from the rule set, but nothing should inject markup."""
    from weave_amr2yarn.transform.rules import RuleMatches

    step = TraceStep(
        "temp", {}, {}, {},
        rules=[RuleMatches(RuleSpec("temp", "<script>", ""), [])],
    )
    assert "&lt;script&gt;" in renderSteps([step], "grs")


def test_eligibilityIsLabelledNotCalledFiring():
    """GREW reports no firing; the wording must not claim otherwise."""
    from weave_amr2yarn.transform.rules import RuleMatches

    step = TraceStep(
        "temp", {}, {}, {}, rules=[RuleMatches(RuleSpec("temp", "r", ""), [])]
    )
    html = renderSteps([step], "grs")
    assert "eligible" in html
    assert "fired" not in html.lower()