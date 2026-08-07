"""The interchange format every stage of align2anchor shares.

An anchor dictionary maps, per sentence, AMR variables to UD token ids:

    {"fracas-015.premise_0": {"p2": "7", "t": "4", "c2": "10"}, ...}

This module is the only place that reads, writes or validates that
format. Everything downstream — filter, repair, evaluation — works with
AnchorDictionary objects and never touches raw JSON.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


class AnchorDictionary:
    """All anchors of a corpus: {sentenceId: {variable: tokenId}}."""

    def __init__(self, data: dict[str, dict[str, str]] | None = None):
        self.data = data or {}


    @classmethod
    def fromFile(cls, path: str | Path) -> "AnchorDictionary":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        clean = {sid: {var: value for var, value in anchors.items()}
                 for sid, anchors in raw.items()}
        return cls(clean)

    def toFile(self, path: str | Path, indent: int = 2) -> None:
        Path(path).write_text(
            json.dumps(self.data, indent=indent, ensure_ascii=False),
            encoding="utf-8")


    def sentence(self, sentenceId: str) -> dict[str, str]:
        return self.data.get(sentenceId, {})

    def sentenceIds(self) -> list[str]:
        return list(self.data)

    def setSentence(self, sentenceId: str, anchors: dict[str, str]) -> None:
        self.data[sentenceId] = anchors


    def anchorCount(self) -> int:
        return sum(len(a) for a in self.data.values())

    def triples(self) -> set[tuple[str, str, str]]:
        """Strict (sentence, variable, token) triples — the scoring unit."""
        return {(sid, var, str(value))
                for sid, anchors in self.data.items()
                for var, value in anchors.items()}

    def sameAs(self, other: "AnchorDictionary") -> bool:
        """Value equality on the triple level (key order irrelevant)."""
        return self.triples() == other.triples()


@dataclass
class ScoreReport:
    """Precision / recall / F1 of a prediction against gold."""

    truePositives: int
    falsePositives: int
    falseNegatives: int
    sentencesScored: int

    @property
    def precision(self) -> float:
        denominator = self.truePositives + self.falsePositives
        return self.truePositives / denominator if denominator else 0.0

    @property
    def recall(self) -> float:
        denominator = self.truePositives + self.falseNegatives
        return self.truePositives / denominator if denominator else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0

    def asRow(self, name: str) -> str:
        return (f"{name:<24}{self.precision:>8.3f}{self.recall:>8.3f}"
                f"{self.f1:>8.3f}{self.truePositives:>8d}"
                f"{self.falsePositives:>6d}{self.falseNegatives:>6d}"
                f"{self.sentencesScored:>8d}")
