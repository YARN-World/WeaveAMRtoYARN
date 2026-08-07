"""What every renderer is.

Renderers return an SVG string or raise. They never return markup describing
their own failure: whether a missing binary should read as a grey note or a red
banner is the caller's decision, and swallowing the difference between "not
installed" and "crashed" makes both harder to diagnose.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from ..errors import WeaveError


class RenderError(WeaveError):
    """A graph could not be drawn."""


@dataclass(frozen=True)
class Requirement:
    """Something a renderer needs, and whether it is here."""

    name: str
    kind: str  # "binary" or "package"
    present: bool
    hint: str = ""


def binaryRequirement(name: str, hint: str = "") -> Requirement:
    return Requirement(name, "binary", shutil.which(name) is not None, hint)


def packageRequirement(name: str, hint: str = "") -> Requirement:
    try:
        __import__(name)
        present = True
    except Exception:
        present = False
    return Requirement(name, "package", present, hint)


@runtime_checkable
class Renderer(Protocol):
    """Draws one kind of graph."""

    #: What this renderer draws, for messages and the doctor.
    name: str

    def render(self, graph, prefix: str = "g") -> str:
        """Return an SVG. ``prefix`` keeps ids unique among embedded SVGs."""
        ...

    def requirements(self) -> list[Requirement]:
        """Everything this renderer needs, present or not."""
        ...

    def available(self) -> bool:
        """Whether it can draw anything right now."""
        ...


class BaseRenderer:
    """Shared availability logic; subclasses declare requirements and draw."""

    name = "base"

    def requirements(self) -> list[Requirement]:
        return []

    def available(self) -> bool:
        return all(item.present for item in self.requirements())

    def missing(self) -> list[Requirement]:
        return [item for item in self.requirements() if not item.present]

    def _ensureAvailable(self) -> None:
        missing = self.missing()
        if missing:
            details = "; ".join(
                f"{item.name} ({item.kind})" + (f" — {item.hint}" if item.hint else "")
                for item in missing
            )
            raise RenderError(f"{self.name}: missing {details}")
