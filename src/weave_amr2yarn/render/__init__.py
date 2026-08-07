"""Drawing graphs as SVG.

One renderer per kind of graph, each declaring what it needs so a caller can
ask before it draws:

    from weave_amr2yarn.render import rendererFor

    renderer = rendererFor("yarn")
    if renderer.available():
        svg = renderer.render(yarnGraph, prefix="s1")

Renderers raise :class:`RenderError`; they never return markup describing their
own failure, so the caller decides how a missing binary should look.
"""

from __future__ import annotations

from .amr import AmrRenderer
from .base import BaseRenderer, RenderError, Renderer, Requirement
from .grew import GrewRenderer
from .svgtools import stripPrologue, toDataUri, uniquifyIds
from .ud import UdRenderer
from .yarn import YarnRenderer

_REGISTRY = {
    "amr": AmrRenderer,
    "ud": UdRenderer,
    "grew": GrewRenderer,
    "yarn": YarnRenderer,
}


def rendererNames() -> list[str]:
    return list(_REGISTRY)


def rendererFor(name: str) -> BaseRenderer:
    """Return a renderer by name."""
    if name not in _REGISTRY:
        raise RenderError(
            f"no renderer named {name!r}; known: {', '.join(_REGISTRY)}"
        )
    return _REGISTRY[name]()


def availability() -> dict[str, bool]:
    """What can be drawn here. Used by ``weave doctor`` and by the UI."""
    return {name: rendererFor(name).available() for name in _REGISTRY}


__all__ = [
    "AmrRenderer",
    "BaseRenderer",
    "GrewRenderer",
    "RenderError",
    "Renderer",
    "Requirement",
    "UdRenderer",
    "YarnRenderer",
    "availability",
    "rendererFor",
    "rendererNames",
    "stripPrologue",
    "toDataUri",
    "uniquifyIds",
]