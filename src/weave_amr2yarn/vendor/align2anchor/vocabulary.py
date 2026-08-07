"""The convention's word classes and string similarity helpers.

Every set names a class of nodes or tokens the licenses reason about;
each cites its evidence base in the legacy notes (postprocessing/NOTES.md).
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

structural = frozenset({
    "name", "and", "or", "multi-sentence", "amr-unknown", "truth-value",
    "amr-choice",
})

discourseFrames = frozenset({"contrast-01"})
verbalDiscourseFrames = frozenset({"cause-01"})

temporalScaffolds = frozenset({"before", "after", "until"})

quantityEntities = frozenset({
    "temporal-quantity", "distance-quantity", "monetary-quantity",
    "mass-quantity", "seismic-quantity", "ordinal-entity", "date-entity",
    "date-interval", "rate-entity", "relative-position",
})

copulaFrames = frozenset({"be-located-at-91", "be-from-91",
                          "be-temporally-at-91"})
degreeFrames = frozenset({"have-degree-91"})
degreeWords = frozenset({"more", "less", "most", "least", "so", "too", "as",
                         "much", "very", "enough"})

geoConcepts = frozenset({
    "country", "city", "state", "continent", "world-region", "organization",
    "company", "region",
})

lightVerbs = frozenset({"make", "take", "give", "go", "have", "set", "throw",
                        "do", "get", "put"})

modalFrames = frozenset({
    "possible-01", "capable-01", "obligate-01", "permit-01", "recommend-01",
    "likely-01",
})

modalAdverbs = frozenset({"maybe", "perhaps", "possibly", "probably"})

# Suppletive pairs the string metrics cannot see: the person/people noun
# pair plus the closed pronoun paradigms (AMR uses the nominative, UD
# lemmatizes possessives/obliques to their own form).
suppletive = {
    "person": {"people"},
    "i": {"my", "me", "mine", "myself"},
    "we": {"our", "us", "ours", "ourselves"},
    "you": {"your", "yours", "yourself", "yourselves"},
    "he": {"his", "him", "himself"},
    "she": {"her", "hers", "herself"},
    "it": {"its", "itself"},
    "they": {"their", "them", "theirs", "themselves"},
}

roleFrames = frozenset({"have-org-role-91", "have-rel-role-91"})

fixedExpressions = frozenset({
    "at-least", "at-most", "more-than", "less-than", "no-more-than",
    "no-less-than", "on-time", "at-all", "at-last", "by-oneself",
})

transferDeprels = frozenset({"case", "det", "mark"})

markerUpos = frozenset({"ADP", "SCONJ", "CCONJ", "PART"})

fuzzyThreshold = 0.7


def stripConcept(concept: str) -> str:
    """'ponder-01' → 'ponder'; lowercased."""
    return re.sub(r"-\d+$", "", concept).lower()


def isPredicate(concept: str) -> bool:
    return bool(re.search(r"-\d+$", concept))


def similarity(a: str, b: str) -> float:
    a, b = a.lower(), b.lower()
    return 1.0 if a == b else SequenceMatcher(None, a, b).ratio()


def stemSimilarity(a: str, b: str) -> float:
    """Similarity robust to derivational suffixes: max of edit ratio and
    shared-prefix proportion (italy/italian 0.67 → 0.80)."""
    a, b = a.lower(), b.lower()
    prefix = 0
    for x, y in zip(a, b):
        if x != y:
            break
        prefix += 1
    shortest = min(len(a), len(b))
    return max(similarity(a, b), prefix / shortest if shortest else 0)