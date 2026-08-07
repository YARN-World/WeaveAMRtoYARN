"""AMR normalisations
Both build or drop a cluster of nodes at once — string joining and subtree
removal — which is natural here and clumsy in GREW.
"""

from __future__ import annotations

import copy


def _label(edge: dict) -> str:
    """Edge labels are strings here, but become dicts further downstream."""
    label = edge["label"]
    return label if isinstance(label, str) else ""


def removeWiki(graph: dict) -> dict:
    """Drop every ``:wiki`` edge and the literal it points at.

    Wikification is metadata: no token realises it, so it only adds nodes for
    anchoring and later rules to trip over.
    """
    result = copy.deepcopy(graph)
    targets = {edge["tar"] for edge in result["edges"] if _label(edge) == "wiki"}
    result["edges"] = [edge for edge in result["edges"] if _label(edge) != "wiki"]
    result["nodes"] = {
        var: node for var, node in result["nodes"].items() if var not in targets
    }
    return result


def combineNameLiterals(graph: dict) -> dict:
    """Merge a ``name`` node's ordered ``:opN`` literals into one node.

    "Queen" "Elizabeth" "II" becomes "Queen Elizabeth II". The combined node
    replaces the individual words and the name node keeps a single unlabelled
    edge to it. A ``name`` node with no ``:opN`` children is left alone.
    """
    result = copy.deepcopy(graph)

    nameVars = [
        var for var, node in result["nodes"].items() if node.get("concept") == "name"
    ]
    for nameVar in nameVars:
        opEdges = sorted(
            (
                edge
                for edge in result["edges"]
                if edge["src"] == nameVar and _label(edge).startswith("op")
            ),
            key=lambda edge: int(_label(edge)[2:]),
        )
        if not opEdges:
            continue

        literalVars = [edge["tar"] for edge in opEdges]
        combined = " ".join(
            result["nodes"][var]["concept"] for var in literalVars
        )

        result["nodes"] = {
            var: node
            for var, node in result["nodes"].items()
            if var not in literalVars
        }
        result["edges"] = [edge for edge in result["edges"] if edge not in opEdges]

        # Deliberately no "var" key: `collapse_name_nodes` collapses this
        # node later, and `remove_labelled_edges` (which requires B[var]) must
        # not match the unlabelled name->combined edge before then.
        combinedVar = f"{nameVar}_{combined}"
        result["nodes"][combinedVar] = {"concept": combined, "type": "V"}
        result["edges"].append({"src": nameVar, "label": {}, "tar": combinedVar})

    return result


def normalizeGraph(graph: dict) -> dict:
    """Apply both passes. Order is fixed: wiki literals must be gone before
    names are combined, so they can never be swept into a combined string."""
    return combineNameLiterals(removeWiki(graph))