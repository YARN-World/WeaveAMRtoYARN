"""The AMR parsers.

The amrlib model is a large download and SPRING is a service, so neither is
exercised here. What is: the wire protocol, the error paths, and how a parsed
result becomes a corpus.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from weave_amr2yarn.errors import MissingDependency
from weave_amr2yarn.providers.parser import (
    MODEL_VARIABLE,
    AmrlibParser,
    AmrParseError,
    SpringParser,
    parseToCorpus,
    readSentences,
)


def _stub(payloadFor, record=None):
    """A server speaking the SPRING protocol: sents in, amrs out."""

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            request = json.loads(self.rfile.read(length).decode("utf-8"))
            if record is not None:
                record.append(request)
            body = json.dumps(payloadFor(request)).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_port}/parse"


@pytest.fixture
def springStub():
    servers = []

    def start(payloadFor, record=None):
        server, endpoint = _stub(payloadFor, record)
        servers.append(server)
        return endpoint

    yield start
    for server in servers:
        server.shutdown()


def _graphs(request):
    """One valid Penman graph per sentence, tagged with its position."""
    return {
        "amrs": {
            str(position): {"graph": f"(x{position} / thing)"}
            for position in range(len(request["sents"]))
        }
    }


def test_parsesInOrder(springStub):
    graphs = SpringParser(springStub(_graphs)).parse(["alpha", "beta"])
    assert graphs == ["(x0 / thing)", "(x1 / thing)"]


def test_repliesAreOrderedNumericallyNotAsText(springStub):
    """Keys are positions as strings, so "10" must not sort before "2"."""
    graphs = SpringParser(springStub(_graphs)).parse([f"w{i}" for i in range(12)])
    assert graphs[10] == "(x10 / thing)"


def test_sentencesAreSentInBatches(springStub):
    seen = []
    parser = SpringParser(springStub(_graphs, record=seen), batchSize=2)
    parser.parse(["a", "b", "c", "d", "e"])
    assert [len(request["sents"]) for request in seen] == [2, 2, 1]


def test_unreachableServiceSaysSo():
    # Port 1 is privileged; nothing listens there.
    with pytest.raises(AmrParseError, match="could not reach"):
        SpringParser("http://127.0.0.1:1/parse", timeoutSeconds=2).parse(["hello"])


def test_availableIsFalseWhenNothingIsListening():
    assert SpringParser("http://127.0.0.1:1/parse", timeoutSeconds=2).available() is False


def test_availableIsTrueAgainstTheStub(springStub):
    assert SpringParser(springStub(_graphs)).available() is True


def test_missingGraphIsReported(springStub):
    with pytest.raises(AmrParseError, match="no graph for sentence 0"):
        SpringParser(springStub(lambda request: {"amrs": {}})).parse(["hello"])


def test_perSentenceErrorIsSurfaced(springStub):
    endpoint = springStub(lambda request: {"amrs": {"0": {"error": "too long"}}})
    with pytest.raises(AmrParseError, match="too long"):
        SpringParser(endpoint).parse(["hello"])


def test_unexpectedShapeIsReported(springStub):
    endpoint = springStub(lambda request: {"unexpected": True})
    with pytest.raises(AmrParseError, match="unexpected reply"):
        SpringParser(endpoint).parse(["hello"])


def test_parsedCorpusCarriesIdsAndTheSentence(springStub):
    corpus = parseToCorpus(
        SpringParser(springStub(_graphs)), ["A dog runs.", "It rains."]
    )
    assert corpus.ids() == ["snt1", "snt2"]
    assert corpus[0].metadata()["snt"] == "A dog runs."


def test_theParsersOwnCommentsAreReplacedNotAppended(springStub):
    """The model may return its own ::snt; ours is the one that counts."""
    endpoint = springStub(
        lambda request: {"amrs": {"0": {"graph": "# ::snt whatever\n(x / thing)"}}}
    )
    corpus = parseToCorpus(SpringParser(endpoint), ["A dog runs."])
    assert corpus[0].penman.count("::snt") == 1
    assert corpus[0].metadata()["snt"] == "A dog runs."


def test_parsedCorpusIsUsableDownstream(springStub):
    """The point of the exercise: it must convert like any other corpus."""
    from weave_amr2yarn.graph import penmanToGrew

    corpus = parseToCorpus(SpringParser(springStub(_graphs)), ["A dog runs."])
    assert penmanToGrew(corpus[0].penman)["meta"]["snt"] == "A dog runs."


def test_emptyInputNeedsNoParser():
    """No sentences means no model load, so this must not raise."""
    assert AmrlibParser.parse(object.__new__(AmrlibParser), []) == []


def test_missingModelDirectoryNamesTheVariable(monkeypatch):
    monkeypatch.delenv(MODEL_VARIABLE, raising=False)
    with pytest.raises(MissingDependency, match=MODEL_VARIABLE):
        AmrlibParser()


def test_modelDirectoryComesFromTheEnvironment(tmp_path, monkeypatch):
    monkeypatch.setenv(MODEL_VARIABLE, str(tmp_path))
    assert AmrlibParser().modelDir == tmp_path


def test_explicitModelDirectoryWins(tmp_path, monkeypatch):
    other = tmp_path / "other"
    other.mkdir()
    monkeypatch.setenv(MODEL_VARIABLE, str(tmp_path))
    assert AmrlibParser(other).modelDir == other


def test_readSentencesSkipsBlankLines(tmp_path):
    path = tmp_path / "text.txt"
    path.write_text("first\n\n  \nsecond\n", encoding="utf-8")
    assert readSentences(path) == ["first", "second"]