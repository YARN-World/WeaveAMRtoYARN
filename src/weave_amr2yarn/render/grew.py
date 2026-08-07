"""Drawing a GREW graph at any stage of the conversion.

This is the diagnostic view: it shows the AMR, the UD tokens, the anchor edges
between them, and whatever YARN structure the rules have built so far, all at
once. Styling encodes the node ontology so a stage is readable at a glance.
"""

from __future__ import annotations

from .base import BaseRenderer, RenderError, binaryRequirement, packageRequirement
from .svgtools import stripPrologue, uniquifyIds

#: type -> (shape, fill, border, text). Kept as data so the palette is one
#: place to edit rather than scattered through the drawing code.
_STYLES = {
    "S": ("rectangle", "#b0c9e8", "#2a6099", "#1a3d5c"),  # event node
    "F": ("rectangle", "#e8e8e8", "#888888", "#444444"),  # feature slot
    "L": ("rectangle", "#fde8c8", "#c07820", "#7a4800"),  # layer value
    "E": ("diamond", "#d4edda", "#4a8a5a", "#1a5a2a"),  # relation
}
_PREDICATE_STYLE = ("#d8c5f0", "#5b2d99", "#3a0d7a")
_CONCEPT_STYLE = ("#ede5fa", "#9e75c7", "#4a1f80")
_TOKEN_STYLE = ("#f0f0f0", "#aaaaaa", "#555555")


def _tokenIds(nodes: dict) -> set[str]:
    """UD tokens: a positive integer id with a surface form."""
    found = set()
    for nodeId, node in nodes.items():
        identifier = str(node.get("id", ""))
        if identifier.isdigit() and int(identifier) > 0 and "form" in node:
            found.add(nodeId)
    return found


class GrewRenderer(BaseRenderer):
    """A GREW graph as a layered diagram, via graphviz."""

    name = "grew"

    def requirements(self):
        return [
            packageRequirement("graphviz", "pip install graphviz"),
            binaryRequirement("dot", "brew install graphviz"),
        ]

    def render(self, graph: dict, prefix: str = "grew") -> str:
        self._ensureAvailable()
        from graphviz import Digraph

        nodes = graph.get("nodes", {})
        edges = graph.get("edges", [])
        tokens = _tokenIds(nodes)

        dot = Digraph(format="svg")
        dot.attr(rankdir="TB", bgcolor="white", fontname="monospace", splines="true")
        dot.attr("node", fontname="monospace", fontsize="10")
        dot.attr("edge", fontname="monospace", fontsize="9")

        self._drawTokens(dot, nodes, tokens)
        self._drawNodes(dot, nodes, tokens)
        self._drawEdges(dot, nodes, edges, tokens)

        try:
            svg = dot.pipe(format="svg").decode("utf-8")
        except Exception as exc:
            raise RenderError(f"grew: {exc}") from exc
        return uniquifyIds(stripPrologue(svg), prefix)

    @staticmethod
    def _drawTokens(dot, nodes: dict, tokens: set[str]) -> None:
        """Tokens share a rank, so the sentence reads left to right."""
        if not tokens:
            return
        with dot.subgraph(name="cluster_ud") as row:
            row.attr(rank="same", style="invis")
            fill, border, text = _TOKEN_STYLE
            for nodeId in sorted(tokens, key=int):
                node = nodes[nodeId]
                form, upos = node.get("form", nodeId), node.get("upos", "")
                row.node(
                    nodeId,
                    label=f"{form}\\n[{upos}]" if upos else form,
                    shape="rectangle",
                    style="filled",
                    fillcolor=fill,
                    color=border,
                    fontcolor=text,
                )

    @staticmethod
    def _drawNodes(dot, nodes: dict, tokens: set[str]) -> None:
        for nodeId, node in nodes.items():
            if nodeId in tokens or str(node.get("id", "")) == "0":
                continue  # tokens are drawn above; "0" is the UD root sentinel
            nodeType = node.get("type", "")

            if nodeType in _STYLES:
                shape, fill, border, text = _STYLES[nodeType]
                if nodeType == "S":
                    label = node.get("event", nodeId)
                elif nodeType == "F":
                    label = node.get("feat", nodeId)
                elif nodeType == "L":
                    feature, value = node.get("feat", ""), node.get("value", nodeId)
                    label = f"{feature}\\n{value}" if feature else str(value)
                else:
                    label = node.get("rel", nodeId)
                style = "filled,bold" if nodeType == "S" else "filled,rounded"
                dot.node(
                    nodeId,
                    label=str(label),
                    shape=shape,
                    style="filled" if nodeType == "E" else style,
                    fillcolor=fill,
                    color=border,
                    fontcolor=text,
                    fontsize="10" if nodeType == "S" else "9",
                )
            elif nodeType == "V":
                predicate = "pred" in node
                fill, border, text = (
                    _PREDICATE_STYLE if predicate else _CONCEPT_STYLE
                )
                concept = node.get("pred") if predicate else node.get("concept", nodeId)
                dot.node(
                    nodeId,
                    label=f"{nodeId}\\n{concept}",
                    shape="ellipse",
                    style="filled",
                    fillcolor=fill,
                    color=border,
                    fontcolor=text,
                )
            else:
                dot.node(
                    nodeId,
                    label=nodeId,
                    shape="ellipse",
                    style="filled",
                    fillcolor="#fafafa",
                    color="#cccccc",
                )

    @staticmethod
    def _drawEdges(dot, nodes: dict, edges: list, tokens: set[str]) -> None:
        for edge in edges:
            source, target = str(edge["src"]), str(edge["tar"])
            label = edge["label"]
            text = "" if isinstance(label, dict) else str(label)

            # Dependency arcs would swamp the diagram, and the UD root sentinel
            # is not part of the semantics.
            if source in tokens and target in tokens:
                continue
            if str(nodes.get(source, {}).get("id", "")) == "0":
                continue

            if text == "link":
                dot.edge(
                    source, target, label="link",
                    color="#2a6099", penwidth="2.0", fontcolor="#2a6099",
                )
            elif text == "anchor":
                dot.edge(
                    source, target, label="",
                    style="dashed", color="#aaaaaa", arrowsize="0.6",
                )
            elif text == "":
                # The YARN backbone: S -> F -> L -> V, unlabelled by design.
                dot.edge(
                    source, target, label="",
                    color="#cccccc", arrowsize="0.5", penwidth="0.8",
                )
            else:
                dot.edge(
                    source, target, label=text,
                    color="#7b4fa6", fontcolor="#7b4fa6",
                )