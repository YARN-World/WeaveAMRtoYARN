"""Merging an AMR graph and a UD graph into one anchored graph."""

from __future__ import annotations

# Purely structural AMR intermediates, which carry no content of their own and
# so are never anchored. See applyAnchoring for why this matters.
STRUCTURAL_CONCEPTS = frozenset({"name"})


def applyAnchoring(amr: dict, ud: dict, anchors: dict[str, str]) -> dict:
    """Return the union of *amr* and *ud* plus one ``anchor`` edge per entry.

    ``name`` nodes are skipped. The ``collapse_name_nodes`` rule matches any
    outgoing edge of a name node and deletes the node:

        pattern { X [rel="name", type="E"]; Y [concept="name"]; X->Y; Y->Z }
        commands { del_node Y; add_edge X->Z }

    """
    skip = {
        var
        for var, node in amr["nodes"].items()
        if node.get("concept") in STRUCTURAL_CONCEPTS
    }
    known = set(amr["nodes"])

    edges = list(amr["edges"])
    edges.extend(
        {"src": var, "label": "anchor", "tar": token}
        for var, token in anchors.items()
        if var in known and var not in skip
    )
    edges.extend(ud["edges"])

    return {**amr, "nodes": {**amr["nodes"], **ud["nodes"]}, "edges": edges}