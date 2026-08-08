"""Turning what the page sends into the graphs it wants back.

Everything substantive lives in the library; this only decides which provider
each request asked for and assembles the pieces.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from weave_amr2yarn.errors import WeaveError
from weave_amr2yarn.formats.amr import AmrCorpus, AmrSentence
from weave_amr2yarn.formats.conllu import parseConlluText
from weave_amr2yarn.graph import (
    applyAnchoring,
    dereify,
    normalizeGraph,
    penmanToGrew,
    splitEvents,
)
from weave_amr2yarn.providers.anchors import LevenshteinAnchorer
from weave_amr2yarn.providers.ud import StanzaUd

_SENTENCE = re.compile(r"::snt\s+(.+)")


class InputError(WeaveError):
    """The request itself was wrong — reported to the user, not logged."""


@dataclass
class Anchored:
    """Everything the page needs about one sentence before rewriting."""

    sentence: AmrSentence
    text: str
    penman: str
    amrGraph: dict
    udGraph: dict
    anchors: dict[str, str]
    graph: dict = field(default_factory=dict)


def _asSentence(amrText: str) -> AmrSentence:
    corpus = AmrCorpus.fromText(amrText)
    if not len(corpus):
        raise InputError("AMR input is empty.")
    return corpus[0]


def buildAnchored(
    amrText: str,
    *,
    udSource: str = "stanza",
    conlluText: str = "",
    anchorSource: str = "levenshtein",
    anchorJson: str = "",
    penmanDereify: bool = True,
    leamrDir: str | None = None,
) -> Anchored:
    """Parse the AMR, get a UD analysis and anchors, and merge them."""
    amrText = amrText.strip()
    if not amrText:
        raise InputError("AMR input is empty.")

    sentence = _asSentence(amrText)
    found = _SENTENCE.search(amrText)
    text = found.group(1).strip() if found else ""

    body = "\n".join(
        line for line in amrText.splitlines() if not line.startswith("#")
    ).strip()

    source = dereify(amrText) if penmanDereify else amrText
    amrGraph = normalizeGraph(penmanToGrew(source, sentenceId=sentence.id))

    udGraph = _resolveUd(sentence, text, udSource, conlluText)

    # LEAMR needs the UD as CoNLL-U. When Stanza produced the parse, ask Stanza
    # for it rather than rebuilding it from the graph.
    if anchorSource == "leamr" and udSource != "manual":
        conlluText = StanzaUd().parseToConllu(text, sentence.id)

    anchors = _resolveAnchors(
        sentence, amrGraph, udGraph, anchorSource, anchorJson, leamrDir, conlluText
    )

    graph = splitEvents(applyAnchoring(amrGraph, udGraph, anchors))
    return Anchored(sentence, text, body, amrGraph, udGraph, anchors, graph)


def _resolveUd(
    sentence: AmrSentence, text: str, source: str, conlluText: str
) -> dict:
    if source == "manual":
        if not conlluText.strip():
            raise InputError("Manual CoNLL-U is empty.")
        graphs = parseConlluText(conlluText)
        if not graphs:
            # The paste box rarely carries a sent_id, so accept a bare table.
            graphs = parseConlluText(f"# sent_id = pasted\n{conlluText}")
        if not graphs:
            raise InputError("No sentences found in the CoNLL-U.")
        return next(iter(graphs.values()))

    if not text:
        raise InputError("No ::snt found — needed for parsing.")
    return StanzaUd().parse(text)


def _resolveAnchors(
    sentence: AmrSentence,
    amrGraph: dict,
    udGraph: dict,
    source: str,
    anchorJson: str,
    leamrDir: str | None,
    conlluText: str = "",
) -> dict[str, str]:
    if source == "manual":
        if not anchorJson.strip():
            raise InputError("Manual anchor dictionary is empty.")
        try:
            loaded = json.loads(anchorJson)
        except json.JSONDecodeError as exc:
            raise InputError(f"Invalid anchor JSON: {exc}") from exc
        if not isinstance(loaded, dict):
            raise InputError("Anchors must be an object of variable to token id.")
        return {str(k): str(v) for k, v in loaded.items()}

    if source == "leamr":
        return _leamrAnchors(sentence, conlluText, leamrDir)

    return LevenshteinAnchorer().anchorsFor(sentence, amrGraph, udGraph)


def _leamrAnchors(
    sentence: AmrSentence, conlluText: str, leamrDir: str | None
) -> dict[str, str]:
    """Align one sentence with LEAMR.

    LEAMR reads an AMR file and a CoNLL-U file, so both are written to a
    scratch directory — but both are written as *text we already have*, never
    rebuilt from a graph. Reconstructing CoNLL-U would mean guessing at
    multiword ranges and tokenisation, and anchors are keyed by token id, so a
    wrong guess would move anchors silently.
    """
    import tempfile
    from pathlib import Path

    from weave_amr2yarn.providers.align2anchor import Align2AnchorAnchorer

    if not conlluText.strip():
        raise InputError(
            "LEAMR aligns against a UD parse. Paste CoNLL-U, or switch UD to "
            "Stanza so one can be produced."
        )

    with tempfile.TemporaryDirectory(prefix="weave-leamr-") as scratch:
        directory = Path(scratch)
        amrFile = directory / "input.amr.txt"
        udFile = directory / "input.conllu"
        # The id has to be the same on both sides for LEAMR to pair them.
        amrFile.write_text(
            f"# ::id {sentence.id}\n{sentence.penman.lstrip()}\n"
            if "::id" not in sentence.penman
            else sentence.penman + "\n",
            encoding="utf-8",
        )
        udFile.write_text(conlluText.rstrip() + "\n", encoding="utf-8")

        anchorer = Align2AnchorAnchorer(amrFile, udFile, leamrDir=leamrDir)
        anchors = anchorer.build().sentence(sentence.id)

    if anchors is None:
        raise InputError(
            f"LEAMR produced no alignment for {sentence.id}. The AMR id and "
            "the CoNLL-U sent_id must match."
        )
    return anchors


def anchorTable(anchored: Anchored) -> dict:
    """The anchor editor's view: tokens, and what each variable points at."""
    tokens = {
        tokenId: node
        for tokenId, node in anchored.udGraph["nodes"].items()
        if tokenId != "0"
    }
    variables = {}
    for var, node in anchored.amrGraph.get("nodes", {}).items():
        concept = node.get("concept") or node.get("pred")
        if not concept:
            continue
        tokenId = anchored.anchors.get(var)
        token = tokens.get(str(tokenId)) if tokenId else None
        variables[var] = {
            "concept": concept,
            "anchor": str(tokenId) if tokenId else None,
            "anchor_form": token["form"] if token else None,
        }
    return {"sentence": anchored.text, "ud_tokens": tokens, "vars": variables}
