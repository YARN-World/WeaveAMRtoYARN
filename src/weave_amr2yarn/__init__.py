"""WeaveAMRtoYARN — Abstract Meaning Representation to YARN conversion.

Importing this package is cheap: no rule set is loaded and no parser model is
built until you actually construct a :class:`Converter` and call it.
"""

from __future__ import annotations

from .errors import (
    AmrParseError,
    ConversionTimeout,
    GrewBackendError,
    GrsError,
    MissingDependency,
    WeaveError,
)

__version__ = "0.1.0"

__all__ = [
    "AmrParseError",
    "ConversionTimeout",
    "GrewBackendError",
    "GrsError",
    "MissingDependency",
    "WeaveError",
    "__version__",
]