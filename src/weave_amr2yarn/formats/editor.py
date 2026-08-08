"""Packaging YARN graphs for the yarn-editor.

The editor imports a sample as a ZIP holding one ``.json`` per record plus a
``metadata.txt`` naming the sample. Two details of its importer decide the
shape here, and neither is guessable from the outside:

* the sidecar is read as ``# key = value`` lines, keys lowercased, and only
  ``sampleid`` and ``samplename`` are used — despite the docstring in its
  importer describing JSON;
* a record is named by ``yarn.meta.sent_id``, falling back to the file path.
  Our graphs carry the sentence id as ``meta.id``, so it is copied across;
  otherwise every record would be named after its filename.
"""

from __future__ import annotations

import json
import re
import uuid
import zipfile
from pathlib import Path

from .. import manifest

#: Characters that are awkward in a filename inside a zip.
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")

#: The importer reads these; editedAt is written for fidelity with the
#: editor's own export, which includes it, and is ignored on the way back in.
METADATA_NAME = "metadata.txt"
RECORD_SUFFIX = ".yarn.json"


def safeName(sentenceId: str) -> str:
    return _UNSAFE.sub("_", sentenceId).strip("_") or "record"


def withEditorMetadata(yarn: dict, sentenceId: str) -> dict:
    """Return *yarn* with the metadata the editor requires.

    Its validator rejects anything without ``meta.sent_id`` and ``meta.text``,
    both strings; this project writes those as ``id`` and ``snt``. Rather than
    renaming, both spellings are kept, so the graph still reads back through
    this library's own tools and comparisons against earlier runs still hold.

    ``text`` falls back to the empty string: the field has to exist and be a
    string, and a graph converted without a surface sentence has none.
    """
    meta = dict(yarn.get("meta") or {})
    meta["sent_id"] = str(meta.get("sent_id") or meta.get("id") or sentenceId)
    meta["text"] = str(meta.get("text") or meta.get("snt") or "")
    meta.setdefault("id", sentenceId)
    return {**yarn, "meta": meta}


def metadataText(sampleName: str, sampleId: str, editedAt: str) -> str:
    return (
        f"# sampleName = {sampleName}\n"
        f"# sampleId = {sampleId}\n"
        f"# editedAt = {editedAt}\n"
    )


def writeEditorZip(
    graphs: dict[str, dict],
    path: str | Path,
    *,
    sampleName: str | None = None,
    sampleId: str | None = None,
    editedAt: str | None = None,
    asJsonl: bool = False,
) -> Path:
    """Write *graphs* as a sample the editor can import.

    ``{sentence_id: yarn}`` becomes one ``<id>.yarn.json`` per graph, or a
    single ``.jsonl`` when *asJsonl* is set — the importer accepts either, and
    one file is easier to move for a large corpus.

    Entries are written inside a folder named after the sample, matching what
    the editor's own export produces.
    """
    path = Path(path)
    sampleName = sampleName or path.stem or "sample"
    sampleId = sampleId or str(uuid.uuid4())
    editedAt = editedAt or manifest.timestamp()
    folder = safeName(sampleName)

    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        if asJsonl:
            lines = [
                json.dumps(withEditorMetadata(yarn, sentenceId), ensure_ascii=False)
                for sentenceId, yarn in graphs.items()
            ]
            archive.writestr(f"{folder}/{folder}.jsonl", "\n".join(lines) + "\n")
        else:
            for sentenceId, yarn in graphs.items():
                archive.writestr(
                    f"{folder}/{safeName(sentenceId)}{RECORD_SUFFIX}",
                    json.dumps(
                        withEditorMetadata(yarn, sentenceId),
                        indent=2,
                        ensure_ascii=False,
                    ),
                )
        archive.writestr(
            f"{folder}/{METADATA_NAME}",
            metadataText(sampleName, sampleId, editedAt),
        )
    return path


def readYarnDirectory(directory: str | Path) -> dict[str, dict]:
    """Load ``{sentence_id: yarn}`` from a directory of YARN JSON.

    The id comes from the graph's own metadata where it has one, so a grouped
    layout (``fracas-001/premise_0.json``) keeps its real ids rather than
    being named after files.
    """
    directory = Path(directory)
    graphs: dict[str, dict] = {}
    for file in sorted(directory.rglob("*.json")):
        if file.name == METADATA_NAME:
            continue
        yarn = json.loads(file.read_text(encoding="utf-8"))
        meta = yarn.get("meta") or {}
        identifier = (
            meta.get("sent_id")
            or meta.get("id")
            or str(file.relative_to(directory).with_suffix(""))
        )
        graphs[identifier] = yarn
    return graphs
