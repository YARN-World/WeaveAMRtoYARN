"""Graph transformations."""

from __future__ import annotations

from .anchoring import applyAnchoring
from .build import penmanToGrew
from .canonical import addVariables, canonicalize, canonicalizeIds, renameSNodes
from .dereify import dereify
from .events import predicativeVerbs, splitEvents
from .normalize import combineNameLiterals, normalizeGraph, removeWiki

__all__ = [
    "addVariables",
    "applyAnchoring",
    "canonicalize",
    "canonicalizeIds",
    "combineNameLiterals",
    "dereify",
    "normalizeGraph",
    "penmanToGrew",
    "predicativeVerbs",
    "removeWiki",
    "renameSNodes",
    "splitEvents",
]