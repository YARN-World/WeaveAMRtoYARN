"""The GREW-graph to YARN-JSON boundary."""

from __future__ import annotations

from ..errors import MissingDependency

# Node types whose outgoing edges graph2yarn reads as "main out" edges.
_MAIN_OUT_TYPES = ("L", "H", "E", "C")


def addMainOut(graph: dict) -> dict:
    """Tag edges the way ``graph2yarn`` expects, returning a new graph.

    The rewriter emits edge labels as plain strings or as ``{}``; graph2yarn
    instead keys on ``label["main_out"] == "Yes"`` to tell an edge leaving an
    L/H/E/C node from one arriving at it.

    ``degree_src`` is the exception. It records that a node's source is the
    L-node, and must stay untagged so graph2yarn files it under
    ``edge_mapping_from[H]`` rather than ``edge_mapping_toward[L]``.
    """
    nodeTypes = {
        nodeId: node.get("type", "") for nodeId, node in graph["nodes"].items()
    }

    edges = []
    for edge in graph["edges"]:
        original = edge["label"]
        label = original if isinstance(original, dict) else {}

        if nodeTypes.get(edge["src"], "") in _MAIN_OUT_TYPES and not label.get(
            "main_out"
        ):
            if original == "degree_src":
                label = {}
            else:
                label = {"main_out": "Yes"}
            edges.append({"src": edge["src"], "label": label, "tar": edge["tar"]})
        else:
            edges.append({**edge, "label": label})

    return {**graph, "edges": edges}


def toYarn(graph: dict) -> dict:
    """Convert a rewritten GREW graph to YARN JSON."""
    try:
        from yarn_utils.yarn2graph import graph2yarn
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise MissingDependency(
            "yarn_utils is required to produce YARN output. Install it with:\n"
            "  pip install 'yarn_utils @ git+https://gitlab.inria.fr/semagramme/"
            "yarn/yarn_utils@fb6f6f88134f89e45866ff2eacd4880ec1f2c764"
            "#subdirectory=utils'"
        ) from exc

    return graph2yarn(addMainOut(graph))