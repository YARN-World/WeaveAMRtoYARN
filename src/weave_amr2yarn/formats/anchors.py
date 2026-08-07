"""The anchor dictionary format.

An anchor dictionary maps, per sentence, AMR variables to UD token ids::

    {"fracas-015.premise_0": {"p2": "7", "t": "4", "c2": "10"},
     "fracas-015.hypothesis_yes": {"t": "11"}}

Token ids are strings, matching the CoNLL-U ``ID`` column
"""

from __future__ import annotations

import json
from pathlib import Path


class AnchorDictionary:
    """The outer ``{sentence_id: {variable: token}}`` mapping."""

    def __init__(self, data: dict[str, dict[str, str]] | None = None) -> None:
        # Values are coerced to str: dictionaries written by hand or by a
        # producer that kept token ids as ints must not compare unequal to
        # otherwise identical ones.
        self.data = {
            sentenceId: {var: str(token) for var, token in anchors.items()}
            for sentenceId, anchors in (data or {}).items()
        }

    @classmethod
    def fromFile(cls, path: str | Path) -> "AnchorDictionary":
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    def toFile(self, path: str | Path) -> None:
        Path(path).write_text(
            json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def sentence(self, sentenceId: str) -> dict[str, str] | None:
        """The inner mapping for one sentence, or None if it has no entry.

        None and ``{}`` mean different things: no entry at all means the
        caller should fall back to computing anchors, whereas an empty entry
        means this sentence is deliberately unanchored.
        """
        return self.data.get(sentenceId)

    def sentenceIds(self) -> list[str]:
        return list(self.data)

    def anchorCount(self) -> int:
        return sum(len(anchors) for anchors in self.data.values())

    def triples(self) -> set[tuple[str, str, str]]:
        """Strict ``(sentence, variable, token)`` triples — the scoring unit."""
        return {
            (sentenceId, var, token)
            for sentenceId, anchors in self.data.items()
            for var, token in anchors.items()
        }

    def __len__(self) -> int:
        return len(self.data)

    def __contains__(self, sentenceId: object) -> bool:
        return sentenceId in self.data