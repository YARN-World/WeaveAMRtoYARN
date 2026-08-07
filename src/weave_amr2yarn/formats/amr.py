"""Reading a Penman AMR corpus.

A corpus file is blank-line-separated Penman blocks, each optionally preceded
by ``# ::key value`` metadata lines::

    # ::id n01027007
    # ::snt Who are they?
    ( t / they :domain (a / amr-unknown))

Four copies of this loop exist across the original project, and two of them
disagree about which id spellings count. This reader accepts all three that
appear in the corpora on hand — ``::id``, ``::sent-id`` and ``::sent_id`` —
which is the union, so no corpus reads differently than it did before.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

# ``::id``, ``::sent-id`` and ``::sent_id`` all name the sentence.
_ID_PATTERN = re.compile(r"::(?:sent[-_])?id\s+(\S+)")


@dataclass(frozen=True)
class AmrSentence:
    """One Penman block, with the identity the corpus gave it.

    ``index`` is the zero-based position in the file, kept because a block
    without any id line is named after it (``snt1``, ``snt2``, …) and because
    it makes failures locatable in corpora that reuse ids.
    """

    id: str
    penman: str
    index: int

    def metadata(self) -> dict[str, str]:
        """The ``# ::key value`` lines, parsed.

        Cheap and dependency-free: used to find the surface sentence for the
        parser without paying for a full Penman decode.
        """
        found: dict[str, str] = {}
        for line in self.penman.splitlines():
            if not line.startswith("#"):
                break
            for key, value in re.findall(r"::(\S+)\s*([^:]*)", line):
                found[key] = value.strip()
        return found


class AmrCorpus:
    """A sequence of :class:`AmrSentence`, read from a file or a string."""

    def __init__(self, sentences: list[AmrSentence]) -> None:
        self._sentences = sentences

    @classmethod
    def fromText(cls, text: str) -> "AmrCorpus":
        sentences = []
        for index, block in enumerate(text.split("\n\n")):
            block = block.strip()
            if not block:
                continue
            match = _ID_PATTERN.search(block)
            identifier = match.group(1) if match else f"snt{index + 1}"
            sentences.append(AmrSentence(identifier, block, index))
        return cls(sentences)

    @classmethod
    def fromFile(cls, path: str | Path) -> "AmrCorpus":
        return cls.fromText(Path(path).read_text(encoding="utf-8"))

    def __iter__(self) -> Iterator[AmrSentence]:
        return iter(self._sentences)

    def __len__(self) -> int:
        return len(self._sentences)

    def __getitem__(self, index: int) -> AmrSentence:
        return self._sentences[index]

    def ids(self) -> list[str]:
        return [sentence.id for sentence in self._sentences]

    def duplicateIds(self) -> list[str]:
        """Ids used by more than one block.

        Worth checking before a batch run: output is written one file per id,
        so duplicates silently overwrite each other.
        """
        seen: dict[str, int] = {}
        for sentence in self._sentences:
            seen[sentence.id] = seen.get(sentence.id, 0) + 1
        return sorted(key for key, count in seen.items() if count > 1)