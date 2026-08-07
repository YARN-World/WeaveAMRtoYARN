"""The repair stage — relocations and additions, off by default.

Layered after the filter for callers who want it: takes the engine's
proposals and applies only those an explicit policy accepts. The
shipped policy set is empty; TenseMovePolicy reproduces the evaluated
relocation rule (a predicate may move onto the VERB/AUX token that
carries tense) for ablations and for weaker alignment sources.
"""

from __future__ import annotations

from .context import CorpusContext
from .format import AnchorDictionary
from .licenses import ConventionJudge, Proposal


class MovePolicy:
    """Decides whether a proposal may be applied. Base: accept nothing."""

    def accepts(self, proposal: Proposal, currentValue: str, sentence) -> bool:
        return False


class TenseMovePolicy(MovePolicy):
    """A predicate may move onto a tense-bearing VERB/AUX token it did
    not already occupy — the one relocation the ablation kept."""

    tenseBearing = {"VERB", "AUX"}

    def accepts(self, proposal: Proposal, currentValue: str, sentence) -> bool:
        if proposal.value == currentValue:
            return False
        if not proposal.concept or not proposal.concept[-1].isdigit():
            return False
        newToken = sentence.toks.get(proposal.value)
        oldToken = sentence.toks.get(currentValue)
        return (newToken is not None
                and newToken.upos in self.tenseBearing
                and (oldToken is None
                     or oldToken.upos not in self.tenseBearing))


class RepairStage:

    def __init__(self, policy: MovePolicy, judge: ConventionJudge | None = None):
        self.policy = policy
        self.judge = judge or ConventionJudge()

    def apply(self, filtered: AnchorDictionary, raw: AnchorDictionary,
              context: CorpusContext) -> AnchorDictionary:
        repaired = AnchorDictionary()
        for sentenceId in filtered.sentenceIds():
            anchors = dict(filtered.sentence(sentenceId))
            sentence = context.sentenceContext(sentenceId)
            if sentence is not None:
                _, proposals = self.judge.judgeSentence(
                    raw.sentence(sentenceId), sentence)
                for proposal in proposals:
                    current = anchors.get(proposal.variable)
                    if current is None:
                        continue  # filter said bare; repair does not resurrect
                    if self.policy.accepts(proposal, current, sentence):
                        anchors[proposal.variable] = proposal.value
            repaired.setSentence(sentenceId, anchors)
        return repaired