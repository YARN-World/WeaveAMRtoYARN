"""The exception hierarchy.

Every failure this library raises derives from :class:`WeaveError`, so a batch
driver can catch that one class and still tell the cases apart. The alternative
the original pipeline used — ``except (TimeoutError, Exception)`` plus sniffing
``"socket" in str(exc).lower()`` to guess whether the GREW backend had died —
could not distinguish a malformed input graph from a crashed subprocess, and so
recovered from neither reliably.
"""

from __future__ import annotations


class WeaveError(Exception):
    """Base class for every error raised by this library."""


class AmrParseError(WeaveError):
    """An AMR block could not be read as Penman.

    Carries the sentence id when one is known, because in a batch run the block
    itself is rarely enough to locate the offending record.
    """

    def __init__(self, message: str, *, sentenceId: str | None = None) -> None:
        super().__init__(f"[{sentenceId}] {message}" if sentenceId else message)
        self.sentenceId = sentenceId


class GrsError(WeaveError):
    """The rule set could not be loaded, or the requested strategy is unknown."""


class GrewBackendError(WeaveError):
    """The GREW OCaml backend failed, or its socket went away mid-run."""


class ConversionTimeout(WeaveError):
    """A single graph exceeded the per-graph time budget."""


class MissingDependency(WeaveError):
    """An optional dependency is needed for what was asked for.

    Raised with the install command rather than a bare ImportError, since the
    two optional pieces here (stanza, and the GREW backend itself) are both
    installed in ways ``pip install`` alone does not cover.
    """