"""Drawing a UD dependency tree."""

from __future__ import annotations

from .base import BaseRenderer, RenderError, packageRequirement
from .svgtools import stripPrologue, uniquifyIds


class UdRenderer(BaseRenderer):
    """UD as a dependency tree, drawn by grewpy itself.

    This one costs nothing extra: the engine that runs the rules can already
    draw its own graphs.
    """

    name = "ud"

    def requirements(self):
        return [packageRequirement("grewpy")]

    def render(self, graph: dict, prefix: str = "ud") -> str:
        self._ensureAvailable()
        try:
            from grewpy import Graph

            svg = Graph(graph).to_svg()
        except Exception as exc:
            raise RenderError(f"ud: {exc}") from exc
        if not svg:
            raise RenderError("ud: nothing to draw")
        return uniquifyIds(stripPrologue(svg), prefix)