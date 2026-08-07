"""Anchoring through align2anchor, including the LEAMR aligner.

align2anchor owns the anchoring conventions: it adapts an aligner's raw output
into an anchor dictionary, drops anchors the conventions do not license, and
repairs the ones that belong on a different token. This wraps that chain as an
:class:`~weave_amr2yarn.providers.anchors.AnchorProvider`.

Anchoring runs over a whole corpus at once — LEAMR loads three models and a
parser — so the dictionary is produced on first use and then served per
sentence.
"""

from __future__ import annotations

import os
from pathlib import Path

from ..errors import MissingDependency, WeaveError
from ..formats.amr import AmrSentence
from ..formats.anchors import AnchorDictionary

#: Points at a LEAMR checkout. It is roughly 1.3 GB,
#: itself it cannot be shipped and has to be found.
LEAMR_VARIABLE = "WEAVE_LEAMR_DIR"

#: Stages align2anchor applies after the aligner, in order.
STAGES = ("filter", "repair")


def resolveLeamrDir(explicit: str | Path | None = None) -> Path:
    """Locate a LEAMR checkout, or say clearly that there isn't one."""
    candidates = []
    if explicit:
        candidates.append(Path(explicit))
    if os.environ.get(LEAMR_VARIABLE):
        candidates.append(Path(os.environ[LEAMR_VARIABLE]))
    # A research checkout beside the project: .../Internship_2026/anchoring/leamr
    for parent in Path.cwd().resolve().parents:
        candidates.append(parent / "anchoring" / "leamr")

    for candidate in candidates:
        if (candidate / "amr_utils").exists():
            return candidate

    raise MissingDependency(
        "no LEAMR checkout found. It is a large external repository, so it is "
        f"not bundled: pass --leamr-dir, or set {LEAMR_VARIABLE}."
    )


def loadAlign2Anchor():
    """Return the bundled ``align2anchor`` package."""
    try:
        from ..vendor import align2anchor

        return align2anchor
    except ImportError as exc:  # pragma: no cover - a broken install
        raise MissingDependency(
            f"the bundled align2anchor could not be imported: {exc}"
        ) from exc


class Align2AnchorAnchorer:
    """Anchors produced by align2anchor, for a whole corpus at a time.

    ``source`` selects what feeds the convention stages: ``leamr`` runs the
    aligner, ``raw`` reads an aligner's output already on disk.
    """

    def __init__(
        self,
        amrPath: str | Path,
        udPath: str | Path,
        *,
        source: str = "leamr",
        rawPath: str | Path | None = None,
        stages: tuple[str, ...] = STAGES,
        leamrDir: str | Path | None = None,
        spanResolution: str = "first",
    ) -> None:
        if source not in ("leamr", "raw"):
            raise WeaveError(f"unknown anchoring source {source!r}; use leamr or raw")
        if source == "raw" and rawPath is None:
            raise WeaveError("source 'raw' needs rawPath, an anchor dictionary on disk")
        unknown = set(stages) - set(STAGES)
        if unknown:
            raise WeaveError(
                f"unknown stage(s) {sorted(unknown)}; known: {', '.join(STAGES)}"
            )

        self.amrPath = Path(amrPath)
        self.udPath = Path(udPath)
        self.source = source
        self.rawPath = Path(rawPath) if rawPath else None
        self.stages = tuple(stages)
        self.leamrDir = leamrDir
        self.spanResolution = spanResolution

        self._anchors: AnchorDictionary | None = None
        self._audit = None

    def _produceRaw(self):
        """Run the aligner, or read its output."""
        if self.source == "raw":
            from ..vendor.align2anchor.adapters.base import adapterFor

            return adapterFor("precomputed").produce(self.rawPath)

        # LeamrAdapter is not in the adapter registry, and its produce() takes
        # the AMR and UD paths rather than the single source path the base
        # class declares, so it is constructed directly. The checkout is always
        # passed explicitly: the copied package would otherwise guess a path
        # relative to its own location, which no longer means anything.
        from ..vendor.align2anchor.adapters.leamr import LeamrAdapter, LeamrResources

        resources = LeamrResources(resolveLeamrDir(self.leamrDir))
        return LeamrAdapter(resources, spanResolution=self.spanResolution).produce(
            self.amrPath, self.udPath
        )

    def build(self) -> AnchorDictionary:
        """Produce the anchor dictionary, running the aligner if needed."""
        if self._anchors is not None:
            return self._anchors

        loadAlign2Anchor()
        from ..vendor.align2anchor.context import CorpusContext
        from ..vendor.align2anchor.filter import ConventionFilter
        from ..vendor.align2anchor.repair import RepairStage, TenseMovePolicy

        raw = self._produceRaw()
        context = CorpusContext(str(self.amrPath), str(self.udPath))

        current = raw
        if "filter" in self.stages:
            current, self._audit = ConventionFilter().apply(current, context)
        if "repair" in self.stages:
            current = RepairStage(TenseMovePolicy()).apply(current, raw, context)

        # align2anchor has its own AnchorDictionary; convert to ours so the
        # rest of the library sees one type.
        self._anchors = AnchorDictionary(current.data)
        return self._anchors

    def anchorsFor(
        self, sentence: AmrSentence, amr: dict, ud: dict
    ) -> dict[str, str] | None:
        return self.build().sentence(sentence.id)

    def audit(self):
        """Rows explaining what the convention filter removed, if it ran."""
        return self._audit

    def writeAudit(self, path: str | Path) -> bool:
        """Write the filter's decisions as a TSV. False if there are none."""
        if self._audit is None:
            return False
        from ..vendor.align2anchor.filter import writeAudit

        writeAudit(self._audit, str(path))
        return True

    def __contains__(self, sentenceId: object) -> bool:
        return sentenceId in self.build()