"""Creating S nodes (situations) for anchored predicates."""

from __future__ import annotations

# Incoming UD relations that mark a VERB/AUX as attributive rather than
# predicative. A participial modifier ("the leading tenors") heads no
# predication of its own, so it gets no situation.
ATTRIBUTIVE_RELATIONS = frozenset({"amod"})


def predicativeVerbs(nodes: dict, edges: list[dict]) -> set[str]:
    """VERB/AUX nodes that head a predication."""
    # Only string labels can be dependency relations. Edges minted earlier
    # carry a mapping instead (``{}``, or grewpy's FsEdge once a graph has
    # been through the engine), and are never attributive.
    incoming: dict[str, set[str]] = {}
    for edge in edges:
        if isinstance(edge["label"], str):
            incoming.setdefault(edge["tar"], set()).add(edge["label"])
    return {
        var
        for var, node in nodes.items()
        if node.get("upos") in ("VERB", "AUX")
        and not incoming.get(var, set()) & ATTRIBUTIVE_RELATIONS
    }


def splitEvents(graph: dict) -> dict:
    nodes, edges = graph["nodes"], graph["edges"]

    predicates = [
        var
        for var, node in nodes.items()
        if node.get("pred") and node.get("pred") != "cause-01"
    ]
    verbal = predicativeVerbs(nodes, edges)
    anchors = {edge["src"]: edge["tar"] for edge in edges if edge["label"] == "anchor"}

    events = [var for var in predicates if anchors.get(var) in verbal]

    for position, event in enumerate(events, 1):
        name = f"S{position}"
        nodes[name] = {
            "event": name,
            "type": "S",
            # Provenance: which mechanism made this S, and for which node.
            # canonical.renameSNodes orders by `core`, so it must be stamped.
            "src": "split",
            "core": nodes[event].get("var", event),
        }
        edges.append({"src": name, "label": "link", "tar": event})

    return graph