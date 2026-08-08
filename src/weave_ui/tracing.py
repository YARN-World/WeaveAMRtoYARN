"""Running the rule set one step at a time.

The conversion normally applies one strategy and hands back the finished graph.
To see *why* a graph came out as it did you need the intermediate states, which
means driving the packages individually.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from weave_amr2yarn.errors import GrsError

#: A step is a package name (wrapped in Onf) or a ready strategy expression.
_ONF = re.compile(r"Onf\s*\(\s*([\w.]+)\s*\)$")


def loadSteps(grsPath: str | Path, strategy: str = "eval") -> list[str]:
    """Read the step order out of the rule set itself.

    Parsed rather than copied, because a hand-kept list drifts: the version
    this replaces had silently lost four steps, among them the repeated
    scoping passes, which are easy to mistake for a duplicate.
    """
    text = Path(grsPath).read_text(encoding="utf-8")
    found = re.search(
        rf"strat\s+{re.escape(strategy)}\s*\{{\s*Seq\s*\((.*?)\)\s*\}}", text, re.S
    )
    if not found:
        raise GrsError(f"no `strat {strategy} {{ Seq(...) }}` in {grsPath}")

    body = "\n".join(line.split("%")[0] for line in found.group(1).splitlines())
    steps = []
    for item in (piece.strip() for piece in body.split(",")):
        if not item:
            continue
        matched = _ONF.match(item)
        steps.append(matched.group(1) if matched else item)
    return steps


def stepStrategy(step: str) -> str:
    """The strategy expression for one step.

    A bare package name is wrapped in ``Onf``. A qualified one passes through
    untouched: a package names its own strategy when its rules overlap and the
    order between them is a deliberate priority, and running such a package to
    a fixed point instead would let them race.
    """
    return step if "." in step else f"Onf({step})"


@dataclass
class TraceStep:
    """One step's name, the graph after it, and what it changed."""

    name: str
    graph: dict
    added: dict[str, int]
    removed: dict[str, int]
    #: Rules of this package and what they matched on the graph going in.
    #: Eligibility, not firing — see weave_amr2yarn.transform.rules.
    rules: list = field(default_factory=list)
    #: Filled in by the caller that draws the trace.
    svg: str = ""
    #: Set when the step itself failed, so the trace shows a gap rather than
    #: silently carrying the previous graph forward.
    error: str | None = None

    @property
    def changed(self) -> bool:
        return bool(self.added or self.removed)

    def summary(self) -> str:
        parts = []
        for count, label, sign in (
            (self.added.get("nodes", 0), "node", "+"),
            (self.removed.get("nodes", 0), "node", "−"),
            (self.added.get("edges", 0), "edge", "+"),
            (self.removed.get("edges", 0), "edge", "−"),
        ):
            if count:
                parts.append(f"{sign}{count} {label}{'s' if count > 1 else ''}")
        return " ".join(parts) if parts else "no change"


def _shortError(exc: Exception) -> str:
    """GREW errors arrive as a JSON blob; the message is the useful part."""
    text = str(exc).strip()
    try:
        import json

        start = text.index("{")
        return json.loads(text[start : text.rindex("}") + 1]).get("message", text)
    except Exception:
        return text.splitlines()[0] if text else exc.__class__.__name__


def _signature(graph: dict):
    nodes = {
        (nodeId, tuple(sorted((k, str(v)) for k, v in node.items())))
        for nodeId, node in graph.get("nodes", {}).items()
    }
    edges = {
        (str(edge["src"]), str(edge["label"]), str(edge["tar"]))
        for edge in graph.get("edges", [])
    }
    return nodes, edges


def difference(before: dict, after: dict) -> tuple[dict[str, int], dict[str, int]]:
    """How many nodes and edges appeared and disappeared."""
    beforeNodes, beforeEdges = _signature(before)
    afterNodes, afterEdges = _signature(after)
    added = {
        "nodes": len(afterNodes - beforeNodes),
        "edges": len(afterEdges - beforeEdges),
    }
    removed = {
        "nodes": len(beforeNodes - afterNodes),
        "edges": len(beforeEdges - afterEdges),
    }
    return {k: v for k, v in added.items() if v}, {
        k: v for k, v in removed.items() if v
    }


class StepTracer:
    """Applies the rule set step by step, keeping each intermediate graph."""

    def __init__(self, session, steps: list[str]) -> None:
        self.session = session
        self.steps = steps

    def trace(self, graph: dict, withRules: bool = False) -> list[TraceStep]:
        """Return the initial graph and the state after every step.

        Each step is applied to the previous result. The version this replaces
        re-ran the whole prefix from the start for every step — `Seq(s1..sn)`
        for n = 1, 2, 3, … — which is quadratic and, since Seq is plain
        sequential composition, produced exactly the same states.

        With *withRules*, each step also carries what its rules matched on the
        graph going in. That costs a search per rule, so it is opt-in.
        """
        from grewpy import Graph

        from weave_amr2yarn.transform.rules import eligibilityIn

        declarations = self.session.declarations() if withRules else {}
        start = Graph(graph)

        trace = [TraceStep("initial", graph, {}, {})]
        current = graph

        for position, name in enumerate(self.steps, 1):
            # Eligibility is judged on the graph going in: once the step has
            # run, the matches it fired on are gone.
            rules = []
            if withRules:
                rules = eligibilityIn(declarations, name.split(".")[0], current)

            after, error = self._prefix(start, position)
            added, removed = difference(current, after)
            trace.append(TraceStep(name, after, added, removed, rules, error=error))
            current = after

        return trace

    def _prefix(self, start, count: int):
        """Run the first *count* steps, always from the original graph.

        Feeding each step's output back in would be cheaper — one run per step
        instead of one per prefix — but it does not work. The rules can leave
        an intermediate graph holding the same edge twice; the engine carries
        that happily inside a single run, while rebuilding a graph from JSON
        rejects it outright. Restarting from a graph that was valid on entry
        keeps every intermediate inside the engine, so the trace agrees with a
        real run instead of dying part-way through it.
        """
        strategy = "Seq(" + ", ".join(
            stepStrategy(step) for step in self.steps[:count]
        ) + ")"
        try:
            result = self.session.grs.run(start, strat=strategy)
        except Exception as exc:
            return start.json_data(), _shortError(exc)
        chosen = result[0] if result else start
        return chosen.json_data(), None
