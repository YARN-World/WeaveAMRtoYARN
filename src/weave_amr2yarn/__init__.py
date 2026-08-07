"""WeaveAMRtoYARN — Abstract Meaning Representation to YARN conversion.

Importing this package is cheap: no rule set is loaded and no parser model is
built until a :class:`Converter` is constructed and called.

    from weave_amr2yarn import Converter, ConlluUd, PrecomputedAnchorer

    converter = Converter(
        ud=ConlluUd.fromFile("corpus.conllu"),
        anchors=PrecomputedAnchorer.fromFile("anchors.json"),
    )
    yarn = converter.convert(amrPenmanString)
"""

from __future__ import annotations

from .config import ConversionConfig
from .errors import (
    AmrParseError,
    ConversionTimeout,
    GrewBackendError,
    GrsError,
    MissingDependency,
    WeaveError,
)
from .formats import AmrCorpus, AmrSentence, AnchorDictionary, readConllu
from .providers import (
    ChainedAnchorer,
    ChainedUd,
    ConlluUd,
    LevenshteinAnchorer,
    PrecomputedAnchorer,
    StanzaUd,
)
from .resources import bundledGrs
from .transform import BatchConverter, BatchReport, Converter, GrsSession

__version__ = "0.1.0"

__all__ = [
    "AmrCorpus",
    "AmrParseError",
    "AmrSentence",
    "AnchorDictionary",
    "BatchConverter",
    "BatchReport",
    "ChainedAnchorer",
    "ChainedUd",
    "ConlluUd",
    "ConversionConfig",
    "ConversionTimeout",
    "Converter",
    "GrewBackendError",
    "GrsError",
    "GrsSession",
    "LevenshteinAnchorer",
    "MissingDependency",
    "PrecomputedAnchorer",
    "StanzaUd",
    "WeaveError",
    "bundledGrs",
    "readConllu",
    "__version__",
]