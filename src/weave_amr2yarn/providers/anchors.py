"""Where the AMR-to-token anchoring comes from."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Protocol, runtime_checkable

from ..formats.amr import AmrSentence
from ..formats.anchors import AnchorDictionary

DEFAULT_THRESHOLD = 0.7

# Concepts that never correspond to a token of their own: structural scaffolding
# and AMR's own operators.
SKIP_CONCEPTS = frozenset(
    {"name", "and", "or", "multi-sentence", "amr-unknown", "truth-value"}
)


@runtime_checkable
class AnchorProvider(Protocol):
    """Supplies ``{variable: token}`` for a sentence, or None if it has none."""

    def anchorsFor(
        self, sentence: AmrSentence, amr: dict, ud: dict
    ) -> dict[str, str] | None: ...


class PrecomputedAnchorer:
    """Anchors looked up in an anchor dictionary, by sentence id."""

    def __init__(self, anchors: AnchorDictionary, *, source: str | None = None) -> None:
        self.anchors = anchors
        self.source = source

    @classmethod
    def fromFile(cls, path: str | Path) -> "PrecomputedAnchorer":
        return cls(AnchorDictionary.fromFile(path), source=str(path))

    def anchorsFor(
        self, sentence: AmrSentence, amr: dict, ud: dict
    ) -> dict[str, str] | None:
        return self.anchors.sentence(sentence.id)

    def __contains__(self, sentenceId: object) -> bool:
        return sentenceId in self.anchors


def _score(amrString: str, lemma: str) -> float:
    """Normalised similarity, case-insensitive, with exact match short-circuited."""
    from Levenshtein import ratio

    left, right = amrString.lower(), lemma.lower()
    return 1.0 if left == right else ratio(left, right)


class LevenshteinAnchorer:
    """Anchors computed by string similarity between concepts and lemmas.

    Every pair scoring at or above its threshold is collected first, then
    assigned highest-score-first, so a weak match cannot claim a token that a
    stronger one needs.

    Named entities go through their literal: ``person -name-> name -[]->
    "John Smith"`` matches the parent against the words of the literal rather
    than against the generic concept ``person``. Those word matches require an
    exact hit, which stops "Sweden" from fuzzy-matching "Swede".
    """

    def __init__(self, threshold: float = DEFAULT_THRESHOLD) -> None:
        self.threshold = threshold

    def _matchSpecs(
        self, node: dict, literal: str | None
    ) -> list[tuple[str, float]]:
        """Strings to match this node by, each with the score it must reach."""
        specs: list[tuple[str, float]] = []
        concept = node.get("concept", "")

        if "pred" in node:
            # Anchored to the end, so only the sense number goes: have-mod-91
            # becomes have-mod, not havemod.
            specs.append((re.sub(r"-\d+$", "", node["pred"]), self.threshold))
        elif concept and not concept.startswith('"'):
            specs.append((concept, self.threshold))

        if literal:
            specs.extend((word, 1.0) for word in literal.split())
        return specs

    def anchorsFor(
        self, sentence: AmrSentence, amr: dict, ud: dict
    ) -> dict[str, str]:
        nodes, edges, tokens = amr["nodes"], amr["edges"], ud["nodes"]

        nameVars = {
            var for var, node in nodes.items() if node.get("concept") == "name"
        }
        # Combined literals hang off a name node by an unlabelled edge.
        nameToLiteral = {
            edge["src"]: nodes[edge["tar"]].get("concept", "")
            for edge in edges
            if edge["src"] in nameVars
            and edge["label"] == {}
            and edge["tar"] in nodes
        }
        literalVars = {
            edge["tar"]
            for edge in edges
            if edge["src"] in nameVars and edge["label"] == {}
        }
        parentToLiteral = {
            edge["src"]: nameToLiteral[edge["tar"]]
            for edge in edges
            if edge["label"] == "name" and edge["tar"] in nameToLiteral
        }
        wikiVars = {edge["tar"] for edge in edges if edge["label"] == "wiki"}

        skip = nameVars | literalVars | wikiVars
        candidates: list[tuple[float, str, str]] = []

        for var, node in nodes.items():
            if var in skip or node.get("concept", "") in SKIP_CONCEPTS:
                continue
            specs = self._matchSpecs(node, parentToLiteral.get(var))
            if not specs:
                continue

            seen: set[str] = set()
            for matchString, minimum in specs:
                for tokenId, token in tokens.items():
                    if tokenId in seen or "lemma" not in token:
                        continue
                    score = _score(matchString, token["lemma"])
                    if score >= minimum:
                        candidates.append((score, var, tokenId))
                        seen.add(tokenId)

        candidates.sort(key=lambda candidate: -candidate[0])

        anchors: dict[str, str] = {}
        claimed: set[str] = set()
        for _, var, tokenId in candidates:
            if var not in anchors and tokenId not in claimed:
                anchors[var] = tokenId
                claimed.add(tokenId)
        return anchors


class ChainedAnchorer:
    """Try each provider in turn, taking the first that answers.

    The usual arrangement: a dictionary for the sentences it covers, computed
    anchors for the rest.
    """

    def __init__(self, *providers: AnchorProvider) -> None:
        self.providers = providers

    def anchorsFor(
        self, sentence: AmrSentence, amr: dict, ud: dict
    ) -> dict[str, str] | None:
        for provider in self.providers:
            anchors = provider.anchorsFor(sentence, amr, ud)
            if anchors is not None:
                return anchors
        return None
