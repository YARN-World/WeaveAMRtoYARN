"""Where the AMR comes from, when it is not supplied.

Two backends, chosen by where the model should run.

:class:`AmrlibParser` runs a model in this process through amrlib. It is the
lightweight route: no service to start, and the smallest model is around
500 MB. Note that amrlib needs ``transformers<5``.

:class:`SpringParser` talks to a SPRING service over HTTP. SPRING's own
dependencies pin an old ``tokenizers`` that will not build on current
platforms, which is why upstream ships a Docker image; keeping it out of
process also means it imposes no version constraints here. The protocol is a
single POST, so this is written against the standard library rather than
pulling in the ``zensols.amrspring`` client.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Iterable, Protocol, runtime_checkable

from ..errors import MissingDependency, WeaveError
from ..formats.amr import AmrCorpus, AmrSentence

DEFAULT_ENDPOINT = "http://localhost:8080/parse"

#: Sentences per request. The service batches internally; this keeps a large
#: corpus from becoming one enormous request.
DEFAULT_BATCH = 32

#: Where a downloaded amrlib model is looked for when none is given.
MODEL_VARIABLE = "WEAVE_AMR_MODEL"


class AmrParseError(WeaveError):
    """The parser could not be reached, loaded, or would not answer."""


@runtime_checkable
class AmrParser(Protocol):
    """Turns sentences into Penman AMR strings, in order."""

    def parse(self, sentences: list[str]) -> list[str]: ...


class AmrlibParser:
    """AMR parsing with an amrlib model, in this process.

    Models are not bundled — the smallest is around 500 MB. Download one from
    the amrlib-models releases, unpack it, and point at the directory::

        AmrlibParser("/path/to/model_parse_xfm_bart_base-v0_1_0")

    ``parse_xfm`` models load through the standard transformers interfaces.
    ``parse_spring`` is also an amrlib model, but its architecture is amrlib's
    own port; a checkpoint from the original SPRING codebase will not load into
    it, as that one carries decoder pointer-attention weights amrlib's model
    has no slots for. Use :class:`SpringParser` for such a checkpoint.
    """

    def __init__(
        self,
        modelDir: str | Path | None = None,
        *,
        device: str | None = None,
        batchSize: int = 8,
        beams: int = 4,
    ) -> None:
        self.modelDir = self._resolveModelDir(modelDir)
        self.device = device
        self.batchSize = batchSize
        self.beams = beams
        self._inference = None

    @staticmethod
    def _resolveModelDir(explicit: str | Path | None) -> Path:
        import os

        candidates = []
        if explicit:
            candidates.append(Path(explicit))
        if os.environ.get(MODEL_VARIABLE):
            candidates.append(Path(os.environ[MODEL_VARIABLE]))

        for candidate in candidates:
            if candidate.is_dir():
                return candidate

        raise MissingDependency(
            "no AMR model directory given. amrlib models are large, so none is "
            f"bundled: pass --amr-model, or set {MODEL_VARIABLE}. Models are at "
            "https://github.com/bjascob/amrlib-models"
        )

    def _load(self):
        """Build the inference object once, on first use."""
        if self._inference is not None:
            return self._inference
        try:
            from amrlib.models.parse_xfm.inference import Inference
        except ImportError as exc:
            raise MissingDependency(
                "amrlib is required for in-process parsing:\n"
                "  pip install 'weave-amr2yarn[parse]'\n"
                "It needs transformers<5; see INSTALL.md."
            ) from exc
        except Exception as exc:
            raise AmrParseError(
                f"amrlib could not be loaded: {exc}. This is usually a "
                "transformers version mismatch — amrlib needs transformers<5."
            ) from exc

        options = {"batch_size": self.batchSize, "num_beams": self.beams}
        if self.device:
            options["device"] = self.device
        try:
            self._inference = Inference(model_dir=str(self.modelDir), **options)
        except Exception as exc:
            raise AmrParseError(
                f"could not load the AMR model at {self.modelDir}: {exc}"
            ) from exc
        return self._inference

    def parse(self, sentences: list[str]) -> list[str]:
        sentences = list(sentences)
        if not sentences:
            return []
        graphs = self._load().parse_sents(sentences, add_metadata=False)
        if len(graphs) != len(sentences):
            raise AmrParseError(
                f"asked for {len(sentences)} graphs, got {len(graphs)}"
            )
        # A sentence the model cannot linearise comes back as None.
        failed = [position for position, graph in enumerate(graphs) if not graph]
        if failed:
            raise AmrParseError(
                f"the model returned no graph for sentence(s) {failed[:5]}"
            )
        return list(graphs)

    def available(self) -> bool:
        """Whether the model can be loaded. Used by ``weave doctor``."""
        try:
            self._load()
            return True
        except WeaveError:
            return False


class SpringParser:
    """AMR parsing by the SPRING service.

    Start one with the upstream image::

        docker run -d -p 8080:8080 \\
            -v "$PWD/docker/models:/opt/models" \\
            -v "$PWD/docker/data:/opt/data" plandes/springserv

    It needs enough memory for a 4.6 GB checkpoint; a Docker VM sized below
    about 12 GB gets the container OOM-killed while the model loads.
    """

    def __init__(
        self,
        endpoint: str = DEFAULT_ENDPOINT,
        *,
        batchSize: int = DEFAULT_BATCH,
        timeoutSeconds: int = 300,
    ) -> None:
        self.endpoint = endpoint
        self.batchSize = batchSize
        self.timeoutSeconds = timeoutSeconds

    def _post(self, sentences: list[str]) -> dict:
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps({"sents": sentences}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeoutSeconds) as reply:
                return json.loads(reply.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise AmrParseError(
                f"could not reach the SPRING service at {self.endpoint}: "
                f"{getattr(exc, 'reason', exc)}. Is the container running?"
            ) from exc
        except json.JSONDecodeError as exc:
            raise AmrParseError(
                f"the SPRING service at {self.endpoint} did not return JSON: {exc}"
            ) from exc

    @staticmethod
    def _graphsFrom(payload: dict, expected: int) -> list[str]:
        """Pull the graphs out, in the order the sentences went in.

        The service replies ``{"amrs": {"0": {"graph": ...}, ...}}``, keyed by
        the sentence's position as a string. Sorting those keys as text would
        put 10 before 2, so they are ordered numerically.
        """
        amrs = payload.get("amrs")
        if not isinstance(amrs, dict):
            raise AmrParseError(
                f"unexpected reply from the SPRING service: {str(payload)[:200]}"
            )

        graphs = []
        for position in range(expected):
            entry = amrs.get(str(position))
            if entry is None:
                raise AmrParseError(
                    f"the SPRING service returned no graph for sentence {position}"
                )
            if isinstance(entry, dict) and "error" in entry:
                raise AmrParseError(
                    f"the SPRING service failed on sentence {position}: {entry['error']}"
                )
            graph = entry.get("graph") if isinstance(entry, dict) else entry
            if not isinstance(graph, str):
                raise AmrParseError(
                    f"no graph in the reply for sentence {position}: {str(entry)[:200]}"
                )
            graphs.append(graph)
        return graphs

    def parse(self, sentences: list[str]) -> list[str]:
        sentences = list(sentences)
        graphs: list[str] = []
        for start in range(0, len(sentences), self.batchSize):
            batch = sentences[start : start + self.batchSize]
            graphs.extend(self._graphsFrom(self._post(batch), len(batch)))
        return graphs

    def available(self) -> bool:
        """Whether the service answers. Used by ``weave doctor``."""
        try:
            self._post(["test"])
            return True
        except AmrParseError:
            return False


def readSentences(path) -> list[str]:
    """Read a plain-text corpus: one sentence per line, blanks ignored."""
    from pathlib import Path

    return [
        line.strip()
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def parseToCorpus(
    parser: AmrParser,
    sentences: Iterable[str],
    *,
    idPrefix: str = "snt",
    sentenceKey: str = "snt",
) -> AmrCorpus:
    """Parse sentences and wrap the result as a corpus.

    Each block carries the sentence as metadata, so everything downstream —
    the UD parser especially — can find its text the usual way.
    """
    sentences = list(sentences)
    graphs = parser.parse(sentences)
    if len(graphs) != len(sentences):
        raise AmrParseError(
            f"asked for {len(sentences)} graphs, got {len(graphs)}"
        )

    blocks = []
    for position, (text, graph) in enumerate(zip(sentences, graphs), 1):
        identifier = f"{idPrefix}{position}"
        body = "\n".join(
            line for line in graph.splitlines() if not line.startswith("#")
        )
        blocks.append(
            AmrSentence(
                id=identifier,
                penman=f"# ::id {identifier}\n# ::{sentenceKey} {text}\n{body}",
                index=position - 1,
            )
        )
    return AmrCorpus(blocks)