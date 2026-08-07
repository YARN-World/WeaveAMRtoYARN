"""Pluggable sources for the two inputs the AMR does not carry itself."""

from __future__ import annotations

from .anchors import (
    AnchorProvider,
    ChainedAnchorer,
    LevenshteinAnchorer,
    PrecomputedAnchorer,
)
from .parser import AmrlibParser, AmrParser, SpringParser, parseToCorpus, readSentences
from .ud import ChainedUd, ConlluUd, StanzaUd, UdProvider

__all__ = [
    "AmrParser",
    "AmrlibParser",
    "AnchorProvider",
    "ChainedAnchorer",
    "ChainedUd",
    "ConlluUd",
    "LevenshteinAnchorer",
    "PrecomputedAnchorer",
    "SpringParser",
    "StanzaUd",
    "UdProvider",
    "parseToCorpus",
    "readSentences",
]