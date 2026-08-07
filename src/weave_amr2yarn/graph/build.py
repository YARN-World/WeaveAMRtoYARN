"""Penman AMR to a GREW graph dict."""

from __future__ import annotations

import re

import penman

from ..errors import AmrParseError

# A PropBank roleset ends in a sense number: eat-01, have-mod-91.
_ROLESET = re.compile(r"-\d\d")


def _isPredicate(concept: str, variable: str, aspectSources: set[str]) -> bool:
    return bool(_ROLESET.search(concept)) or variable in aspectSources


def _literalId(source: str, role: str, target: str) -> str:
    return f"{source}_{role}_{target}"


def penmanToGrew(penmanString: str, *, sentenceId: str | None = None) -> dict:
    """Decode a Penman AMR into ``{"meta", "nodes", "edges"}``.
    Inverse ``-of`` roles are already normalised by penman.
    """
    try:
        graph = penman.decode(penmanString)
    except Exception as exc:
        raise AmrParseError(str(exc), sentenceId=sentenceId) from exc

    aspectSources = {
        attribute.source
        for attribute in graph.attributes()
        if attribute.role == ":aspect"
    }

    nodes: dict[str, dict] = {}
    for instance in graph.instances():
        key = (
            "pred"
            if _isPredicate(instance.target, instance.source, aspectSources)
            else "concept"
        )
        nodes[instance.source] = {
            key: instance.target,
            "type": "V",
            "var": instance.source,
        }

    # Mark the Penman top explicitly. Detecting it later as "the node with no
    # incoming edge" would fail on reentrancy, where a root can acquire one.
    # The event_recovery package uses this as its last-chance host.
    if graph.top in nodes:
        nodes[graph.top]["focus"] = "yes"

    edges = [
        {"src": edge.source, "label": edge.role[1:], "tar": edge.target}
        for edge in graph.edges()
    ]

    for attribute in graph.attributes():
        role = attribute.role[1:]
        value = attribute.target.replace('"', "")
        identifier = _literalId(attribute.source, role, value)
        nodes[identifier] = {"concept": value, "type": "V", "var": identifier}
        edges.append({"src": attribute.source, "label": role, "tar": identifier})

    return {"meta": dict(graph.metadata), "nodes": nodes, "edges": edges}