"""Adapter layer: every alignment source becomes the same dictionary.

An adapter owns everything format-shaped about its source — parsing,
span-to-token resolution, index remapping — and emits an
AnchorDictionary containing only genuine graph variables with scalar
UD token ids. Downstream stages never learn which aligner ran.

The registry maps source names to adapter classes so the CLI can say
`--source leamr` and nothing more.
"""

from __future__ import annotations

from pathlib import Path

from ..format import AnchorDictionary


class AdapterError(Exception):
    pass


class Adapter:
    """Base contract: produce(raw source path) -> AnchorDictionary."""

    name = "base"

    def produce(self, sourcePath: str | Path) -> AnchorDictionary:
        raise NotImplementedError

    def validate(self, dictionary: AnchorDictionary) -> AnchorDictionary:
        """Enforce the adapter contract before anything ships downstream."""
        for sentenceId in dictionary.sentenceIds():
            for variable, value in dictionary.sentence(sentenceId).items():
                if isinstance(value, list):
                    raise AdapterError(
                        f"{self.name}: span value leaked for {variable} "
                        f"in {sentenceId} — spans must be resolved here")
        return dictionary


class PrecomputedAdapter(Adapter):
    """A source that is already an anchor dictionary on disk.

    Covers every aligner whose runner script exists today; the runners
    migrate behind this interface one at a time (README plan, step 4).
    """

    name = "precomputed"

    def produce(self, sourcePath: str | Path) -> AnchorDictionary:
        return self.validate(AnchorDictionary.fromFile(sourcePath))


registry: dict[str, type[Adapter]] = {
    PrecomputedAdapter.name: PrecomputedAdapter,
}


def adapterFor(name: str) -> Adapter:
    if name not in registry:
        raise AdapterError(f"unknown source '{name}' — "
                           f"known: {', '.join(sorted(registry))}")
    return registry[name]()