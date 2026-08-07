"""Scoring anchor dictionaries against gold, at the strict triple level.

A predicted (sentence, variable, token) triple is correct only if gold
contains exactly it. Only sentences present in both dictionaries are
scored, so partial corpora compare fairly.
"""

from __future__ import annotations

from .format import AnchorDictionary, ScoreReport


class Evaluator:

    def __init__(self, gold: AnchorDictionary):
        self.gold = gold

    def score(self, prediction: AnchorDictionary) -> ScoreReport:
        common = set(prediction.sentenceIds()) & set(self.gold.sentenceIds())
        predicted = {t for t in prediction.triples() if t[0] in common}
        expected = {t for t in self.gold.triples() if t[0] in common}
        return ScoreReport(
            truePositives=len(predicted & expected),
            falsePositives=len(predicted - expected),
            falseNegatives=len(expected - predicted),
            sentencesScored=len(common))

    def table(self, predictions: dict[str, AnchorDictionary]) -> str:
        header = (f"{'Method':<24}{'P':>8}{'R':>8}{'F1':>8}"
                  f"{'TP':>8}{'FP':>6}{'FN':>6}{'Sents':>8}")
        rows = [header, "-" * len(header)]
        for name, prediction in predictions.items():
            rows.append(self.score(prediction).asRow(name))
        return "\n".join(rows)