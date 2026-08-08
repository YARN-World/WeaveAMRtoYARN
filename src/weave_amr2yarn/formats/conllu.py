"""Reading UD annotations from CoNLL-U into GREW-shaped graphs.

The result is the same ``{"nodes": ..., "edges": ...}`` dict the Stanza parser
produces, so the two are interchangeable downstream::

    {"nodes": {"0": {"id": "0", "form": "_0_"},
               "1": {"id": "1", "form": "Who", "lemma": "who",
                     "upos": "PRON", "PronType": "Int"}},
     "edges": [{"src": "0", "label": "root", "tar": "2"}]}

Node ``"0"`` is a sentinel standing for the CoNLL-U root, so that ``HEAD = 0``
has something to point at.

Nine hand-written CoNLL-U readers exist across the original project with subtly
different tolerances. This is the canonical one (ported from ``load_conllu``),
with two liberalisations that can only ever accept more input: the ``# sent_id``
line no longer has to be spelled with exactly one space either side of ``=``,
and short rows are skipped rather than raising ``IndexError``.
"""

from __future__ import annotations

from pathlib import Path

# CoNLL-U column positions we read. ID and HEAD are strings throughout: GREW
# node identifiers are strings, and round-tripping through int would drop the
# distinction between "1" and the "1-2"/"1.1" rows we skip.
_ID, _FORM, _LEMMA, _UPOS, _FEATS, _HEAD, _DEPREL = 0, 1, 2, 3, 5, 6, 7
_MINIMUM_COLUMNS = 8


def _rootNode() -> dict[str, dict[str, str]]:
    return {"0": {"id": "0", "form": "_0_"}}


def _parseFeats(field: str) -> dict[str, str]:
    """``Number=Sing|PronType=Int`` becomes a flat dict of node features."""
    if field == "_":
        return {}
    return {
        key: value
        for item in field.split("|")
        if "=" in item
        for key, value in [item.split("=", 1)]
    }


def readConllu(path: str | Path) -> dict[str, dict]:
    """Return ``{sent_id: ud_graph}`` for every sentence in *path*."""
    with open(path, encoding="utf-8") as handle:
        return parseConllu(handle)


def parseConlluText(text: str) -> dict[str, dict]:
    """The same, for CoNLL-U already in memory — a paste box, say."""
    return parseConllu(text.splitlines())


def parseConllu(lines) -> dict[str, dict]:
    """Return ``{sent_id: ud_graph}`` for any iterable of CoNLL-U lines."""
    graphs: dict[str, dict] = {}
    sentenceId: str | None = None
    nodes = _rootNode()
    edges: list[dict[str, str]] = []

    def flush() -> None:
        nonlocal sentenceId
        # More than the sentinel means we actually saw tokens.
        if sentenceId is not None and len(nodes) > 1:
            graphs[sentenceId] = {"nodes": nodes, "edges": edges}
        sentenceId = None

    for line in lines:
        line = line.rstrip("\n")

        if line.startswith("#"):
            comment = line[1:].strip()
            if comment.startswith("sent_id"):
                _, _, value = comment.partition("=")
                sentenceId = value.strip()
                nodes, edges = _rootNode(), []
            continue

        if not line:
            flush()
            continue

        if sentenceId is None:
            continue  # tokens before any sent_id: nothing to key them by

        fields = line.split("\t")
        # Multiword-token ranges ("1-2") and empty nodes ("1.1") are not
        # graph nodes; their ID does not read as a plain integer.
        if not fields[_ID].isdigit() or len(fields) < _MINIMUM_COLUMNS:
            continue

        tokenId = fields[_ID]
        nodes[tokenId] = {
            "id": tokenId,
            "form": fields[_FORM],
            "lemma": fields[_LEMMA],
            "upos": fields[_UPOS],
            **_parseFeats(fields[_FEATS]),
        }
        edges.append(
            {"src": fields[_HEAD], "label": fields[_DEPREL], "tar": tokenId}
            )

    flush()  # a file that does not end in a blank line still has a sentence
    return graphs