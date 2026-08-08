"""Looking inside a rule set.

GREW reports nothing about which rules fired: the backend takes a strategy and
gives back a graph. What it does expose is every rule's own text, through
``GRS.json()``, and a way to search a pattern against a graph. Together those
answer a weaker but still useful question — which rules *could* apply here, and
to which nodes.

That is eligibility, not firing. ``Onf`` runs a package to a fixed point and
its rules feed and bleed each other, so a rule eligible at entry may never fire
because another destroys its match, and one not eligible at entry may fire once
something else has run.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RuleSpec:
    """One rule, as the engine describes itself."""

    package: str
    name: str
    request: str
    commands: tuple[str, ...] = ()

    @property
    def qualified(self) -> str:
        return f"{self.package}.{self.name}"


def _requestText(rule: dict) -> str:
    """Rebuild the request as GREW source.

    A rule's request is a list of clauses, each a single-key mapping of
    ``pattern``/``without``/``global`` to its lines. Several ``without``
    clauses are ordinary and must stay separate blocks — merging them would
    change the meaning from "none of these individually" to "not all together".
    """
    blocks = []
    for clause in rule.get("request", []):
        for kind, lines in clause.items():
            body = "; ".join(lines)
            blocks.append(f"{kind} {{ {body} }}")
    return " ".join(blocks)


def rulesOf(declarations: dict, package: str) -> list[RuleSpec]:
    """Every rule in a package, in declaration order."""
    body = declarations.get(package)
    if not isinstance(body, dict):
        return []

    rules = []
    for name, rule in body.get("decls", {}).items():
        # A package can also declare strategies; those have no request.
        if not isinstance(rule, dict) or "request" not in rule:
            continue
        rules.append(
            RuleSpec(
                package=package,
                name=name,
                request=_requestText(rule),
                commands=tuple(rule.get("commands", [])),
            )
        )
    return rules


@dataclass
class RuleMatches:
    """What one rule could match on one graph."""

    rule: RuleSpec
    matches: list[dict] = field(default_factory=list)
    error: str | None = None

    @property
    def count(self) -> int:
        return len(self.matches)

    @property
    def eligible(self) -> bool:
        return bool(self.matches)

    def summary(self) -> str:
        if self.error:
            return "not searchable"
        if not self.matches:
            return "no match"
        return f"{self.count} match{'es' if self.count > 1 else ''}"


def matchesFor(rule: RuleSpec, graph: dict) -> RuleMatches:
    """Search one rule's request against one graph."""
    from grewpy import Corpus, Graph, Request
    from grewpy.corpus import CorpusDraft

    if not rule.request:
        return RuleMatches(rule, [], "rule has no request")
    try:
        corpus = Corpus(CorpusDraft({"g": Graph(graph)}))
        found = corpus.search(Request(rule.request))
    except Exception as exc:
        # Some requests do not survive the round trip through JSON; that is a
        # gap in this view, not a problem with the rule.
        return RuleMatches(rule, [], str(exc).strip().splitlines()[0] if str(exc).strip() else "search failed")
    return RuleMatches(rule, [dict(item) for item in found])


def eligibilityIn(
    declarations: dict, package: str, graph: dict
) -> list[RuleMatches]:
    """Every rule in a package, with what it matches on *graph*."""
    return [matchesFor(rule, graph) for rule in rulesOf(declarations, package)]
