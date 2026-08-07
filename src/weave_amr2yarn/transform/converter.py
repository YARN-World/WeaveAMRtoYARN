"""Conversion, for one graph and for a corpus."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

from ..config import ConversionConfig
from ..errors import GrewBackendError, WeaveError
from ..formats.amr import AmrCorpus, AmrSentence
from ..formats.yarn import toYarn
from ..graph import (
    applyAnchoring,
    canonicalize,
    dereify,
    normalizeGraph,
    penmanToGrew,
    splitEvents,
)
from ..providers.anchors import AnchorProvider, LevenshteinAnchorer
from ..providers.ud import StanzaUd, UdProvider
from .session import GrsSession


class Converter:
    """Turns one AMR into a YARN graph.

    Holds the loaded rule set, so build it once and reuse it::

        converter = Converter()
        yarn = converter.convert("(r / run-01 :ARG0 (d / dog))")
    """

    def __init__(
        self,
        config: ConversionConfig | None = None,
        *,
        ud: UdProvider | None = None,
        anchors: AnchorProvider | None = None,
    ) -> None:
        self.config = config or ConversionConfig()
        self.session = GrsSession(self.config.grsPath, self.config.strategy)
        self.ud = ud if ud is not None else StanzaUd(sentenceKey=self.config.sentenceKey)
        self.anchors = anchors if anchors is not None else LevenshteinAnchorer()

    @staticmethod
    def _asSentence(source: str | AmrSentence) -> AmrSentence:
        if isinstance(source, AmrSentence):
            return source
        return AmrCorpus.fromText(source)[0]

    def anchored(self, source: str | AmrSentence) -> dict:
        """The merged AMR + UD graph, before rewriting.

        Exposed because it is the useful thing to look at when anchoring is
        suspect: it shows what the rules will actually see.
        """
        sentence = self._asSentence(source)

        text = sentence.penman
        if self.config.penmanDereify:
            text = dereify(text, sentenceId=sentence.id)

        amr = normalizeGraph(penmanToGrew(text, sentenceId=sentence.id))

        udGraph = self.ud.graphFor(sentence)
        if udGraph is None:
            raise WeaveError(
                f"[{sentence.id}] no UD analysis available. Supply a CoNLL-U file "
                f"covering this sentence, or a parser that can read its "
                f"::{self.config.sentenceKey} metadata."
            )

        anchors = self.anchors.anchorsFor(sentence, amr, udGraph) or {}
        return splitEvents(applyAnchoring(amr, udGraph, anchors))

    def toGrew(self, source: str | AmrSentence) -> dict:
        """Rewrite, returning the GREW graph."""
        rewritten = self.session.apply(
            self.anchored(source), timeoutSeconds=self.config.timeoutSeconds
        )
        return canonicalize(rewritten)

    def convert(self, source: str | AmrSentence) -> dict:
        """Rewrite, returning YARN JSON."""
        return toYarn(self.toGrew(source))


@dataclass
class BatchReport:
    """What a batch run did."""

    converted: int = 0
    failures: list[tuple[str, str]] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    @property
    def failed(self) -> int:
        return len(self.failures)

    def summary(self) -> str:
        parts = [f"{self.converted} converted"]
        if self.failures:
            parts.append(f"{self.failed} failed")
        if self.skipped:
            parts.append(f"{len(self.skipped)} skipped")
        return ", ".join(parts)


def _outputPath(root: Path, sentenceId: str, layout: str) -> Path:
    """Where one sentence's output goes.

    ``grouped`` puts ``fracas-001.premise_0`` at ``fracas-001/premise_0.json``,
    generalising the corpus-specific rule the original hard-coded for FraCaS.
    """
    if layout == "grouped" and "." in sentenceId:
        prefix, part = sentenceId.split(".", 1)
        return root / prefix / f"{part}.json"
    return root / f"{sentenceId}.json"


class BatchConverter:
    """Runs a :class:`Converter` over a corpus and writes the results."""

    def __init__(self, converter: Converter) -> None:
        self.converter = converter

    def run(
        self,
        corpus: Iterable[AmrSentence],
        outDir: str | Path,
        *,
        layout: str = "flat",
        grewOnly: bool = False,
        onProgress: Callable[[AmrSentence], None] | None = None,
    ) -> BatchReport:
        outDir = Path(outDir)
        grewDir, yarnDir = outDir / "grew", outDir / "yarn"
        report = BatchReport()

        for sentence in corpus:
            if onProgress:
                onProgress(sentence)
            try:
                grew = self.converter.toGrew(sentence)
                self._write(_outputPath(grewDir, sentence.id, layout), grew)
                if not grewOnly:
                    self._write(
                        _outputPath(yarnDir, sentence.id, layout), toYarn(grew)
                    )
                report.converted += 1
            except GrewBackendError as exc:
                # The engine is a separate process; losing it costs this graph
                # but the run can go on once it is back.
                report.failures.append((sentence.id, str(exc)))
                try:
                    self.converter.session.restart()
                except WeaveError:
                    raise
            except Exception as exc:
                report.failures.append((sentence.id, f"{type(exc).__name__}: {exc}"))

        return report

    @staticmethod
    def _write(path: Path, data: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )