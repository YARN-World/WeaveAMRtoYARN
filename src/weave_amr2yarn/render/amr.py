"""Drawing a Penman AMR."""

from __future__ import annotations

from .base import BaseRenderer, RenderError, binaryRequirement, packageRequirement
from .svgtools import stripPrologue, uniquifyIds


class AmrRenderer(BaseRenderer):
    """AMR as a graph, via yarn_utils.

    yarn_utils already ships this, so no separate drawing code is needed; it
    lays the graph out with graphviz, which is why ``dot`` has to be on PATH.
    """

    name = "amr"

    def requirements(self):
        return [
            packageRequirement("yarn_utils"),
            packageRequirement("graphviz", "pip install graphviz"),
            binaryRequirement("dot", "brew install graphviz"),
        ]

    def render(self, graph: str, prefix: str = "amr") -> str:
        self._ensureAvailable()
        try:
            from yarn_utils.penman2svg import penman2svg

            svg = penman2svg(graph)
        except Exception as exc:
            raise RenderError(f"amr: {exc}") from exc
        if not svg:
            raise RenderError("amr: nothing to draw")
        return uniquifyIds(stripPrologue(svg), prefix)