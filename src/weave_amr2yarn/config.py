"""Conversion settings, as one value rather than five loose arguments."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .resources import bundledGrs


@dataclass(frozen=True)
class ConversionConfig:
    """What to run, and how.

    Defaults reproduce the settings the project's own runs use.
    """

    #: GRS entry file. Defaults to the copy bundled with the package, which is
    #: what makes the library independent of the working directory.
    grsPath: Path = field(default_factory=bundledGrs)

    #: Strategy declared in the GRS. ``eval`` differs from ``main`` only by
    #: running ``finalize_eval`` first, which strips the scoring-only features.
    strategy: str = "eval"

    #: Metadata key holding the surface sentence. Corpora differ: ``snt`` is
    #: usual, some releases use ``text``.
    sentenceKey: str = "snt"

    #: Per-graph budget in seconds; 0 disables. Guards against the rewriter
    #: hanging on a pathological graph and stalling a whole batch.
    timeoutSeconds: int = 30

    #: Run the Penman-level ``-91`` dereification before rewriting. The GRS has
    #: a ``dereify`` package of its own, but it does not cover the root-level
    #: and role-91 cases this pass handles. Turning it off changes output.
    penmanDereify: bool = False

    #: Record the anchors used and the time of conversion in each graph's
    #: metadata. Off by default because it changes the output, which would
    #: otherwise no longer compare byte-for-byte against earlier runs.
    stampMetadata: bool = False

    def replace(self, **changes) -> "ConversionConfig":
        from dataclasses import replace

        return replace(self, **changes)