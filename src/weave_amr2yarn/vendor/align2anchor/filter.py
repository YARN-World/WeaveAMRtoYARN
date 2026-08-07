"""The convention filter — the shipped postprocessing configuration.

Removal-only by construction: a variable either keeps the anchor the
aligner gave it, or loses it with a named reason. Values are never
changed and never added here; that is the repair stage's business,
and it is off by default.
"""

from __future__ import annotations

from dataclasses import dataclass

from .context import CorpusContext
from .format import AnchorDictionary
from .licenses import ConventionJudge


@dataclass
class AuditRow:
    sentenceId: str
    variable: str
    concept: str
    value: str
    kept: bool
    license: str
    reason: str


class ConventionFilter:

    def __init__(self, judge: ConventionJudge | None = None):
        self.judge = judge or ConventionJudge()

    def apply(self, raw: AnchorDictionary, context: CorpusContext
              ) -> tuple[AnchorDictionary, list[AuditRow]]:
        filtered = AnchorDictionary()
        audit: list[AuditRow] = []

        for sentenceId in raw.sentenceIds():
            anchors = raw.sentence(sentenceId)
            sentence = context.sentenceContext(sentenceId)

            if sentence is None:
                # no evidence to judge on — pass through, never guess
                filtered.setSentence(sentenceId, dict(anchors))
                continue

            verdicts, _ = self.judge.judgeSentence(anchors, sentence)
            keep = {v.variable: v for v in verdicts if v.keep}
            kept = {variable: str(value)
                    for variable, value in anchors.items()
                    if variable in keep}
            filtered.setSentence(sentenceId, kept)

            for verdict in verdicts:
                audit.append(AuditRow(
                    sentenceId, verdict.variable, verdict.concept,
                    str(anchors.get(verdict.variable, "")),
                    verdict.keep, verdict.license, verdict.reason))
        return filtered, audit


def writeAudit(audit: list[AuditRow], path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("sent_id\tvar\tconcept\tvalue\tkept\tlicense\treason\n")
        for row in audit:
            fh.write(f"{row.sentenceId}\t{row.variable}\t{row.concept}\t"
                     f"{row.value}\t{'yes' if row.kept else 'no'}\t"
                     f"{row.license}\t{row.reason}\n")