"""Where the UD analysis comes from."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from ..errors import MissingDependency
from ..formats.amr import AmrSentence
from ..formats.conllu import readConllu


@runtime_checkable
class UdProvider(Protocol):
    """Supplies a UD graph for a sentence, or None if it has none."""

    def graphFor(self, sentence: AmrSentence) -> dict | None: ...


class ConlluUd:
    """UD read from a CoNLL-U file, matched by sentence id."""

    def __init__(self, graphs: dict[str, dict], *, source: str | None = None) -> None:
        self._graphs = graphs
        self.source = source

    @classmethod
    def fromFile(cls, path: str | Path) -> "ConlluUd":
        return cls(readConllu(path), source=str(path))

    def graphFor(self, sentence: AmrSentence) -> dict | None:
        return self._graphs.get(sentence.id)

    def __contains__(self, sentenceId: object) -> bool:
        return sentenceId in self._graphs

    def __len__(self) -> int:
        return len(self._graphs)


class StanzaUd:
    """UD parsed from the surface sentence with Stanza.

    The pipeline is built on first use, not on import. The original built one
    at module import, which cost seconds and failed outright on a machine
    without models even for callers who supplied CoNLL-U and never parsed.
    """

    def __init__(
        self,
        *,
        language: str = "en",
        sentenceKey: str = "snt",
        processors: str = "tokenize,mwt,pos,lemma,depparse",
        downloadMethod=None,
    ) -> None:
        self.language = language
        self.sentenceKey = sentenceKey
        self.processors = processors
        self._downloadMethod = downloadMethod
        self._pipeline = None

    def _ensurePipeline(self):
        if self._pipeline is None:
            try:
                import stanza
            except ImportError as exc:
                raise MissingDependency(
                    "stanza is required to parse UD from raw text. Either supply "
                    "a CoNLL-U file, or install it with:\n"
                    "  pip install 'weave-amr2yarn[stanza]'"
                ) from exc
            try:
                self._pipeline = stanza.Pipeline(
                    lang=self.language,
                    processors=self.processors,
                    download_method=self._downloadMethod,
                )
            except Exception as exc:
                raise MissingDependency(
                    f"could not build the Stanza pipeline for {self.language!r}: "
                    f"{exc}\nModels are downloaded separately:\n"
                    f"  python -c \"import stanza; stanza.download('{self.language}')\""
                ) from exc
        return self._pipeline

    def graphFor(self, sentence: AmrSentence) -> dict | None:
        text = sentence.metadata().get(self.sentenceKey)
        if not text:
            return None
        return self.parse(text)

    def parseToConllu(self, text: str, sentenceId: str) -> str:
        """Parse *text* and return it as CoNLL-U.

        Stanza writes this itself rather than us rebuilding it from the graph.
        Its own output keeps what the graph does not carry — multiword ranges,
        XPOS, the untouched ``# text`` line — and a serialiser of ours would
        have to guess at all three. Since aligners index tokens by id, a wrong
        guess corrupts anchors silently instead of failing.
        """
        import io

        from stanza.utils.conll import CoNLL

        buffer = io.StringIO()
        CoNLL.write_doc2conll(self._ensurePipeline()(text), buffer)

        # Stanza numbers sentences from zero; the id has to match the AMR's.
        lines = [
            f"# sent_id = {sentenceId}"
            if line.startswith("# sent_id")
            else line
            for line in buffer.getvalue().splitlines()
        ]
        return "\n".join(lines) + "\n"

    def parse(self, text: str) -> dict:
        """Parse *text* into a GREW-shaped UD graph."""
        document = self._ensurePipeline()(text)

        nodes: dict[str, dict] = {"0": {"id": "0", "form": "_0_"}}
        edges: list[dict[str, str]] = []
        for parsed in document.sentences:
            for word in parsed.words:
                features = (
                    {
                        key: value
                        for item in word.feats.split("|")
                        if "=" in item
                        for key, value in [item.split("=", 1)]
                    }
                    if word.feats and word.feats != "_"
                    else {}
                )
                nodes[str(word.id)] = {
                    "id": str(word.id),
                    "form": word.text,
                    "lemma": word.lemma,
                    "upos": word.pos,
                    **features,
                }
                edges.append(
                    {"src": str(word.head), "label": word.deprel, "tar": str(word.id)}
                )

        return {"nodes": nodes, "edges": edges}


class ChainedUd:
    """Try each provider in turn, taking the first that answers.

    Useful for the common mixed case: gold CoNLL-U where it exists, a parse
    everywhere else.
    """

    def __init__(self, *providers: UdProvider) -> None:
        self.providers = providers

    def graphFor(self, sentence: AmrSentence) -> dict | None:
        for provider in self.providers:
            graph = provider.graphFor(sentence)
            if graph is not None:
                return graph
        return None